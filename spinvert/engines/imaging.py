"""Photo tools as pure functions: a Pillow image and settings in, a new image out.

The editors run them on a small copy for the live preview and the jobs run them
on the full-size photo, so the result matches the preview. Sizes (padding,
line widths, blur) are relative to the photo, which keeps the two alike.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# ---------------------------------------------------------------- edit photos

ADJUSTMENTS = [  # key, label, minimum, maximum
    ("exposure", "Exposure", -100, 100), ("contrast", "Contrast", -100, 100),
    ("highlights", "Highlights", -100, 100), ("shadows", "Shadows", -100, 100),
    ("whites", "Whites", -100, 100), ("blacks", "Blacks", -100, 100),
    ("temperature", "Temperature", -100, 100), ("tint", "Tint", -100, 100),
    ("vibrance", "Vibrance", -100, 100), ("saturation", "Saturation", -100, 100),
    ("clarity", "Clarity", -100, 100), ("dehaze", "Dehaze", -100, 100),
    ("sharpness", "Sharpness", 0, 100), ("noise", "Noise reduction", 0, 100),
    ("grain", "Grain", 0, 100), ("vignette", "Vignette", -100, 100),
]

PRESETS = {
    "Original": {},
    "Vivid": {"contrast": 18, "vibrance": 35, "saturation": 8, "clarity": 12},
    "Punch": {"exposure": 12, "contrast": 25, "vibrance": 25, "dehaze": 20},
    "Warm": {"temperature": 32, "tint": 6, "vibrance": 10},
    "Cool": {"temperature": -30, "vibrance": 8},
    "Matte": {"contrast": -18, "blacks": 30, "saturation": -10, "grain": 12},
    "Fade": {"contrast": -25, "blacks": 35, "highlights": -12},
    "Vintage": {"temperature": 25, "saturation": -25, "blacks": 22, "vignette": 35, "grain": 25},
    "Dramatic": {"contrast": 35, "clarity": 40, "shadows": -12, "vignette": 30, "saturation": -12},
    "B&W": {"saturation": -100, "contrast": 22, "clarity": 15},
}


def _smooth(edge0: float, edge1: float, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


def adjust(im: Image.Image, settings: dict) -> Image.Image:
    a = {k: float(v) / 100 for k, v in settings.items() if v}
    alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
    if not a:
        return im.copy()
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    h, w = rgb.shape[:2]
    short = min(w, h)

    t, tint = a.get("temperature", 0), a.get("tint", 0)
    if t or tint:
        rgb[..., 0] *= 1 + 0.16 * t
        rgb[..., 2] *= 1 - 0.16 * t
        rgb[..., 1] *= 1 - 0.10 * tint
    if a.get("exposure"):
        rgb *= 2 ** (a["exposure"] * 2)  # the slider covers -2 to +2 stops
    dehaze = a.get("dehaze", 0)
    if dehaze > 0:
        rgb = (rgb - 0.07 * dehaze) / (1 - 0.07 * dehaze)
    elif dehaze < 0:
        rgb = rgb + (-dehaze) * 0.25 * (1 - rgb)

    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    tone = np.zeros_like(lum)
    L = np.clip(lum, 0, 1)
    if a.get("shadows"):
        tone += a["shadows"] * 0.30 * (1 - _smooth(0.0, 0.5, L))
    if a.get("highlights"):
        tone += a["highlights"] * 0.30 * _smooth(0.5, 1.0, L)
    if a.get("whites"):
        tone += a["whites"] * 0.15 * _smooth(0.65, 1.0, L)
    if a.get("blacks"):
        tone += a["blacks"] * 0.15 * (1 - _smooth(0.0, 0.35, L))
    if tone.any():
        rgb += tone[..., None]

    contrast = a.get("contrast", 0) + 0.25 * dehaze
    if contrast:
        rgb = (rgb - 0.5) * (1 + contrast) + 0.5

    sat, vib = a.get("saturation", 0) + 0.2 * dehaze, a.get("vibrance", 0)
    if sat or vib:
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        chroma = rgb - lum[..., None]
        now = np.clip(rgb.max(axis=2) - rgb.min(axis=2), 0, 1)
        factor = np.clip(1 + sat + vib * (1 - now), 0, None)
        rgb = lum[..., None] + chroma * factor[..., None]

    if a.get("grain"):
        rng = np.random.default_rng(7)
        rgb += rng.normal(0, 0.09 * a["grain"], (h, w, 1)).astype(np.float32)
    if a.get("vignette"):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
        edge = _smooth(0.35, 1.0, d)[..., None]
        v = a["vignette"]
        rgb = rgb * (1 - 0.85 * v * edge) if v > 0 else rgb + (-v) * 0.6 * edge * (1 - rgb)

    out = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    clarity = a.get("clarity", 0)
    if clarity > 0:
        out = out.filter(ImageFilter.UnsharpMask(radius=max(2, short / 60), percent=int(clarity * 110), threshold=2))
    elif clarity < 0:
        out = Image.blend(out, out.filter(ImageFilter.GaussianBlur(max(1, short / 160))), -clarity * 0.6)
    if a.get("noise"):
        out = Image.blend(out, out.filter(ImageFilter.GaussianBlur(max(0.8, short / 900))), a["noise"] * 0.8)
    if a.get("sharpness"):
        out = out.filter(ImageFilter.UnsharpMask(radius=max(1, short / 700), percent=int(a["sharpness"] * 220), threshold=1))
    if alpha is not None:
        out.putalpha(alpha)
    return out


# ------------------------------------------------------- crop, rotate, resize

ASPECTS = {"Free": None, "Original": "original", "1:1": (1, 1), "4:5": (4, 5), "3:4": (3, 4),
           "2:3": (2, 3), "9:16": (9, 16), "16:9": (16, 9), "3:2": (3, 2), "4:3": (4, 3)}


def rotate(im: Image.Image, quarter_turns: int, flip: bool = False) -> Image.Image:
    turns = quarter_turns % 4
    if turns:
        im = im.transpose([None, Image.Transpose.ROTATE_270, Image.Transpose.ROTATE_180,
                           Image.Transpose.ROTATE_90][turns])
    if flip:
        im = ImageOps.mirror(im)
    return im


def crop(im: Image.Image, rect, size=None, quarter_turns: int = 0, flip: bool = False) -> Image.Image:
    """rect is (x0, y0, x1, y1) as fractions of the (rotated) image."""
    im = rotate(im, quarter_turns, flip)
    w, h = im.size
    x0, y0, x1, y1 = rect
    box = (round(x0 * w), round(y0 * h), max(round(x0 * w) + 1, round(x1 * w)), max(round(y0 * h) + 1, round(y1 * h)))
    out = im.crop(box)
    if size:
        out = resize(out, size=size)
    return out


def resize(im: Image.Image, scale: float | None = None, size=None, sharpen: bool = True) -> Image.Image:
    w, h = im.size
    if size:
        tw, th = int(size[0]), int(size[1])
    else:
        tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    out = im.resize((tw, th), Image.Resampling.LANCZOS)
    factor = tw / w
    if sharpen and factor > 1.05:
        out = out.filter(ImageFilter.UnsharpMask(radius=min(4, 0.8 * factor), percent=70, threshold=2))
    return out


# ------------------------------------------------------------ add background

GRADIENTS = {
    "Sunset": ["#FF5F6D", "#FFC371"], "Aurora": ["#7C5CFF", "#06B6D4", "#34D399"],
    "Candy": ["#F093FB", "#F5576C"], "Ocean": ["#2193B0", "#6DD5ED"], "Peach": ["#FFECD2", "#FCB69F"],
    "Mint": ["#43E97B", "#38F9D7"], "Grape": ["#8E2DE2", "#4A00E0"], "Sky": ["#A1C4FD", "#C2E9FB"],
    "Fire": ["#F83600", "#F9D423"], "Night": ["#0F2027", "#203A43", "#2C5364"],
}
SOLIDS = ["#FFFFFF", "#F2F2F5", "#F4D35E", "#A3D977", "#4CAF7A", "#3FA7A0", "#6CCFE0",
          "#3F6FE0", "#1F2A44", "#7A4FD8", "#111114"]
RATIOS = {"Auto": None, "1:1": (1, 1), "4:5": (4, 5), "9:16": (9, 16), "16:9": (16, 9)}


def hex_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def gradient(size, colors: list[str], angle: float = 135) -> Image.Image:
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rad = math.radians(angle)
    proj = xx * math.cos(rad) + yy * math.sin(rad)
    t = (proj - proj.min()) / max(1e-6, proj.max() - proj.min())
    stops = np.linspace(0, 1, len(colors))
    rgb = np.array([hex_rgb(c) for c in colors], dtype=np.float32)
    out = np.stack([np.interp(t, stops, rgb[:, ch]) for ch in range(3)], axis=2)
    return Image.fromarray(out.astype(np.uint8), "RGB")


def _rounded_mask(size, radius: float) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=max(0, radius), fill=255)
    return mask


def add_background(im: Image.Image, opts: dict) -> Image.Image:
    """opts: background {kind: gradient|solid|image|blur, ...}, padding, corners and
    shadow (per-mille of the photo's long side / 0-100), ratio (a RATIOS key)."""
    photo = im.convert("RGBA")
    pw, ph = photo.size
    unit = max(pw, ph) / 1000
    pad = opts.get("padding", 120) * unit
    cw, chh = pw + 2 * pad, ph + 2 * pad
    ratio = RATIOS.get(opts.get("ratio", "Auto"))
    if ratio:
        rw, rh = ratio
        if cw / chh > rw / rh:
            chh = cw * rh / rw
        else:
            cw = chh * rw / rh
    canvas_size = (max(1, round(cw)), max(1, round(chh)))

    bg = opts.get("background", {"kind": "gradient", "name": "Aurora"})
    kind = bg.get("kind")
    if kind == "solid":
        canvas = Image.new("RGB", canvas_size, hex_rgb(bg.get("color", "#FFFFFF")))
    elif kind == "image" and bg.get("path") and Path(bg["path"]).is_file():
        canvas = ImageOps.fit(ImageOps.exif_transpose(Image.open(bg["path"])).convert("RGB"), canvas_size)
    elif kind == "blur":
        canvas = ImageOps.fit(photo.convert("RGB"), canvas_size)
    else:
        canvas = gradient(canvas_size, GRADIENTS.get(bg.get("name"), GRADIENTS["Aurora"]), bg.get("angle", 135))
    blur = bg.get("blur", 40 if kind == "blur" else 0)
    if blur:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur * unit * 0.6))
    canvas = canvas.convert("RGBA")

    radius = opts.get("corners", 30) * unit
    x, y = round((canvas_size[0] - pw) / 2), round((canvas_size[1] - ph) / 2)
    shadow = opts.get("shadow", 30)
    if shadow:
        spread = shadow * unit * 0.6
        layer = Image.new("L", canvas_size, 0)
        layer.paste(_rounded_mask((pw, ph), radius), (x, y + round(spread * 0.35)))
        layer = layer.filter(ImageFilter.GaussianBlur(max(1, spread)))
        darkness = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        darkness.putalpha(layer.point(lambda v: v * min(0.85, 0.3 + shadow / 140)))
        canvas.alpha_composite(darkness)
    mask = _rounded_mask((pw, ph), radius)
    if photo.mode == "RGBA":
        mask = Image.fromarray(np.minimum(np.asarray(mask), np.asarray(photo.getchannel("A"))))
    canvas.paste(photo, (x, y), mask)
    return canvas


