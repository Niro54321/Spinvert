"""Archives: ZIP, TAR, TAR.GZ and GZ. Pack, extract and repack."""

from __future__ import annotations

import gzip
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from spinvert.util import ConversionError, ext_of, natural_key, stem_of

KIND_EXT = {"zip": "zip", "tar": "tar", "tar.gz": "tar.gz"}


def _walk(paths: list[Path]):
    """(file on disk, name inside the archive) for files and whole folders."""
    for base in paths:
        if base.is_dir():
            yield base, base.name + "/"
            for root, dirs, files in os.walk(base):
                dirs.sort()
                for name in sorted(files):
                    full = Path(root) / name
                    yield full, str(full.relative_to(base.parent)).replace("\\", "/")
        else:
            yield base, base.name


def pack(ctx, paths: list[Path], out: Path, kind: str) -> None:
    entries = list(_walk(paths))
    total = max(1, len(entries))
    if kind == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for i, (full, arc) in enumerate(entries):
                ctx.check()
                if arc.endswith("/"):
                    zf.writestr(arc, b"")
                else:
                    zf.write(full, arc)
                ctx.progress(0.95 * (i + 1) / total)
    else:
        mode = "w:gz" if kind == "tar.gz" else "w"
        with tarfile.open(out, mode) as tf:
            for i, (full, arc) in enumerate(entries):
                ctx.check()
                tf.add(full, arc.rstrip("/"), recursive=False)
                ctx.progress(0.95 * (i + 1) / total)


def extract_to(ctx, src: Path, folder: Path) -> None:
    kind = ext_of(src)
    try:
        if kind == "zip":
            with zipfile.ZipFile(src) as zf:
                for member in zf.infolist():
                    ctx.check()
                    zf.extract(member, folder)
        elif kind in ("tar", "tar.gz", "tgz"):
            with tarfile.open(src) as tf:
                if hasattr(tarfile, "data_filter"):
                    tf.extractall(folder, filter="data")
                else:
                    for member in tf.getmembers():
                        if member.name.startswith(("/", "\\")) or ".." in Path(member.name).parts:
                            raise ConversionError("This archive has unsafe paths.")
                    tf.extractall(folder)
        elif kind == "gz":
            with gzip.open(src) as fin, open(folder / stem_of(src), "wb") as fout:
                shutil.copyfileobj(fin, fout)
        elif kind == "rar":
            # Windows 10 and 11 ship bsdtar (libarchive), which reads RAR and RAR5.
            tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
            if not tar.is_file():
                raise ConversionError("Opening RAR needs Windows 10 (1803) or newer.")
            try:
                ctx.run([tar, "-xf", src, "-C", folder])
            except ConversionError as e:
                raise ConversionError(f"Can't open {src.name}. Is it password protected? ({e})") from e
        else:
            raise ConversionError(f"Can't open .{kind} archives.")
    except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile, EOFError) as e:
        raise ConversionError(f"{src.name} is damaged or not a real archive.") from e
    except RuntimeError as e:  # encrypted zip
        raise ConversionError(f"{src.name} is password protected.") from e


def extract(ctx):
    src = ctx.inputs[0]
    folder = ctx.output_dir(stem_of(src))
    extract_to(ctx, src, folder)
    return [folder]


def repack(kind: str):
    def run(ctx):
        src = ctx.inputs[0]
        with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
            extract_to(ctx, src, Path(tmp))
            ctx.progress(0.3)
            items = sorted(Path(tmp).iterdir(), key=natural_key)
            if not items:
                raise ConversionError(f"{src.name} is empty.")
            out = ctx.output(stem_of(src), KIND_EXT[kind])
            pack(ctx, items, out, kind)
        return [out]
    return run


def folder_to(kind: str):
    def run(ctx):
        src = ctx.inputs[0]
        out = ctx.output(src.name, KIND_EXT[kind], folder=src.parent)
        pack(ctx, [src], out, kind)
        return [out]
    return run


def zip_all(ctx):
    items = sorted(ctx.inputs, key=natural_key)
    stem = stem_of(items[0]) if len(items) == 1 else "Archive"
    out = ctx.output(stem, "zip")
    if out in items:
        raise ConversionError("Can't write the archive over one of its own files.")
    pack(ctx, items, out, "zip")
    return [out]
