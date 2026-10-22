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


def _open(path: Path) -> Image.Image:
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


def compress(ctx):
    src = ctx.inputs[0]
    im = _open(src)
    kind = normal_ext(ext_of(src))
    upright = _upright(im)
    if kind in ("jpg", "webp"):
        target = kind
    elif kind == "png" or _has_alpha(upright):
        target = "png"
    else:
        target = "jpg"
    out = ctx.output(f"{src.stem} (compressed)", target)
    if target == "png":
        small = _rgb_or_rgba(upright)
        method = Image.Quantize.FASTOCTREE if small.mode == "RGBA" else Image.Quantize.MEDIANCUT
        small.quantize(colors=256, method=method).save(out, "PNG", optimize=True)
    else:
        save_still(upright, out, target, 72)
    if out.stat().st_size >= src.stat().st_size:
        raise ConversionError("Already compact: a smaller copy wasn't possible.")
    return [out]


def strip_metadata(ctx):
    src = ctx.inputs[0]
    im = _open(src)
    kind = normal_ext(ext_of(src))
    out = ctx.output(f"{src.stem} (clean)", kind)
    if kind in ("gif", "webp") and getattr(im, "n_frames", 1) > 1:
        _save_animated(im, out, kind, 95)
    else:
        clean = _upright(im)
        clean.info = {}
        save_still(clean, out, kind, 95, keep_meta=False)
    return [out]


def combine_to_pdf(ctx):
    files = sorted(ctx.inputs, key=natural_key)
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
