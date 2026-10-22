"""The progress window: one row per job, with cancel and Show in folder."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from spinvert import system
from spinvert.theme import app_icon


class JobRow(QFrame):
    def __init__(self, title: str, on_cancel):
        super().__init__()
        self.outputs: list[Path] = []
        self.done = False
        self.failed = False
        self.title = QLabel(title)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.status = QLabel("Waiting…")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(placeholder-text);")
        self.button = QPushButton("Cancel")
        self.button.clicked.connect(self._clicked)
        self.on_cancel = on_cancel
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addLayout(top)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

    def set_progress(self, fraction: float):
        self.bar.setValue(int(fraction * 1000))
        self.status.setText(f"{int(fraction * 100)}%")

    def finish(self, outputs: list[str], error: str):
        self.done = True
        self.outputs = [Path(o) for o in outputs]
        if error == "cancelled":
            self.status.setText("Cancelled")
            self.bar.setValue(0)
            self.button.hide()
        elif error:
            self.failed = True
            self.status.setText(error)
            self.status.setStyleSheet("color: #E5484D;")
            self.button.hide()
        else:
            self.bar.setValue(1000)
            names = ", ".join(p.name for p in self.outputs[:3])
            more = f" and {len(self.outputs) - 3} more" if len(self.outputs) > 3 else ""
            self.status.setText(f"Saved {names}{more}")
            self.button.setText("Show in folder")

    def _clicked(self):
        if self.done:
            if self.outputs:
                system.show_in_explorer(self.outputs[0])
        else:
            self.button.setEnabled(False)
            self.status.setText("Cancelling…")
            self.on_cancel()


class ProgressWindow(QWidget):
    def __init__(self, jobs):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.jobs = jobs
        self.rows: dict[int, JobRow] = {}
        self.setWindowTitle("Spinvert")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(430, 380)
        self.header = QLabel("")
        self.header.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.list = QVBoxLayout()
        self.list.setSpacing(4)
        self.list.addStretch()
        holder = QWidget()
        holder.setLayout(self.list)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(holder)
        clear = QPushButton("Clear finished")
        clear.clicked.connect(self.clear_finished)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        bottom = QHBoxLayout()
        bottom.addWidget(clear)
        bottom.addStretch()
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(scroll, 1)
        layout.addLayout(bottom)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._auto_hide)
        jobs.progressed.connect(self._progress)
        jobs.finished.connect(self._finished)

    def add_job(self, job_id: int, title: str):
        self.hide_timer.stop()
        row = JobRow(title, lambda: self.jobs.cancel(job_id))
        self.rows[job_id] = row
        self.list.insertWidget(self.list.count() - 1, row)
        self._update_header()
        if not self.isVisible():
            self._place()
            self.show()

    def _place(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 16, screen.bottom() - self.height() - 48)

    def _progress(self, job_id: int, fraction: float):
        row = self.rows.get(job_id)
        if row and not row.done:
            row.set_progress(fraction)

    def _finished(self, job_id: int, outputs: list, error: str):
        row = self.rows.get(job_id)
        if row:
            row.finish(outputs, error)
        self._update_header()
        if all(r.done for r in self.rows.values()):
            if not any(r.failed for r in self.rows.values()):
                self.hide_timer.start(6000)

    def _update_header(self):
        rows = list(self.rows.values())
        running = sum(not r.done for r in rows)
        failed = sum(r.failed for r in rows)
        ok = sum(r.done and not r.failed and bool(r.outputs) for r in rows)
        if running:
            self.header.setText(f"Working on {running} job{'s' if running > 1 else ''}…")
        else:
            text = f"Done: {ok} saved"
            if failed:
                text += f", {failed} failed"
            self.header.setText(text)

    def _auto_hide(self):
        if not self.underMouse():
            self.hide()

    def clear_finished(self):
        for job_id, row in list(self.rows.items()):
            if row.done:
                row.deleteLater()
                del self.rows[job_id]
        self._update_header()
