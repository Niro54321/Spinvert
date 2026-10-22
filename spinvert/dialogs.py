"""Dialogs: settings, and the page order for "Reorder"."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSlider,
                               QVBoxLayout)

from spinvert import system
from spinvert.glassui import MARGIN, GlassFrame
from spinvert.settings import KEYS
from spinvert.theme import app_icon
from spinvert.util import find_ffmpeg

KEY_LABELS = {"shift": "Shift", "ctrl": "Ctrl", "alt": "Alt"}
QUALITY_LABELS = {"high": "High (bigger files)", "balanced": "Balanced", "small": "Small files"}
ENGINE_LABELS = [("ffmpeg", "FFmpeg"), ("pandoc", "Pandoc"), ("word", "Word"),
                 ("powerpoint", "PowerPoint"), ("excel", "Excel")]


class ReorderDialog(QDialog):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        from spinvert.engines.pdfs import thumbnails

        self.setWindowTitle(f"Reorder pages: {path.name}")
        self.setWindowIcon(app_icon())
        self.resize(820, 560)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(130, 180))
        self.list.setGridSize(QSize(160, 230))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Snap)
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for i, image in enumerate(thumbnails(path)):
            buf = BytesIO()
            image.convert("RGB").save(buf, "PNG")
            pm = QPixmap()
            pm.loadFromData(buf.getvalue())
            item = QListWidgetItem(QIcon(pm), f"Page {i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)

        hint = QLabel("Drag pages into the new order. Select pages and press Remove to leave them out.")
        hint.setWordWrap(True)
        reverse = QPushButton("Reverse")
        reverse.clicked.connect(self._reverse)
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save a copy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(reverse)
        row.addWidget(remove)
        row.addStretch()
        row.addWidget(buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.list)
        layout.addLayout(row)

    def _reverse(self):
        items = [self.list.takeItem(0) for _ in range(self.list.count())]
        for item in reversed(items):
            self.list.addItem(item)

    def _remove(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def order(self) -> list[int]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]


def ask_page_order(inputs: list[Path], parent=None):
    """prepare hook for the Reorder tool: returns params, or None to cancel."""
    dialog = ReorderDialog(inputs[0], parent)
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    order = dialog.order()
    if not order:
        QMessageBox.information(parent, "Spinvert", "No pages left, so nothing was saved.")
        return None
    return {"order": order}


class SettingsDialog(QDialog):
    """Settings, as a liquid-glass card like the drop window."""

    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.controller = controller
        s = controller.settings
        self.setWindowTitle("Spinvert settings")
        self.setWindowIcon(app_icon())
        self.resize(560, 480)
        self.frame = GlassFrame(self, "Settings")

        self.convert_key = self._key_box(s.convert_key)
        self.tools_key = self._key_box(s.tools_key)
        self.explorer_only = QCheckBox("Only react to drags that start in File Explorer")
        self.explorer_only.setChecked(s.explorer_only)
        self.image_quality = QSlider(Qt.Orientation.Horizontal)
        self.image_quality.setRange(40, 100)
        self.image_quality.setValue(s.image_quality)
        quality_value = QLabel(str(s.image_quality))
        quality_value.setMinimumWidth(28)
        self.image_quality.valueChanged.connect(lambda v: quality_value.setText(str(v)))
        quality_row = QHBoxLayout()
        quality_row.addWidget(self.image_quality, 1)
        quality_row.addWidget(quality_value)
        self.video_quality = QComboBox()
        for key, label in QUALITY_LABELS.items():
            self.video_quality.addItem(label, key)
        self.video_quality.setCurrentIndex(list(QUALITY_LABELS).index(s.video_quality))
        self.ffmpeg = QLineEdit(s.ffmpeg_path)
        detected = find_ffmpeg()
        self.ffmpeg.setPlaceholderText(str(detected) if detected else "Not found: install FFmpeg")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg, 1)
        ffmpeg_row.addWidget(browse)
        self.startup = QCheckBox("Start Spinvert when Windows starts")
        self.startup.setChecked(system.startup_enabled())
        self.sendto = QCheckBox("Add Spinvert to the right-click \"Send to\" menu")
        self.sendto.setChecked(system.sendto_enabled())
        engines = controller.engines
        engine_label = QLabel("   ".join(f"{label} {'✓' if engines.get(key) else '✗'}"
                                       for key, label in ENGINE_LABELS))
        engine_label.setToolTip("Word, PowerPoint and Excel are used for Office to PDF. "
                                "Without Word, documents still convert to PDF with Spinvert's own writer.")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(11)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("Convert wheel key", self.convert_key)
        form.addRow("Tools wheel key", self.tools_key)
        form.addRow("", self.explorer_only)
        form.addRow("JPG / WebP quality", quality_row)
        form.addRow("Video quality", self.video_quality)
        form.addRow("FFmpeg", ffmpeg_row)
        form.addRow("", self.startup)
        form.addRow("", self.sendto)
        form.addRow("Engines", engine_label)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setProperty("primary", True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(self.frame.close_button(self.reject))
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(cancel)
        bottom.addWidget(save)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MARGIN + 18, MARGIN + 10, MARGIN + 18, MARGIN + 16)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addSpacing(6)
        layout.addLayout(form)
        layout.addStretch()
        layout.addLayout(bottom)
        self.frame.style_children()

    def place(self, anchor=None) -> None:
        """Centre on the drop window when it is open, else on the screen."""
        area = anchor.frameGeometry() if anchor is not None else \
            QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)

    # window events

    def paintEvent(self, event):
        p = QPainter(self)
        self.frame.paint(p)
        p.end()

    def moveEvent(self, event):
        self.frame.moved()

    def resizeEvent(self, event):
        self.frame.resized()

    def mousePressEvent(self, event):
        self.frame.press(event)

    # settings

    @staticmethod
    def _key_box(current: str) -> QComboBox:
        box = QComboBox()
        for key in KEYS:
            box.addItem(KEY_LABELS[key], key)
        box.setCurrentIndex(KEYS.index(current))
        return box

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Find ffmpeg.exe", "", "ffmpeg.exe (ffmpeg.exe)")
        if path:
            self.ffmpeg.setText(path)

    def _save(self):
        convert_key = self.convert_key.currentData()
        tools_key = self.tools_key.currentData()
        if convert_key == tools_key:
            QMessageBox.warning(self, "Spinvert", "The two wheels need different keys.")
            return
        s = self.controller.settings
        s.convert_key, s.tools_key = convert_key, tools_key
        s.explorer_only = self.explorer_only.isChecked()
        s.image_quality = self.image_quality.value()
        s.video_quality = self.video_quality.currentData()
        s.ffmpeg_path = self.ffmpeg.text().strip()
        s.save()
        try:
            if self.startup.isChecked() != system.startup_enabled():
                system.set_startup(self.startup.isChecked())
            if self.sendto.isChecked() != system.sendto_enabled():
                system.set_sendto(self.sendto.isChecked())
        except Exception as e:
            QMessageBox.warning(self, "Spinvert", f"Couldn't change the Windows setting: {e}")
        self.controller.refresh_engines()
        self.accept()
