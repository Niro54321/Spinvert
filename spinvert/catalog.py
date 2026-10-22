"""Every operation Spinvert offers, and which ones fit a selection of files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from spinvert.engines import (archives, documents, images, media, metadata, ocr, pages, pdfs, sheets,
                              slides, subtitles)
from spinvert.util import ext_of, normal_ext

EXTENSIONS = {
    "image": "jpg jpeg png webp tif tiff bmp gif heic heif avif svg",
    "audio": "mp3 m4a wav flac ogg oga opus aac wma aiff aif",
    "video": "mp4 mov mkv webm avi wmv m4v flv mpg mpeg 3gp ts",
    "pdf": "pdf",
    "document": "docx md markdown html htm epub odt rtf rtfd txt textclipping",
    "pages": "pages",
    "slides": "pptx ppt",
    "sheet": "xlsx xls ods csv tsv",
    "subtitle": "srt vtt",
    "archive": "zip tar tar.gz tgz gz rar",
}
CATEGORY_OF = {ext: cat for cat, exts in EXTENSIONS.items() for ext in exts.split()}
ANY = "*"
BUNDLES = {"rtfd", "pages"}  # macOS documents that can arrive as folders


def category(path: Path) -> str | None:
    if path.is_dir() and ext_of(path) not in BUNDLES:
        return "folder"
    return CATEGORY_OF.get(ext_of(path))


@dataclass(frozen=True)
class Op:
    key: str                      # same key across categories means "same choice"
    label: str
    wheel: str                    # "convert" or "tools"
    categories: frozenset
    func: Callable
    combine: bool = False         # one job for all the files instead of one per file
    min_items: int = 1
    max_items: int | None = None
    target: str | None = None     # skip files that are already in this format
    needs: tuple = ()             # engines: ffmpeg, pandoc, word, powerpoint, excel
    in_exts: frozenset | None = None
    prepare: str | None = None    # "module:function": an editor asked before the job
    icon: str = ""                # a Segoe Fluent Icons glyph, shown on the tools wheel


@dataclass
class Choice:
    key: str
    label: str
    wheel: str
    plan: list = field(default_factory=list)   # [(Op, [paths]), ...]
    skipped: int = 0
    icon: str = ""
    ask: str | None = None        # "module:function" asked once before the plan runs
    alternative: Op | None = None  # what `ask` can switch to (e.g. one PDF for all images)


OPS: list[Op] = []


def _add(key, label, wheel, cats, func, **kw):
    OPS.append(Op(key, label, wheel, frozenset(cats.split()), func, **kw))


# Convert wheel. The order here is the order around the wheel.

for ext, label in [("jpg", "JPG"), ("png", "PNG"), ("webp", "WebP"), ("heic", "HEIC"),
                   ("tiff", "TIFF"), ("avif", "AVIF"), ("bmp", "BMP"), ("gif", "GIF"), ("pdf", "PDF")]:
    _add(ext, label, "convert", "image", images.image_to(ext), target=ext)

for ext, label in [("mp3", "MP3"), ("m4a", "M4A"), ("wav", "WAV"), ("flac", "FLAC"),
                   ("ogg", "OGG"), ("opus", "Opus"), ("aiff", "AIFF"), ("wma", "WMA")]:
    _add(ext, label, "convert", "audio", media.audio_to(ext), target=ext, needs=("ffmpeg",))

for ext, label in [("mp4", "MP4"), ("mov", "MOV"), ("mkv", "MKV"), ("webm", "WebM"),
                   ("avi", "AVI"), ("wmv", "WMV")]:
    _add(ext, label, "convert", "video", media.video_to(ext), target=ext, needs=("ffmpeg",))
_add("gif", "GIF", "convert", "video", media.video_to_gif, needs=("ffmpeg",))
_add("mp3", "MP3", "convert", "video", media.audio_to("mp3"), needs=("ffmpeg",))

_add("docx", "DOCX", "convert", "pdf", pdfs.pdf_to("docx"), needs=("pandoc",))
_add("pptx", "PPTX", "convert", "pdf", pdfs.pdf_to_pptx)
_add("xlsx", "XLSX", "convert", "pdf", pdfs.pdf_to_xlsx)
_add("jpg", "JPG", "convert", "pdf", pdfs.pdf_to_images("jpg"))
_add("png", "PNG", "convert", "pdf", pdfs.pdf_to_images("png"))
_add("epub", "EPUB", "convert", "pdf", pdfs.pdf_to("epub"), needs=("pandoc",))
_add("txt", "TXT", "convert", "pdf", pdfs.pdf_to_text)
_add("md", "Markdown", "convert", "pdf", pdfs.pdf_to("md"), needs=("pandoc",))

for ext, label in [("docx", "DOCX"), ("pdf", "PDF"), ("md", "Markdown"), ("html", "HTML"),
                   ("epub", "EPUB"), ("txt", "TXT")]:
    _add(ext, label, "convert", "document", documents.doc_to(ext), target=ext, needs=("pandoc",))

_add("pdf", "PDF", "convert", "pages", pages.via_pdf(None))
_add("docx", "DOCX", "convert", "pages", pages.via_pdf(pdfs.pdf_to("docx")), needs=("pandoc",))
_add("md", "Markdown", "convert", "pages", pages.via_pdf(pdfs.pdf_to("md")), needs=("pandoc",))
_add("epub", "EPUB", "convert", "pages", pages.via_pdf(pdfs.pdf_to("epub")), needs=("pandoc",))
_add("txt", "TXT", "convert", "pages", pages.via_pdf(pdfs.pdf_to_text))
_add("jpg", "JPG", "convert", "pages", pages.via_pdf(pdfs.pdf_to_images("jpg")))
_add("png", "PNG", "convert", "pages", pages.via_pdf(pdfs.pdf_to_images("png")))

_add("pdf", "PDF", "convert", "slides", slides.slides_to_pdf, needs=("powerpoint",))
_add("png", "PNG", "convert", "slides", slides.slides_to_images("png"), needs=("powerpoint",))
_add("jpg", "JPG", "convert", "slides", slides.slides_to_images("jpg"), needs=("powerpoint",))
_add("txt", "TXT", "convert", "slides", slides.slides_to_text("txt"), in_exts=frozenset({"pptx"}))
_add("md", "Markdown", "convert", "slides", slides.slides_to_text("md"), in_exts=frozenset({"pptx"}))

_add("xlsx", "XLSX", "convert", "sheet", sheets.to_xlsx, target="xlsx")
_add("ods", "ODS", "convert", "sheet", sheets.to_ods, target="ods")
_add("csv", "CSV", "convert", "sheet", sheets.to_delimited("csv"), target="csv")
_add("tsv", "TSV", "convert", "sheet", sheets.to_delimited("tsv"), target="tsv")
_add("pdf", "PDF", "convert", "sheet", sheets.to_pdf, needs=("excel",))

for ext, label in [("srt", "SRT"), ("vtt", "VTT"), ("txt", "TXT")]:
    _add(ext, label, "convert", "subtitle", subtitles.subs_to(ext), target=ext)

_add("extract", "Extract", "convert", "archive", archives.extract)
for kind, label in [("zip", "ZIP"), ("tar", "TAR"), ("tar.gz", "GZIP")]:
    _add(kind, label, "convert", "archive", archives.repack(kind), target=kind)
    _add(kind, label, "convert", "folder", archives.folder_to(kind))

# Tools wheel. Each tool has an icon from Segoe Fluent Icons (built into
# Windows 11) and, when it needs settings, an editor (`prepare`). The order
# here is the order around the wheel for each kind of file.

ICON = {k: chr(v) for k, v in {
    "compress": 0xE73F, "metadata": 0xE8EC, "edit": 0xE9E9, "annotate": 0xE70F, "background": 0xE91B,
    "crop": 0xE7A8, "resize": 0xE740, "redact": 0xED1A, "text": 0xE8D2, "collage": 0xF0E2,
    "pdf": 0xEA90, "mute": 0xE74F, "trim": 0xE8C6, "speed": 0xEC4A, "frames": 0xE722,
    "split": 0xE89F, "join": 0xE71B, "normalize": 0xE995, "visualize": 0xE9D9, "channels": 0xE7F5,
    "bleep": 0xE7BA, "organize": 0xE8A9, "merge": 0xE8C8, "password": 0xE72E, "zip": 0xF012,
}.items()}
FF = ("ffmpeg",)
PHOTO = "spinvert.editors.photo:"
AV = "spinvert.editors.av:"
FILES = "spinvert.editors.files:"
STILL = frozenset(EXTENSIONS["image"].split()) - {"gif"}


def _tool(key, label, cats, func, **kw):
    _add(key, label, "tools", cats, func, icon=ICON.get(key, ""), **kw)


_tool("compress", "Compress", "image", images.compress, prepare=FILES + "ask_compress")
_tool("compress", "Compress", "video", media.compress_video, needs=FF, prepare=FILES + "ask_compress")
_tool("compress", "Compress", "audio", media.compress_audio, needs=FF, prepare=FILES + "ask_compress")
_tool("compress", "Compress", "pdf", pdfs.compress)
_tool("metadata", "Metadata", "image video audio pdf", metadata.write, prepare=FILES + "edit_metadata",
      in_exts=frozenset(EXTENSIONS["image"].split() + EXTENSIONS["audio"].split()
                        + EXTENSIONS["video"].split() + ["pdf"]) - {"svg", "bmp", "gif"})
_tool("edit", "Edit", "image", images.photo_tool("edit"), prepare=PHOTO + "edit_photo", in_exts=STILL)
_tool("annotate", "Annotate", "image", images.photo_tool("annotate"), max_items=1,
      prepare=PHOTO + "annotate", in_exts=STILL)
_tool("background", "Add BG", "image", images.photo_tool("background"), prepare=PHOTO + "add_background",
      in_exts=STILL)
_tool("crop", "Crop", "image", images.photo_tool("crop"), prepare=PHOTO + "crop_photo", in_exts=STILL)
_tool("resize", "Resize", "image", images.photo_tool("resize"), prepare=PHOTO + "resize_photo",
      in_exts=STILL)
_tool("redact", "Redact", "image", images.photo_tool("redact"), max_items=1, prepare=PHOTO + "redact",
      in_exts=STILL)
_tool("text", "Text", "image pdf", ocr.extract_text, in_exts=STILL | {"pdf"})
_tool("collage", "Collage", "image", images.make_collage, combine=True, min_items=2,
      prepare=PHOTO + "make_collage")
_tool("to-pdf", "To PDF", "image", images.combine_to_pdf, combine=True, min_items=2,
      prepare=FILES + "order_files")

_tool("mute", "Mute", "video", media.remove_audio, needs=FF)
_tool("normalize", "Normalize", "audio", media.normalize_audio, needs=FF, prepare=AV + "normalize")
_tool("visualize", "Visualize", "audio", media.visualize, needs=FF, prepare=AV + "visualizer")
_tool("trim", "Trim", "video audio", media.trim, needs=FF, max_items=1, prepare=AV + "trim")
_tool("crop", "Crop", "video", media.crop_video, needs=FF, prepare=AV + "crop_video")
_tool("channels", "Channels", "audio", media.channels, needs=FF, prepare=AV + "channels")
_tool("bleep", "Bleep", "audio", media.bleep, needs=FF, max_items=1, prepare=AV + "bleep")
_tool("speed", "Speed", "video audio", media.change_speed, needs=FF, prepare=AV + "speed")
_tool("frames", "Frames", "video", media.save_frames, needs=FF, max_items=1, prepare=AV + "frames")
_tool("split", "Split", "video audio", media.split_media, needs=FF, max_items=1, prepare=AV + "split")
_tool("split", "Split", "pdf", pdfs.split, prepare=FILES + "split_pdf")
_tool("redact", "Redact", "video", media.redact_video, needs=FF, max_items=1, prepare=AV + "redact_video")
for kind in ("video", "audio"):  # all videos, or all audio; not a mix
    _tool("join", "Join", kind, media.join_media, needs=FF, combine=True, min_items=2,
          prepare=FILES + "order_files")

_tool("organize", "Organize", "pdf", pdfs.organize, max_items=1, prepare=FILES + "organize_pdf")
_tool("password", "Password", "pdf", pdfs.password, prepare=FILES + "pdf_password")
_tool("merge", "Merge", "pdf", pdfs.merge, combine=True, min_items=2, prepare=FILES + "order_files")
_tool("zip", "ZIP", ANY, archives.zip_all, combine=True)

IMAGES_TO_ONE_PDF = next(op for op in OPS if op.key == "to-pdf")


def detect_engines(settings) -> dict:
    from spinvert.engines import office
    from spinvert.util import find_ffmpeg

    return {
        "ffmpeg": find_ffmpeg(settings.ffmpeg_path) is not None,
        "pandoc": documents.pandoc_path() is not None,
        "word": office.available("word"),
        "powerpoint": office.available("powerpoint"),
        "excel": office.available("excel"),
    }


def _fits(op: Op, path: Path, cat: str | None) -> bool:
    if ANY not in op.categories and cat not in op.categories:
        return False
    return op.in_exts is None or ext_of(path) in op.in_exts


def choices_for(items: list[Path], wheel: str, engines: dict) -> list[Choice]:
    """The choices to show on a wheel for these files, in wheel order."""
    if not items:
        return []
    cats = [category(p) for p in items]
    usable = [op for op in OPS if op.wheel == wheel and all(engines.get(n) for n in op.needs)]
    keys = list(dict.fromkeys(op.key for op in usable))

    def rank(key):  # wheel order follows the first file's own list
        for i, op in enumerate(usable):
            if op.key == key and (ANY in op.categories or cats[0] in op.categories):
                return i
        return len(usable)

    keys.sort(key=rank)
    result = []
    for key in keys:
        ops = [op for op in usable if op.key == key]
        combos = [op for op in ops if op.combine]
        if combos:
            fit = next((op for op in combos if len(items) >= op.min_items
                        and all(_fits(op, p, c) for p, c in zip(items, cats))), None)
            if fit:
                result.append(Choice(key, fit.label, wheel, [(fit, list(items))], icon=fit.icon))
            continue
        plan, skipped, ok = [], 0, True
        for path, cat in zip(items, cats):
            op = next((o for o in ops if _fits(o, path, cat)), None)
            if op is None:
                ok = False
                break
            if op.target and normal_ext(ext_of(path)) == normal_ext(op.target):
                skipped += 1
                continue
            plan.append((op, [path]))
        max_items = max((o.max_items or 0 for o in ops), default=0)
        if ok and plan and (not max_items or len(items) <= max_items):
            choice = Choice(key, ops[0].label, wheel, plan, skipped, icon=ops[0].icon)
            if key == "pdf" and len(plan) > 1 and all(c == "image" for c in cats):
                # Several pictures to PDF: one PDF each, or all in one? Asked when chosen.
                choice.ask = FILES + "ask_pdf_mode"
                choice.alternative = IMAGES_TO_ONE_PDF
            result.append(choice)
    return result
