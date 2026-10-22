"""Video and audio editors: trim, crop (Reels, square...), speed, frames, split,
redact, normalize, visualizer, channels and bleep.

Video editors show the frame under the playhead and a strip of thumbnails;
audio editors show the waveform and can play the selection.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QPushButton, QSpinBox

from spinvert.editors.base import (Background, BoxesTool, CropTool, GlassDialog, ImageCanvas, Segmented,
                                   SliderRow, TimeEdit, Timeline, busy, fmt_time, label,
                                   play_wav, qimage_from_png, stop_sound, to_qimage)
from spinvert.editors.pickers import Swatches
from spinvert.engines import media
from spinvert.settings import Settings


def _custom() -> str:
    return Settings.load().ffmpeg_path


class MediaDialog(GlassDialog):
    """Loads the file's facts, a frame preview (video) and the strip or waveform."""

    def __init__(self, title: str, path: Path, mode: str = "range", size=(1060, 760),
                 primary: str = "Save copy", show_frame: bool = True):
        super().__init__(title, size, primary)
        self.path = path
        self.custom = _custom()
        self.info = busy(lambda: media.info(path, self.custom))
        self.duration = self.info["duration"] or 0.1
        self.video = bool(self.info["video"])
        self.canvas = ImageCanvas((480, 270)) if self.video and show_frame else None
        self.timeline = Timeline(self.duration, mode)
        self.timeline.setMinimumHeight(96 if self.video else 130)
        self._strip = Background()
        self._strip.done.connect(lambda data, err: data and self.timeline.set_background(qimage_from_png(data)))
        if self.video:
            self._strip.start(lambda: media.strip_png(path, self.duration, 14, 64, self.custom))
        else:
            self._strip.start(lambda: media.waveform_png(path, 1600, 200, "#FFFFFF", self.custom))
        self._frames = Background()
        self._frames.done.connect(self._frame_ready)
        self._want, self._loading = None, False
        self._frame_soon = QTimer(self)
        self._frame_soon.setSingleShot(True)
        self._frame_soon.setInterval(110)
        self._frame_soon.timeout.connect(self._load_frame)
        self.timeline.scrubbed.connect(lambda t: self._frame_soon.start())
        if self.canvas is not None:
            self._want = self.duration / 2 if mode != "range" else 0.0
            self.timeline.playhead = self._want
            self._load_frame()

    def _load_frame(self):
        if self.canvas is None:
            return
        t = self.timeline.playhead
        if self._loading:
            self._want = t
            return
        self._loading, self._want = True, None
        self._frames.start(lambda: media.frame_png(self.path, min(t, self.duration - 0.05), 960, self.custom))

    def _frame_ready(self, data, error):
        self._loading = False
        if data:
            self.canvas.set_image(qimage_from_png(data))
        if self._want is not None:
            self._load_frame()

    def step_frame(self, direction: int):
        fps = self.info["fps"] or 25
        self.timeline.playhead = min(self.duration, max(0.0, self.timeline.playhead + direction / fps))
        self.timeline.update()
        self.timeline.scrubbed.emit(self.timeline.playhead)

    def play(self, start: float, end: float, af: str = "", graph=None):
        try:
            play_wav(busy(lambda: media.preview_wav(self.path, start, end, af, graph, self.custom)))
        except Exception as e:  # a preview is a convenience; say why it didn't play
            self.set_status(f"Couldn't play the preview: {e}")

    def set_status(self, text: str):
        if hasattr(self, "status"):
            self.status.setText(text)


def _buttons(*pairs) -> QHBoxLayout:
    row = QHBoxLayout()
    for text, fn in pairs:
        b = QPushButton(text)
        b.clicked.connect(fn)
        row.addWidget(b)
    return row


# ------------------------------------------------------------------ trim

class TrimDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Trim", path, "range", primary="Trim")
        tl = self.timeline
        if self.canvas is not None:
            self.body.addWidget(self.canvas, 1)
        self.body.addWidget(tl)
        self.start_edit, self.end_edit = TimeEdit(0), TimeEdit(self.duration)
        self.length = label("", bold=True)
        self.start_edit.changed.connect(lambda v: self._set(v, None))
        self.end_edit.changed.connect(lambda v: self._set(None, v))
        row = QHBoxLayout()
        row.addWidget(label("Start"))
        row.addWidget(self.start_edit)
        row.addWidget(label("End"))
        row.addWidget(self.end_edit)
        row.addWidget(self.length)
        row.addStretch()
        if self.video:
            row.addLayout(_buttons(("◀ Frame", lambda: self.step_frame(-1)), ("Frame ▶", lambda: self.step_frame(1))))
        row.addLayout(_buttons(("Start here", lambda: self._set(tl.playhead, None)),
                               ("End here", lambda: self._set(None, tl.playhead))))
        self.body.addLayout(row)
        opts = QHBoxLayout()
        self.fade_in = SliderRow("Fade in", 0, 100, 0, " s", scale=10, width=60)
        self.fade_out = SliderRow("Fade out", 0, 100, 0, " s", scale=10, width=60)
        opts.addWidget(self.fade_in, 1)
        opts.addWidget(self.fade_out, 1)
        if self.video:
            self.fast = QCheckBox("Fast: no re-encoding (cuts at the nearest keyframe)")
            opts.addWidget(self.fast)
        else:
            self.fast = None
            opts.addLayout(_buttons(("Remove silence at the ends", self._silence),
                                    ("▶ Play selection", lambda: self.play(tl.start, tl.end)), ("■ Stop", stop_sound)))
        self.body.addLayout(opts)
        self.status = label("Drag the white handles, or type exact times.", muted=True)
        self.body.addWidget(self.status)
        tl.changed.connect(self._sync)
        self._sync()

    def _set(self, start, end):
        tl = self.timeline
        if start is not None:
            tl.start = min(max(0.0, start), tl.end - 0.05)
            tl.playhead = tl.start
        if end is not None:
            tl.end = max(min(self.duration, end), tl.start + 0.05)
            tl.playhead = tl.end
        tl.update()
        tl.scrubbed.emit(tl.playhead)
        self._sync()

    def _sync(self):
        tl = self.timeline
        self.start_edit.set(tl.start)
        self.end_edit.set(tl.end)
        self.length.setText(f"Keeps {fmt_time(tl.end - tl.start)}")

    def _silence(self):
        start, end = busy(lambda: media.silence_edges(self.path, self.custom))
        self._set(start, end)
        self.status.setText("Silence at the start and end is now outside the selection.")

    def params(self) -> dict:
        tl = self.timeline
        return {"start": tl.start, "end": tl.end, "fade_in": self.fade_in.get() / 10,
                "fade_out": self.fade_out.get() / 10, "fast": bool(self.fast and self.fast.isChecked())}


def trim(paths, parent=None):
    d = TrimDialog(paths[0])
    return d.params() if d.run() else None


# ------------------------------------------------------------------ crop

PRESETS = [("9:16", "Reels / TikTok 9:16", (1080, 1920)), ("1:1", "Square 1:1", (1080, 1080)),
           ("4:5", "Portrait 4:5", (1080, 1350)), ("16:9", "Landscape 16:9", (1920, 1080)),
           ("free", "Free", None)]


class VideoCropDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Crop video", path, "point", primary="Crop")
        self.tool = CropTool()
        self.canvas.set_tool(self.tool)
        self.body.addWidget(self.canvas, 1)
        self.body.addWidget(self.timeline)
        self.presets = Segmented([(k, text) for k, text, _ in PRESETS], "9:16")
        self.presets.changed.connect(self._preset)
        self.body.addWidget(self.presets)
        row = QHBoxLayout()
        self.exact = QCheckBox("Output size")
        self.exact.setChecked(True)
        self.out_w, self.out_h = QSpinBox(), QSpinBox()
        for box in (self.out_w, self.out_h):
            box.setRange(16, 8192)
        row.addWidget(self.exact)
        row.addWidget(self.out_w)
        row.addWidget(label("×"))
        row.addWidget(self.out_h)
        row.addStretch()
        row.addWidget(label(f"Original {self.info['width']} × {self.info['height']}. The audio is kept.",
                            muted=True))
        self.body.addLayout(row)
        QTimer.singleShot(400, lambda: self._preset("9:16"))

    def _preset(self, key):
        for k, _, size in PRESETS:
            if k == key:
                if size:
                    w, h = size
                    self.tool.set_aspect(w / h)
                    self.out_w.setValue(w)
                    self.out_h.setValue(h)
                else:
                    self.tool.set_aspect(None)
                    self.exact.setChecked(False)
        self.canvas.update()

    def params(self) -> dict:
        p = {"rect": list(self.tool.rect)}
        if self.exact.isChecked():
            p["size"] = [self.out_w.value(), self.out_h.value()]
        return p


