"""Subtitles: SRT and VTT both ways, and plain text."""

from __future__ import annotations

import re
from pathlib import Path

from spinvert.util import ConversionError

TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
TAG = re.compile(r"<[^>]+>")


def _ms(text: str) -> int:
    m = TIME.search(text)
    if not m:
        raise ValueError(text)
    h, mnt, s, frac = m.groups()
    return ((int(h or 0) * 60 + int(mnt)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def _stamp(ms: int, sep: str) -> str:
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def parse(path: Path) -> list[tuple[int, int, str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", "replace")
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        lines = [l for l in block.strip("\n").split("\n")]
        timing = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if timing is None:
            continue  # WEBVTT header, NOTE, STYLE, stray numbers
        start, _, end = lines[timing].partition("-->")
        try:
            cues.append((_ms(start), _ms(end), "\n".join(lines[timing + 1:]).strip()))
        except ValueError:
            continue
    if not cues:
        raise ConversionError(f"No subtitles found in {path.name}.")
    return cues


def subs_to(ext: str):
    def run(ctx):
        src = ctx.inputs[0]
        cues = parse(src)
        out = ctx.output(src.stem, ext)
        if ext == "srt":
            body = "\n\n".join(f"{i}\n{_stamp(a, ',')} --> {_stamp(b, ',')}\n{t}"
                               for i, (a, b, t) in enumerate(cues, 1))
        elif ext == "vtt":
            body = "WEBVTT\n\n" + "\n\n".join(f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n{t}"
                                              for a, b, t in cues)
        else:
            body = "\n".join(TAG.sub("", t) for _, _, t in cues if t)
        out.write_text(body + "\n", encoding="utf-8")
        return [out]
    return run
