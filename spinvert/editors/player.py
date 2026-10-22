"""Playback with sound for the video and audio editors (Qt Multimedia), and the
transport bar: play/pause, 10 s back and forward, speed, time. Space plays or
pauses; the left and right arrows jump 10 seconds."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_FFMPEG_DEBUG", "0")

from PySide6.QtCore import QObject, Qt, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QImage, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget  # noqa: E402

from spinvert.editors.base import Segmented, fmt_time  # noqa: E402


class Player(QObject):
    """A file playing with sound. Emits each video frame and the position (s)."""

    frame = Signal(QImage)
    position = Signal(float)
    playing = Signal(bool)

    def __init__(self, path: Path, video: bool = True, parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player.setAudioOutput(self.audio)
        if video:
            self.sink = QVideoSink(self)
            self.sink.videoFrameChanged.connect(self._frame)
            self.player.setVideoSink(self.sink)
        self.player.positionChanged.connect(lambda ms: self._moved(ms / 1000))
        self.player.playbackStateChanged.connect(
            lambda s: self.playing.emit(s == QMediaPlayer.PlaybackState.PlayingState))
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.stop_at = None  # pause when reaching this time (play selection)

    def _frame(self, frame):
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.frame.emit(image)

    def _moved(self, seconds: float):
        if self.stop_at is not None and seconds >= self.stop_at:
            self.stop_at = None
            self.player.pause()
        self.position.emit(seconds)

    @property
    def is_playing(self) -> bool:
        from PySide6.QtMultimedia import QMediaPlayer

        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle(self):
        if self.is_playing:
            self.player.pause()
        else:
            self.stop_at = None
            self.player.play()

    def play_range(self, start: float, end: float):
        self.seek(start)
        self.stop_at = end
        self.player.play()

    def pause(self):
        self.player.pause()

    def seek(self, seconds: float):
        self.player.setPosition(int(max(0.0, seconds) * 1000))

    def skip(self, delta: float):
        self.seek(self.player.position() / 1000 + delta)

    def set_rate(self, rate: float):
        self.player.setPlaybackRate(rate)

    def close(self):
        self.player.stop()
        self.player.setSource(QUrl())


class TransportBar(QWidget):
    """⏪ 10 s · ▶/⏸ · 10 s ⏩ · time · speed. Keyboard: Space, ←, →."""

    def __init__(self, player: Player, duration: float, window: QWidget, speeds=True):
        super().__init__()
        self.player, self.duration = player, duration
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.back = QPushButton("« 10 s")
        self.back.setToolTip("Back 10 seconds (←)")
        self.play = QPushButton()
        self.play.setProperty("primary", True)
        self.play.setMinimumWidth(92)
        self.play.setToolTip("Play or pause (Space)")
        self.forward = QPushButton("10 s »")
        self.forward.setToolTip("Forward 10 seconds (→)")
        self.time = QLabel()
        self.time.setMinimumWidth(150)
        for b in (self.back, self.play, self.forward):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.back.clicked.connect(lambda: player.skip(-10))
        self.forward.clicked.connect(lambda: player.skip(10))
        self.play.clicked.connect(player.toggle)
        lay.addWidget(self.back)
        lay.addWidget(self.play)
        lay.addWidget(self.forward)
        lay.addWidget(self.time)
        lay.addStretch()
        if speeds:
            lay.addWidget(QLabel("Preview speed"))
            self.speed = Segmented([("0.5", "0.5×"), ("1", "1×"), ("1.5", "1.5×"), ("2", "2×"), ("3", "3×"),
                                    ("4", "4×")], "1")
            self.speed.changed.connect(lambda k: player.set_rate(float(k)))
            for b in self.speed.buttons.values():
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            lay.addWidget(self.speed)
        player.playing.connect(self._state)
        player.position.connect(self._time)
        self._state(False)
        self._time(0.0)
        for key, fn in ((Qt.Key.Key_Space, player.toggle), (Qt.Key.Key_Left, lambda: player.skip(-10)),
                        (Qt.Key.Key_Right, lambda: player.skip(10))):
            shortcut = QShortcut(QKeySequence(key), window)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(fn)

    def _state(self, playing: bool):
        self.play.setText("❚❚  Pause" if playing else "▶  Play")

    def _time(self, seconds: float):
        self.time.setText(f"{fmt_time(seconds)} / {fmt_time(self.duration)}")
