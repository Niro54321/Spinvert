"""Run a function on the Qt main thread from a job thread, and wait for it.

Some Qt classes (text layout, PDF painting) are safest on the main thread.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal, Slot


class _Invoker(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.ConnectionType.BlockingQueuedConnection)

    @Slot(object)
    def _run(self, box):
        try:
            box["result"] = box["fn"]()
        except BaseException as e:
            box["error"] = e


_invoker: _Invoker | None = None


def install() -> None:
    """Call once from the main thread, after the QApplication exists."""
    global _invoker
    _invoker = _Invoker()


def run_in_main(fn):
    app = QCoreApplication.instance()
    if _invoker is None or app is None or QThread.currentThread() == app.thread():
        return fn()
    box = {"fn": fn}
    _invoker.call.emit(box)
    if "error" in box:
        raise box["error"]
    return box.get("result")
