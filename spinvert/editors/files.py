"""Editors for any file and for PDFs: compress, metadata, order, organize pages,
split, password, and the 'one PDF or one each?' question."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLineEdit, QListView, QListWidget, QListWidgetItem, QPushButton,
                               QTableWidget, QTableWidgetItem)

from spinvert.catalog import category
from spinvert.editors.base import GlassDialog, Segmented, SliderRow, busy, label
from spinvert.util import natural_key


def _size_mb(paths) -> float:
    return sum(p.stat().st_size for p in paths) / 1_000_000


# -------------------------------------------------------------- compress

class CompressDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Compress", (660, 500), "Compress")
        self.kind = category(paths[0])
        size = _size_mb(paths[:1])
        self.body.addWidget(label(f"{paths[0].name} is {size:.2f} MB now."
                                  + (f" Settings apply to all {len(paths)} files." if len(paths) > 1 else ""),
                                  muted=True))
        self.mode = Segmented([("quality", "By quality"), ("size", "Target size"), ("percent", "Reduce by %")],
                              "quality")
        self.body.addWidget(self.mode)
        self.quality = Segmented([("high", "High quality"), ("balanced", "Balanced"), ("small", "Smallest")],
                                 "balanced")
        self.target = QDoubleSpinBox()
        self.target.setRange(0.01, 100000)
        self.target.setDecimals(2)
        self.target.setSuffix(" MB")
        self.target.setValue(round(max(0.01, size / 2), 2))
        self.percent = SliderRow("Smaller by", 10, 95, 50, "%", width=90)
        self.body.addWidget(self.quality)
        row = QHBoxLayout()
        row.addWidget(label("Target"))
        row.addWidget(self.target)
        row.addStretch()
        self.body.addLayout(row)
        self.body.addWidget(self.percent)
        self.resize_box = None
        if self.kind == "image":
            self.resize_box = Segmented([("0", "Keep size"), ("3840", "Max 3840 px"), ("2560", "2560 px"),
                                         ("1920", "1920 px"), ("1280", "1280 px")], "0")
            self.body.addWidget(label("Also make it smaller in pixels", bold=True))
            self.body.addWidget(self.resize_box)
        elif self.kind == "video":
            self.resize_box = Segmented([("0", "Keep size"), ("1920", "Max 1080p"), ("1280", "720p"),
                                         ("854", "480p")], "1920")
            self.body.addWidget(label("Picture size", bold=True))
            self.body.addWidget(self.resize_box)
        elif self.kind == "audio":
            self.kbps = Segmented([("64", "64 kbps"), ("96", "96 kbps"), ("128", "128 kbps"), ("192", "192 kbps")],
                                  "128")
            self.body.addWidget(label("Bitrate for 'By quality'", bold=True))
            self.body.addWidget(self.kbps)
        self.body.addStretch()
        self.mode.changed.connect(self._show)
        self._show(self.mode.get())

    def _show(self, mode):
        self.quality.setVisible(mode == "quality")
        self.target.setEnabled(mode == "size")
        self.percent.setVisible(mode == "percent")

    def params(self) -> dict:
        mode = self.mode.get()
        p = {"mode": mode, "target_mb": self.target.value(), "percent": self.percent.get()}
        q = self.quality.get()
        if self.kind == "image":
            p["quality"] = {"high": 85, "balanced": 72, "small": 55}[q]
            if self.resize_box.get() != "0":
                p["max_side"] = int(self.resize_box.get())
        elif self.kind == "video":
            p["quality"] = q
            p["max_width"] = int(self.resize_box.get()) or 100000
        elif self.kind == "audio":
            p["kbps"] = int(self.kbps.get())
        return p


def ask_compress(paths, parent=None):
    d = CompressDialog(paths)
    return d.params() if d.run() else None


# -------------------------------------------------------------- metadata

class MetadataDialog(GlassDialog):
    def __init__(self, paths):
        from spinvert.engines import metadata
        from spinvert.settings import Settings
        from spinvert.util import find_ffmpeg, find_ffprobe

        super().__init__("Metadata", (920, 720), "Save copy")
        probe = find_ffprobe(find_ffmpeg(Settings.load().ffmpeg_path))
        self.data = busy(lambda: metadata.read(paths[0], probe))
        kind = self.data["kind"]
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search fields…")
        self.search.textChanged.connect(self._filter)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Group", "Field", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for group, name, value in self.data["fields"]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, text in enumerate((group, name, value)):
                self.table.setItem(r, c, QTableWidgetItem(str(text)))
        self.table.resizeColumnsToContents()
        self.body.addWidget(self.search)
        self.body.addWidget(self.table, 1)
        self.edits = {}
        if kind in metadata.EDITABLE:
            form = QFormLayout()
            for key, name in metadata.EDITABLE[kind]:
                edit = QLineEdit(self.data["values"].get(key, ""))
                self.edits[key] = edit
                form.addRow(name, edit)
            self.body.addWidget(label("Change", bold=True))
            self.body.addLayout(form)
        self.remove_all = QCheckBox("Remove everything else (camera, software, dates, comments…)")
        self.remove_gps = QCheckBox("Remove the location only")
        self.remove_gps.setVisible(self.data.get("gps", False))
        self.body.addWidget(self.remove_all)
        self.body.addWidget(self.remove_gps)
        if len(paths) > 1:
            self.footer_left.addWidget(label(f"Shown: {paths[0].name}. Changes apply to all {len(paths)} files.",
                                             muted=True))

    def _filter(self, text):
        text = text.lower()
        for r in range(self.table.rowCount()):
            row = " ".join(self.table.item(r, c).text().lower() for c in range(3))
            self.table.setRowHidden(r, text not in row)

    def params(self) -> dict:
        changed = {k: e.text() for k, e in self.edits.items() if e.text() != self.data["values"].get(k, "")}
        return {"set": changed, "remove_all": self.remove_all.isChecked(), "remove_gps": self.remove_gps.isChecked()}


def edit_metadata(paths, parent=None):
    d = MetadataDialog(paths)
    if not d.run():
        return None
    p = d.params()
    if not (p["set"] or p["remove_all"] or p["remove_gps"]):
        return None  # nothing to do
    return p


# ----------------------------------------------------------------- order

def _thumb(path: Path, size: int = 96) -> QIcon:
    try:
        from spinvert.engines.images import _open, _upright

        im = _upright(_open(path))
        im.thumbnail((size, size))
        buf = BytesIO()
        im.convert("RGB").save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue())
        return QIcon(pm)
    except Exception:
        return QIcon()


class OrderDialog(GlassDialog):
    """Arrange files before they are combined (PDF, join, merge)."""

    def __init__(self, paths, title="Arrange the order", primary="Continue"):
        super().__init__(title, (640, 620), primary)
        self.paths = paths
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setIconSize(QSize(56, 56))
        pictures = all(category(p) == "image" for p in paths)
        order = sorted(range(len(paths)), key=lambda i: natural_key(paths[i]))
        for i in order:
            item = QListWidgetItem(paths[i].name)
            if pictures:
                item.setIcon(busy(lambda p=paths[i]: _thumb(p, 56)))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)
        self.body.addWidget(label("Drag to change the order. The first one goes first.", muted=True))
        self.body.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in [("A → Z", lambda: self.list.sortItems(Qt.SortOrder.AscendingOrder)),
                         ("Z → A", lambda: self.list.sortItems(Qt.SortOrder.DescendingOrder)),
                         ("Reverse", self._reverse)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        self.body.addLayout(row)
        self.gap = None
        if all(category(p) == "audio" for p in paths):  # joining recordings: silence between them
            self.gap = SliderRow("Gap between files", 0, 100, 0, " s", scale=10, width=130)
            self.body.addWidget(self.gap)

    def _reverse(self):
        items = [self.list.takeItem(0) for _ in range(self.list.count())]
        for item in reversed(items):
            self.list.addItem(item)

    def order(self) -> list[int]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def params(self) -> dict:
        p = {"order": self.order()}
        if self.gap is not None:
            p["gap"] = self.gap.get() / 10
        return p


def order_files(paths, parent=None):
    d = OrderDialog(paths)
    return d.params() if d.run() else None


# ------------------------------------------------------- one PDF or many?

class PdfModeDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Pictures to PDF", (560, 360), "Continue")
        self.answer = None
        self.body.addWidget(label(f"You picked {len(paths)} pictures.", bold=True))
        one = QPushButton(f"One PDF with all {len(paths)} pictures")
        one.setProperty("primary", True)
        each = QPushButton(f"{len(paths)} PDFs, one per picture")
        one.clicked.connect(lambda: self._pick("combine"))
        each.clicked.connect(lambda: self._pick("each"))
        for b in (one, each):
            b.setMinimumHeight(46)
            self.body.addWidget(b)
        self.arrange = QCheckBox("Let me arrange the page order first")
        self.body.addWidget(self.arrange)
        self.body.addStretch()
        self.ok_button.hide()

    def _pick(self, answer):
        self.answer = answer
        self.accept()


def ask_pdf_mode(paths, parent=None):
    """'combine' (with an optional order), 'each', or None to cancel."""
    d = PdfModeDialog(paths)
    if not d.run():
        return None
    if d.answer == "combine" and d.arrange.isChecked():
        order = order_files(paths)
        return ("combine", order) if order else None
    return (d.answer, None)


# ------------------------------------------------------------ PDF pages

class OrganizeDialog(GlassDialog):
    def __init__(self, path: Path):
        from spinvert.engines.pdfs import thumbnails

        super().__init__("Organize pages", (1000, 740), "Save copy")
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(130, 180))
        self.list.setGridSize(QSize(160, 228))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Snap)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pixmaps = []
        for i, image in enumerate(busy(lambda: thumbnails(path))):
            buf = BytesIO()
            image.convert("RGB").save(buf, "PNG")
            pm = QPixmap()
            pm.loadFromData(buf.getvalue())
            self.pixmaps.append(pm)
            self.list.addItem(self._item(i, 0))
        self.body.addWidget(label("Drag pages to reorder. Select pages, then rotate, duplicate or remove them.",
                                  muted=True))
        self.body.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in [("⟲ Rotate left", lambda: self._rotate(-90)), ("⟳ Rotate right", lambda: self._rotate(90)),
                         ("Duplicate", self._duplicate), ("Remove", self._remove), ("Reverse", self._reverse)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        self.body.addLayout(row)

    def _item(self, index: int, rotation: int) -> QListWidgetItem:
        pm = self.pixmaps[index].transformed(QTransform().rotate(rotation)) if rotation else self.pixmaps[index]
        item = QListWidgetItem(QIcon(pm), f"Page {index + 1}" + (f" ↻{rotation}°" if rotation else ""))
        item.setData(Qt.ItemDataRole.UserRole, [index, rotation])
        return item

    def _rotate(self, degrees):
        for item in self.list.selectedItems():
            index, rotation = item.data(Qt.ItemDataRole.UserRole)
            row = self.list.row(item)
            self.list.takeItem(row)
            new = self._item(index, (rotation + degrees) % 360)
            self.list.insertItem(row, new)
            new.setSelected(True)

    def _duplicate(self):
        for item in self.list.selectedItems():
            index, rotation = item.data(Qt.ItemDataRole.UserRole)
            self.list.insertItem(self.list.row(item) + 1, self._item(index, rotation))

    def _remove(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def _reverse(self):
        items = [self.list.takeItem(0) for _ in range(self.list.count())]
        for item in reversed(items):
            self.list.addItem(item)

    def pages(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]


def organize_pdf(paths, parent=None):
    d = OrganizeDialog(paths[0])
    if not d.run():
        return None
    pages = d.pages()
    return {"pages": pages} if pages else None


class SplitPdfDialog(GlassDialog):
    def __init__(self, path: Path):
        from spinvert.engines.pdfs import page_count

        super().__init__("Split PDF", (620, 420), "Split")
        self.count = busy(lambda: page_count(path))
        self.body.addWidget(label(f"{path.name} has {self.count} pages.", muted=True))
        self.mode = Segmented([("each", "Every page"), ("every", "Every N pages"), ("ranges", "My ranges")], "each")
        self.every = SliderRow("Pages per file", 1, max(2, self.count), min(2, self.count), width=110)
        self.ranges = QLineEdit(f"1-{max(1, self.count // 2)}, {self.count // 2 + 1}-")
        self.ranges.setPlaceholderText("e.g. 1-3, 4-7, 8-")
        self.body.addWidget(self.mode)
        self.body.addWidget(self.every)
        self.body.addWidget(self.ranges)
        self.body.addWidget(label("Ranges: '1-3' is pages 1 to 3, '8-' is page 8 to the end.", muted=True))
        self.body.addStretch()

    def params(self) -> dict:
        return {"mode": self.mode.get(), "every": self.every.get(), "ranges": self.ranges.text()}


def split_pdf(paths, parent=None):
    d = SplitPdfDialog(paths[0])
    return d.params() if d.run() else None


class PasswordDialog(GlassDialog):
    def __init__(self, path: Path):
        from spinvert.engines.pdfs import is_locked

        self.locked = is_locked(path)
        super().__init__("Unlock PDF" if self.locked else "Lock PDF with a password", (560, 380),
                         "Unlock" if self.locked else "Lock")
        self.first, self.second = QLineEdit(), QLineEdit()
        for e in (self.first, self.second):
            e.setEchoMode(QLineEdit.EchoMode.Password)
        if self.locked:
            self.body.addWidget(label("This PDF has a password. Type it to save a copy without one.", muted=True))
            self.body.addWidget(self.first)
        else:
            self.body.addWidget(label("Anyone opening the copy will need this password (AES-256).", muted=True))
            self.body.addWidget(self.first)
            self.body.addWidget(label("Type it again"))
            self.body.addWidget(self.second)
        self.problem = label("", bold=True)
        self.body.addWidget(self.problem)
        self.body.addStretch()
        self.ok_button.clicked.disconnect()
        self.ok_button.clicked.connect(self._check)

    def _check(self):
        if not self.first.text():
            self.problem.setText("Type a password.")
        elif not self.locked and self.first.text() != self.second.text():
            self.problem.setText("The two passwords are different.")
        else:
            self.accept()


def pdf_password(paths, parent=None):
    d = PasswordDialog(paths[0])
    return {"password": d.first.text()} if d.run() else None
