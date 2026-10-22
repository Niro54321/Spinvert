"""Watches the mouse and keyboard to spot a file drag plus a key press.

Windows has no event for "a drag is in progress in Explorer", so this polls
the button and key states (GetAsyncKeyState) a few dozen times a second. It
installs no hooks and reads no keystrokes: only the state of the primary
mouse button, Shift, Ctrl, Alt and Esc.
"""

from __future__ import annotations

import ctypes
import math
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Signal

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]

VK = {"lbutton": 0x01, "rbutton": 0x02, "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "esc": 0x1B}
SM_SWAPBUTTON, SM_CXDRAG = 23, 68
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _cursor() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def process_at(x: int, y: int) -> str:
    """Executable name of the window under a screen point, lower case."""
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    root = user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
    if not root:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


class DragWatcher(QObject):
    pressed = Signal(int, int)  # mouse down where a drag may start (physical px)
    triggered = Signal(str)   # a mode key was pressed during a drag: open the wheel
    switched = Signal(str)    # a mode key was pressed while the wheel is open
    released = Signal()       # the mouse button went up
    escaped = Signal()

    def __init__(self, get_settings, wheel_is_open, parent=None):
        super().__init__(parent)
        self.get_settings = get_settings
        self.wheel_is_open = wheel_is_open
        self.button = False
        self.dragging = False
        self.source_ok = False
        self.down_at = (0, 0)
        self.keys: dict[str, bool] = {}
        self.esc = False
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._poll)

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def _poll(self):
        settings = self.get_settings()
        primary = VK["rbutton"] if user32.GetSystemMetrics(SM_SWAPBUTTON) else VK["lbutton"]
        button = _down(primary)
        pos = _cursor()
        if button and not self.button:
            self.down_at = pos
            self.dragging = False
            self.source_ok = (not settings.explorer_only) or process_at(*pos) == "explorer.exe"
            if self.source_ok:
                self.pressed.emit(*pos)
        if button and not self.dragging:
            threshold = max(8, user32.GetSystemMetrics(SM_CXDRAG))
            if math.dist(pos, self.down_at) > threshold:
                self.dragging = True
        if self.button and not button:
            self.dragging = False
            self.released.emit()
        self.button = button

        keys = {name: _down(VK[name]) for name in ("shift", "ctrl", "alt")}
        for mode, key in (("convert", settings.convert_key), ("tools", settings.tools_key)):
            if keys.get(key) and not self.keys.get(key):
                if self.wheel_is_open():
                    self.switched.emit(mode)
                elif self.dragging and self.source_ok:
                    self.triggered.emit(mode)
        self.keys = keys

        esc = _down(VK["esc"])
        if esc and not self.esc and self.wheel_is_open():
            self.escaped.emit()
        self.esc = esc
