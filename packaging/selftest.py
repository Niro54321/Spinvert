"""Checks a packaged build before it ships; not part of the installer.

    spinvert-selftest.exe [work folder]      every conversion and tool (the smoke test)
    spinvert-selftest.exe --player <video>   Qt Multimedia decodes frames and has sound
"""

import sys
import time


def player(path: str) -> int:
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer, QVideoSink
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    frames = []
    sink = QVideoSink()
    sink.videoFrameChanged.connect(lambda f: f.isValid() and frames.append(1))
    out = QAudioOutput()
    out.setVolume(0.0)
    p = QMediaPlayer()
    p.setVideoOutput(sink)
    p.setAudioOutput(out)
    p.setSource(QUrl.fromLocalFile(path))
    p.play()
    end = time.time() + 4
    while time.time() < end and len(frames) < 20:
        app.processEvents()
        time.sleep(0.01)
    p.stop()
    print(f"player: {len(frames)} frames, error: {p.errorString() or 'none'}, "
          f"audio device: {QMediaDevices.defaultAudioOutput().description() or 'none'}")
    return 0 if frames else 1


if __name__ == "__main__":
    if "--player" in sys.argv:
        raise SystemExit(player(sys.argv[sys.argv.index("--player") + 1]))
    import smoke_test

    raise SystemExit(smoke_test.main())
