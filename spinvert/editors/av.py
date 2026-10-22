"""Video and audio editors: trim and edit (text, pictures and sound on the
video, save speed), crop or fit for Reels and more, speed, frames, split,
redact, normalize, visualizer, channels and bleep.

Every editor with a video or a recording plays it with sound: Play/Pause,
10 seconds back and forward, preview speed; Space plays or pauses and the
arrow keys jump 10 seconds.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QListWidget, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from spinvert import layers as L
from spinvert.editors.annotate import LayerCanvas, LayerList, Properties, side_panel
from spinvert.editors.base import (Background, BoxesTool, CropTool, GlassDialog, ImageCanvas, Segmented,
                                   SliderRow, TimeEdit, Timeline, busy, fmt_time, label, play_wav,
                                   qimage_from_png, stop_sound, to_qimage)
from spinvert.editors.pickers import Swatches
from spinvert.editors.player import Player, TransportBar
from spinvert.engines import imaging, media
from spinvert.settings import Settings

SPEEDS = [("0.25", "0.25×"), ("0.5", "0.5×"), ("0.75", "0.75×"), ("1", "Normal"), ("1.5", "1.5×"), ("2", "2×"),
          ("3", "3×"), ("4", "4×")]


def _custom() -> str:
    return Settings.load().ffmpeg_path


def _buttons(*pairs) -> QHBoxLayout:
    row = QHBoxLayout()
    for text, fn in pairs:
        b = QPushButton(text)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(fn)
        row.addWidget(b)
    return row


def _panel(*items) -> QWidget:
    """A column of widgets and layouts, for the side panel."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for item in items:
        if isinstance(item, QWidget):
            lay.addWidget(item)
        else:
            lay.addLayout(item)
    lay.addStretch()
    return box


class MediaDialog(GlassDialog):
    """Plays the file with sound and keeps the timeline in step with it."""

    def __init__(self, title: str, path: Path, mode: str = "range", size=(1180, 820),
                 primary: str = "Save copy", start_at: float | None = None):
        super().__init__(title, size, primary)
        from PySide6.QtMultimedia import QMediaPlayer

        self.path = path
        self.custom = _custom()
        self.info = busy(lambda: media.info(path, self.custom))
        self.duration = self.info["duration"] or 0.1
        self.video = bool(self.info["video"])
        self.screen = None
        self.effect = None
        self.last_frame = QImage()
        self.timeline = Timeline(self.duration, mode)
        self.timeline.setMinimumHeight(90 if self.video else 150)
        self._strip = Background()
        self._strip.done.connect(lambda data, err: data and self.timeline.set_background(qimage_from_png(data)))
        if self.video:
            self._strip.start(lambda: media.strip_png(path, self.duration, 14, 64, self.custom))
        else:
            self._strip.start(lambda: media.waveform_png(path, 1600, 200, "#FFFFFF", self.custom))
        self.player = Player(path, video=self.video, parent=self)
        self.player.frame.connect(self._frame)
        self.player.position.connect(self._position)
        self.timeline.scrubbed.connect(self.player.seek)
        self.transport = TransportBar(self.player, self.duration, self)
        self._start_at = start_at if start_at is not None else (0.0 if mode == "range" else self.duration / 2)
        self.timeline.playhead = self._start_at
        self.player.player.mediaStatusChanged.connect(
            lambda s: s == QMediaPlayer.MediaStatus.LoadedMedia and self._loaded())

    def _loaded(self):
        self.player.seek(self._start_at)
        self.player.pause()  # shows the frame without playing

    def _frame(self, img: QImage):
        if img.width() > 1280:
            img = img.scaledToWidth(1280, Qt.TransformationMode.SmoothTransformation)
        self.last_frame = img
        self.show_frame(img)

    def show_frame(self, img: QImage):
        if self.screen is not None:
            self.screen.set_image(self.effect(img) if self.effect else img)

    def refresh_frame(self):
        if not self.last_frame.isNull():
            self.show_frame(self.last_frame)

    def _position(self, t: float):
        if self.timeline._drag is None:
            self.timeline.playhead = t
            self.timeline.update()
        self.on_time(t)

    def on_time(self, t: float):
        pass

    def now(self) -> float:
        return self.timeline.playhead

    def step_frame(self, direction: int):
        self.player.pause()
        self.player.seek(self.now() + direction / (self.info["fps"] or 25))

    def play_preview(self, start: float, end: float, af: str = "", graph=None):
        """A filtered preview (e.g. bleeped) through Windows' sound player."""
        self.player.pause()
        try:
            play_wav(busy(lambda: media.preview_wav(self.path, start, end, af, graph, self.custom)))
        except Exception as e:  # a preview is a convenience; say why it didn't play
            if hasattr(self, "status"):
                self.status.setText(f"Couldn't play the preview: {e}")

    def done(self, result):
        self.player.close()
        stop_sound()
        super().done(result)


