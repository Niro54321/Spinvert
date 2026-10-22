"""Screenshots: freeze every screen, let the user drag an area (or click for the
whole screen), and hand the picture to the screenshot editor.

Also the global shortcut (Ctrl+Alt+S unless changed in Settings) that starts a
screenshot from anywhere, through Windows' RegisterHotKey.
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
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0x5350  # "SP"
VK_SNAPSHOT = 0x2C

KEY_NAMES = {0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "Caps Lock", 0x1B: "Esc",
             0x20: "Space", 0x21: "Page Up", 0x22: "Page Down", 0x23: "End", 0x24: "Home", 0x25: "Left",
             0x26: "Up", 0x27: "Right", 0x28: "Down", VK_SNAPSHOT: "Print Screen", 0x2D: "Insert",
             0x2E: "Delete", 0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /",
             0x91: "Scroll Lock"}
# Keys that are fine on their own; anything else needs Ctrl, Alt, Shift or Win
# or it would stop working for typing.
ALONE_OK = {0x13, VK_SNAPSHOT, 0x2D, 0x91, *range(0x70, 0x88)}


def key_name(vk: int) -> str:
    if vk in KEY_NAMES:
        return KEY_NAMES[vk]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    char = user32.MapVirtualKeyW(vk, 2) & 0xFFFF  # punctuation keys, as printed on this keyboard
    return chr(char).upper() if char else f"Key {vk}"


def modifier_text(modifiers: int) -> str:
    return "+".join(name for flag, name in ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"),
                                            (MOD_WIN, "Win")) if modifiers & flag)


def hotkey_text(modifiers: int, vk: int) -> str:
    return "+".join(part for part in (modifier_text(modifiers), key_name(vk)) if part)


def available(modifiers: int, vk: int) -> bool:
    """Whether Windows would let Spinvert have this combination right now."""
    if not user32.RegisterHotKey(None, HOTKEY_ID + 1, modifiers | MOD_NOREPEAT, vk):
        return False
    user32.UnregisterHotKey(None, HOTKEY_ID + 1)
    return True


class Hotkey(QAbstractNativeEventFilter):
    """A key combination (Ctrl+Alt+S by default) that calls `action` from
    anywhere in Windows, on the UI thread."""

    def __init__(self, action, modifiers: int = MOD_CONTROL | MOD_ALT, vk: int = ord("S")):
        super().__init__()
        self.action = action
        self.modifiers, self.vk = modifiers, vk
        self.registered = False
        self.register()

    def register(self) -> bool:
        if not self.registered:
            self.registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, self.modifiers | MOD_NOREPEAT, self.vk))
        return self.registered

    def change(self, modifiers: int, vk: int) -> bool:
        """Switch to another combination. False (and the old one kept) if Windows
        refuses it, usually because another app already uses it."""
        old = self.modifiers, self.vk
        self.unregister()
        self.modifiers, self.vk = modifiers, vk
        if self.register():
            return True
        self.modifiers, self.vk = old
        self.register()
        return False

    @property
    def text(self) -> str:
        return hotkey_text(self.modifiers, self.vk)

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
