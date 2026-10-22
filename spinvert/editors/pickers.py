"""Colour choosing: round swatches with a (+) for any colour, a glass colour
picker (hue, shade, hex), and a gradient designer."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

ACCENT = QColor("#7C5CFF")


class Dot(QAbstractButton):
    """A round swatch: a colour (or gradient) circle inside a ring, or a (+)."""

    def __init__(self, colors=None, size: int = 28, plus: bool = False, angle: float = 135):
        super().__init__()
        self.colors = [QColor(c) for c in (colors or [])]
        self.plus = plus
        self.angle = angle
        self.setCheckable(not plus)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose any colour" if plus else (self.colors[0].name() if len(self.colors) == 1 else ""))

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        c = r.center()
        if self.isChecked():
            p.setPen(QPen(ACCENT, 2.6))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 110 if self.underMouse() else 70), 1.2))
        p.setBrush(QColor(255, 255, 255, 28) if self.plus else Qt.BrushStyle.NoBrush)
        p.drawEllipse(r)
        inner = r.adjusted(4, 4, -4, -4)
        if self.plus:
            p.setPen(QPen(QColor("white"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            arm = inner.width() * 0.32
            p.drawLine(QPointF(c.x() - arm, c.y()), QPointF(c.x() + arm, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - arm), QPointF(c.x(), c.y() + arm))
            return
        if len(self.colors) > 1:
            grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
            for i, col in enumerate(self.colors):
                grad.setColorAt(i / (len(self.colors) - 1), col)
            p.setBrush(grad)
        else:
            p.setBrush(self.colors[0] if self.colors else QColor("white"))
        p.setPen(QPen(QColor(0, 0, 0, 50), 0.8))
        p.drawEllipse(inner)


class Swatches(QWidget):
    """Round colour (or gradient) swatches in tidy rows, with (+) for any colour.

    items: [(key, colour)] or [(key, [colours])]. changed emits the key; a
    colour picked with (+) is added as a new swatch and its key is the hex."""

    changed = Signal(object)

    def __init__(self, items, current=None, size: int = 28, wrap: int = 9, custom: bool = True,
                 gradient: bool = False):
        super().__init__()
        self.size, self.wrap, self.gradient = size, wrap, gradient
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        self.items = list(items)
        self.grid = QVBoxLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.plus = Dot(plus=True, size=size) if custom else None
        if self.plus:
            self.plus.clicked.connect(self._custom)
        self._build()
        if current in self.buttons:
            self.buttons[current].setChecked(True)

    def _build(self):
        while self.grid.count():
            row = self.grid.takeAt(0).layout()
            while row and row.count():
                item = row.takeAt(0)
                if item.widget() and item.widget() is not self.plus:
                    item.widget().setParent(None)
        for b in list(self.buttons.values()):
            self.group.removeButton(b)
        self.buttons = {}
        widgets = []
        for key, look in self.items:
            colors = look if isinstance(look, (list, tuple)) else [look]
            b = Dot(colors, self.size)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            self.buttons[key] = b
            widgets.append(b)
        if self.plus:
            widgets.append(self.plus)
        # Every row gets the same gap between dots and a stretch at its end,
        # so the dots line up in columns instead of spreading over the width.
        for start in range(0, len(widgets), self.wrap):
            row = QHBoxLayout()
            row.setSpacing(8)
            for w in widgets[start:start + self.wrap]:
                row.addWidget(w)
            row.addStretch(1)
            self.grid.addLayout(row)

    def _custom(self):
        if self.gradient:
            result = pick_gradient(self.window())
            if not result:
                return
            key = "custom:" + ",".join(result["colors"]) + f"@{result['angle']}"
            look = result["colors"]
        else:
            color = pick_color(self.window())
            if not color:
                return
            key, look = color, color
        if key not in self.buttons:
            self.items.append((key, look))
            self._build()
        self.buttons[key].setChecked(True)
        self.changed.emit(key)

    def select(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def clear(self):
        self.group.setExclusive(False)
        for b in self.buttons.values():
            b.setChecked(False)
        self.group.setExclusive(True)


# -------------------------------------------------------------- the picker

class _HueBar(QWidget):
    changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.hue = 0.0
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        grad = QLinearGradient(r.topLeft(), r.topRight())
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))
        path = QPainterPath()
        path.addRoundedRect(r, 7, 7)
        p.fillPath(path, grad)
        x = r.left() + self.hue * r.width()
        p.setPen(QPen(QColor("white"), 2.5))
        p.setBrush(QColor.fromHsvF(self.hue, 1, 1))
        p.drawEllipse(QPointF(x, r.center().y()), 8, 8)

    def _set(self, x):
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        self.hue = min(0.999, max(0.0, (x - r.left()) / r.width()))
        self.update()
        self.changed.emit(self.hue)

    def mousePressEvent(self, e):
        self._set(e.position().x())

    def mouseMoveEvent(self, e):
        self._set(e.position().x())


class _ShadeSquare(QWidget):
    """Saturation left to right, brightness bottom to top, for the current hue."""

    changed = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.hue, self.sat, self.val = 0.0, 1.0, 1.0
        self.setMinimumSize(300, 200)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.setClipPath(path)
        p.fillRect(r, QColor.fromHsvF(self.hue, 1, 1))
        white = QLinearGradient(r.topLeft(), r.topRight())
        white.setColorAt(0, QColor(255, 255, 255, 255))
        white.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, white)
        black = QLinearGradient(r.topLeft(), r.bottomLeft())
        black.setColorAt(0, QColor(0, 0, 0, 0))
        black.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(r, black)
        p.setClipping(False)
        pt = QPointF(r.left() + self.sat * r.width(), r.top() + (1 - self.val) * r.height())
        p.setPen(QPen(QColor("white"), 2.5))
        p.setBrush(QColor.fromHsvF(self.hue, self.sat, self.val))
        p.drawEllipse(pt, 9, 9)

    def _set(self, pos):
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        self.sat = min(1.0, max(0.0, (pos.x() - r.left()) / r.width()))
        self.val = min(1.0, max(0.0, 1 - (pos.y() - r.top()) / r.height()))
        self.update()
        self.changed.emit(self.sat, self.val)

    def mousePressEvent(self, e):
        self._set(e.position())

    def mouseMoveEvent(self, e):
        self._set(e.position())


def _color_dialog_class():
    from spinvert.editors.base import GlassDialog, label

    class ColorDialog(GlassDialog):
        def __init__(self, start: str = "#7C5CFF"):
            super().__init__("Choose a colour", (460, 520), "Use colour")
            color = QColor(start)
            self.square = _ShadeSquare()
            self.hue = _HueBar()
            h, s, v, _ = color.getHsvF()
            self.square.hue = self.hue.hue = max(0.0, h)
            self.square.sat, self.square.val = s, v
            self.hex = QLineEdit(color.name().upper())
            self.hex.setMaxLength(7)
            self.preview = Dot([color], 34)
            self.preview.setCheckable(False)
            self.hue.changed.connect(self._hue)
            self.square.changed.connect(lambda *_: self._sync())
            self.hex.editingFinished.connect(self._typed)
            self.body.addWidget(self.square, 1)
            self.body.addWidget(self.hue)
            row = QHBoxLayout()
            row.addWidget(self.preview)
            row.addWidget(label("Hex"))
            row.addWidget(self.hex)
            row.addStretch()
            self.body.addLayout(row)

        def _hue(self, h):
            self.square.hue = h
            self.square.update()
            self._sync()

        def _sync(self):
            c = QColor.fromHsvF(self.square.hue, self.square.sat, self.square.val)
            self.hex.setText(c.name().upper())
            self.preview.colors = [c]
            self.preview.update()

        def _typed(self):
            c = QColor(self.hex.text().strip() if self.hex.text().startswith("#") else "#" + self.hex.text().strip())
            if c.isValid():
                h, s, v, _ = c.getHsvF()
                self.square.hue = self.hue.hue = max(0.0, h)
                self.square.sat, self.square.val = s, v
                self.square.update()
                self.hue.update()
                self.preview.colors = [c]
                self.preview.update()

        def color(self) -> str:
            return QColor.fromHsvF(self.square.hue, self.square.sat, self.square.val).name().upper()

    return ColorDialog


def pick_color(parent=None, start: str = "#7C5CFF") -> str | None:
    d = _color_dialog_class()(start)
    return d.color() if d.run() else None


def pick_gradient(parent=None) -> dict | None:
    from spinvert.editors.base import GlassDialog, SliderRow, label

    class GradientDialog(GlassDialog):
        def __init__(self):
            super().__init__("Design a gradient", (520, 460), "Use gradient")
            self.colors = ["#F472B6", "#34D399"]
            self.preview = QWidget()
            self.preview.setMinimumHeight(150)
            self.preview.paintEvent = self._paint_preview
            self.stops = QHBoxLayout()
            self.angle = SliderRow("Angle", 0, 360, 135, "°", width=60)
            self.angle.changed.connect(lambda _: self.preview.update())
            add = QPushButton("+ Colour")
            add.clicked.connect(self._add)
            remove = QPushButton("− Colour")
            remove.clicked.connect(self._remove)
            self.body.addWidget(label("Click a colour to change it.", muted=True))
            self.body.addLayout(self.stops)
            row = QHBoxLayout()
            row.addWidget(add)
            row.addWidget(remove)
            row.addStretch()
            self.body.addLayout(row)
            self.body.addWidget(self.angle)
            self.body.addWidget(self.preview, 1)
            self._rebuild()

        def _rebuild(self):
            while self.stops.count():
                w = self.stops.takeAt(0).widget()
                if w:
                    w.setParent(None)
            for i, c in enumerate(self.colors):
                dot = Dot([c], 40)
                dot.setCheckable(False)
                dot.clicked.connect(lambda _=False, i=i: self._edit(i))
                self.stops.addWidget(dot)
            self.stops.addStretch()
            self.preview.update()

        def _edit(self, i):
            c = pick_color(self, self.colors[i])
            if c:
                self.colors[i] = c
                self._rebuild()

        def _add(self):
            if len(self.colors) < 4:
                self.colors.append("#FFFFFF")
                self._rebuild()
                self._edit(len(self.colors) - 1)

        def _remove(self):
            if len(self.colors) > 2:
                self.colors.pop()
                self._rebuild()

        def _paint_preview(self, e):
            import math

            p = QPainter(self.preview)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(self.preview.rect()).adjusted(2, 2, -2, -2)
            a = math.radians(self.angle.get())
            c = r.center()
            half = max(r.width(), r.height()) / 2
            grad = QLinearGradient(QPointF(c.x() - math.cos(a) * half, c.y() - math.sin(a) * half),
                                   QPointF(c.x() + math.cos(a) * half, c.y() + math.sin(a) * half))
            for i, col in enumerate(self.colors):
                grad.setColorAt(i / (len(self.colors) - 1), QColor(col))
            path = QPainterPath()
            path.addRoundedRect(r, 16, 16)
            p.fillPath(path, grad)

    d = GradientDialog()
    return {"colors": d.colors, "angle": d.angle.get()} if d.run() else None

