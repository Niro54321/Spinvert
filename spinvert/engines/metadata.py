"""Read, change or remove the information stored inside a file: photo EXIF
(camera, date, location), audio and video tags, PDF document properties."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from PIL import ExifTags, Image

from spinvert.util import ConversionError, ext_of, normal_ext

# What the editor lets you type, per kind of file: (key, label).
EDITABLE = {
    "image": [("title", "Title"), ("artist", "Artist"), ("copyright", "Copyright"),
              ("date", "Date taken (YYYY:MM:DD HH:MM:SS)")],
    "media": [("title", "Title"), ("artist", "Artist"), ("album", "Album"), ("date", "Year / date"),
              ("genre", "Genre"), ("comment", "Comment")],
    "pdf": [("title", "Title"), ("author", "Author"), ("subject", "Subject"), ("keywords", "Keywords")],
}
EXIF_KEYS = {"title": 0x010E, "artist": 0x013B, "copyright": 0x8298}
EXIF_IFD, GPS_IFD, DATE_ORIGINAL = 0x8769, 0x8825, 0x9003
PDF_KEYS = {"title": "/Title", "author": "/Author", "subject": "/Subject", "keywords": "/Keywords"}
IMAGE_EXTS = {"jpg", "png", "webp", "tiff", "heic", "avif"}


def kind_of(path: Path) -> str:
    from spinvert.catalog import category

    cat = category(path)
    if cat == "image" and normal_ext(ext_of(path)) in IMAGE_EXTS:
        return "image"
    if cat in ("audio", "video"):
        return "media"
    if cat == "pdf":
        return "pdf"
    return "file"


def _text(value) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace").strip("\x00")
    text = str(value)
    return text if len(text) < 300 else text[:300] + "…"


def read(path: Path, ffprobe=None) -> dict:
    """{kind, fields: [(group, label, value)], values: {editable key: value}, gps: bool}"""
    kind = kind_of(path)
    stat = path.stat()
    fields = [("File", "Name", path.name), ("File", "Size", f"{stat.st_size / 1_000_000:.2f} MB"),
              ("File", "Modified", dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"))]
    values, gps = {}, False
    if kind == "image":
        with Image.open(path) as im:
            fields.append(("Image", "Size", f"{im.width} × {im.height}"))
            exif = im.getexif()
            for tag, value in exif.items():
                fields.append(("Camera & file", ExifTags.TAGS.get(tag, hex(tag)), _text(value)))
            for tag, value in exif.get_ifd(EXIF_IFD).items():
                fields.append(("Photo", ExifTags.TAGS.get(tag, hex(tag)), _text(value)))
            location = exif.get_ifd(GPS_IFD)
            gps = bool(location)
            for tag, value in location.items():
                fields.append(("Location", ExifTags.GPSTAGS.get(tag, hex(tag)), _text(value)))
            for key, tag in EXIF_KEYS.items():
                values[key] = _text(exif.get(tag, ""))
            values["date"] = _text(exif.get_ifd(EXIF_IFD).get(DATE_ORIGINAL, ""))
    elif kind == "media" and ffprobe:
        import subprocess

        from spinvert.util import CREATE_NO_WINDOW

        out = subprocess.run([str(ffprobe), "-v", "error", "-print_format", "json", "-show_format",
                              "-show_streams", "-show_chapters", str(path)], capture_output=True,
                             creationflags=CREATE_NO_WINDOW).stdout
        data = json.loads(out or b"{}")
        fmt = data.get("format", {})
        fields.append(("File", "Format", fmt.get("format_long_name", "")))
        fields.append(("File", "Duration", f"{float(fmt.get('duration') or 0):.2f} s"))
        for key, value in (fmt.get("tags") or {}).items():
            fields.append(("Tags", key, _text(value)))
            if key.lower() in dict(EDITABLE["media"]):
                values[key.lower()] = _text(value)
        for s in data.get("streams", []):
            group = f"Track {s.get('index', 0) + 1} ({s.get('codec_type', '?')})"
            fields.append((group, "Codec", s.get("codec_long_name", s.get("codec_name", ""))))
            if s.get("width"):
                fields.append((group, "Size", f"{s['width']} × {s['height']}"))
            if s.get("sample_rate"):
                fields.append((group, "Sample rate", f"{s['sample_rate']} Hz, {s.get('channels', '?')} ch"))
            for key, value in (s.get("tags") or {}).items():
                fields.append((group, key, _text(value)))
        for n, ch in enumerate(data.get("chapters", []), 1):
            fields.append((f"Chapter {n}", "Title", (ch.get("tags") or {}).get("title", "")))
    elif kind == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        fields.append(("Document", "Pages", str(len(reader.pages))))
        for key, value in (reader.metadata or {}).items():
            fields.append(("Document", key.lstrip("/"), _text(value)))
        for key, name in PDF_KEYS.items():
            values[key] = _text((reader.metadata or {}).get(name, ""))
    return {"kind": kind, "fields": fields, "values": values, "gps": gps}


def write(ctx):
    """params: set {key: value}, remove_all, remove_gps."""
    src = ctx.inputs[0]
    p = ctx.params
    changes = {k: v for k, v in (p.get("set") or {}).items() if v is not None}
    remove_all, remove_gps = bool(p.get("remove_all")), bool(p.get("remove_gps"))
    if not (changes or remove_all or remove_gps):
        remove_all = True  # the quick action from the wheel without a dialog
    kind = kind_of(src)
    ext = normal_ext(ext_of(src))
    suffix = "clean" if remove_all and not changes else "metadata"
    if kind == "image":
        out = ctx.output(f"{src.stem} ({suffix})", ext)
        with Image.open(src) as im:
            exif = Image.Exif() if remove_all else im.getexif()
            if remove_all:
                orientation = im.getexif().get(0x0112)
                if orientation:
                    exif[0x0112] = orientation  # keep the picture the right way up
            if remove_gps and GPS_IFD in exif:
                del exif[GPS_IFD]
            for key, tag in EXIF_KEYS.items():
                if key in changes:
                    exif[tag] = changes[key]
            if "date" in changes:
                exif.get_ifd(EXIF_IFD)[DATE_ORIGINAL] = changes["date"]
            options = {"exif": exif.tobytes()}
            if im.info.get("icc_profile"):
                options["icc_profile"] = im.info["icc_profile"]
            if ext == "jpg":
                im.save(out, "JPEG", quality="keep", **options)  # same pixels, no re-compression
            elif ext in ("webp", "heic", "avif"):
                im.save(out, quality=95, **options)
            else:
                im.save(out, **options)
        return [out]
    if kind == "media":
        from spinvert.engines.media import ffmpeg, probe

        info_ = probe(ctx, src)
        out = ctx.output(f"{src.stem} ({suffix})", ext_of(src))
        args = ["-map", "0", "-c", "copy"]
        if remove_all:
            args += ["-map_metadata", "-1", "-map_chapters", "-1"]
        for key, value in changes.items():
            args += ["-metadata", f"{key}={value}"]
        ffmpeg(ctx, src, out, args, info_["duration"])
        return [out]
    if kind == "pdf":
        from pypdf import PdfWriter

        from spinvert.engines.pdfs import _reader

        writer = PdfWriter(clone_from=_reader(src))
        if remove_all:
            writer.metadata = None
        info = {PDF_KEYS[k]: v for k, v in changes.items() if k in PDF_KEYS}
        if info:
            writer.add_metadata(info)
        out = ctx.output(f"{src.stem} ({suffix})", "pdf")
        with open(out, "wb") as fh:
            writer.write(fh)
        return [out]
    raise ConversionError("This kind of file has no metadata Spinvert can change.")
