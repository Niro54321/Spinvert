"""Documents with Pandoc. PDF output goes through Word when it is installed,
and through Qt's own PDF writer when it is not."""

from __future__ import annotations

import plistlib
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from spinvert.engines import office
from spinvert.util import ConversionError, ext_of

READERS = {"docx": "docx", "md": "markdown", "markdown": "markdown", "html": "html",
           "htm": "html", "epub": "epub", "odt": "odt", "rtf": "rtf", "rtfd": "rtf",
           "txt": "markdown+hard_line_breaks", "textclipping": "markdown+hard_line_breaks"}

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


def _clipping_text(src: Path) -> str:
    """A macOS text clipping is a property list with the text under a type name."""
    try:
        data = plistlib.loads(src.read_bytes())
    except Exception as e:
        raise ConversionError(f"Can't read {src.name}: not a text clipping this Spinvert knows.") from e
    store = data.get("UTIData", data) if isinstance(data, dict) else {}
    for key in ("public.utf8-plain-text", "public.utf16-plain-text", "public.plain-text",
                "NSStringPboardType"):
        value = store.get(key)
        if isinstance(value, bytes):
            value = value.decode("utf-16" if "utf16" in key else "utf-8", "replace")
        if isinstance(value, str) and value.strip():
            return value
    raise ConversionError(f"No text found in {src.name}.")


@contextmanager
def _readable(src: Path):
    """(file Pandoc can read, folder to run in) for any document input."""
    kind = ext_of(src)
    if kind == "rtfd":  # a macOS bundle: a folder holding TXT.rtf and its pictures
        rtf = next((p for p in src.glob("*.rtf")), None)
        if rtf is None:
            raise ConversionError(f"{src.name} has no RTF text inside.")
        yield rtf, src
    elif kind == "textclipping":
        with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
            text = Path(tmp) / f"{src.stem}.txt"
            text.write_text(_clipping_text(src), encoding="utf-8")
            yield text, Path(tmp)
    else:
        yield src, src.parent


def _pandoc(ctx, src: Path, out: Path, writer_args: list, extra: list = ()) -> None:
    pandoc = pandoc_path()
    if not pandoc:
        raise ConversionError("Pandoc is missing. Reinstall Spinvert's requirements.")
    reader = READERS[ext_of(src)]
    with _readable(src) as (path, cwd):
        ctx.run([pandoc, path.name, "-f", reader, *writer_args, *extra, "-o", out], cwd=cwd)


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
