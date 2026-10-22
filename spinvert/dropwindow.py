"""The drop window, drawn as a liquid-glass card over the screen behind it."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from spinvert import APP_NAME, glass
from spinvert.theme import ACCENT, ON_BRIGHT, ON_DARK, app_icon, draw_mark, soft_text, thin_pen
from spinvert.wheel import KEY_NAMES

MARGIN = 26      # room around the card for its shadow
RADIUS = 26
HEADER = 52

BUTTON_CSS = {
    "dark": ("QPushButton {{ color: white; background: rgba(255,255,255,{bg}); "
             "border: 1px solid rgba(255,255,255,0.38); border-radius: {r}px; padding: 6px 16px; "
             "font-weight: 600; }} QPushButton:hover {{ background: rgba(255,255,255,0.28); }}"),
    "bright": ("QPushButton {{ color: #17171F; background: rgba(255,255,255,{bg}); "
               "border: 1px solid rgba(0,0,0,0.14); border-radius: {r}px; padding: 6px 16px; "
               "font-weight: 600; }} QPushButton:hover {{ background: rgba(255,255,255,0.85); }}"),
}


def _shadow_image(width: int, height: int) -> QImage:
    """A soft drop shadow for the card, like box-shadow: 0 16px 40px rgba(0,0,0,.28)."""
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (MARGIN, MARGIN + 10, width - MARGIN, height - MARGIN + 6), RADIUS, fill=72)
    mask = mask.filter(ImageFilter.GaussianBlur(14))
    rgba = Image.merge("RGBA", (Image.new("L", mask.size, 0),) * 3 + (mask,))
    return QImage(rgba.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888).copy()


class DropWindow(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.resize(500, 430)
        self.backdrop = None
        self.look = ON_DARK
        self.over = False
        self._shadow = None

        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("Hide to tray")
        self.close_button.clicked.connect(self.hide)
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(controller.show_settings)
        self.hide_button = QPushButton("Hide to tray")
        self.hide_button.clicked.connect(self.hide)

        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(self.close_button)
        bottom = QHBoxLayout()
        bottom.addWidget(self.settings_button)
        bottom.addStretch()
        bottom.addWidget(self.hide_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MARGIN + 14, MARGIN + 10, MARGIN + 16, MARGIN + 14)
        layout.addLayout(top)
        layout.addStretch()
        layout.addLayout(bottom)

        self._moved = QTimer(self)
        self._moved.setSingleShot(True)
        self._moved.setInterval(60)
        self._moved.timeout.connect(self._update_look)
        self._style_buttons()

    # glass

    def card(self) -> QRectF:
        return QRectF(self.rect()).adjusted(MARGIN, MARGIN - 6, -MARGIN, -MARGIN - 6)

    def refresh_backdrop(self) -> None:
        """Snapshot the monitor behind the window. Call while it is hidden."""
        try:
            snap = glass.snapshot_for(self)
            self.backdrop = glass.Backdrop(snap) if snap else None
        except Exception:
            self.backdrop = None
        self._update_look()

    def place(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)

    def _update_look(self) -> None:
        look = ON_DARK
        if self.backdrop is not None:
            if self.backdrop.brightness(glass.window_rect(self)) > 0.6:
                look = ON_BRIGHT
        if look is not self.look:
            self.look = look
            self._style_buttons()
        self.update()

    def _style_buttons(self) -> None:
        css = BUTTON_CSS["bright" if self.look is ON_BRIGHT else "dark"]
        self.settings_button.setStyleSheet(css.format(bg="0.16" if self.look is ON_DARK else "0.6", r=15))
        self.hide_button.setStyleSheet(css.format(bg="0.16" if self.look is ON_DARK else "0.6", r=15))
        self.close_button.setStyleSheet(css.format(bg="0.10" if self.look is ON_DARK else "0.5", r=15)
                                        + " QPushButton { padding: 0; }")

    def moveEvent(self, event):
        self.update()
        self._moved.start()

    def resizeEvent(self, event):
        self._shadow = None

    # moving the window and dropping files

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < MARGIN + HEADER:
            self.windowHandle().startSystemMove()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.controller.note_still_running()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.over = True
            self.update()

    def dragMoveEvent(self, event):
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.over = False
        self.update()

    def dropEvent(self, event):
        self.over = False
        self.update()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if paths:
            # Open the wheel after the drop finishes, so Explorer is not kept waiting.
            QTimer.singleShot(0, lambda: self.controller.open_files(paths))

    # painting

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        look = self.look
        if self._shadow is None:
            self._shadow = _shadow_image(self.width(), self.height())
        p.drawImage(0, 0, self._shadow)

        card = self.card()
        shape = QPainterPath()
        shape.addRoundedRect(card, RADIUS, RADIUS)
        p.save()
        p.setClipPath(shape)
        src = self.backdrop.source(glass.window_rect(self)) if self.backdrop else None
        if src is not None:
            p.drawImage(QRectF(self.rect()), self.backdrop.image, src)
        else:
            p.fillPath(shape, QColor(30, 30, 42, 230))
        p.fillPath(shape, look.tint)
        sheen = QLinearGradient(card.topLeft(), card.center())
        sheen.setColorAt(0.0, QColor(255, 255, 255, look.sheen))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(shape, sheen)
        p.restore()
        # border, and the bright inset line along the top edge
        rim = QLinearGradient(card.topLeft(), card.bottomLeft())
        rim.setColorAt(0.0, QColor(255, 255, 255, look.rim_top))
        rim.setColorAt(1.0, QColor(255, 255, 255, look.rim_bottom))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rim, 1.2))
        p.drawRoundedRect(card.adjusted(0.6, 0.6, -0.6, -0.6), RADIUS, RADIUS)
        p.setPen(thin_pen(look.outline, 1))
        p.drawRoundedRect(card.adjusted(-0.5, -0.5, 0.5, 0.5), RADIUS, RADIUS)

        # header
        draw_mark(p, QRectF(card.left() + 18, card.top() + 15, 24, 24))
        font = QFont(self.font())
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        soft_text(p, QRectF(card.left() + 50, card.top() + 12, 200, 30), APP_NAME, look.text,
                  look.text_shadow, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # drop zone
        zone = QRectF(card.left() + 18, card.top() + HEADER + 4, card.width() - 36, card.height() - HEADER - 130)
        accent = ACCENT["convert"]
        fill = QColor(accent) if self.over else QColor(look.segment)
        if self.over:
            fill.setAlpha(70)
        edge = QColor(accent) if self.over else QColor(look.text)
        edge.setAlpha(230 if self.over else 120)
        pen = QPen(edge, 1.6, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.setBrush(fill)
        p.drawRoundedRect(zone, 18, 18)
        size = 54
        draw_mark(p, QRectF(zone.center().x() - size / 2, zone.top() + 22, size, size))
        font.setPixelSize(19)
        p.setFont(font)
        soft_text(p, QRectF(zone.left(), zone.top() + 86, zone.width(), 28), "Drop files here",
                  look.text, look.text_shadow)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        soft_text(p, QRectF(zone.left(), zone.top() + 114, zone.width(), 20),
                  "then pick a format on the wheel", look.muted, look.text_shadow)

        # tip
        s = self.controller.settings
        tip = (f"Faster: start dragging any file in File Explorer, then press "
               f"{KEY_NAMES[s.convert_key]} to convert or {KEY_NAMES[s.tools_key]} for tools. "
               f"Let go over a format. Esc cancels.")
        soft_text(p, QRectF(card.left() + 20, zone.bottom() + 12, card.width() - 40, 46), tip,
                  look.text, look.text_shadow, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
        p.end()
