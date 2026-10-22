"""PDF: render pages with PDFium, edit pages with pypdf."""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter

from spinvert.util import ConversionError, natural_key

MAX_PIXELS = 40_000_000


def _open_pdfium(path: Path):
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            raise ConversionError(f"{path.name} is password protected.") from e
        raise ConversionError(f"Can't read {path.name}: {e}") from e


def _reader(path: Path) -> PdfReader:
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise ConversionError(f"Can't read {path.name}: {e}") from e
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise ConversionError(f"{path.name} is password protected.")
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(f"{path.name} is password protected.") from e
    return reader


def _render(page, dpi: int):
    width, height = page.get_size()
    scale = dpi / 72
    pixels = width * scale * height * scale
    if pixels > MAX_PIXELS:
        scale *= (MAX_PIXELS / pixels) ** 0.5
    return page.render(scale=scale).to_pil()


def pdf_to_images(fmt: str):
    def run(ctx):
        src = ctx.inputs[0]
        pdf = _open_pdfium(src)
        try:
            count = len(pdf)
            if count == 1:
                targets = [ctx.output(src.stem, fmt)]
                result = targets
            else:
                folder = ctx.output_dir(f"{src.stem} pages")
                digits = len(str(count))
                targets = [folder / f"{src.stem}-p{i + 1:0{digits}d}.{fmt}" for i in range(count)]
                result = [folder]
            for i, target in enumerate(targets):
                ctx.check()
                image = _render(pdf[i], 300)
                if fmt == "jpg":
                    image.convert("RGB").save(target, "JPEG", quality=90, optimize=True)
                else:
                    image.save(target, "PNG")
                ctx.progress((i + 1) / count)
        finally:
            pdf.close()
        return result
    return run


def pdf_to_text(ctx):
    src = ctx.inputs[0]
    pdf = _open_pdfium(src)
    parts = []
    try:
        for i in range(len(pdf)):
            ctx.check()
            textpage = pdf[i].get_textpage()
            parts.append(textpage.get_text_bounded().replace("\r\n", "\n").strip())
            ctx.progress((i + 1) / len(pdf))
    finally:
        pdf.close()
    text = "\n\n".join(parts).strip()
    if not text:
        raise ConversionError("No text found. This PDF is probably scanned images.")
    out = ctx.output(src.stem, "txt")
    out.write_text(text + "\n", encoding="utf-8")
    return [out]


def pdf_to_pptx(ctx):
    from pptx import Presentation
    from pptx.util import Emu

    src = ctx.inputs[0]
    pdf = _open_pdfium(src)
    try:
        w_pt, h_pt = pdf[0].get_size()
        shrink = min(1.0, 4000 / max(w_pt, h_pt))
        prs = Presentation()
        prs.slide_width = Emu(int(w_pt * shrink * 12700))
        prs.slide_height = Emu(int(h_pt * shrink * 12700))
        blank = prs.slide_layouts[6]
        for i in range(len(pdf)):
            ctx.check()
            stream = io.BytesIO()
            _render(pdf[i], 150).convert("RGB").save(stream, "JPEG", quality=88)
            stream.seek(0)
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(stream, 0, 0, prs.slide_width, prs.slide_height)
            ctx.progress(0.95 * (i + 1) / len(pdf))
    finally:
        pdf.close()
    out = ctx.output(src.stem, "pptx")
    prs.save(str(out))
    return [out]


def merge(ctx):
    files = sorted(ctx.inputs, key=natural_key)
    writer = PdfWriter()
    for i, path in enumerate(files):
        ctx.check()
        writer.append(_reader(path))
        ctx.progress(0.9 * (i + 1) / len(files))
    out = ctx.output("Merged", "pdf")
    with open(out, "wb") as fh:
        writer.write(fh)
    return [out]


def split(ctx):
    src = ctx.inputs[0]
    reader = _reader(src)
    count = len(reader.pages)
    if count < 2:
        raise ConversionError("This PDF has only one page.")
    folder = ctx.output_dir(f"{src.stem} split")
    digits = len(str(count))
    for i, page in enumerate(reader.pages):
        ctx.check()
        writer = PdfWriter()
        writer.add_page(page)
        with open(folder / f"{src.stem}-p{i + 1:0{digits}d}.pdf", "wb") as fh:
            writer.write(fh)
        ctx.progress((i + 1) / count)
    return [folder]


def page_count(path: Path) -> int:
    return len(_reader(path).pages)


def reorder(ctx):
    src = ctx.inputs[0]
    order = ctx.params.get("order")
    reader = _reader(src)
    if not order or any(i < 0 or i >= len(reader.pages) for i in order):
        raise ConversionError("No page order was given.")
    writer = PdfWriter()
    for i in order:
        writer.add_page(reader.pages[i])
    out = ctx.output(f"{src.stem} (reordered)", "pdf")
    with open(out, "wb") as fh:
        writer.write(fh)
    return [out]


def compress(ctx):
    src = ctx.inputs[0]
    _reader(src)  # friendly error for locked files
    writer = PdfWriter(clone_from=str(src))
    pages = list(writer.pages)
    for i, page in enumerate(pages):
        ctx.check()
        for image in page.images:
            try:
                picture = image.image
                if picture.width * picture.height < 250_000:
                    continue
                if max(picture.size) > 2200:
                    picture.thumbnail((2200, 2200))
                if picture.mode not in ("RGB", "L"):
                    picture = picture.convert("RGB")
                image.replace(picture, quality=65)
            except Exception:
                continue  # leave images we can't recompress as they are
        page.compress_content_streams()
        ctx.progress(0.9 * (i + 1) / len(pages))
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    out = ctx.output(f"{src.stem} (compressed)", "pdf")
    with open(out, "wb") as fh:
        writer.write(fh)
    if out.stat().st_size >= src.stat().st_size:
        raise ConversionError("Already compact: a smaller copy wasn't possible.")
    return [out]


def thumbnails(path: Path, height: int = 180):
    """Small page images for the reorder dialog."""
    pdf = _open_pdfium(path)
    try:
        images = []
        for i in range(len(pdf)):
            page = pdf[i]
            _, h_pt = page.get_size()
            images.append(page.render(scale=height / h_pt).to_pil())
        return images
    finally:
        pdf.close()
