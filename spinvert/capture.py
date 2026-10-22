"""Screenshots: freeze every screen, let the user drag an area (or click for the
whole screen), and hand the picture to the screenshot editor.

Also the global hotkey (Ctrl+Alt+S by default) that starts a screenshot from
anywhere, through Windows' RegisterHotKey.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

ACCENT = QColor("#7C5CFF")


class SnipOverlay(QWidget):
    """One frozen screen. Drag to choose an area; a click takes all of it."""

    def __init__(self, screen, shot: QPixmap, done):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.screen_, self.shot, self.done = screen, shot, done
        self.start = self.end = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(screen.geometry())

    def _rect(self) -> QRectF:
        if self.start is None or self.end is None:
            return QRectF()
        return QRectF(self.start, self.end).normalized()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(self.rect(), self.shot)
        dim = QPainterPath()
        dim.addRect(QRectF(self.rect()))
        r = self._rect()
        if not r.isEmpty():
            hole = QPainterPath()
            hole.addRect(r)
            dim = dim.subtracted(hole)
        p.fillPath(dim, QColor(0, 0, 0, 120))
        if not r.isEmpty():
            p.setPen(QPen(ACCENT, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            ratio = self.shot.width() / max(1, self.width())
            text = f"{round(r.width() * ratio)} × {round(r.height() * ratio)}"
            self._pill(p, text, QPointF(r.left(), max(0.0, r.top() - 34)))
        hint = "Drag to capture an area  •  Click to capture the whole screen  •  Esc to cancel"
        self._pill(p, hint, QPointF(self.width() / 2, 24), centred=True)
        p.end()

    def _pill(self, p: QPainter, text: str, at: QPointF, centred: bool = False):
        font = QFont("Segoe UI")
        font.setPixelSize(14)
        font.setBold(True)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(text) + 28
        x = at.x() - width / 2 if centred else at.x()
        box = QRectF(x, at.y(), width, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(22, 22, 30, 215))
        p.drawRoundedRect(box, 14, 14)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.done(None, None)
            return
        self.start = self.end = e.position()
        self.update()

    def mouseMoveEvent(self, e):
        if self.start is not None:
            self.end = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self.start is None:
            return
        r = self._rect()
        self.done(self, None if r.width() < 6 or r.height() < 6 else r)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.done(None, None)
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.done(self, None)


class Snipper:
    """Freezes all screens at once and returns the chosen picture to `deliver`."""

    def __init__(self, deliver):
        self.deliver = deliver
        self.overlays = []

    def start(self):
        shots = [(screen, screen.grabWindow(0)) for screen in QGuiApplication.screens()]
        for screen, shot in shots:
            overlay = SnipOverlay(screen, shot, self._done)
            overlay.show()
            self.overlays.append(overlay)
        under = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center())
        for overlay in self.overlays:
            if overlay.screen_ is under or len(self.overlays) == 1:
                overlay.activateWindow()
                overlay.setFocus()

    def _done(self, overlay, rect):
        image = None
        if overlay is not None:
            shot = overlay.shot
            if rect is None:
                image = shot.toImage()
            else:
                ratio = shot.width() / max(1, overlay.width())
                box = QRect(round(rect.left() * ratio), round(rect.top() * ratio),
                            round(rect.width() * ratio), round(rect.height() * ratio))
                image = shot.copy(box).toImage()
        for o in self.overlays:
            o.close()
            o.deleteLater()
        self.overlays = []
        if image is not None and not image.isNull():
            QTimer.singleShot(60, lambda: self.deliver(image))


# ------------------------------------------------------------ global hotkey

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
HOTKEY_ID = 0x5350  # "SP"


class Hotkey(QAbstractNativeEventFilter):
    """Ctrl+Alt+S anywhere in Windows calls `action` (on the UI thread)."""

    def __init__(self, action, key: str = "S", modifiers: int = MOD_CONTROL | MOD_ALT):
        super().__init__()
        self.action = action
        self.registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, modifiers | MOD_NOREPEAT, ord(key)))

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                QTimer.singleShot(0, self.action)
                return True, 0
        return False, 0

    def unregister(self):
        if self.registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False

