"""Documents with Pandoc. PDF output goes through Word when it is installed,
and through Qt's own PDF writer when it is not."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from spinvert.engines import office
from spinvert.util import ConversionError, ext_of

READERS = {"docx": "docx", "md": "markdown", "markdown": "markdown", "html": "html",
           "htm": "html", "epub": "epub", "odt": "odt", "rtf": "rtf",
           "txt": "markdown+hard_line_breaks"}

WRITERS = {
    "docx": ["-t", "docx"],
    "md": ["-t", "gfm"],
    "html": ["-t", "html5", "--standalone", "--embed-resources"],
    "epub": ["-t", "epub3"],
    "txt": ["-t", "plain", "--wrap=none"],
}


def pandoc_path() -> Path | None:
    try:
        import pypandoc

        path = Path(pypandoc.get_pandoc_path())
        for candidate in (path, path.with_name(path.name + ".exe")):
            if candidate.is_file():
                return candidate
    except Exception:
        pass
    found = shutil.which("pandoc")
    return Path(found) if found else None


def _pandoc(ctx, src: Path, out: Path, writer_args: list, extra: list = ()) -> None:
    pandoc = pandoc_path()
    if not pandoc:
        raise ConversionError("Pandoc is missing. Reinstall Spinvert's requirements.")
    reader = READERS[ext_of(src)]
    ctx.run([pandoc, src.name, "-f", reader, *writer_args, *extra, "-o", out], cwd=src.parent)


def doc_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        out = ctx.output(src.stem, ext)
        if ext == "pdf":
            _to_pdf(ctx, src, out)
            return [out]
        extra = []
        if ext == "html":
            extra = ["--metadata", f"pagetitle={src.stem}"]
        elif ext == "epub":
            extra = ["--metadata", f"title={src.stem}"]
        _pandoc(ctx, src, out, WRITERS[ext], extra)
        return [out]
    return run


def _to_pdf(ctx, src: Path, out: Path) -> None:
    if ctx.engines.get("word"):
        if ext_of(src) == "docx":
            office.word_to_pdf(src, out)
            return
        with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
            docx = Path(tmp) / f"{src.stem}.docx"
            _pandoc(ctx, src, docx, WRITERS["docx"])
            ctx.progress(0.4)
            office.word_to_pdf(docx, out)
        return
    with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
        html = Path(tmp) / "page.html"
        _pandoc(ctx, src, html, ["-t", "html5", "--standalone"],
                ["--extract-media", tmp, "--metadata", f"pagetitle={src.stem}"])
        ctx.progress(0.5)
        from spinvert.mainthread import run_in_main
        from spinvert.qtpdf import html_to_pdf

        run_in_main(lambda: html_to_pdf(html.read_text(encoding="utf-8"), Path(tmp), out))
