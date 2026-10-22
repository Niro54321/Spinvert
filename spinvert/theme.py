"""Colours and the app icon, drawn in code (no image files to ship)."""

from __future__ import annotations

from io import BytesIO

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ACCENT = {"convert": QColor("#7C5CFF"), "tools": QColor("#06B6D4")}
MARK = [QColor("#7C5CFF"), QColor("#06B6D4"), QColor("#F472B6"), QColor("#34D399")]
SURFACE = QColor(22, 22, 30, 238)
SURFACE_HI = QColor(255, 255, 255, 18)
TEXT = QColor("#F4F4F8")
TEXT_MUTED = QColor(244, 244, 248, 150)


def ring_segment(center: QPointF, r_in: float, r_out: float, start: float, sweep: float) -> QPainterPath:
    """Annular sector. Angles in degrees, Qt style (counter-clockwise from 3 o'clock)."""
    outer = QRectF(center.x() - r_out, center.y() - r_out, 2 * r_out, 2 * r_out)
    inner = QRectF(center.x() - r_in, center.y() - r_in, 2 * r_in, 2 * r_in)
    path = QPainterPath()
    path.arcMoveTo(outer, start)
    path.arcTo(outer, start, sweep)
    path.arcTo(inner, start + sweep, -sweep)
    path.closeSubpath()
    return path


def draw_mark(p: QPainter, rect: QRectF) -> None:
    """The Spinvert mark: a four-part ring around a dot."""
    c = rect.center()
    r = min(rect.width(), rect.height()) / 2
    p.setPen(Qt.PenStyle.NoPen)
    for i, color in enumerate(MARK):
        p.setBrush(color)
        p.drawPath(ring_segment(c, r * 0.52, r * 0.98, 90 - i * 90 - 84, 78))
    p.setBrush(QColor("#F4F4F8"))
    p.drawEllipse(c, r * 0.26, r * 0.26)


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_mark(p, QRectF(0, 0, size, size))
        p.end()
        icon.addPixmap(pm)
    return icon


def save_ico(path) -> None:
    """Write the icon as .ico for the Send to shortcut."""
    from PIL import Image

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    app_icon().pixmap(256, 256).save(buf, "PNG")
    Image.open(BytesIO(bytes(buf.data()))).save(
        path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])


def thin_pen(color: QColor, width: float = 1.0) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    return pen