def _range_row(dialog, timeline: Timeline, with_frames: bool):
    """Start and end fields, the kept length and 'here' buttons for a range timeline."""
    dialog.start_edit, dialog.end_edit = TimeEdit(0), TimeEdit(dialog.duration)
    dialog.length = label("", bold=True)

    def set_range(start, end):
        if start is not None:
            timeline.start = min(max(0.0, start), timeline.end - 0.05)
        if end is not None:
            timeline.end = max(min(dialog.duration, end), timeline.start + 0.05)
        timeline.update()
        sync()

    def sync():
        dialog.start_edit.set(timeline.start)
        dialog.end_edit.set(timeline.end)
        dialog.length.setText(f"Keeps {fmt_time(timeline.end - timeline.start)}")

    dialog.start_edit.changed.connect(lambda v: set_range(v, None))
    dialog.end_edit.changed.connect(lambda v: set_range(None, v))
    timeline.changed.connect(sync)
    row = QHBoxLayout()
    row.addWidget(label("Start"))
    row.addWidget(dialog.start_edit)
    row.addWidget(label("End"))
    row.addWidget(dialog.end_edit)
    row.addWidget(dialog.length)
    row.addStretch()
    if with_frames:
        row.addLayout(_buttons(("◀ Frame", lambda: dialog.step_frame(-1)), ("Frame ▶", lambda: dialog.step_frame(1))))
    row.addLayout(_buttons(("Start here", lambda: set_range(dialog.now(), None)),
                           ("End here", lambda: set_range(None, dialog.now())),
                           ("▶ Selection", lambda: dialog.player.play_range(timeline.start, timeline.end))))
    sync()
    dialog.set_range = set_range
    return row


def _save_options(dialog, has_audio: bool) -> QWidget:
    dialog.speed = Segmented(SPEEDS, "1", wrap=4)
    dialog.keep_pitch = QCheckBox("Keep the voice's pitch")
    dialog.keep_pitch.setChecked(True)
    dialog.fade_in = SliderRow("Fade in", 0, 100, 0, " s", scale=10, width=64)
    dialog.fade_out = SliderRow("Fade out", 0, 100, 0, " s", scale=10, width=64)
    items = [label("Save at speed", bold=True), dialog.speed]
    if has_audio:
        items += [dialog.keep_pitch, dialog.fade_in, dialog.fade_out]
    return _panel(*items)


# ------------------------------------------------------------- trim & edit

