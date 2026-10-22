"""Every operation Spinvert offers, and which ones fit a selection of files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from spinvert.engines import (archives, documents, images, media, pages, pdfs, sheets, slides,
                              subtitles)
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
    prepare: str | None = None    # "module:function" asked in the UI before the job


@dataclass
class Choice:
    key: str
    label: str
    wheel: str
    plan: list = field(default_factory=list)   # [(Op, [paths]), ...]
    skipped: int = 0


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

# Tools wheel.

_add("compress", "Compress", "tools", "image", images.compress)
_add("compress", "Compress", "tools", "video", media.compress_video, needs=("ffmpeg",))
_add("compress", "Compress", "tools", "pdf", pdfs.compress)
_add("to-pdf", "Combine to PDF", "tools", "image", images.combine_to_pdf, combine=True)
_add("merge", "Merge", "tools", "pdf", pdfs.merge, combine=True, min_items=2)
_add("split", "Split pages", "tools", "pdf", pdfs.split)
_add("reorder", "Reorder", "tools", "pdf", pdfs.reorder, max_items=1,
     prepare="spinvert.dialogs:ask_page_order")
_add("clean", "Remove metadata", "tools", "image", images.strip_metadata,
     in_exts=frozenset(EXTENSIONS["image"].split()) - {"svg"})
_add("normalize", "Normalize volume", "tools", "audio", media.normalize_audio, needs=("ffmpeg",))
_add("mute", "Remove sound", "tools", "video", media.remove_audio, needs=("ffmpeg",))
_add("zip", "ZIP all", "tools", ANY, archives.zip_all, combine=True)


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
        combined = next((op for op in ops if op.combine), None)
        if combined:
            if (len(items) >= combined.min_items
                    and all(_fits(combined, p, c) for p, c in zip(items, cats))):
                result.append(Choice(key, combined.label, wheel, [(combined, list(items))]))
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
            result.append(Choice(key, ops[0].label, wheel, plan, skipped))
    return result
