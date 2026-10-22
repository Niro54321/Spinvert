"""Building blocks for the editors: a glass dialog, a picture canvas with tools
on top (crop box, boxes, drawn shapes), a timeline, and small controls."""

from __future__ import annotations


import threading
import winsound
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QIcon, QImage, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)

from spinvert.glassui import MARGIN, GlassFrame
from spinvert.theme import ACCENT, app_icon

ACCENT_COLOR = ACCENT["convert"]


# ------------------------------------------------------------- the dialog

class GlassDialog(QDialog):
    """A frameless liquid-glass dialog: title, body, Cancel and a primary button."""

    def __init__(self, title: str, size=(900, 660), primary: str = "Save copy"):
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(f"Spinvert: {title}")
        self.setWindowIcon(app_icon())
        screen = (QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()).availableGeometry()
        self.resize(min(size[0], int(screen.width() * 0.96)), min(size[1], int(screen.height() * 0.94)))
        self.frame = GlassFrame(self, title)
        root = QVBoxLayout(self)
        root.setContentsMargins(MARGIN + 18, MARGIN + 10, MARGIN + 18, MARGIN + 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(self.frame.close_button(self.reject))
        root.addLayout(top)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body, 1)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.footer_left = QHBoxLayout()
        self.footer.addLayout(self.footer_left)
        self.footer.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button = QPushButton(primary)
        self.ok_button.setProperty("primary", True)
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)
        self.footer.addWidget(self.cancel_button)
        self.footer.addWidget(self.ok_button)
        root.addLayout(self.footer)

    def run(self) -> bool:
        """Show it in the middle of the screen with the mouse, as glass, and wait."""
        self.winId()
        screen = (QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()).availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
        self.frame.refresh_backdrop()
        accepted = self.exec() == QDialog.DialogCode.Accepted
        stop_sound()
        return accepted

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


def busy(fn):
    """Run fn with the wait cursor."""
    QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        return fn()
    finally:
        QGuiApplication.restoreOverrideCursor()


class Background(QObject):
    """Run slow work (FFmpeg previews, OCR) off the UI thread; deliver the result back."""

    done = Signal(object, object)  # result, error

    def start(self, fn):
        def work():
            try:
                self.done.emit(fn(), None)
            except Exception as e:  # shown to the user by the receiver
                self.done.emit(None, e)
        threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------- images and sound

def to_qimage(im: Image.Image) -> QImage:
    rgba = im.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


def qimage_from_png(data: bytes) -> QImage:
    img = QImage()
    img.loadFromData(data, "PNG")
    return img


def preview_copy(im: Image.Image, longest: int = 1100) -> Image.Image:
    small = im.copy()
    small.thumbnail((longest, longest), Image.Resampling.LANCZOS)
    return small


def play_wav(path: Path) -> None:
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)


def stop_sound() -> None:
    winsound.PlaySound(None, winsound.SND_PURGE)


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}" if h else f"{int(m):02d}:{s:06.3f}"


def parse_time(text: str) -> float | None:
    try:
        parts = [float(p) for p in text.strip().replace(",", ".").split(":")]
    except ValueError:
        return None
    total = 0.0
    for part in parts:
        total = total * 60 + part
    return total


# --------------------------------------------------------------- controls

def label(text: str, muted: bool = False, bold: bool = False) -> QLabel:
    lab = QLabel(text)
    if bold:
        lab.setStyleSheet("font-weight: 700; font-size: 13px;")
    elif muted:
        lab.setStyleSheet("font-size: 12px;")
    lab.setWordWrap(True)
    return lab


