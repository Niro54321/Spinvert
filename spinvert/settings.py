"""User settings, stored as JSON in %APPDATA%\\Spinvert. No Qt in here."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from spinvert.util import app_data_dir

KEYS = ("shift", "ctrl", "alt")
VIDEO_CRF = {"high": 18, "balanced": 22, "small": 28}
VP9_CRF = {"high": 28, "balanced": 33, "small": 40}


@dataclass
class Settings:
    convert_key: str = "shift"
    tools_key: str = "ctrl"
    explorer_only: bool = True
    image_quality: int = 92
    video_quality: str = "balanced"
    ffmpeg_path: str = ""
    welcomed: bool = False

    @property
    def crf(self) -> int:
        return VIDEO_CRF.get(self.video_quality, 22)

    @property
    def vp9_crf(self) -> int:
        return VP9_CRF.get(self.video_quality, 33)

    @classmethod
    def path(cls):
        return app_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in data.items() if k in known})
        if s.convert_key not in KEYS:
            s.convert_key = "shift"
        if s.tools_key not in KEYS or s.tools_key == s.convert_key:
            s.tools_key = next(k for k in KEYS if k != s.convert_key)
        s.image_quality = max(40, min(100, int(s.image_quality)))
        return s

    def save(self) -> None:
        try:
            self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass
