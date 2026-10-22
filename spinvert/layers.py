"""Layers drawn over a photo or a video frame: arrows, lines, boxes, circles,
pen and highlighter strokes, text, numbered labels, a magnifier and pictures.

A layer is a plain dict, positioned in fractions of the picture (0..1) and
sized in thousandths of its longest side, so the same layers fit the small
preview and the full-size result. Everything is drawn with Qt, which shapes
Arabic and other scripts correctly and uses any installed font.
"""

from __future__ import annotations

import copy
import math
import unicodedata
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPolygonF,
                           QTextOption)

NAMES = {"arrow": "Arrow", "line": "Line", "rect": "Box", "ellipse": "Circle", "pen": "Pen",
         "highlight": "Highlight", "text": "Text", "number": "Number", "magnify": "Magnifier",
         "image": "Picture"}

TEXT_DEFAULTS = {"font": "Segoe UI", "size": 55, "bold": True, "italic": False, "align": "auto",
                 "bg": {"on": False, "color": "#111114", "opacity": 85, "padding": 35, "radius": 35},
                 "shadow": {"on": True, "color": "#000000", "opacity": 55, "blur": 4, "distance": 3}}


def new(kind: str, **fields) -> dict:
    layer = {"id": uuid.uuid4().hex[:8], "type": kind, "points": [], "color": "#FF3B30", "width": 6,
             "opacity": 100}
    if kind == "text":
        layer.update(copy.deepcopy(TEXT_DEFAULTS), text="", color="#FFFFFF")
    elif kind == "number":
        layer.update(size=26, number=1)
    elif kind == "magnify":
        layer.update(zoom=2.0, color="#FFFFFF")
    elif kind == "highlight":
        layer.update(color="#FFCC00", width=8)
    layer.update(copy.deepcopy(fields))
    return layer


def name(layer: dict) -> str:
    base = NAMES.get(layer["type"], layer["type"])
    if layer["type"] == "text" and layer.get("text"):
        first = layer["text"].strip().splitlines()[0] if layer["text"].strip() else ""
        return f"{base}: {first[:18]}"
    if layer["type"] == "number":
        return f"{base} {layer.get('number', 1)}"
    return base


def is_rtl(text: str) -> bool:
    for ch in text:
        kind = unicodedata.bidirectional(ch)
        if kind in ("R", "AL"):
            return True
        if kind == "L":
            return False
    return False


def _color(layer: dict, key: str = "color", opacity: float | None = None) -> QColor:
    c = QColor(layer.get(key, "#FF3B30"))
    c.setAlphaF(max(0.0, min(1.0, (layer.get("opacity", 100) if opacity is None else opacity) / 100)))
    return c


def _pts(layer, W, H):
    return [QPointF(x * W, y * H) for x, y in layer.get("points", [])]


def _unit(W, H) -> float:
    return max(W, H) / 1000


# ---------------------------------------------------------------- text

def text_font(layer: dict, W: float, H: float) -> QFont:
    font = QFont(layer.get("font", "Segoe UI"))
    font.setPixelSize(max(4, round(layer.get("size", 55) * _unit(W, H))))
    font.setBold(bool(layer.get("bold")))
    font.setItalic(bool(layer.get("italic")))
    return font


def _text_option(layer: dict) -> QTextOption:
    rtl = is_rtl(layer.get("text", ""))
    align = layer.get("align", "auto")
    flag = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight}.get(align,
                                                      Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
    opt = QTextOption(flag)
    opt.setTextDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)
    opt.setWrapMode(QTextOption.WrapMode.NoWrap)
    return opt


def text_rect(layer: dict, W: float, H: float) -> QRectF:
    """The text itself (without its background), in pixels."""
    metrics = QFontMetricsF(text_font(layer, W, H))
    lines = (layer.get("text") or " ").split("\n")
    width = max(metrics.horizontalAdvance(line or " ") for line in lines)
    height = metrics.lineSpacing() * len(lines)
    x, y = layer["points"][0]
    return QRectF(x * W, y * H, width + 2, height)


def _text_padding(layer: dict, W, H) -> float:
    px = text_font(layer, W, H).pixelSize()
    return px * layer.get("bg", {}).get("padding", 35) / 100 if layer.get("bg", {}).get("on") else 0.0


# ---------------------------------------------------------------- bounds