class SliderRow(QWidget):
    """Name, slider, value. scale divides the slider's integer value for display."""

    changed = Signal(int)

    def __init__(self, name: str, lo: int, hi: int, value: int, unit: str = "", scale: float = 1,
                 width: int = 110):
        super().__init__()
        self.unit, self.scale = unit, scale
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel(name)
        self.name.setFixedWidth(width)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.value = QLabel()
        self.value.setFixedWidth(58)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.name)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.value)
        self.slider.valueChanged.connect(self._changed)
        self._show(value)

    def _show(self, v: int):
        shown = v / self.scale
        text = f"{shown:g}" if self.scale != 1 else str(v)
        self.value.setText(f"{text}{self.unit}")

    def _changed(self, v: int):
        self._show(v)
        self.changed.emit(v)

    def get(self) -> int:
        return self.slider.value()

    def set(self, v: int, quiet: bool = False):
        if quiet:
            self.slider.blockSignals(True)
        self.slider.setValue(int(v))
        self._show(self.slider.value())
        if quiet:
            self.slider.blockSignals(False)


class Segmented(QWidget):
    """A row of pill buttons, one checked at a time."""

    changed = Signal(str)

    def __init__(self, options, current=None, wrap: int = 0):
        super().__init__()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        row = None
        for i, (key, text) in enumerate(options):
            if row is None or (wrap and i % wrap == 0):
                row = QHBoxLayout()
                row.setSpacing(6)
                outer.addLayout(row)
            b = QPushButton(text.replace("&", "&&"))  # a lone & would become a keyboard shortcut
            b.setCheckable(True)
            b.setProperty("segment", True)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            self.buttons[key] = b
            row.addWidget(b)
        if row is not None and not wrap:
            row.addStretch()
        if current is not None and current in self.buttons:
            self.buttons[current].setChecked(True)

    def get(self):
        for key, b in self.buttons.items():
            if b.isChecked():
                return key
        return None

    def set(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)




class TimeEdit(QLineEdit):
    """mm:ss.mmm; emits the value in seconds when edited."""

    changed = Signal(float)

    def __init__(self, seconds: float = 0.0):
        super().__init__(fmt_time(seconds))
        self.setFixedWidth(118)
        self.editingFinished.connect(self._done)

    def _done(self):
        value = parse_time(self.text())
        if value is not None:
            self.changed.emit(value)

    def set(self, seconds: float):
        self.setText(fmt_time(seconds))


# ------------------------------------------------------------- the canvas