# ------------------------------------------------------- annotate and redact

PALETTE = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#0A84FF", "#7C5CFF", "#FFFFFF", "#111114"]


def _font(size: float, bold: bool = True):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, max(8, int(size)))
        except OSError:
            continue
    return ImageFont.load_default()


def _light(color) -> bool:
    r, g, b = color[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b > 170


def annotate(im: Image.Image, shapes: list[dict]) -> Image.Image:
    """shapes: {type, points (fractions), color, width (per-mille), text}. Types:
    arrow, rect, ellipse, line, pen, highlight, text, number, magnify."""
    out = im.convert("RGBA")
    W, H = out.size
    unit = max(W, H) / 1000
    number = 0
    for shape in shapes:
        pts = [(x * W, y * H) for x, y in shape.get("points", [])]
        if not pts:
            continue
        kind = shape.get("type")
        color = hex_rgb(shape.get("color", "#FF3B30")) + (255,)
        width = max(1, round(shape.get("width", 6) * unit))
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        a, b = pts[0], pts[-1]
        box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        if kind == "arrow":
            d.line([a, b], fill=color, width=width)
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            head = width * 4.2
            left = (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45))
            right = (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))
            d.polygon([b, left, right], fill=color)
        elif kind == "rect":
            d.rounded_rectangle(box, radius=width * 1.5, outline=color, width=width)
        elif kind == "ellipse":
            d.ellipse(box, outline=color, width=width)
        elif kind == "line":
            d.line([a, b], fill=color, width=width)
        elif kind in ("pen", "highlight"):
            if kind == "highlight":
                color = color[:3] + (110,)
                width *= 4
            if len(pts) == 1:
                pts = pts * 2
            d.line(pts, fill=color, width=width, joint="curve")
            r = width / 2
            for x, y in (pts[0], pts[-1]):
                d.ellipse((x - r, y - r, x + r, y + r), fill=color)
        elif kind == "text":
            text = shape.get("text") or "Text"
            font = _font(shape.get("size", 36) * unit)
            l, t, r_, bt = d.textbbox(a, text, font=font)
            pad = (bt - t) * 0.45
            d.rounded_rectangle((l - pad, t - pad, r_ + pad, bt + pad), radius=pad * 1.4, fill=color)
            d.text(a, text, font=font, fill=(17, 17, 20, 255) if _light(color) else (255, 255, 255, 255))
        elif kind == "number":
            number += 1
            r = 22 * unit
            d.ellipse((a[0] - r, a[1] - r, a[0] + r, a[1] + r), fill=color, outline=(255, 255, 255, 255),
                      width=max(1, round(2.5 * unit)))
            d.text(a, str(number), font=_font(r * 1.15), anchor="mm",
                   fill=(17, 17, 20, 255) if _light(color) else (255, 255, 255, 255))
        elif kind == "magnify":
            r = max(10.0, math.dist(a, b))
            region = out.crop((round(a[0] - r / 2), round(a[1] - r / 2), round(a[0] + r / 2), round(a[1] + r / 2)))
            zoom = region.resize((round(2 * r), round(2 * r)), Image.Resampling.LANCZOS)
            mask = Image.new("L", zoom.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, zoom.size[0] - 1, zoom.size[1] - 1), fill=255)
            layer.paste(zoom, (round(a[0] - r), round(a[1] - r)), mask)
            d.ellipse((a[0] - r, a[1] - r, a[0] + r, a[1] + r), outline=(255, 255, 255, 255), width=max(2, width // 2))
        out.alpha_composite(layer)
    return out


def redact(im: Image.Image, areas: list[dict]) -> Image.Image:
    """areas: {rect (fractions), style: blur|pixelate|solid, color}."""
    out = im.convert("RGBA")
    W, H = out.size
    for area in areas:
        x0, y0, x1, y1 = area["rect"]
        box = (max(0, round(x0 * W)), max(0, round(y0 * H)), min(W, round(x1 * W)), min(H, round(y1 * H)))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        region = out.crop(box)
        style = area.get("style", "blur")
        if style == "solid":
            region = Image.new("RGBA", region.size, hex_rgb(area.get("color", "#111114")) + (255,))
        elif style == "pixelate":
            cells = max(1, max(region.size) // 14)
            small = region.resize((max(1, region.size[0] // cells), max(1, region.size[1] // cells)),
                                  Image.Resampling.BILINEAR)
            region = small.resize(region.size, Image.Resampling.NEAREST)
        else:
            region = region.filter(ImageFilter.GaussianBlur(max(6, max(region.size) / 6)))
        out.paste(region, box[:2])
    return out


# ------------------------------------------------------------------ collage

COLLAGE_SIZES = {"Square": (2160, 2160), "Portrait 4:5": (2160, 2700), "Story 9:16": (2160, 3840),
                 "Landscape 16:9": (3840, 2160)}


def _cells(n: int, layout: str, w: float, h: float, gap: float):
    def grid(cols, rows, x0, y0, cw, ch):
        tw, th = (cw - gap * (cols - 1)) / cols, (ch - gap * (rows - 1)) / rows
        return [(x0 + c * (tw + gap), y0 + r * (th + gap), tw, th) for r in range(rows) for c in range(cols)]

    if layout == "Row":
        return grid(n, 1, gap, gap, w - 2 * gap, h - 2 * gap)[:n]
    if layout == "Column":
        return grid(1, n, gap, gap, w - 2 * gap, h - 2 * gap)[:n]
    if layout == "Featured" and n > 1:
        main_w = (w - 3 * gap) * 0.62
        rest = grid(1, n - 1, gap * 2 + main_w, gap, w - 3 * gap - main_w, h - 2 * gap)
        return [(gap, gap, main_w, h - 2 * gap)] + rest
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return grid(cols, rows, gap, gap, w - 2 * gap, h - 2 * gap)[:n]


def collage(images: list[Image.Image], opts: dict) -> Image.Image:
    w, h = opts.get("size") or COLLAGE_SIZES["Square"]
    unit = max(w, h) / 1000
    gap = opts.get("spacing", 12) * unit
    radius = opts.get("corners", 16) * unit
    canvas = Image.new("RGB", (int(w), int(h)), hex_rgb(opts.get("background", "#FFFFFF")))
    for im, (x, y, cw, ch) in zip(images, _cells(len(images), opts.get("layout", "Grid"), w, h, gap)):
        size = (max(1, round(cw)), max(1, round(ch)))
        tile = ImageOps.fit(im.convert("RGB"), size, Image.Resampling.LANCZOS)
        canvas.paste(tile, (round(x), round(y)), _rounded_mask(size, radius))
    return canvas