class VideoEditDialog(MediaDialog):
    """Trim, and put text, pictures and sound on the video."""

    def __init__(self, path):
        super().__init__("Trim & edit video", path, "range", (1340, 900), "Save video", start_at=0.0)
        w, h = self.info["width"] or 16, self.info["height"] or 9
        blank = QImage(w, h, QImage.Format.Format_ARGB32)
        blank.fill(QColor("black"))
        self.canvas = LayerCanvas(blank)
        self.canvas.time = 0.0
        self.canvas.edited.connect(self._stamp_layers)
        self.canvas.selection.connect(self._layer_picked)
        self.layer_list = LayerList(self.canvas)
        self.props = Properties(self.canvas)
        self.tools = Segmented([("select", "↖ Select"), ("text", "+ Text")], "select")
        self.tools.changed.connect(self._tool)
        # the selected layer's time range
        self.layer_from, self.layer_to = TimeEdit(0), TimeEdit(self.duration)
        self.layer_from.changed.connect(lambda v: self._layer_time(v, None))
        self.layer_to.changed.connect(lambda v: self._layer_time(None, v))
        self.layer_time = _panel(label("Selected layer shows", bold=True),
                                 self._row(label("from"), self.layer_from, label("to"), self.layer_to),
                                 _buttons(("From here", lambda: self._layer_time(self.now(), None)),
                                          ("Until here", lambda: self._layer_time(None, self.now())),
                                          ("Whole video", lambda: self._layer_time(0.0, self.duration))))
        self.layer_time.setVisible(False)
        # sound tracks
        self.tracks = []
        self.track_list = QListWidget()
        self.track_list.setFixedHeight(90)
        self.track_list.currentRowChanged.connect(self._track_picked)
        self.track_at = TimeEdit(0)
        self.track_at.changed.connect(lambda v: self._track_set("at", v))
        self.track_volume = SliderRow("Volume", 0, 200, 100, "%", width=60)
        self.track_volume.changed.connect(lambda v: self._track_set("volume", v))
        self.mute = QCheckBox("Mute the video's own sound")
        sound = _panel(label("Sound", bold=True),
                       _buttons(("+ Add sound…", self._add_track), ("Remove", self._remove_track)),
                       self.track_list, self._row(label("Starts at"), self.track_at,
                                                  _buttons(("Here", lambda: self._track_set("at", self.now())))),
                       self.track_volume, self.mute)
        right = _panel(_save_options(self, True), self.layer_time, self.props, sound)
        # layout
        middle = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.canvas, 1)
        left.addWidget(self.transport)
        left.addWidget(self.timeline)
        left.addLayout(_range_row(self, self.timeline, True))
        layers_row = QHBoxLayout()
        layers_row.addWidget(self.tools)
        layers_row.addLayout(_buttons(("+ Picture…", self._picture)))
        layers_row.addWidget(self.layer_list, 1)
        layers_row.addLayout(_buttons(("Delete", self.canvas.delete)))
        left.addLayout(layers_row)
        middle.addLayout(left, 1)
        middle.addWidget(side_panel(right, 340))
        self.body.addLayout(middle, 1)
        self.footer_left.addWidget(label("Space plays or pauses, ← → jump 10 s. Text and pictures can be "
                                         "dragged on the video.", muted=True))

    @staticmethod
    def _row(*items) -> QHBoxLayout:
        row = QHBoxLayout()
        for item in items:
            if isinstance(item, QWidget):
                row.addWidget(item)
            else:
                row.addLayout(item)
        row.addStretch()
        return row

    def show_frame(self, img: QImage):
        self.canvas.image = img
        self.canvas.update()

    def on_time(self, t: float):
        self.canvas.time = t
        self.canvas.update()

    def _tool(self, key):
        self.canvas.finish_text()
        self.canvas.tool = key
        if key != "select":
            self.canvas.select(None)
        self.props.load()

    def _stamp_layers(self):
        for layer in self.canvas.layers:  # new layers show for the whole video until changed
            layer.setdefault("start", 0.0)
            layer.setdefault("end", self.duration)

    def _layer_picked(self, layer):
        self.layer_time.setVisible(layer is not None)
        if layer is not None:
            self._stamp_layers()
            self.layer_from.set(layer["start"])
            self.layer_to.set(layer["end"])

    def _layer_time(self, start, end):
        layer = self.canvas.current
        if layer is None:
            return
        self._stamp_layers()
        if start is not None:
            layer["start"] = max(0.0, min(start, layer["end"] - 0.05))
        if end is not None:
            layer["end"] = min(self.duration, max(end, layer["start"] + 0.05))
        self._layer_picked(layer)
        self.canvas.commit()

    def _picture(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add a picture", "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.heic *.bmp *.gif *.svg)")
        if path:
            img = L._image(path)
            aspect = img.width() / img.height() if not img.isNull() and img.height() else 1.0
            self.canvas.add(L.new("image", path=path, points=[[0.6, 0.6]], w=0.3, aspect=aspect,
                                  start=0.0, end=self.duration))

    def _add_track(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add sound", "",
                                              "Sound (*.mp3 *.m4a *.wav *.flac *.ogg *.opus *.aac *.wma *.aiff "
                                              "*.mp4 *.mov *.mkv)")
        if path:
            self.tracks.append({"path": path, "at": self.now(), "volume": 100})
            self._show_tracks(len(self.tracks) - 1)

    def _remove_track(self):
        row = self.track_list.currentRow()
        if 0 <= row < len(self.tracks):
            self.tracks.pop(row)
            self._show_tracks(min(row, len(self.tracks) - 1))

    def _show_tracks(self, select: int):
        self.track_list.blockSignals(True)
        self.track_list.clear()
        for t in self.tracks:
            self.track_list.addItem(f"♪ {Path(t['path']).name}  from {fmt_time(t['at'])}  {t['volume']}%")
        self.track_list.blockSignals(False)
        if 0 <= select < len(self.tracks):
            self.track_list.setCurrentRow(select)

    def _track_picked(self, row):
        if 0 <= row < len(self.tracks):
            self.track_at.set(self.tracks[row]["at"])
            self.track_volume.set(self.tracks[row]["volume"], quiet=True)

    def _track_set(self, key, value):
        row = self.track_list.currentRow()
        if 0 <= row < len(self.tracks):
            self.tracks[row][key] = value
            self._show_tracks(row)

    def accept(self):
        self.canvas.finish_text()
        super().accept()

    def params(self) -> dict:
        self._stamp_layers()
        tl = self.timeline
        return {"start": tl.start, "end": tl.end, "speed": float(self.speed.get() or 1),
                "keep_pitch": self.keep_pitch.isChecked(), "fade_in": self.fade_in.get() / 10,
                "fade_out": self.fade_out.get() / 10, "layers": [dict(x) for x in self.canvas.layers],
                "tracks": [dict(t) for t in self.tracks], "mute_original": self.mute.isChecked()}


class AudioTrimDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Trim audio", path, "range", (1120, 700), "Trim", start_at=0.0)
        self.body.addWidget(self.transport)
        self.body.addWidget(self.timeline, 1)
        self.body.addLayout(_range_row(self, self.timeline, False))
        options = QHBoxLayout()
        options.addWidget(_save_options(self, True), 1)
        options.addLayout(_buttons(("Remove silence at the ends", self._silence)))
        self.body.addLayout(options)
        self.status = label("Drag the white handles or type exact times. Space plays, ← → jump 10 s.", muted=True)
        self.body.addWidget(self.status)

    def _silence(self):
        start, end = busy(lambda: media.silence_edges(self.path, self.custom))
        self.set_range(start, end)
        self.status.setText("Silence at the start and end is now outside the selection.")

    def params(self) -> dict:
        tl = self.timeline
        return {"start": tl.start, "end": tl.end, "speed": float(self.speed.get() or 1),
                "keep_pitch": self.keep_pitch.isChecked(), "fade_in": self.fade_in.get() / 10,
                "fade_out": self.fade_out.get() / 10}


def trim(paths, parent=None):
    info = busy(lambda: media.info(paths[0], _custom()))
    d = VideoEditDialog(paths[0]) if info["video"] else AudioTrimDialog(paths[0])
    return d.params() if d.run() else None


# ------------------------------------------------------------- crop / fit

PRESETS = [("9:16", "Reels / TikTok 9:16", (1080, 1920)), ("1:1", "Square 1:1", (1080, 1080)),
           ("4:5", "Portrait 4:5", (1080, 1350)), ("16:9", "Landscape 16:9", (1920, 1080)),
           ("free", "Free", None)]


class VideoCropDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Crop video", path, "point", (1240, 860), "Save video")
        self.screen = ImageCanvas((480, 300))
        self.tool = CropTool()
        self.screen.set_tool(self.tool)
        self.background = {"kind": "blur", "blur": 40}
        self.presets = Segmented([(k, text) for k, text, _ in PRESETS], "9:16")
        self.presets.changed.connect(self._preset)
        self.mode = Segmented([("fill", "Crop to fill"), ("fit", "Fit, with a background")], "fill")
        self.mode.changed.connect(self._mode)
        self.exact = QCheckBox("Output size")
        self.exact.setChecked(True)
        self.out_w, self.out_h = QSpinBox(), QSpinBox()
        for box in (self.out_w, self.out_h):
            box.setRange(16, 8192)
            box.valueChanged.connect(lambda *_: self.refresh_frame())
        grads = Swatches([(n, c) for n, c in imaging.GRADIENTS.items()], None, size=28, wrap=6, gradient=True)
        solids = Swatches([(c, c) for c in imaging.SOLIDS], None, size=28, wrap=6)
        grads.changed.connect(lambda k: (solids.clear(), self._set_bg(_gradient_key(k))))
        solids.changed.connect(lambda c: (grads.clear(), self._set_bg({"kind": "solid", "color": c})))
        self.blur = SliderRow("Blur", 0, 100, 40, width=50)
        self.blur.changed.connect(lambda v: (self.background.__setitem__("blur", v), self.refresh_frame()))
        self.bg_panel = _panel(label("Background", bold=True),
                               _buttons(("Blurred video", lambda: (grads.clear(), solids.clear(),
                                                                    self._set_bg({"kind": "blur",
                                                                                  "blur": self.blur.get()}))),
                                        ("Image…", lambda: self._pick(grads, solids))),
                               self.blur, label("Gradients"), grads, label("Colours"), solids)
        self.bg_panel.setVisible(False)
        size_row = QHBoxLayout()
        size_row.addWidget(self.exact)
        size_row.addWidget(self.out_w)
        size_row.addWidget(label("×"))
        size_row.addWidget(self.out_h)
        size_row.addStretch()
        left = QVBoxLayout()
        left.addWidget(self.screen, 1)
        left.addWidget(self.transport)
        left.addWidget(self.timeline)
        left.addWidget(self.presets)
        left.addWidget(self.mode)
        left.addLayout(size_row)
        main = QHBoxLayout()
        main.addLayout(left, 1)
        main.addWidget(side_panel(self.bg_panel, 330))
        self.body.addLayout(main, 1)
        self.footer_left.addWidget(label(f"Original {self.info['width']} × {self.info['height']}. "
                                         "The sound is kept.", muted=True))
        self._preset("9:16")

    def _out_size(self):
        return self.out_w.value(), self.out_h.value()

    def show_frame(self, img: QImage):
        first = self.screen.image.isNull()
        super().show_frame(img)
        if first and self.mode.get() == "fill":  # the crop box needs the real picture shape
            self._preset(self.presets.get())

    def _preset(self, key):
        for k, _, size in PRESETS:
            if k == key:
                if size:
                    self.out_w.setValue(size[0])
                    self.out_h.setValue(size[1])
                    self.exact.setChecked(True)
                    self.tool.set_aspect(size[0] / size[1])
                else:
                    self.tool.set_aspect(None)
                    self.exact.setChecked(False)
        self.screen.update()
        self.refresh_frame()

    def _mode(self, key):
        fit = key == "fit"
        self.bg_panel.setVisible(fit)
        self.screen.set_tool(None if fit else self.tool)
        self.effect = self._fit_preview if fit else None
        self.refresh_frame()

    def _set_bg(self, bg):
        self.background = bg
        self.refresh_frame()

    def _pick(self, grads, solids):
        path, _ = QFileDialog.getOpenFileName(self, "Background image", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.heic *.bmp)")
        if path:
            grads.clear()
            solids.clear()
            self._set_bg({"kind": "image", "path": path})

    def _fit_preview(self, img: QImage) -> QImage:
        W, H = self._out_size()
        k = 720 / max(W, H)
        pw, ph = max(2, round(W * k)), max(2, round(H * k))
        frame = L.to_pil(img).convert("RGB")
        canvas = imaging._background(self.background, (pw, ph), frame, max(pw, ph) / 1000)
        fg = ImageOps.contain(frame, (pw, ph), Image.Resampling.LANCZOS)
        canvas.paste(fg, ((pw - fg.width) // 2, (ph - fg.height) // 2))
        return to_qimage(canvas)

    def params(self) -> dict:
        if self.mode.get() == "fit":
            return {"mode": "fit", "size": list(self._out_size()), "background": dict(self.background)}
        p = {"mode": "fill", "rect": list(self.tool.rect)}
        if self.exact.isChecked():
            p["size"] = list(self._out_size())
        return p


def _gradient_key(key: str) -> dict:
    from spinvert.editors.photo import background_from_key

    return background_from_key(key)


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
        self.screen = ImageCanvas((480, 270))
        self.body.addWidget(self.screen, 1)
        self.body.addWidget(self.transport)
        self.body.addWidget(self.timeline)
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
        self.list = label("No frames picked yet. Pause on a frame and press Add.", muted=True)
        self.body.addWidget(self.list)

    def _add(self):
        t = round(self.now(), 3)
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
        return {"times": self.timeline.points or [self.now()]}


def frames(paths, parent=None):
    d = FramesDialog(paths[0])
    return d.params() if d.run() else None


# ----------------------------------------------------------------- split

class SplitDialog(MediaDialog):
    def __init__(self, path):
        super().__init__("Split", path, "points", primary="Split")
        if self.video:
            self.screen = ImageCanvas((480, 270))
            self.body.addWidget(self.screen, 1)
        self.body.addWidget(self.transport)
        self.body.addWidget(self.timeline, 0 if self.video else 1)
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
        t = round(self.now(), 3)
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
        return {"mode": self.mode.get(), "parts": self.parts.value(), "every": self.every.value(),
                "points": list(self.timeline.points), "fast": bool(self.fast and self.fast.isChecked())}


def split(paths, parent=None):
    d = SplitDialog(paths[0])
    return d.params() if d.run() else None


# ---------------------------------------------------------------- redact

REDACT_COLORS = ["#000000", "#FFFFFF", "#FF3B30", "#7C5CFF", "#FFCC00", "#34C759"]


class RedactVideoDialog(MediaDialog):
    """Boxes with their own time ranges; the effect plays live in the preview."""

    def __init__(self, path):
        super().__init__("Redact video", path, "point", (1180, 860), "Save video")
        self.style, self.color, self.strength = "blur", "#000000", 60
        self.screen = ImageCanvas((480, 270))
        self.tool = BoxesTool(lambda: {"style": self.style, "color": self.color, "strength": self.strength,
                                       "start": 0.0, "end": self.duration})
        self.screen.set_tool(self.tool)
        self.screen.changed.connect(self._changed)
        self.effect = self._apply
        styles = Segmented([("blur", "Blur"), ("pixelate", "Pixelate"), ("solid", "Solid colour")], "blur")
        styles.changed.connect(lambda k: self._set("style", k))
        colors = Swatches([(c, c) for c in REDACT_COLORS], "#000000", size=26, wrap=8)
        colors.changed.connect(lambda c: self._set("color", c))
        strength = SliderRow("Strength", 1, 100, 60, "%", width=70)
        strength.changed.connect(lambda v: self._set("strength", v))
        self.start_edit, self.end_edit = TimeEdit(0), TimeEdit(self.duration)
        self.start_edit.changed.connect(lambda v: self._range(v, None))
        self.end_edit.changed.connect(lambda v: self._range(None, v))
        self.body.addWidget(self.screen, 1)
        self.body.addWidget(self.transport)
        self.body.addWidget(self.timeline)
        row = QHBoxLayout()
        row.addWidget(styles)
        row.addWidget(strength, 1)
        row.addWidget(label("Colour"))
        row.addWidget(colors)
        self.body.addLayout(row)
        times = QHBoxLayout()
        times.addWidget(label("Selected box shows from"))
        times.addWidget(self.start_edit)
        times.addWidget(label("to"))
        times.addWidget(self.end_edit)
        times.addStretch()
        times.addLayout(_buttons(("From here", lambda: self._range(self.now(), None)),
                                 ("Until here", lambda: self._range(None, self.now())),
                                 ("Whole video", lambda: self._range(0.0, self.duration)),
                                 ("Delete box", self._delete)))
        self.body.addLayout(times)
        self.body.addWidget(label("Drag over the area to hide. Drag a box to move it, its corners to resize "
                                  "it; Delete removes it.", muted=True))

    def _apply(self, img: QImage) -> QImage:
        t = self.now()
        boxes = [b for b in self.tool.boxes if b["start"] <= t <= b["end"]]
        if not boxes:
            return img
        return to_qimage(imaging.redact(L.to_pil(img), boxes))

    def _box(self):
        return self.tool.boxes[self.tool.selected] if self.tool.selected is not None else None

    def _changed(self):
        box = self._box()
        if box:
            self.start_edit.set(box["start"])
            self.end_edit.set(box["end"])
        self.refresh_frame()

    def _set(self, key, value):
        setattr(self, key, value)
        if self._box():
            self._box()[key] = value
        self.refresh_frame()

    def _range(self, start, end):
        box = self._box()
        if not box:
            return
        if start is not None:
            box["start"] = max(0.0, min(start, box["end"] - 0.05))
        if end is not None:
            box["end"] = min(self.duration, max(end, box["start"] + 0.05))
        self._changed()

    def _delete(self):
        if self.tool.selected is not None:
            self.tool.boxes.pop(self.tool.selected)
            self.tool.selected = None
            self.refresh_frame()

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
        waves = Swatches([(c, c) for c in ("#FFFFFF", "#FFCC00", "#34D399", "#06B6D4", "#F472B6", "#7C5CFF",
                                           "#111114")], "#FFFFFF", size=26, wrap=8)
        backs = Swatches([(c, c) for c in ("#16161D", "#0F2027", "#3F6FE0", "#7A4FD8", "#F4D35E", "#FFFFFF")],
                         "#16161D", size=26, wrap=7)
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
        super().__init__("Bleep", path, "ranges", (1120, 720), "Save copy", start_at=0.0)
        tl = self.timeline
        self.body.addWidget(self.transport)
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
        self.body.addLayout(_buttons(("▶ Hear it bleeped", lambda: self._play(True)),
                                     ("▶ Hear the original", lambda: self._play(False)), ("■ Stop", stop_sound)))
        self.status = label("Play or click on the waveform, then + Bleep here. Drag a red range to move it, "
                            "or its edges to fine-tune.", muted=True)
        self.body.addWidget(self.status)
        tl.changed.connect(self._sync)

    def _add(self):
        tl = self.timeline
        a = self.now()
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
            a, b = self.now(), self.now()
        w0, w1 = max(0.0, a - 1.5), min(self.duration, b + 1.5)
        graph = None
        if bleeped and tl.ranges:
            tone, freq = self._tone()
            shifted = [[x - w0, y - w0] for x, y in tl.ranges if y > w0 and x < w1]
            if shifted:
                graph = media.bleep_graph(shifted, self.info["rate"] or 48000, w1 - w0, tone, freq)
        self.play_preview(w0, w1, "", graph)

    def params(self):
        if not self.timeline.ranges:
            return None
        tone, freq = self._tone()
        return {"ranges": sorted(self.timeline.ranges), "tone": tone, "frequency": freq}


def bleep(paths, parent=None):
    d = BleepDialog(paths[0])
    return d.params() if d.run() else None