def crop_video(paths, parent=None):
    d = VideoCropDialog(paths[0])
    return d.params() if d.run() else None


# ----------------------------------------------------------------- speed

class SpeedDialog(GlassDialog):
    def __init__(self, path):
        super().__init__("Change speed", (640, 420), "Save copy")
        self.info = busy(lambda: media.info(path, _custom()))
        self.choice = Segmented([(s, f"{s}×") for s in ("0.25", "0.5", "0.75", "1.25", "1.5", "2", "3", "4")], "2")
        self.choice.changed.connect(lambda k: self.custom.setValue(float(k)))
        self.custom = QDoubleSpinBox()
        self.custom.setRange(0.1, 16)
        self.custom.setSingleStep(0.05)
        self.custom.setValue(2.0)
        self.custom.valueChanged.connect(self._update)
        self.pitch = QCheckBox("Keep the voice's pitch")
        self.pitch.setChecked(True)
        self.pitch.setVisible(bool(self.info["audio"]))
        self.result = label("", bold=True)
        self.body.addWidget(label("Speed", bold=True))
        self.body.addWidget(self.choice)
        row = QHBoxLayout()
        row.addWidget(label("Exact"))
        row.addWidget(self.custom)
        row.addStretch()
        self.body.addLayout(row)
        self.body.addWidget(self.pitch)
        self.body.addWidget(self.result)
        self.body.addStretch()
        self._update()

    def _update(self, *_):
        speed = self.custom.value()
        self.result.setText(f"{fmt_time(self.info['duration'])} becomes {fmt_time(self.info['duration'] / speed)}")

    def params(self) -> dict:
        return {"speed": self.custom.value(), "keep_pitch": self.pitch.isChecked()}


def speed(paths, parent=None):
    d = SpeedDialog(paths[0])
    return d.params() if d.run() else None


# ---------------------------------------------------------------- frames

class FramesDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Save frames", path, "points", primary="Save frames")
        tl = self.timeline
        self.body.addWidget(self.canvas, 1)
        self.body.addWidget(tl)
        self.mode = Segmented([("pick", "Pick frames"), ("every", "One every…")], "pick")
        self.every = QDoubleSpinBox()
        self.every.setRange(0.1, 3600)
        self.every.setValue(1.0)
        self.every.setSuffix(" s")
        row = QHBoxLayout()
        row.addWidget(self.mode)
        row.addWidget(self.every)
        row.addStretch()
        row.addLayout(_buttons(("◀ Frame", lambda: self.step_frame(-1)), ("Frame ▶", lambda: self.step_frame(1)),
                               ("+ Add this frame", self._add), ("Clear", self._clear)))
        self.body.addLayout(row)
        self.list = label("No frames picked yet. Move to a frame and press Add.", muted=True)
        self.body.addWidget(self.list)

    def _add(self):
        t = round(self.timeline.playhead, 3)
        if t not in self.timeline.points:
            self.timeline.points.append(t)
            self.timeline.points.sort()
        self.timeline.update()
        self.mode.set("pick")
        self.list.setText("Frames at " + ", ".join(fmt_time(x) for x in self.timeline.points) + " (full-size PNG)")

    def _clear(self):
        self.timeline.points.clear()
        self.timeline.update()
        self.list.setText("No frames picked yet.")

    def params(self) -> dict:
        if self.mode.get() == "every":
            return {"every": self.every.value()}
        return {"times": self.timeline.points or [self.timeline.playhead]}


def frames(paths, parent=None):
    d = FramesDialog(paths[0])
    return d.params() if d.run() else None


# ----------------------------------------------------------------- split

class SplitDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Split", path, "points", primary="Split")
        tl = self.timeline
        if self.canvas is not None:
            self.body.addWidget(self.canvas, 1)
        self.body.addWidget(tl)
        self.mode = Segmented([("parts", "Equal parts"), ("every", "Every…"), ("points", "At my points")], "parts")
        self.parts = QSpinBox()
        self.parts.setRange(2, 100)
        self.parts.setValue(2)
        self.every = QDoubleSpinBox()
        self.every.setRange(0.5, 36000)
        self.every.setValue(60)
        self.every.setSuffix(" s")
        for w in (self.parts, self.every):
            w.valueChanged.connect(self._update)
        self.mode.changed.connect(self._update)
        row = QHBoxLayout()
        row.addWidget(self.mode)
        row.addWidget(label("Parts"))
        row.addWidget(self.parts)
        row.addWidget(label("Seconds"))
        row.addWidget(self.every)
        row.addStretch()
        row.addLayout(_buttons(("+ Cut here", self._add), ("Clear", self._clear)))
        self.body.addLayout(row)
        self.fast = QCheckBox("Fast: no re-encoding (cuts at the nearest keyframe)") if self.video else None
        if self.fast:
            self.body.addWidget(self.fast)
        self.result = label("", muted=True)
        self.body.addWidget(self.result)
        self._update()

    def _add(self):
        t = round(self.timeline.playhead, 3)
        if 0 < t < self.duration and t not in self.timeline.points:
            self.timeline.points.append(t)
            self.timeline.points.sort()
        self.mode.set("points")
        self._update()

    def _clear(self):
        self.timeline.points.clear()
        self._update()

    def _update(self, *_):
        mode = self.mode.get()
        if mode == "parts":
            n = self.parts.value()
            cuts = [self.duration * i / n for i in range(1, n)]
        elif mode == "every":
            step = self.every.value()
            cuts = [i * step for i in range(1, int(self.duration // step) + 1) if i * step < self.duration - 0.05]
        else:
            cuts = list(self.timeline.points)
        if mode != "points":
            self.timeline.points = cuts
        self.timeline.update()
        self.result.setText(f"{len(cuts) + 1} clips, all in one new folder.")

    def params(self) -> dict:
        mode = self.mode.get()
        p = {"mode": mode, "parts": self.parts.value(), "every": self.every.value(),
             "points": list(self.timeline.points), "fast": bool(self.fast and self.fast.isChecked())}
        return p


def split(paths, parent=None):
    d = SplitDialog(paths[0])
    return d.params() if d.run() else None


# ---------------------------------------------------------------- redact

class RedactVideoDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Redact video", path, "point", primary="Save copy")
        self.style, self.color = "blur", "#000000"
        self.tool = BoxesTool(lambda: {"style": self.style, "color": self.color, "start": 0.0,
                                       "end": self.duration})
        self.canvas.set_tool(self.tool)
        self.canvas.changed.connect(self._selected)
        self.body.addWidget(self.canvas, 1)
        self.body.addWidget(self.timeline)
        row = QHBoxLayout()
        styles = Segmented([("blur", "Blur"), ("pixelate", "Pixelate"), ("solid", "Solid colour")], "blur")
        styles.changed.connect(self._style)
        colors = Swatches([(c, c) for c in ("#000000", "#FFFFFF", "#FF3B30")], "#000000")
        colors.changed.connect(self._color)
        row.addWidget(styles)
        row.addWidget(colors)
        row.addStretch()
        self.start_edit, self.end_edit = TimeEdit(0), TimeEdit(self.duration)
        self.start_edit.changed.connect(lambda v: self._range(v, None))
        self.end_edit.changed.connect(lambda v: self._range(None, v))
        row.addWidget(label("Box shows from"))
        row.addWidget(self.start_edit)
        row.addWidget(label("to"))
        row.addWidget(self.end_edit)
        row.addLayout(_buttons(("From here", lambda: self._range(self.timeline.playhead, None)),
                               ("Until here", lambda: self._range(None, self.timeline.playhead)),
                               ("Whole video", lambda: self._range(0.0, self.duration)),
                               ("Delete box", self._delete)))
        self.body.addLayout(row)
        self.body.addWidget(label("Drag over the area to hide. Each box has its own time range.", muted=True))

    def _box(self):
        return self.tool.boxes[self.tool.selected] if self.tool.selected is not None else None

    def _selected(self):
        box = self._box()
        if box:
            self.start_edit.set(box["start"])
            self.end_edit.set(box["end"])

    def _range(self, start, end):
        box = self._box()
        if not box:
            return
        if start is not None:
            box["start"] = max(0.0, min(start, box["end"] - 0.05))
        if end is not None:
            box["end"] = min(self.duration, max(end, box["start"] + 0.05))
        self._selected()

    def _style(self, key):
        self.style = key
        if self._box():
            self._box()["style"] = key

    def _color(self, c):
        self.color = c
        if self._box():
            self._box()["color"] = c

    def _delete(self):
        if self.tool.selected is not None:
            self.tool.boxes.pop(self.tool.selected)
            self.tool.selected = None
            self.canvas.update()

    def params(self):
        return {"areas": self.tool.boxes} if self.tool.boxes else None


def redact_video(paths, parent=None):
    d = RedactVideoDialog(paths[0])
    return d.params() if d.run() else None


# ------------------------------------------------------------- normalize

TARGETS = [("-14", "Streaming −14 LUFS"), ("-16", "Podcast −16 LUFS"), ("-23", "Broadcast −23 LUFS"),
           ("custom", "Custom")]


class NormalizeDialog(GlassDialog):
    def __init__(self, path):
        super().__init__("Normalize volume", (700, 480), "Normalize")
        self.preset = Segmented(TARGETS, "-16")
        self.preset.changed.connect(lambda k: k != "custom" and self.target.set(int(k)))
        self.target = SliderRow("Loudness", -30, -5, -16, " LUFS", width=90)
        self.peak = SliderRow("True peak", -90, 0, -15, " dBTP", scale=10, width=90)
        self.lra = SliderRow("Range", 1, 20, 11, " LU", width=90)
        self.target.changed.connect(lambda v: self.preset.set(str(v) if str(v) in ("-14", "-16", "-23") else "custom"))
        self.measured = label("Measuring the file…", muted=True)
        self.result = label("", bold=True)
        for w in (label("Target", bold=True), self.preset, self.target, self.peak, self.lra, self.measured,
                  self.result):
            self.body.addWidget(w)
        self.body.addStretch()
        self.target.changed.connect(self._compare)
        self._levels = None
        self.worker = Background()
        self.worker.done.connect(self._measured)
        self.worker.start(lambda: media.loudness(path, _custom()))

    def _measured(self, levels, error):
        if error or not levels:
            self.measured.setText("Couldn't measure the input.")
            return
        self._levels = levels
        self.measured.setText(f"Input now: {float(levels['input_i']):.1f} LUFS, peak {float(levels['input_tp']):.1f} dBTP, "
                              f"range {float(levels['input_lra']):.1f} LU")
        self._compare()

    def _compare(self, *_):
        if self._levels:
            change = self.target.get() - float(self._levels["input_i"])
            self.result.setText(f"Output: {self.target.get()} LUFS ({change:+.1f} dB)")

    def params(self) -> dict:
        return {"target": self.target.get(), "true_peak": self.peak.get() / 10, "lra": self.lra.get()}


def normalize(paths, parent=None):
    d = NormalizeDialog(paths[0])
    return d.params() if d.run() else None


# ------------------------------------------------------------ visualizer

class VisualizerDialog(GlassDialog):
    def __init__(self, path):
        super().__init__("Audio visualizer", (1040, 740), "Make video")
        self.path = path
        self.color, self.bg, self.image = "#FFFFFF", "#16161D", None
        self.wave = None
        self.canvas = ImageCanvas()
        self.style = Segmented([("wave", "Waveform"), ("bars", "Bars"), ("still", "Still image")], "wave")
        self.size = Segmented([(k, k) for k in media.VISUALIZER_SIZES], "Square")
        waves = Swatches([(c, c) for c in ("#FFFFFF", "#FFCC00", "#34D399", "#06B6D4", "#F472B6",
                                                       "#7C5CFF", "#111114")], "#FFFFFF")
        backs = Swatches([(c, c) for c in ("#16161D", "#0F2027", "#3F6FE0", "#7A4FD8", "#F4D35E",
                                                       "#FFFFFF")], "#16161D")
        pick = QPushButton("Image…")
        pick.clicked.connect(self._pick)
        waves.changed.connect(lambda c: (setattr(self, "color", c), self._render()))
        backs.changed.connect(lambda c: (setattr(self, "bg", c), setattr(self, "image", None), self._render()))
        for s in (self.style, self.size):
            s.changed.connect(lambda *_: self._render())
        top = QHBoxLayout()
        top.addWidget(self.style)
        top.addWidget(self.size)
        top.addStretch()
        colors = QHBoxLayout()
        colors.addWidget(label("Wave"))
        colors.addWidget(waves)
        colors.addWidget(label("Background"))
        colors.addWidget(backs)
        colors.addWidget(pick)
        colors.addStretch()
        self.body.addLayout(top)
        self.body.addLayout(colors)
        self.body.addWidget(self.canvas, 1)
        self.worker = Background()
        self.worker.done.connect(lambda data, err: data and self._wave(data))
        self.worker.start(lambda: media.waveform_png(path, 1200, 300, "#FFFFFF", _custom()))
        self._render()

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Background image", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.heic *.bmp)")
        if path:
            self.image = path
            self._render()

    def _wave(self, data):
        import io

        self.wave = Image.open(io.BytesIO(data)).convert("RGBA")
        self._render()

    def _render(self):
        from PIL import ImageOps

        from spinvert.engines.imaging import hex_rgb

        W, H = media.VISUALIZER_SIZES[self.size.get()]
        W, H = W // 3, H // 3
        if self.image:
            frame = ImageOps.fit(Image.open(self.image).convert("RGB"), (W, H)).convert("RGBA")
        else:
            frame = Image.new("RGBA", (W, H), hex_rgb(self.bg) + (255,))
        if self.wave is not None and self.style.get() != "still":
            wave = self.wave.resize((W - 54, H // 3))
            tint = Image.new("RGBA", wave.size, hex_rgb(self.color) + (255,))
            tint.putalpha(wave.getchannel("A") if wave.mode == "RGBA" else wave.convert("L"))
            frame.alpha_composite(tint, ((W - wave.width) // 2, (H - wave.height) // 2))
        self.canvas.set_image(to_qimage(frame))

    def params(self) -> dict:
        p = {"style": self.style.get(), "size": self.size.get(), "color": self.color, "background": self.bg}
        if self.image:
            p["image"] = self.image
        return p


def visualizer(paths, parent=None):
    d = VisualizerDialog(paths[0])
    return d.params() if d.run() else None


# -------------------------------------------------------------- channels

class ChannelsDialog(GlassDialog):
    def __init__(self, path):
        super().__init__("Audio channels", (720, 460), "Save copy")
        self.path = path
        self.custom = _custom()
        self.info = busy(lambda: media.info(path, self.custom))
        stereo = self.info["channels"] >= 2
        self.body.addWidget(label(f"This file has {self.info['channels'] or '?'} channel(s).", muted=True))
        self.mode = Segmented([("mono", "Mono"), ("stereo", "Stereo"), ("left", "Left only"),
                               ("right", "Right only"), ("swap", "Swap L/R")], "mono" if stereo else "stereo")
        self.left = SliderRow("Left volume", 0, 200, 100, "%", width=100)
        self.right = SliderRow("Right volume", 0, 200, 100, "%", width=100)
        self.body.addWidget(self.mode)
        self.body.addWidget(self.left)
        self.body.addWidget(self.right)
        end = min(self.info["duration"], 20)
        self.body.addLayout(_buttons(
            ("▶ Left only", lambda: self._play(media.channels_graph("left", 1, 1, stereo))),
            ("▶ Right only", lambda: self._play(media.channels_graph("right", 1, 1, stereo))),
            ("▶ Result", lambda: self._play(media.channels_graph(self.mode.get(), self.left.get() / 100,
                                                                  self.right.get() / 100, stereo))),
            ("■ Stop", stop_sound)))
        self.body.addWidget(label(f"Previews play the first {int(end)} seconds.", muted=True))
        self.body.addStretch()
        self._end = end

    def _play(self, af):
        play_wav(busy(lambda: media.preview_wav(self.path, 0, self._end, af, None, self.custom)))

    def params(self) -> dict:
        return {"mode": self.mode.get(), "left": self.left.get(), "right": self.right.get()}


def channels(paths, parent=None):
    d = ChannelsDialog(paths[0])
    return d.params() if d.run() else None


# ----------------------------------------------------------------- bleep

class BleepDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Bleep", path, "ranges", primary="Save copy", show_frame=False)
        tl = self.timeline
        self.body.addWidget(tl, 1)
        self.tone = Segmented([("beep", "Beep 1 kHz"), ("low", "Beep 440 Hz"), ("silence", "Silence")], "beep")
        self.start_edit, self.end_edit = TimeEdit(0), TimeEdit(0)
        self.start_edit.changed.connect(lambda v: self._edit(v, None))
        self.end_edit.changed.connect(lambda v: self._edit(None, v))
        row = QHBoxLayout()
        row.addLayout(_buttons(("+ Bleep here", self._add), ("Remove", self._remove)))
        row.addWidget(label("From"))
        row.addWidget(self.start_edit)
        row.addWidget(label("to"))
        row.addWidget(self.end_edit)
        row.addStretch()
        row.addWidget(self.tone)
        self.body.addLayout(row)
        self.body.addLayout(_buttons(("▶ Original", lambda: self._play(False)), ("▶ Bleeped", lambda: self._play(True)),
                                     ("■ Stop", stop_sound)))
        self.status = label("Click on the waveform, then + Bleep here. Drag a red range to move it, "
                            "or its edges to fine-tune.", muted=True)
        self.body.addWidget(self.status)
        tl.changed.connect(self._sync)

    def _add(self):
        tl = self.timeline
        a = tl.playhead
        tl.ranges.append([a, min(self.duration, a + 1.0)])
        tl.selected = len(tl.ranges) - 1
        tl.update()
        self._sync()

    def _remove(self):
        tl = self.timeline
        if tl.selected is not None:
            tl.ranges.pop(tl.selected)
            tl.selected = None
            tl.update()

    def _edit(self, start, end):
        tl = self.timeline
        if tl.selected is None:
            return
        a, b = tl.ranges[tl.selected]
        if start is not None:
            a = max(0.0, min(start, b - 0.05))
        if end is not None:
            b = min(self.duration, max(end, a + 0.05))
        tl.ranges[tl.selected] = [a, b]
        tl.update()

    def _sync(self):
        tl = self.timeline
        if tl.selected is not None:
            a, b = tl.ranges[tl.selected]
            self.start_edit.set(a)
            self.end_edit.set(b)

    def _tone(self):
        key = self.tone.get()
        return ("silence", 1000) if key == "silence" else ("beep", 440 if key == "low" else 1000)

    def _play(self, bleeped: bool):
        tl = self.timeline
        if tl.selected is not None:
            a, b = tl.ranges[tl.selected]
        elif tl.ranges:
            a, b = tl.ranges[0]
        else:
            a, b = tl.playhead, tl.playhead
        w0, w1 = max(0.0, a - 1.5), min(self.duration, b + 1.5)
        graph = None
        if bleeped and tl.ranges:
            tone, freq = self._tone()
            shifted = [[x - w0, y - w0] for x, y in tl.ranges if y > w0 and x < w1]
            if shifted:
                graph = media.bleep_graph(shifted, self.info["rate"] or 48000, w1 - w0, tone, freq)
        self.play(w0, w1, "", graph)

    def params(self):
        if not self.timeline.ranges:
            return None
        tone, freq = self._tone()
        return {"ranges": sorted(self.timeline.ranges), "tone": tone, "frequency": freq}


def bleep(paths, parent=None):
    d = BleepDialog(paths[0])
    return d.params() if d.run() else None
