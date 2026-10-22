"""The radial wheel. It opens under the cursor and takes the file drop.

Two ways in:
- drag mode: opened during an Explorer drag. The files are not known until
  the drag enters the wheel, which happens on the first mouse move.
- click mode: opened with known files (Send to, the drop window). Click a
  segment, click the hub to switch wheels, click outside or Esc to close.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from spinvert.catalog import choices_for
from spinvert.theme import ACCENT, SURFACE, SURFACE_HI, TEXT, TEXT_MUTED, ring_segment, thin_pen
from spinvert.watcher import VK, _down

SIZE = 380
R_OUT = 172
R_IN = 70
HUB = 60
GAP = 1.4
TITLES = {"convert": "Convert", "tools": "Tools"}
KEY_NAMES = {"shift": "Shift", "ctrl": "Ctrl", "alt": "Alt"}


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
        self.t = 1.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(140)
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
        self._show_at(pos)

    def open_click(self, items: list[Path], mode: str, pos) -> None:
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
        self.move(x, y)
        self.t = 0.0
        self.show()
        self.raise_()
        self.anim.start()

    def _tick(self, value):
        self.t = float(value)
        self.update()

    def _recompute(self) -> None:
        self.choices = choices_for(self.items, self.mode, self.controller.engines) if self.items else []
        self.hover = None

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
        self.hover = seg
        self.update()
        if isinstance(seg, int):
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
            self.hover = seg
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

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c = self._center()
        # A nearly invisible disc so the gaps between hub and ring still catch the drop.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 2))
        p.drawEllipse(c, R_OUT + 10, R_OUT + 10)
        scale = 0.86 + 0.14 * self.t
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)
        p.setOpacity(self.t)
        accent = ACCENT[self.mode]

        ring = QPainterPath()
        ring.addEllipse(c, R_OUT, R_OUT)
        p.fillPath(ring, SURFACE)
        p.setPen(thin_pen(QColor(255, 255, 255, 30)))
        p.drawPath(ring)

        n = len(self.choices)
        if n:
            span = 360 / n
            mid = (R_IN + R_OUT) / 2
            for i, choice in enumerate(self.choices):
                center_angle = 90 - i * span
                if n == 1:
                    path = ring_segment(c, R_IN + 5, R_OUT - 5, 90, 359.9)
                else:
                    path = ring_segment(c, R_IN + 5, R_OUT - 5,
                                        center_angle - span / 2 + GAP / 2, span - GAP)
                hovered = i == self.hover
                p.fillPath(path, accent if hovered else SURFACE_HI)
                a = math.radians(center_angle) if n > 1 else math.radians(90)
                x = c.x() + mid * math.cos(a)
                y = c.y() - mid * math.sin(a)
                self._label(p, choice.label, QRectF(x - 52, y - 22, 104, 44), hovered, n)
        self._hub(p, c, accent)
        p.end()

    def _label(self, p, text, rect, hovered, n):
        font = QFont(self.font())
        size = 15 if n <= 7 else 13 if n <= 10 else 11
        if len(text) > 8:
            size -= 2
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.DemiBold if not hovered else QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(TEXT if hovered else QColor(244, 244, 248, 215))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def _hub(self, p, c, accent):
        hub_color = QColor(36, 36, 50, 252)
        if self.hover == "hub" and not self.drag_mode:
            hub_color = QColor(48, 48, 66, 252)
        p.setBrush(hub_color)
        edge = QColor(accent)
        edge.setAlpha(200)
        p.setPen(thin_pen(edge, 2))
        p.drawEllipse(c, HUB, HUB)

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
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(TEXT)
        p.drawText(QRectF(c.x() - HUB, c.y() - 30, 2 * HUB, 22), Qt.AlignmentFlag.AlignCenter, title)

        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(TEXT_MUTED)
        sub = QFontMetrics(font).elidedText(sub, Qt.TextElideMode.ElideMiddle, int(2 * HUB - 18))
        p.drawText(QRectF(c.x() - HUB, c.y() - 7, 2 * HUB, 16), Qt.AlignmentFlag.AlignCenter, sub)

        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(accent.lighter(130))
        p.drawText(QRectF(c.x() - HUB, c.y() + 12, 2 * HUB, 16), Qt.AlignmentFlag.AlignCenter, hint)
