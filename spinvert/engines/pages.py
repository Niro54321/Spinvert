"""Apple Pages files, read through the PDF copy that Pages saves inside them.

Nothing outside Apple's own apps can write a .pages file, so Pages is an input
only. The document itself is in a private format, but Pages also stores a
full-quality PDF of it (QuickLook/Preview.pdf), and the PDF engines take it
from there.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
import zipfile
from pathlib import Path

from spinvert.util import ConversionError

PREVIEWS = ("quicklook/preview.pdf", "preview.pdf")


def preview_pdf(src: Path, folder: Path) -> Path:
    out = folder / f"{src.stem}.pdf"
    if src.is_dir():  # a Pages package copied as a folder (Windows paths ignore case)
        for name in PREVIEWS:
            candidate = src / name
            if candidate.is_file():
                shutil.copyfile(candidate, out)
                return out
    else:
        try:
            with zipfile.ZipFile(src) as zf:
                names = {n.lower(): n for n in zf.namelist()}
                for name in PREVIEWS:
                    if name in names:
                        out.write_bytes(zf.read(names[name]))
                        return out
        except zipfile.BadZipFile as e:
            raise ConversionError(f"{src.name} is damaged or not a Pages file.") from e
    raise ConversionError("This Pages file has no PDF copy inside. In Pages, use "
                          "File > Export To > Word or PDF, then convert that.")


def _free(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


def via_pdf(pdf_op):
    """Run a PDF operation on the Pages file's PDF copy; results land beside the original."""
    def run(ctx):
        src = ctx.inputs[0]
        with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
            pdf = preview_pdf(src, Path(tmp))
            inner = dataclasses.replace(ctx, inputs=[pdf], created=[])
            made = pdf_op(inner) if pdf_op else [pdf]
            moved = []
            for path in made:
                target = _free(src.parent, path.name)
                shutil.move(str(path), str(target))
                ctx.created.append(target)
                moved.append(target)
            return moved
    return run
