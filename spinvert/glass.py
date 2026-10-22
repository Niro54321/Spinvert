"""Frosted glass: blur what is on screen behind a window, the way CSS
backdrop-filter does on the web.

Windows only blurs whole rectangular windows, so the wheel takes a snapshot of
the screen just before it appears, frosts it here, and paints it as its own
background. The wheel opens mid-drag, so what is behind it does not change.
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageFilter, ImageStat
from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication, QImage

BLUR = 16          # px, like backdrop-filter: blur(16px)
SATURATE = 1.25    # like backdrop-filter: saturate(1.25)
SHRINK = 3         # blur a smaller copy: same look, much faster


def capture(x: int, y: int, w: int, h: int) -> QImage | None:
    """Screen pixels under a rectangle in logical coordinates, at full DPI."""
    screen = QGuiApplication.screenAt(QPoint(x + w // 2, y + h // 2)) or QGuiApplication.primaryScreen()
    geo = screen.geometry()
    pm = screen.grabWindow(0, x - geo.x(), y - geo.y(), w, h)
    if pm.isNull() or pm.width() == 0:
        return None
    return pm.toImage()


def frost(image: QImage, logical_width: int) -> tuple[QImage, float]:
    """Blurred, slightly saturated copy, and its brightness from 0 to 1."""
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = rgba.width(), rgba.height()
    ratio = w / logical_width
    pil = Image.frombuffer("RGBA", (w, h), bytes(rgba.constBits()), "raw", "RGBA",
                           rgba.bytesPerLine(), 1).convert("RGB")
    small = pil.resize((max(1, w // SHRINK), max(1, h // SHRINK)), Image.Resampling.BOX)
    small = small.filter(ImageFilter.GaussianBlur(BLUR * ratio / SHRINK))
    small = ImageEnhance.Color(small).enhance(SATURATE)
    brightness = ImageStat.Stat(small.convert("L")).mean[0] / 255
    big = small.resize((w, h), Image.Resampling.BICUBIC).convert("RGBA")
    out = QImage(big.tobytes(), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    out.setDevicePixelRatio(ratio)
    return out, brightness