class ImageCanvas(QWidget):
    """A picture scaled to fit, with an optional tool drawing on top of it.
    Tools work in fractions of the picture (0..1), so they fit any size."""

    changed = Signal()

    def __init__(self, min_size=(420, 300)):
        super().__init__()
        self.image = QImage()
        self.tool = None
        self.setMouseTracking(True)
        self.setMinimumSize(*min_size)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_image(self, image: QImage):
        self.image = image
        self.update()

    def set_tool(self, tool):
        self.tool = tool
        if tool is not None:
            tool.canvas = self
        self.update()

    def target(self) -> QRectF:
        if self.image.isNull():
            return QRectF(self.rect())
        area = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        ratio = self.image.width() / self.image.height()
        if area.width() / area.height() > ratio:
            w = area.height() * ratio
            return QRectF(area.center().x() - w / 2, area.top(), w, area.height())
        h = area.width() / ratio
        return QRectF(area.left(), area.center().y() - h / 2, area.width(), h)

    def to_norm(self, pos: QPointF):
        t = self.target()
        return (min(1.0, max(0.0, (pos.x() - t.left()) / t.width())),
                min(1.0, max(0.0, (pos.y() - t.top()) / t.height())))

    def to_widget(self, x: float, y: float) -> QPointF:
        t = self.target()
        return QPointF(t.left() + x * t.width(), t.top() + y * t.height())

    def norm_rect(self, rect) -> QRectF:
        a, b = self.to_widget(rect[0], rect[1]), self.to_widget(rect[2], rect[3])
        return QRectF(a, b).normalized()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        t = self.target()
        path = QPainterPath()
        path.addRoundedRect(t, 10, 10)
        p.setClipPath(path)
        # a soft checkerboard shows transparency
        cell = 12
        for yy in range(int(t.top()), int(t.bottom()) + cell, cell):
            for xx in range(int(t.left()), int(t.right()) + cell, cell):
                odd = ((xx - int(t.left())) // cell + (yy - int(t.top())) // cell) % 2
                p.fillRect(xx, yy, cell, cell, QColor(255, 255, 255, 34 if odd else 18))
        if not self.image.isNull():
            p.drawImage(t, self.image)
        p.setClipping(False)
        if self.tool is not None:
            self.tool.paint(p, self)
        p.end()

    def mousePressEvent(self, e):
        if self.tool is not None:
            self.tool.press(self.to_norm(e.position()), e)
            self.update()

    def mouseMoveEvent(self, e):
        if self.tool is not None:
            self.tool.move(self.to_norm(e.position()), e)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.tool is not None:
            self.tool.release(self.to_norm(e.position()), e)
            self.update()

    def keyPressEvent(self, e):
        if self.tool is not None and hasattr(self.tool, "key"):
            self.tool.key(e)
            self.update()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        if self.tool is not None and hasattr(self.tool, "wheel"):
            self.tool.wheel(self.to_norm(e.position()), e.angleDelta().y())
            self.update()


def _handle(p: QPainter, pt: QPointF, r: float = 5.5):
    p.setPen(QPen(QColor(0, 0, 0, 90), 1))
    p.setBrush(QColor("white"))
    p.drawEllipse(pt, r, r)


class CropTool:
    """A crop box with corner and edge handles, an optional fixed aspect ratio,
    a dimmed outside and rule-of-thirds lines."""

    def __init__(self, rect=(0.0, 0.0, 1.0, 1.0)):
        self.rect = list(rect)
        self.aspect = None  # width/height in pixels, or None for free
        self.canvas = None
        self._drag = None

    def _px_ratio(self) -> float:
        img = self.canvas.image
        return img.width() / img.height() if not img.isNull() and img.height() else 1.0

    def set_aspect(self, aspect):
        """Fit the biggest box of this ratio, centred on the current one."""
        self.aspect = aspect
        if not aspect:
            return
        norm = aspect / self._px_ratio()  # the ratio in fraction units
        cx, cy = (self.rect[0] + self.rect[2]) / 2, (self.rect[1] + self.rect[3]) / 2
        w, h = 1.0, 1.0 / norm
        if h > 1:
            w, h = norm, 1.0
        x0 = min(max(0.0, cx - w / 2), 1 - w)
        y0 = min(max(0.0, cy - h / 2), 1 - h)
        self.rect = [x0, y0, x0 + w, y0 + h]

    def _hit(self, pos):
        x0, y0, x1, y1 = self.rect
        r = self.canvas.norm_rect(self.rect)
        p = self.canvas.to_widget(*pos)
        near = 10
        corners = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
        for name, c in corners.items():
            if abs(p.x() - c.x()) < near and abs(p.y() - c.y()) < near:
                return name
        if abs(p.x() - r.left()) < near and r.top() < p.y() < r.bottom():
            return "l"
        if abs(p.x() - r.right()) < near and r.top() < p.y() < r.bottom():
            return "r"
        if abs(p.y() - r.top()) < near and r.left() < p.x() < r.right():
            return "t"
        if abs(p.y() - r.bottom()) < near and r.left() < p.x() < r.right():
            return "b"
        if r.contains(p):
            return "move"
        return "new"

    def press(self, pos, e):
        kind = self._hit(pos)
        if kind == "new":
            self.rect = [pos[0], pos[1], pos[0], pos[1]]
            kind = "br"
        self._drag = (kind, pos, list(self.rect))

    def move(self, pos, e):
        if not self._drag:
            hit = self._hit(pos)
            cursor = {"move": Qt.CursorShape.SizeAllCursor, "tl": Qt.CursorShape.SizeFDiagCursor,
                      "br": Qt.CursorShape.SizeFDiagCursor, "tr": Qt.CursorShape.SizeBDiagCursor,
                      "bl": Qt.CursorShape.SizeBDiagCursor, "l": Qt.CursorShape.SizeHorCursor,
                      "r": Qt.CursorShape.SizeHorCursor, "t": Qt.CursorShape.SizeVerCursor,
                      "b": Qt.CursorShape.SizeVerCursor}.get(hit, Qt.CursorShape.CrossCursor)
            self.canvas.setCursor(cursor)
            return
        kind, start, orig = self._drag
        dx, dy = pos[0] - start[0], pos[1] - start[1]
        x0, y0, x1, y1 = orig
        if kind == "move":
            w, h = x1 - x0, y1 - y0
            nx = min(max(0.0, x0 + dx), 1 - w)
            ny = min(max(0.0, y0 + dy), 1 - h)
            self.rect = [nx, ny, nx + w, ny + h]
        else:
            if "l" in kind:
                x0 = pos[0]
            if "r" in kind:
                x1 = pos[0]
            if "t" in kind:
                y0 = pos[1]
            if "b" in kind:
                y1 = pos[1]
            if self.aspect:
                norm = self.aspect / self._px_ratio()
                w = abs(x1 - x0)
                h = w / norm
                if kind in ("t", "b"):
                    h = abs(y1 - y0)
                    w = h * norm
                if "t" in kind:
                    y0 = y1 - h if y1 > y0 else y1 + h
                else:
                    y1 = y0 + h if y1 >= y0 else y0 - h
                if kind in ("t", "b"):
                    x1 = x0 + w
            self.rect = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            self.rect = [max(0.0, self.rect[0]), max(0.0, self.rect[1]),
                         min(1.0, self.rect[2]), min(1.0, self.rect[3])]
        self.canvas.changed.emit()

    def release(self, pos, e):
        self._drag = None
        if self.rect[2] - self.rect[0] < 0.01 or self.rect[3] - self.rect[1] < 0.01:
            self.rect = [0.0, 0.0, 1.0, 1.0]
            if self.aspect:
                self.set_aspect(self.aspect)
        self.canvas.changed.emit()

    def paint(self, p: QPainter, canvas):
        t = canvas.target()
        r = canvas.norm_rect(self.rect)
        outside = QPainterPath()
        outside.addRect(t)
        inner = QPainterPath()
        inner.addRect(r)
        p.fillPath(outside.subtracted(inner), QColor(0, 0, 0, 120))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for i in (1, 2):
            p.drawLine(QPointF(r.left() + r.width() * i / 3, r.top()), QPointF(r.left() + r.width() * i / 3, r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + r.height() * i / 3), QPointF(r.right(), r.top() + r.height() * i / 3))
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            _handle(p, c)


class BoxesTool:
    """Several boxes (for redaction). Drag on empty space to add one, drag a
    box to move it, drag a corner of the selected box to resize it, Delete
    removes it. Boxes show only their effect: no outline, just small corner
    handles on the selected one."""

    def __init__(self, new_box):
        self.boxes = []          # dicts with "rect" plus whatever new_box() adds
        self.selected = None
        self.new_box = new_box
        self.canvas = None
        self._drag = None

    def _index_at(self, pos):
        for i in reversed(range(len(self.boxes))):
            x0, y0, x1, y1 = self.boxes[i]["rect"]
            if x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                return i
        return None

    def _corner_at(self, pos):
        if self.selected is None:
            return None
        r = self.canvas.norm_rect(self.boxes[self.selected]["rect"])
        p = self.canvas.to_widget(*pos)
        for name, c in (("tl", r.topLeft()), ("tr", r.topRight()), ("bl", r.bottomLeft()), ("br", r.bottomRight())):
            if abs(p.x() - c.x()) < 9 and abs(p.y() - c.y()) < 9:
                return name
        return None

    def press(self, pos, e):
        corner = self._corner_at(pos)
        if corner:
            self._drag = ("corner", corner, list(self.boxes[self.selected]["rect"]))
            return
        i = self._index_at(pos)
        if i is not None:
            self.selected = i
            self._drag = ("move", pos, list(self.boxes[i]["rect"]))
        else:
            box = self.new_box()
            box["rect"] = [pos[0], pos[1], pos[0], pos[1]]
            self.boxes.append(box)
            self.selected = len(self.boxes) - 1
            self._drag = ("new", pos, None)
        self.canvas.changed.emit()

    def move(self, pos, e):
        if not self._drag or self.selected is None:
            corner = self._corner_at(pos)
            self.canvas.setCursor(Qt.CursorShape.SizeFDiagCursor if corner else
                                  Qt.CursorShape.SizeAllCursor if self._index_at(pos) is not None
                                  else Qt.CursorShape.CrossCursor)
            return
        kind, start, orig = self._drag
        box = self.boxes[self.selected]
        if kind == "new":
            box["rect"] = [min(start[0], pos[0]), min(start[1], pos[1]), max(start[0], pos[0]), max(start[1], pos[1])]
        elif kind == "corner":
            x0, y0, x1, y1 = orig
            if "l" in start:
                x0 = pos[0]
            else:
                x1 = pos[0]
            if "t" in start:
                y0 = pos[1]
            else:
                y1 = pos[1]
            box["rect"] = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        else:
            w, h = orig[2] - orig[0], orig[3] - orig[1]
            nx = min(max(0.0, orig[0] + pos[0] - start[0]), 1 - w)
            ny = min(max(0.0, orig[1] + pos[1] - start[1]), 1 - h)
            box["rect"] = [nx, ny, nx + w, ny + h]
        self.canvas.changed.emit()

    def release(self, pos, e):
        if self._drag and self._drag[0] == "new" and self.selected is not None:
            x0, y0, x1, y1 = self.boxes[self.selected]["rect"]
            if x1 - x0 < 0.01 or y1 - y0 < 0.01:
                self.boxes.pop(self.selected)
                self.selected = None
        self._drag = None
        self.canvas.changed.emit()

    def key(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected is not None:
            self.boxes.pop(self.selected)
            self.selected = None
            self.canvas.changed.emit()

    def paint(self, p: QPainter, canvas):
        if self.selected is None or self.selected >= len(self.boxes):
            return
        r = canvas.norm_rect(self.boxes[self.selected]["rect"])
        for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            p.setPen(QPen(QColor(ACCENT_COLOR), 1.6))
            p.setBrush(QColor("white"))
            p.drawEllipse(c, 5, 5)


# ------------------------------------------------------------ the timeline

class Timeline(QWidget):
    """A strip (video thumbnails or a waveform) with a playhead and either one
    range (trim), several ranges (bleep) or points (split, frames)."""

    changed = Signal()      # something was set (on mouse release)
    scrubbed = Signal(float)  # the playhead moved (while dragging)

    def __init__(self, duration: float, mode: str = "range"):
        super().__init__()
        self.duration = max(0.01, duration)
        self.mode = mode
        self.background = QImage()
        self.start, self.end = 0.0, self.duration
        self.ranges = []
        self.points = []
        self.selected = None
        self.playhead = 0.0
        self._drag = None
        self.setMinimumHeight(86)
        self.setMouseTracking(True)

    def set_background(self, image: QImage):
        self.background = image
        self.update()

    def _area(self) -> QRectF:
        return QRectF(self.rect()).adjusted(10, 8, -10, -8)

    def x_of(self, t: float) -> float:
        a = self._area()
        return a.left() + a.width() * t / self.duration

    def t_of(self, x: float) -> float:
        a = self._area()
        return min(self.duration, max(0.0, (x - a.left()) / a.width() * self.duration))

    def _near(self, x: float, t: float) -> bool:
        return abs(x - self.x_of(t)) < 9

    def mousePressEvent(self, e):
        x = e.position().x()
        t = self.t_of(x)
        if self.mode == "range":
            if self._near(x, self.start):
                self._drag = "start"
            elif self._near(x, self.end):
                self._drag = "end"
            else:
                self._drag = "playhead"
        elif self.mode == "ranges":
            self._drag = "playhead"
            for i, (a, b) in enumerate(self.ranges):
                if self._near(x, a):
                    self.selected, self._drag = i, "a"
                    break
                if self._near(x, b):
                    self.selected, self._drag = i, "b"
                    break
                if a < t < b:
                    self.selected, self._drag = i, ("move", t, a, b)
                    break
        else:
            self._drag = "playhead"
        self._apply(t)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            edge = (self.mode == "range" and (self._near(x, self.start) or self._near(x, self.end))) or \
                   (self.mode == "ranges" and any(self._near(x, a) or self._near(x, b) for a, b in self.ranges))
            self.setCursor(Qt.CursorShape.SizeHorCursor if edge else Qt.CursorShape.PointingHandCursor)
            return
        self._apply(self.t_of(x))

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.changed.emit()

    def _apply(self, t: float):
        d = self._drag
        if d == "start":
            self.start = min(t, self.end - 0.05)
            self.playhead = self.start
        elif d == "end":
            self.end = max(t, self.start + 0.05)
            self.playhead = self.end
        elif d == "a" and self.selected is not None:
            a, b = self.ranges[self.selected]
            self.ranges[self.selected] = [min(t, b - 0.05), b]
            self.playhead = self.ranges[self.selected][0]
        elif d == "b" and self.selected is not None:
            a, b = self.ranges[self.selected]
            self.ranges[self.selected] = [a, max(t, a + 0.05)]
            self.playhead = self.ranges[self.selected][1]
        elif isinstance(d, tuple):
            _, t0, a, b = d
            shift = min(max(t - t0, -a), self.duration - b)
            self.ranges[self.selected] = [a + shift, b + shift]
            self.playhead = self.ranges[self.selected][0]
        else:
            self.playhead = t
        self.scrubbed.emit(self.playhead)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        a = self._area()
        clip = QPainterPath()
        clip.addRoundedRect(a, 8, 8)
        p.setClipPath(clip)
        p.fillRect(a, QColor(0, 0, 0, 70))
        if not self.background.isNull():
            p.drawImage(a, self.background)
        if self.mode == "range":
            p.fillRect(QRectF(a.left(), a.top(), self.x_of(self.start) - a.left(), a.height()), QColor(0, 0, 0, 150))
            p.fillRect(QRectF(self.x_of(self.end), a.top(), a.right() - self.x_of(self.end), a.height()),
                       QColor(0, 0, 0, 150))
        for i, (s, e) in enumerate(self.ranges):
            r = QRectF(self.x_of(s), a.top(), self.x_of(e) - self.x_of(s), a.height())
            p.fillRect(r, QColor(255, 59, 48, 120 if i == self.selected else 80))
        p.setClipping(False)
        if self.mode == "range":
            p.setPen(QPen(QColor("white"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.x_of(self.start), a.top(), self.x_of(self.end) - self.x_of(self.start),
                                     a.height()), 6, 6)
            for t in (self.start, self.end):
                p.setBrush(QColor("white"))
                p.drawRoundedRect(QRectF(self.x_of(t) - 4, a.center().y() - 16, 8, 32), 4, 4)
        for i, (s, e) in enumerate(self.ranges):
            if i == self.selected:
                p.setPen(QPen(QColor("white"), 2))
                for t in (s, e):
                    p.setBrush(QColor("white"))
                    p.drawRoundedRect(QRectF(self.x_of(t) - 3, a.center().y() - 12, 6, 24), 3, 3)
        p.setPen(QPen(QColor(ACCENT_COLOR), 2))
        for t in self.points:
            p.drawLine(QPointF(self.x_of(t), a.top()), QPointF(self.x_of(t), a.bottom()))
        x = self.x_of(self.playhead)
        p.setPen(QPen(QColor("#FFCC00"), 2))
        p.drawLine(QPointF(x, a.top() - 4), QPointF(x, a.bottom() + 4))
        p.setBrush(QColor("#FFCC00"))
        p.drawEllipse(QPointF(x, a.top() - 4), 4, 4)
        p.end()


def gradient_icon(colors: list[str], size: int = 22) -> QPixmap:
    from spinvert.engines.imaging import gradient

    return QPixmap.fromImage(to_qimage(gradient((size, size), colors)))


def color_icon(color: str, size: int = 22) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return pm


def font_icon(glyph: str, size: int = 16, color: str = "white") -> QIcon:
    pm = QPixmap(size + 4, size + 4)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(size)
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return QIcon(pm)


def card(widget: QWidget) -> QWidget:
    """Wrap a panel so it reads as a slightly lighter glass card."""
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setProperty("card", True)
    return widget

