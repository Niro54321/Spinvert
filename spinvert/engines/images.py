"""Images with Pillow. HEIC through pillow-heif, AVIF through Pillow itself."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from spinvert.util import ConversionError, ext_of, natural_key, normal_ext

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # HEIC input is optional
    pillow_heif = None

Image.MAX_IMAGE_PIXELS = 400_000_000


def _open_svg(path: Path) -> Image.Image:
    """Draw an SVG with Qt, at least 2048 px on its long side."""
    from spinvert.mainthread import run_in_main

    def render():
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return None
        size = renderer.defaultSize()
        w, h = max(1, size.width()), max(1, size.height())
        scale = min(max(1.0, 2048 / max(w, h)), 8192 / max(w, h))
        img = QImage(round(w * scale), round(h * scale), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()),
                                "raw", "RGBA", img.bytesPerLine(), 1).copy()

    im = run_in_main(render)
    if im is None:
        raise ConversionError("Can't read this SVG.")
    return im


def _open(path: Path) -> Image.Image:
    if ext_of(path) == "svg":
        return _open_svg(path)
    try:
        im = Image.open(path)
        im.load()
        return im
    except Exception as e:
        raise ConversionError(f"Can't read this image ({type(e).__name__}).") from e


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def _to_8bit(im: Image.Image) -> Image.Image:
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        return im.point(lambda v: v * (1 / 256)).convert("L")
    if im.mode == "F":
        return im.convert("L")
    return im


def _flatten(im: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """RGB with transparent areas painted white (for JPG, BMP and PDF)."""
    im = _to_8bit(im)
    if _has_alpha(im):
        rgba = im.convert("RGBA")
        base = Image.new("RGB", rgba.size, background)
        base.paste(rgba, mask=rgba.getchannel("A"))
        return base
    return im if im.mode == "RGB" else im.convert("RGB")


def _rgb_or_rgba(im: Image.Image) -> Image.Image:
    im = _to_8bit(im)
    if _has_alpha(im):
        return im if im.mode == "RGBA" else im.convert("RGBA")
    return im if im.mode in ("RGB", "L") else im.convert("RGB")


def _upright(im: Image.Image) -> Image.Image:
    im.seek(0)
    try:
        return ImageOps.exif_transpose(im)
    except Exception:
        return im.copy()


def _exif_bytes(im: Image.Image) -> bytes | None:
    try:
        exif = im.getexif()
        return exif.tobytes() if len(exif) else None
    except Exception:
        return None


def _pdf_resolution(sizes) -> float:
    """Pick a DPI so the widest image fits an A4 page width."""
    widest = max(w for w, _ in sizes)
    return max(72.0, widest / 8.27)


def save_still(im: Image.Image, out: Path, ext: str, quality: int, keep_meta: bool = True) -> None:
    icc = im.info.get("icc_profile") if keep_meta else None
    exif = _exif_bytes(im) if keep_meta else None
    extra = {}
    if icc:
        extra["icc_profile"] = icc
    if ext == "jpg":
        if exif:
            extra["exif"] = exif
        _flatten(im).save(out, "JPEG", quality=quality, optimize=True, progressive=True, **extra)
    elif ext == "png":
        _rgb_or_rgba(im).save(out, "PNG", **extra)
    elif ext == "webp":
        if exif:
            extra["exif"] = exif
        _rgb_or_rgba(im).save(out, "WEBP", quality=quality, method=4, **extra)
    elif ext == "tiff":
        src = im if im.mode in ("RGB", "RGBA", "L", "CMYK", "P") else _rgb_or_rgba(im)
        src.save(out, "TIFF", compression="tiff_lzw", **extra)
    elif ext == "bmp":
        _flatten(im).save(out, "BMP")
    elif ext == "gif":
        _rgb_or_rgba(im).save(out, "GIF")
    elif ext == "pdf":
        flat = _flatten(im)
        flat.save(out, "PDF", resolution=_pdf_resolution([flat.size]))
    elif ext == "heic" and pillow_heif:
        _rgb_or_rgba(im).save(out, "HEIF", quality=quality)
    elif ext == "avif":
        _rgb_or_rgba(im).save(out, "AVIF", quality=quality)
    else:
        raise ConversionError(f"Can't write {ext.upper()} images.")


def _save_animated(im: Image.Image, out: Path, ext: str, quality: int) -> None:
    frames, durations = [], []
    for frame in ImageSequence.Iterator(im):
        frames.append(frame.convert("RGBA"))
        durations.append(frame.info.get("duration", im.info.get("duration", 100)) or 100)
    options = dict(save_all=True, append_images=frames[1:], duration=durations,
                   loop=im.info.get("loop", 0))
    if ext == "gif":
        frames[0].save(out, "GIF", disposal=2, **options)
    else:
        frames[0].save(out, "WEBP", quality=quality, **options)


def image_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        im = _open(src)
        out = ctx.output(src.stem, ext)
        if ext in ("gif", "webp") and getattr(im, "n_frames", 1) > 1:
            _save_animated(im, out, ext, ctx.settings.image_quality)
        else:
            save_still(_upright(im), out, ext, ctx.settings.image_quality)
        return [out]
    return run


def _encoded_size(im: Image.Image, ext: str, quality: int) -> tuple[bytes, int]:
    import io

    buf = io.BytesIO()
    if ext == "png":
        small = _rgb_or_rgba(im)
        method = Image.Quantize.FASTOCTREE if small.mode == "RGBA" else Image.Quantize.MEDIANCUT
        small.quantize(colors=max(16, int(quality * 2.56)), method=method).save(buf, "PNG", optimize=True)
    elif ext == "webp":
        _rgb_or_rgba(im).save(buf, "WEBP", quality=quality, method=4)
    else:
        _flatten(im).save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue(), buf.tell()


def compress(ctx):
    """By quality, to a target size, or by a percentage; optionally smaller in pixels too."""
    src = ctx.inputs[0]
    upright = _upright(_open(src))
    p = ctx.params
    kind = normal_ext(ext_of(src))
    if kind in ("jpg", "webp"):
        target = kind
    elif kind == "png" or _has_alpha(upright):
        target = "png"
    else:
        target = "jpg"
    if p.get("max_side"):
        upright.thumbnail((int(p["max_side"]), int(p["max_side"])), Image.Resampling.LANCZOS)
    size = src.stat().st_size
    goal = None
    if p.get("mode") == "size" and p.get("target_mb"):
        goal = int(float(p["target_mb"]) * 1_000_000)
    elif p.get("mode") == "percent":
        goal = int(size * (1 - float(p.get("percent", 50)) / 100))
    if goal:
        im = upright
        for _ in range(8):  # lower the quality first, then the pixel size
            lo, hi, best = 20, 95, None
            while lo <= hi:
                mid = (lo + hi) // 2
                data, length = _encoded_size(im, target, mid)
                if length <= goal:
                    best, lo = data, mid + 1
                else:
                    hi = mid - 1
            if best:
                break
            im = im.resize((max(1, int(im.width * 0.8)), max(1, int(im.height * 0.8))), Image.Resampling.LANCZOS)
        if not best:
            raise ConversionError("Couldn't reach that size, even much smaller.")
    else:
        best, _ = _encoded_size(upright, target, int(p.get("quality", 72)))
    out = ctx.output(f"{src.stem} (compressed)", target)
    out.write_bytes(best)
    if out.stat().st_size >= size and not goal:
        raise ConversionError("Already compact: a smaller copy wasn't possible.")
    return [out]


def combine_to_pdf(ctx):
    order = ctx.params.get("order")
    files = [ctx.inputs[i] for i in order] if order else sorted(ctx.inputs, key=natural_key)
    pages = []
    for i, path in enumerate(files):
        ctx.check()
        pages.append(_flatten(_upright(_open(path))))
        ctx.progress(0.8 * (i + 1) / len(files))
    stem = files[0].stem if len(files) == 1 else f"{files[0].stem} and {len(files) - 1} more"
    out = ctx.output(stem, "pdf")
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:],
                  resolution=_pdf_resolution([p.size for p in pages]))
    return [out]


# Photo tools. The settings come from the editors (spinvert.editors.photo);
# without them (a quick run, or the test) each tool uses a sensible default.

DEFAULT_LAYERS = [
    {"id": "a1", "type": "arrow", "points": [[0.15, 0.2], [0.42, 0.45]], "color": "#FF3B30", "width": 8},
    {"id": "t1", "type": "text", "points": [[0.45, 0.1]], "color": "#FFFFFF", "text": "Look here • انظر هنا",
     "size": 50, "bold": True, "bg": {"on": True, "color": "#7C5CFF", "opacity": 90, "padding": 35, "radius": 35},
     "shadow": {"on": True, "color": "#000000", "opacity": 50, "blur": 4, "distance": 3}},
    {"id": "n1", "type": "number", "points": [[0.75, 0.7]], "color": "#0A84FF", "size": 26, "number": 1},
]


def _output_ext(src: Path, wants_alpha: bool = False) -> str:
    ext = normal_ext(ext_of(src))
    if ext == "svg" or (wants_alpha and ext in ("jpg", "bmp")):
        return "png"
    return ext if ext in ("jpg", "png", "webp", "tiff", "bmp", "gif", "heic", "avif") else "png"


def photo_tool(kind: str):
    from spinvert.engines import imaging

    def run(ctx):
        src = ctx.inputs[0]
        im = _upright(_open(src))
        p = ctx.params
        alpha = False
        if kind == "edit":
            result, suffix = imaging.adjust(im, p.get("adjust", imaging.PRESETS["Vivid"])), "edited"
        elif kind == "crop":
            rect = p.get("rect") or (0.1, 0.1, 0.9, 0.9)
            result, suffix = imaging.crop(im, rect, p.get("size"), p.get("turns", 0), p.get("flip", False)), "cropped"
        elif kind == "resize":
            size = p.get("size")
            scale = None if size else float(p.get("scale", 2.0))
            result = imaging.resize(im, scale=scale, size=size, sharpen=p.get("sharpen", True))
            suffix = f"{result.width}x{result.height}"
        elif kind == "background":
            result, suffix, alpha = imaging.add_background(im, p), "background", True
        elif kind == "annotate":
            from spinvert import layers
            from spinvert.mainthread import run_in_main

            drawn = p.get("layers") or DEFAULT_LAYERS
            result = layers.to_pil(run_in_main(lambda: layers.render(layers.from_pil(im), drawn)))
            suffix = "annotated"
        elif kind == "redact":
            areas = p.get("areas") or [{"rect": (0.3, 0.3, 0.7, 0.7), "style": "blur"}]
            result, suffix = imaging.redact(im, areas), "redacted"
        else:
            raise ConversionError(f"Unknown photo tool {kind}.")
        ext = p.get("format") or _output_ext(src, alpha)
        out = ctx.output(f"{src.stem} ({suffix})", ext)
        save_still(result, out, ext, ctx.settings.image_quality)
        return [out]
    return run


def background_group(ctx):
    """Several pictures side by side on one background."""
    from spinvert.engines import imaging

    order = ctx.params.get("order")
    files = [ctx.inputs[i] for i in order] if order else sorted(ctx.inputs, key=natural_key)
    pictures = []
    for i, path in enumerate(files):
        ctx.check()
        pictures.append(_upright(_open(path)))
        ctx.progress(0.5 * (i + 1) / len(files))
    result = imaging.add_background(pictures, ctx.params)
    ext = ctx.params.get("format", "png")
    out = ctx.output(f"{files[0].stem} and {len(files) - 1} more (background)", ext)
    save_still(result, out, ext, ctx.settings.image_quality)
    return [out]


def make_collage(ctx):
    from spinvert.engines import imaging

    order = ctx.params.get("order")
    files = [ctx.inputs[i] for i in order] if order else sorted(ctx.inputs, key=natural_key)
    pictures = []
    for i, path in enumerate(files):
        ctx.check()
        pictures.append(_upright(_open(path)))
        ctx.progress(0.6 * (i + 1) / len(files))
    result = imaging.collage(pictures, ctx.params)
    ext = ctx.params.get("format", "jpg")
    out = ctx.output("Collage", ext)
    save_still(result, out, ext, ctx.settings.image_quality)
    return [out]