def bounds(layer: dict, W: float, H: float) -> QRectF:
    kind = layer["type"]
    unit = _unit(W, H)
    pts = _pts(layer, W, H)
    if not pts:
        return QRectF()
    if kind == "text":
        pad = _text_padding(layer, W, H)
        return text_rect(layer, W, H).adjusted(-pad, -pad, pad, pad)
    if kind == "number":
        r = layer.get("size", 26) * unit
        return QRectF(pts[0].x() - r, pts[0].y() - r, 2 * r, 2 * r)
    if kind == "magnify":
        r = layer.get("radius", 0.12) * W
        return QRectF(pts[0].x() - r, pts[0].y() - r, 2 * r, 2 * r)
    if kind == "image":
        w = layer.get("w", 0.3) * W
        return QRectF(pts[0].x(), pts[0].y(), w, w / max(0.01, layer.get("aspect", 1.0)))
    xs, ys = [p.x() for p in pts], [p.y() for p in pts]
    half = layer.get("width", 6) * unit * (2 if kind == "highlight" else 0.5) + (layer.get("width", 6) * unit * 2
                                                                                 if kind == "arrow" else 0)
    return QRectF(min(xs) - half, min(ys) - half, max(xs) - min(xs) + 2 * half, max(ys) - min(ys) + 2 * half)


def _segment_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = dx * dx + dy * dy
    t = 0.0 if not length else max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


def hit(layer: dict, x: float, y: float, W: float, H: float, slack: float = 6) -> bool:
    kind = layer["type"]
    p = QPointF(x, y)
    pts = _pts(layer, W, H)
    if not pts:
        return False
    width = layer.get("width", 6) * _unit(W, H) * (4 if kind == "highlight" else 1)
    if kind in ("arrow", "line") and len(pts) >= 2:
        return _segment_distance(p, pts[0], pts[-1]) <= width / 2 + slack
    if kind in ("pen", "highlight"):
        return any(_segment_distance(p, a, b) <= width / 2 + slack for a, b in zip(pts, pts[1:])) or \
            (len(pts) == 1 and math.hypot(p.x() - pts[0].x(), p.y() - pts[0].y()) <= width)
    if kind in ("number", "magnify"):
        r = bounds(layer, W, H)
        return math.hypot(p.x() - r.center().x(), p.y() - r.center().y()) <= r.width() / 2 + slack
    return bounds(layer, W, H).adjusted(-slack, -slack, slack, slack).contains(p)


def top_hit(layers: list[dict], x: float, y: float, W: float, H: float, slack: float = 6):
    for layer in reversed(layers):
        if hit(layer, x, y, W, H, slack):
            return layer
    return None


# ---------------------------------------------------------- moving, sizing

def translate(layer: dict, dx: float, dy: float) -> None:
    """Move by fractions of the picture."""
    layer["points"] = [[x + dx, y + dy] for x, y in layer["points"]]


def scale(layer: dict, factor: float, W: float, H: float) -> None:
    """Grow or shrink around its centre."""
    c = bounds(layer, W, H).center()
    cx, cy = c.x() / W, c.y() / H
    kind = layer["type"]
    if kind == "text":
        layer["size"] = max(4, layer.get("size", 55) * factor)
        return
    if kind == "number":
        layer["size"] = max(6, layer.get("size", 26) * factor)
        return
    if kind == "magnify":
        layer["radius"] = max(0.01, layer.get("radius", 0.12) * factor)
        return
    if kind == "image":
        x, y = layer["points"][0]
        w = layer.get("w", 0.3)
        layer["w"] = max(0.02, w * factor)
        layer["points"][0] = [cx - (cx - x) * factor, cy - (cy - y) * factor]
        return
    layer["points"] = [[cx + (x - cx) * factor, cy + (y - cy) * factor] for x, y in layer["points"]]
    if kind not in ("rect", "ellipse"):
        layer["width"] = max(1, layer.get("width", 6) * math.sqrt(factor))


# ----------------------------------------------------------------- drawing

_images: dict[str, QImage] = {}


def _image(path: str) -> QImage:
    if path not in _images:
        img = QImage(path)
        if img.isNull():
            try:
                from spinvert.editors.base import to_qimage
                from spinvert.engines.images import _open, _upright

                img = to_qimage(_upright(_open(__import__("pathlib").Path(path))))
            except Exception:
                img = QImage()
        _images[path] = img
    return _images[path]


