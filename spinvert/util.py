"""Small helpers shared by the engines and the UI. No Qt in here."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Extensions that name the same format.
_SAME = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "markdown": "md",
         "tgz": "tar.gz", "oga": "ogg", "aif": "aiff", "heif": "heic"}


class ConversionError(Exception):
    """A failure the user will read. Keep the message short and plain."""


class Cancelled(Exception):
    """The user cancelled the job."""


def ext_of(path: Path) -> str:
    """Lower-case extension without the dot. Knows about .tar.gz."""
    name = path.name.lower()
    if name.endswith(".tar.gz"):
        return "tar.gz"
    return path.suffix.lower().lstrip(".")


def normal_ext(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return _SAME.get(ext, ext)


def stem_of(path: Path) -> str:
    """File name without its extension, .tar.gz included."""
    if path.name.lower().endswith(".tar.gz"):
        return path.name[:-7]
    return path.stem


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    """A path that does not exist yet: name.ext, then name (1).ext, ..."""
    ext = ext.lstrip(".")
    candidate = folder / f"{stem}.{ext}"
    n = 1
    while candidate.exists():
        candidate = folder / f"{stem} ({n}).{ext}"
        n += 1
    return candidate


def unique_dir(folder: Path, name: str) -> Path:
    candidate = folder / name
    n = 1
    while candidate.exists():
        candidate = folder / f"{name} ({n})"
        n += 1
    candidate.mkdir(parents=True)
    return candidate


def natural_key(path: Path):
    """Sort 'page 2' before 'page 10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def safe_name(text: str) -> str:
    """Make text usable as part of a Windows file name."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")
    return text or "untitled"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / "Spinvert"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def app_root() -> Path:
    """Folder of the installed app (the exe when frozen, the repo otherwise)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def find_ffmpeg(custom: str = "") -> Path | None:
    candidates = []
    if custom:
        candidates.append(Path(custom))
    candidates.append(app_root() / "bin" / "ffmpeg.exe")
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(Path(found))
    # Installed by winget after this process started, so not on its PATH yet.
    for base, links in (("LOCALAPPDATA", "Microsoft/WinGet/Links"), ("ProgramFiles", "WinGet/Links")):
        if os.environ.get(base):
            candidates.append(Path(os.environ[base]) / links / "ffmpeg.exe")
    for c in candidates:
        if c.is_file():
            return c
    return None


def find_ffprobe(ffmpeg: Path | None) -> Path | None:
    if ffmpeg:
        sibling = ffmpeg.with_name("ffprobe.exe")
        if sibling.is_file():
            return sibling
    found = shutil.which("ffprobe")
    return Path(found) if found else None
