"""The radial wheel. It opens under the cursor and takes the file drop.

Two ways in:
- drag mode: opened during an Explorer drag. The files are not known until
  the drag enters the wheel, which happens on the first mouse move.
- click mode: opened with known files (Send to, the drop window). Click a
  segment, click the hub to switch wheels, click outside or Esc to close.

It is drawn as frosted glass: what is on screen behind it shows through,
blurred (see glass.py).
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QFontMetrics, QGuiApplication,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QApplication, QWidget

from spinvert import glass
from spinvert.catalog import choices_for
from spinvert.theme import ACCENT, ON_BRIGHT, ON_DARK, annulus, pill_segment, thin_pen
from spinvert.watcher import VK, _down

SIZE = 380
R_OUT = 168
R_IN = 70
HUB = 60
GAP = 6          # px between segments
ROUND = 7        # px corner rounding of segments
TITLES = {"convert": "Convert", "tools": "Tools"}
KEY_NAMES = {"shift": "Shift", "ctrl": "Ctrl", "alt": "Alt"}
CENTER = Qt.AlignmentFlag.AlignCenter


class Wheel(QWidget):
    chosen = Signal(object)  # catalog.Choice

    def __init__(self, controller):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.controller = controller
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFixedSize(SIZE, SIZE)
        self.items: list[Path] = []
        self.mode = "convert"
        self.choices = []
        self.pending = False
        self.drag_mode = False
        self.dropped = False
        self.hover = None
        self.backdrop = None
        self.look = ON_DARK
        self._base = None
        self._shapes, self._shapes_n = [], -1
        self.t = 1.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(160)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._tick)
        self.outside = QTimer(self)
        self.outside.setInterval(30)
        self.outside.timeout.connect(self._watch_outside_click)
        self._button_was_down = True
        self.winId()  # create the native window now, so it is a drop target from the start

    # opening and closing

    def open_drag(self, mode: str, pos) -> None:
        self.drag_mode, self.dropped, self.pending = True, False, True
        self.items, self.choices, self.hover, self.mode = [], [], None, mode
        self._base = None
        self._show_at(pos)

    def open_click(self, items: list[Path], mode: str, pos) -> None:
        if self.isVisible():
            self.close_wheel()
            QApplication.processEvents()
        self.drag_mode, self.dropped, self.pending = False, False, False
        self.items, self.mode, self.hover = list(items), mode, None
        self._recompute()
        self._button_was_down = True
        self._show_at(pos)
        self.outside.start()

    def close_wheel(self) -> None:
        self.outside.stop()
        self.anim.stop()
        self.hide()
        self.items, self.choices, self.hover = [], [], None
        self._base = None

    def close_if_no_drop(self) -> None:
        if self.isVisible() and self.drag_mode and not self.dropped:
            self.close_wheel()

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.mode = mode
            self._recompute()
            self.update()

    def _show_at(self, pos) -> None:
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(max(pos.x() - SIZE // 2, geo.left()), geo.right() - SIZE)
        y = min(max(pos.y() - SIZE // 2, geo.top()), geo.bottom() - SIZE)
        self.set_backdrop(glass.capture(x, y, SIZE, SIZE))
        self.move(x, y)
        self.t = 0.0
        self.show()
        self.raise_()
        self.anim.start()

    def set_backdrop(self, image) -> None:
        """Frost a screenshot of what is behind the wheel. None: plain dark glass."""
        self.backdrop, self.look, self._base = None, ON_DARK, None
        if image is not None:
            try:
                self.backdrop, brightness = glass.frost(image, SIZE)
                self.look = ON_BRIGHT if brightness > 0.6 else ON_DARK
            except Exception:
                self.backdrop = None

    def _tick(self, value):
        self.t = float(value)
        self.update()

    def _recompute(self) -> None:
        self.choices = choices_for(self.items, self.mode, self.controller.engines) if self.items else []
        self.hover = None
        self._base = None

    # geometry

    def _center(self) -> QPointF:
        return QPointF(SIZE / 2, SIZE / 2)

    def _segment_at(self, point: QPointF):
        c = self._center()
        dx, dy = point.x() - c.x(), point.y() - c.y()
        r = math.hypot(dx, dy)
        if r < R_IN - 2:
            return "hub"
        if r > R_OUT + 10 or not self.choices:
            return None
        clockwise = (90 - math.degrees(math.atan2(-dy, dx))) % 360
        span = 360 / len(self.choices)
        return int(((clockwise + span / 2) % 360) // span)

    # drag and drop

    @staticmethod
    def _paths(event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile() and u.toLocalFile()]

    def dragEnterEvent(self, event):
        paths = self._paths(event)
        if not paths:
            event.ignore()
            return
        if paths != self.items:
            self.items = paths
            self.pending = False
            self._recompute()
        # Always Copy: a Move answer would let Explorer delete the source files.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self._drag_hover(event)

    def dragMoveEvent(self, event):
        self._drag_hover(event)

    def _drag_hover(self, event):
        seg = self._segment_at(event.position())
        if seg != self.hover:
            self.hover = seg
            self.update()
        # Accept over the hub too, so no "not allowed" cursor shows inside the
        # wheel. A drop on the hub just closes it.
        if seg is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.hover = None
        self.update()

    def dropEvent(self, event):
        seg = self._segment_at(event.position())
        if isinstance(seg, int) and seg < len(self.choices):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.dropped = True
            choice = self.choices[seg]
            self.close_wheel()
            self.chosen.emit(choice)
        else:
            event.ignore()
            self.close_wheel()

    # mouse (click mode)

    def mouseMoveEvent(self, event):
        seg = self._segment_at(event.position())
        if seg != self.hover:
            hub_changed = (seg == "hub") != (self.hover == "hub")
            self.hover = seg
            if hub_changed:
                self._base = None  # the hub's own hover look is in the cached layer
            self.update()

    def mousePressEvent(self, event):
        seg = self._segment_at(event.position())
        if isinstance(seg, int) and seg < len(self.choices):
            choice = self.choices[seg]
            self.close_wheel()
            self.chosen.emit(choice)
        elif seg == "hub":
            self.set_mode("tools" if self.mode == "convert" else "convert")
        else:
            self.close_wheel()

    def leaveEvent(self, event):
        if not self.drag_mode and self.hover is not None:
            if self.hover == "hub":
                self._base = None
            self.hover = None
            self.update()

    def _watch_outside_click(self):
        down = _down(VK["lbutton"]) or _down(VK["rbutton"])
        if down and not self._button_was_down:
            local = self.mapFromGlobal(QCursor.pos())
            if self._segment_at(QPointF(local)) is None:
                self.close_wheel()
        self._button_was_down = down

    # painting

    # The glass, the idle segments and the hub are drawn once into a cached
    # pixmap. A mouse move then only paints the highlighted segment on top.

    def _invalidate(self) -> None:
        self._base = None
        self.update()

    def _segments(self):
        """(shape, label box) per segment, rebuilt only when the count changes."""
        n = len(self.choices)
        if self._shapes_n != n:
            c = self._center()
            span = 360 / n if n else 0
            mid = (R_IN + R_OUT) / 2
            shapes = []
            for i in range(n):
                angle = 90 - i * span
                if n == 1:
                    path = annulus(c, R_IN + 6, R_OUT - 8)
                else:
                    path = pill_segment(c, R_IN + 6, R_OUT - 8, angle, span, GAP, ROUND)
                a = math.radians(angle if n > 1 else 90)
                x, y = c.x() + mid * math.cos(a), c.y() - mid * math.sin(a)
                shapes.append((path, QRectF(x - 50, y - 22, 100, 44)))
            self._shapes, self._shapes_n = shapes, n
        return self._shapes

    def _build_base(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(round(SIZE * dpr), round(SIZE * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = self._center()
        look = self.look
        self._shadow(p, c, look)
        disc = QPainterPath()
        disc.addEllipse(c, R_OUT, R_OUT)
        self._glass(p, disc, c, look, zoom=1.035, tint=look.tint)
        self._rim(p, c, R_OUT, look)
        n = len(self.choices)
        for choice, (path, box) in zip(self.choices, self._segments()):
            p.setPen(thin_pen(look.segment_edge, 1))
            p.setBrush(look.segment)
            p.drawPath(path)
            self._label(p, choice.label, box, False, n, look)
        self._hub(p, c, ACCENT[self.mode], look)
        p.end()
        return pm

    def paintEvent(self, event):
        if self._base is None:
            self._base = self._build_base()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = self._center()
        # Nearly invisible, so the whole disc catches the drop from the first frame.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 2))
        p.drawEllipse(c, R_OUT + 12, R_OUT + 12)
        if self.t < 1.0:
            p.setOpacity(self.t)
            scale = 0.9 + 0.1 * self.t
            p.translate(c)
            p.scale(scale, scale)
            p.translate(-c)
        p.drawPixmap(0, 0, self._base)
        if isinstance(self.hover, int) and self.hover < len(self.choices):
            path, box = self._segments()[self.hover]
            p.setPen(thin_pen(ACCENT[self.mode], 1.6))
            p.setBrush(self.look.hover)
            p.drawPath(path)
            self._label(p, self.choices[self.hover].label, box, True, len(self.choices), self.look)
        p.end()

    def _shadow(self, p, c, look):
        center = QPointF(c.x(), c.y() + 7)
        radius = R_OUT + 16
        grad = QRadialGradient(center, radius)
        grad.setColorAt((R_OUT - 30) / radius, QColor(0, 0, 0, look.shadow))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(center, radius, radius)

    def _glass(self, p, shape: QPainterPath, c, look, zoom: float, tint: QColor):
        """Fill a shape with the frosted backdrop, magnified a little like a lens."""
        p.save()
        p.setClipPath(shape)
        if self.backdrop is not None:
            p.save()
            p.translate(c)
            p.scale(zoom, zoom)
            p.translate(-c)
            p.drawImage(QRectF(0, 0, SIZE, SIZE), self.backdrop)
            p.restore()
        else:
            p.fillPath(shape, QColor(30, 30, 42, 225))
        p.fillPath(shape, tint)
        bounds = shape.boundingRect()
        sheen = QLinearGradient(bounds.topLeft(), bounds.center())
        sheen.setColorAt(0.0, QColor(255, 255, 255, look.sheen))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(shape, sheen)
        p.restore()

    def _rim(self, p, c, radius, look):
        """Light catching the edge: bright at the top, faint at the bottom."""
        grad = QLinearGradient(c.x(), c.y() - radius, c.x(), c.y() + radius)
        grad.setColorAt(0.0, QColor(255, 255, 255, look.rim_top))
        grad.setColorAt(1.0, QColor(255, 255, 255, look.rim_bottom))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(grad), 1.3))
        p.drawEllipse(c, radius - 0.7, radius - 0.7)
        p.setPen(thin_pen(look.outline, 1))
        p.drawEllipse(c, radius + 0.5, radius + 0.5)

    @staticmethod
    def _text(p, rect, text, color, shadow, flags=CENTER):
        if shadow.alpha():
            p.setPen(shadow)
            p.drawText(rect.translated(0, 1), flags, text)
        p.setPen(color)
        p.drawText(rect, flags, text)

    def _label(self, p, text, rect, hovered, n, look):
        font = QFont(self.font())
        size = 15 if n <= 7 else 13 if n <= 10 else 11
        if len(text) > 8:
            size -= 2
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.Bold if hovered else QFont.Weight.DemiBold)
        p.setFont(font)
        color = look.hover_text if hovered else look.text
        shadow = QColor(0, 0, 0, 0) if hovered else look.text_shadow
        self._text(p, rect, text, color, shadow, CENTER | Qt.TextFlag.TextWordWrap)

    def _hub(self, p, c, accent, look):
        hub = QPainterPath()
        hub.addEllipse(c, HUB, HUB)
        tint = QColor(look.hub)
        if self.hover == "hub" and not self.drag_mode:
            tint.setAlpha(min(255, tint.alpha() + 40))
        self._glass(p, hub, c, look, zoom=1.12, tint=tint)
        p.setBrush(Qt.BrushStyle.NoBrush)
        edge = QColor(accent)
        edge.setAlpha(235)
        p.setPen(thin_pen(edge, 2))
        p.drawEllipse(c, HUB, HUB)
        self._rim(p, c, HUB - 2, look)

        title = TITLES[self.mode]
        if self.pending:
            sub = "Move to see options"
        elif not self.items:
            sub = ""
        elif not self.choices:
            sub = "Nothing for this file"
        elif len(self.items) == 1:
            sub = self.items[0].name
        else:
            sub = f"{len(self.items)} files"
        settings = self.controller.settings
        other = "tools" if self.mode == "convert" else "convert"
        other_key = settings.tools_key if self.mode == "convert" else settings.convert_key
        hint = f"{KEY_NAMES[other_key]}: {TITLES[other]}"
        if self.hover == "hub" and not self.drag_mode:
            hint = f"Click: {TITLES[other]}"

        font = QFont(self.font())
        font.setPixelSize(17)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        self._text(p, QRectF(c.x() - HUB, c.y() - 33, 2 * HUB, 24), title, look.text, look.text_shadow)

        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        sub = QFontMetrics(font).elidedText(sub, Qt.TextElideMode.ElideMiddle, int(2 * HUB - 20))
        self._text(p, QRectF(c.x() - HUB, c.y() - 9, 2 * HUB, 16), sub, look.muted, QColor(0, 0, 0, 0))

        font.setPixelSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        pill_w = QFontMetrics(font).horizontalAdvance(hint) + 16
        pill = QRectF(c.x() - pill_w / 2, c.y() + 12, pill_w, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(look.pill)
        p.drawRoundedRect(pill, 9, 9)
        self._text(p, pill, hint, look.text, QColor(0, 0, 0, 0))