def _arrow(p: QPainter, a: QPointF, b: QPointF, width: float, color: QColor):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    head = min(length * 0.7, max(width * 4.4, 10))
    half = head * 0.42
    base = QPointF(b.x() - ux * head, b.y() - uy * head)
    notch = QPointF(b.x() - ux * head * 0.78, b.y() - uy * head * 0.78)
    pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(a, QPointF(b.x() - ux * head * 0.6, b.y() - uy * head * 0.6))
    p.setPen(QPen(color, max(1.0, width * 0.35), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(color)
    p.drawPolygon(QPolygonF([b, QPointF(base.x() + nx * half, base.y() + ny * half), notch,
                             QPointF(base.x() - nx * half, base.y() - ny * half)]))


def _smooth_path(pts) -> QPainterPath:
    path = QPainterPath(pts[0])
    if len(pts) == 1:
        path.lineTo(pts[0])
        return path
    for a, b in zip(pts[1:], pts[2:]):
        path.quadTo(a, QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
    path.lineTo(pts[-1])
    return path


def _light(color: QColor) -> bool:
    return 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue() > 170


def paint(p: QPainter, layer: dict, W: float, H: float, source: QImage | None = None) -> None:
    """Draw one layer; the painter works in the picture's pixels."""
    kind = layer["type"]
    pts = _pts(layer, W, H)
    if not pts:
        return
    unit = _unit(W, H)
    color = _color(layer)
    width = max(1.0, layer.get("width", 6) * unit)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    a, b = pts[0], pts[-1]
    if kind == "arrow":
        _arrow(p, a, b, width, color)
    elif kind == "line":
        p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(a, b)
    elif kind in ("rect", "ellipse"):
        p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = QRectF(a, b).normalized()
        if kind == "rect":
            p.drawRoundedRect(r, width * 1.4, width * 1.4)
        else:
            p.drawEllipse(r)
    elif kind in ("pen", "highlight"):
        if kind == "highlight":
            color.setAlphaF(color.alphaF() * 0.45)
            width *= 4
        p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_smooth_path(pts))
    elif kind == "number":
        r = layer.get("size", 26) * unit
        p.setPen(QPen(QColor(255, 255, 255, int(255 * color.alphaF())), max(1.5, r * 0.11)))
        p.setBrush(color)
        p.drawEllipse(a, r, r)
        font = QFont("Segoe UI")
        font.setPixelSize(max(4, round(r * 1.05)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#16161D") if _light(color) else QColor("white"))
        p.drawText(QRectF(a.x() - r, a.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter,
                   str(layer.get("number", 1)))
    elif kind == "magnify" and source is not None and not source.isNull():
        r = layer.get("radius", 0.12) * W
        zoom = max(1.1, layer.get("zoom", 2.0))
        sx, sy = source.width() / W, source.height() / H
        src = QRectF((a.x() - r / zoom) * sx, (a.y() - r / zoom) * sy, 2 * r / zoom * sx, 2 * r / zoom * sy)
        circle = QPainterPath()
        circle.addEllipse(a, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(a.x(), a.y() + r * 0.05), r * 1.03, r * 1.03)
        p.setClipPath(circle)
        p.drawImage(QRectF(a.x() - r, a.y() - r, 2 * r, 2 * r), source, src)
        p.setClipping(False)
        p.setPen(QPen(color, max(2.0, r * 0.045)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(a, r, r)
    elif kind == "image":
        img = _image(layer.get("path", ""))
        if not img.isNull():
            p.setOpacity(layer.get("opacity", 100) / 100)
            p.drawImage(bounds(layer, W, H), img)
    elif kind == "text" and layer.get("text"):
        _text(p, layer, W, H)
    p.restore()


def _text(p: QPainter, layer: dict, W, H):
    font = text_font(layer, W, H)
    rect = text_rect(layer, W, H)
    opt = _text_option(layer)
    unit = _unit(W, H)
    bg = layer.get("bg", {})
    if bg.get("on"):
        pad = _text_padding(layer, W, H)
        box = rect.adjusted(-pad, -pad, pad, pad)
        radius = font.pixelSize() * bg.get("radius", 35) / 100
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color(bg, "color", bg.get("opacity", 85) * layer.get("opacity", 100) / 100))
        p.drawRoundedRect(box, radius, radius)
    p.setFont(font)
    text = layer.get("text", "")
    shadow = layer.get("shadow", {})
    if shadow.get("on"):
        blur = shadow.get("blur", 4) * unit
        dist = shadow.get("distance", 3) * unit
        steps = 12 if blur > 0.5 else 1
        base = _color(shadow, "color", shadow.get("opacity", 55) * layer.get("opacity", 100) / 100)
        base.setAlphaF(base.alphaF() / (steps ** 0.6))
        p.setPen(base)
        for i in range(steps):
            ang = 2 * math.pi * i / steps
            off = QPointF(math.cos(ang) * blur, dist + math.sin(ang) * blur)
            p.drawText(rect.translated(off), text, opt)
    p.setPen(_color(layer))
    p.drawText(rect, text, opt)


def paint_all(p: QPainter, layers: list[dict], W: float, H: float, source: QImage | None = None,
              skip: str | None = None) -> None:
    for layer in layers:
        if layer.get("id") != skip and not layer.get("hidden"):
            paint(p, layer, W, H, source)


def from_pil(im) -> QImage:
    rgba = im.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


def to_pil(img: QImage):
    from PIL import Image

    rgba = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()), "raw", "RGBA",
                            rgba.bytesPerLine(), 1).copy()


def render(image: QImage, layers: list[dict]) -> QImage:
    """The picture with its layers drawn on it, at full size."""
    out = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    source = out.copy()
    p = QPainter(out)
    paint_all(p, layers, out.width(), out.height(), source)
    p.end()
    return out


def render_alone(width: int, height: int, layers: list[dict]) -> QImage:
    """Just the layers on a transparent picture (for video overlays)."""
    out = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    paint_all(p, layers, width, height, None)
    p.end()
    return out
