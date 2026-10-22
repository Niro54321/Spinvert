"""The app: tray icon, drop window, single instance, and the glue between them."""

from __future__ import annotations

import ctypes
import getpass
import importlib
import json
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from spinvert import APP_NAME, __version__, glass, mainthread
from spinvert.catalog import detect_engines
from spinvert.dropwindow import DropWindow
from spinvert.jobs import JobManager
from spinvert.progress import ProgressWindow
from spinvert.settings import Settings
from spinvert.theme import app_icon
from spinvert.watcher import DragWatcher
from spinvert.wheel import KEY_NAMES, Wheel

SERVER_NAME = f"spinvert-{getpass.getuser()}"


class Controller(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.engines = detect_engines(self.settings)
        self.jobs = JobManager(self)
        self.progress = ProgressWindow(self.jobs)
        self.jobs.finished.connect(self._job_finished)
        self.wheel = Wheel(self)
        self.wheel.chosen.connect(self.run_choice)
        self.snapshot = None
        self.watcher = DragWatcher(lambda: self.settings, self.wheel.isVisible, self)
        self.watcher.pressed.connect(self._take_snapshot)
        self.watcher.triggered.connect(
            lambda mode: self.wheel.open_drag(mode, QCursor.pos(), self.snapshot))
        self.watcher.switched.connect(self.wheel.set_mode)
        self.watcher.released.connect(self.wheel.on_button_released)
        self.watcher.escaped.connect(self.wheel.close_wheel)
        self.drop_window = DropWindow(self)
        self.drop_window.place()
        self.batch_saved = 0
        self.batch_failed = 0
        self._told_running = False
        self._build_tray()
        self.watcher.start()

    def _take_snapshot(self, x: int, y: int):
        """The screen at the mouse press that may start a drag, before Explorer's
        drag image is drawn. Kept in memory only, for the wheel's glass."""
        try:
            self.snapshot = glass.snapshot_at(x, y)
        except Exception:
            self.snapshot = None

    # tray

    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} {__version__}: drag a file, press "
                             f"{KEY_NAMES[self.settings.convert_key]}")
        menu = QMenu()
        for text, slot in [("Open Spinvert", self.show_drop_window),
                           ("Settings…", self.show_settings),
                           ("Show progress", self.progress.show)]:
            action = QAction(text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_drop_window()

    def show_drop_window(self):
        if not self.drop_window.isVisible():
            self.drop_window.refresh_backdrop()  # while hidden, so the glass shows what's behind
        self.drop_window.show()
        self.drop_window.raise_()
        self.drop_window.activateWindow()

    def show_settings(self):
        from spinvert.dialogs import SettingsDialog

        SettingsDialog(self, self.drop_window if self.drop_window.isVisible() else None).exec()
        self.drop_window.update()

    def note_still_running(self):
        if not self._told_running:
            self._told_running = True
            self.tray.showMessage(APP_NAME, "Still running in the tray. Drag a file in Explorer "
                                  f"and press {KEY_NAMES[self.settings.convert_key]}.",
                                  app_icon(), 4000)

    def refresh_engines(self):
        self.engines = detect_engines(self.settings)

    # work

    def open_files(self, paths: list[Path]):
        paths = [p for p in paths if p.exists()]
        if paths:
            self.wheel.open_click(paths, "convert", QCursor.pos())

    def run_choice(self, choice):
        for op, inputs in choice.plan:
            params = {}
            if op.prepare:
                module, func = op.prepare.split(":")
                params = getattr(importlib.import_module(module), func)(inputs, None)
                if params is None:
                    continue
            job_id = self.jobs.submit(op, inputs, params)
            name = inputs[0].name if len(inputs) == 1 else f"{len(inputs)} files"
            self.progress.add_job(job_id, f"{name}  →  {choice.label}")

    def _job_finished(self, job_id, outputs, error):
        if error and error != "cancelled":
            self.batch_failed += 1
        elif outputs:
            self.batch_saved += 1
        if not self.jobs.busy():
            QTimer.singleShot(0, self._batch_done)

    def _batch_done(self):
        if self.jobs.busy():
            return
        saved, failed = self.batch_saved, self.batch_failed
        self.batch_saved = self.batch_failed = 0
        if self.progress.isVisible() and not failed:
            return  # the progress window already says it
        if saved or failed:
            text = f"{saved} saved" + (f", {failed} failed" if failed else "")
            self.tray.showMessage(APP_NAME, text, app_icon(), 3000)

    def quit(self):
        self.watcher.stop()
        self.jobs.shutdown()
        self.tray.hide()
        self.app.quit()


def _forward_to_running(args: list[str]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps(args).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _listen(controller: Controller) -> QLocalServer:
    server = QLocalServer(controller)
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def on_connection():
        conn = server.nextPendingConnection()
        chunks = []
        conn.readyRead.connect(lambda: chunks.append(bytes(conn.readAll())))

        def done():
            chunks.append(bytes(conn.readAll()))
            conn.deleteLater()
            try:
                args = json.loads(b"".join(chunks).decode("utf-8") or "[]")
            except ValueError:
                return
            _handle_args(controller, args)
        conn.disconnected.connect(done)

    server.newConnection.connect(on_connection)
    return server


def _handle_args(controller: Controller, args: list[str]):
    files = [Path(a) for a in args if not a.startswith("--")]
    if files:
        controller.open_files(files)
    elif "--background" not in args:
        controller.show_drop_window()


def main() -> int:
    if sys.platform != "win32":
        print("Spinvert runs on Windows.")
        return 1
    args = sys.argv[1:]
    # Our own app ID, so the taskbar shows Spinvert's icon instead of grouping
    # the window under pythonw.exe with Python's logo.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Niro54321.Spinvert")
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    if _forward_to_running(args):
        return 0
    mainthread.install()
    controller = Controller(app)
    server = _listen(controller)  # noqa: F841 (kept alive for the app's lifetime)
    if not controller.engines["ffmpeg"]:
        controller.tray.showMessage(APP_NAME, "FFmpeg not found, so audio and video are off. "
                                    "Install it with: winget install Gyan.FFmpeg",
                                    QSystemTrayIcon.MessageIcon.Warning, 8000)
    elif not controller.settings.welcomed:
        controller.settings.welcomed = True
        controller.settings.save()
        controller.tray.showMessage(APP_NAME, "Ready. Drag a file in File Explorer, then press "
                                    f"{KEY_NAMES[controller.settings.convert_key]}.", app_icon(), 5000)
    _handle_args(controller, args)
    return app.exec()
