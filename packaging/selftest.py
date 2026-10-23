"""Checks a packaged build before it ships; not part of the installer.

    spinvert-selftest.exe [work folder]      every conversion and tool (the smoke test)
    spinvert-selftest.exe --player <video>   Qt Multimedia decodes frames and has sound
    spinvert-selftest.exe --share            uploading to the share server works over HTTPS
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


def share_check() -> int:
    """Upload a tiny picture to the share server over HTTPS, then delete it."""
    import io
    import urllib.request

    from PIL import Image

    from spinvert import share

    share.remember = lambda result: None  # not in the real history
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (124, 92, 255)).save(buf, "PNG")
    result = share.upload(buf.getvalue(), share.DEFAULT_SERVER)
    urllib.request.urlopen(urllib.request.Request(result["delete"], method="POST",
                                                  headers={"User-Agent": "Spinvert-selftest"}), timeout=30)
    print(f"share: uploaded and deleted {result['url']}")
    return 0


if __name__ == "__main__":
    if "--share" in sys.argv:
        raise SystemExit(share_check())
    if "--player" in sys.argv:
        raise SystemExit(player(sys.argv[sys.argv.index("--player") + 1]))
    import smoke_test

    raise SystemExit(smoke_test.main())
