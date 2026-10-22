"""The layer editor behind Annotate (and the overlays of the video editor).

Click a layer to select it, drag to move it, drag a corner to resize it.
Right-click for more (edit, bigger, smaller, duplicate, order, delete);
Delete removes it. Text is typed right on the picture, like in Photoshop,
in any installed font, with an optional background and shadow. Layers are
listed at the bottom, back to front; drag them to change the order.
"""

from __future__ import annotations

import copy
import json
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFontComboBox, QHBoxLayout, QListView,
                               QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from spinvert import layers as L
from spinvert.editors.base import GlassDialog, Segmented, SliderRow, card, label, preview_copy, to_qimage
from spinvert.editors.pickers import Swatches

ACCENT = QColor("#7C5CFF")
PALETTE = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#0A84FF", "#7C5CFF", "#F472B6", "#FFFFFF", "#111114"]
DRAW_TOOLS = ("arrow", "line", "rect", "ellipse", "magnify")
TOOLS = [("select", "↖ Select"), ("arrow", "Arrow"), ("rect", "Box"), ("ellipse", "Circle"), ("line", "Line"),
         ("pen", "Pen"), ("highlight", "Highlight"), ("text", "Text"), ("number", "Number"),
         ("magnify", "Magnifier")]


class LayerCanvas(QWidget):
    """The picture with its layers, and the mouse and keyboard to edit them."""

    selection = Signal(object)  # the selected layer dict, or None
    edited = Signal()           # the layer list changed

    def __init__(self, image: QImage, layers: list | None = None):
        super().__init__()
        self.image = image
        self.layers = layers or []
        self.selected = None
        self.tool = "select"
        self.defaults = {}         # style for new layers, per kind
        self.editor = None
        self.editing = None
        self.time = None           # video: only layers whose start..end covers this show
        self._mode = None
        self._history, self._future = [json.dumps(self.layers)], []
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(520, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # geometry -----------------------------------------------------------

    @property
    def W(self):
        return self.image.width() or 1

    @property
    def H(self):
        return self.image.height() or 1

    def target(self) -> QRectF:
        area = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        ratio = self.W / self.H
        if area.width() / area.height() > ratio:
            w = area.height() * ratio
            return QRectF(area.center().x() - w / 2, area.top(), w, area.height())
        h = area.width() / ratio
        return QRectF(area.left(), area.center().y() - h / 2, area.width(), h)

    def _scale(self) -> float:
        return self.target().width() / self.W

    def to_img(self, pos: QPointF) -> QPointF:
        t = self.target()
        s = self._scale()
        return QPointF((pos.x() - t.left()) / s, (pos.y() - t.top()) / s)

    def to_widget(self, r: QRectF) -> QRectF:
        t = self.target()
        s = self._scale()
        return QRectF(t.left() + r.left() * s, t.top() + r.top() * s, r.width() * s, r.height() * s)

    def layer(self, layer_id):
        return next((x for x in self.layers if x["id"] == layer_id), None)

    @property
    def current(self):
        return self.layer(self.selected)

    def visible(self) -> list:
        if self.time is None:
            return self.layers
        return [x for x in self.layers if x.get("start", 0) <= self.time <= x.get("end", 1e12)]

    # history ------------------------------------------------------------

    def commit(self):
        state = json.dumps(self.layers)
        if state != self._history[-1]:
            self._history.append(state)
            self._future.clear()
        self.edited.emit()
        self.update()

    def undo(self):
        if len(self._history) > 1:
            self._future.append(self._history.pop())
            self.layers[:] = json.loads(self._history[-1])
            self._reselect()

    def redo(self):
        if self._future:
            self._history.append(self._future.pop())
            self.layers[:] = json.loads(self._history[-1])
            self._reselect()

    def _reselect(self):
        if not self.layer(self.selected):
            self.selected = None
        self.selection.emit(self.current)
        self.edited.emit()
        self.update()

    def select(self, layer_id):
        self.selected = layer_id
        self.selection.emit(self.current)
        self.update()

    # operations -----------------------------------------------------------

    def add(self, layer):
        self.layers.append(layer)
        self.select(layer["id"])
        self.commit()

    def delete(self):
        if self.current:
            self.layers.remove(self.current)
            self.select(None)
            self.commit()

    def duplicate(self):
        if self.current:
            twin = copy.deepcopy(self.current)
            twin["id"] = L.new(twin["type"])["id"]
            L.translate(twin, 0.03, 0.03)
            self.add(twin)

    def order(self, step: int):
        """step: +1 forward, -1 back, +99 front, -99 back."""
        layer = self.current
        if not layer:
            return
        i = self.layers.index(layer)
        j = max(0, min(len(self.layers) - 1, i + step))
        self.layers.insert(j, self.layers.pop(i))
        self.commit()

    def resize_by(self, factor: float):
        if self.current:
            L.scale(self.current, factor, self.W, self.H)
            self.commit()

    def next_number(self) -> int:
        return 1 + max((x.get("number", 0) for x in self.layers if x["type"] == "number"), default=0)

    def style_for(self, kind: str) -> dict:
        return copy.deepcopy(self.defaults.get(kind, {}))

    # text editing ---------------------------------------------------------

    def edit_text(self, layer):
        self.finish_text()
        self.select(layer["id"])
        self.editing = layer["id"]
        editor = QPlainTextEdit(self)
        editor.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.document().setDocumentMargin(0)
        editor.setPlainText(layer.get("text", ""))
        editor.textChanged.connect(lambda: self._typed(layer, editor))
        editor.installEventFilter(self)
        self.editor = editor
        self._style_editor(layer)
        editor.show()
        editor.setFocus()
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        self.update()

    def _style_editor(self, layer):
        if not self.editor:
            return
        font = QFont(L.text_font(layer, self.W, self.H))
        font.setPixelSize(max(4, round(font.pixelSize() * self._scale())))
        self.editor.setFont(font)
        color = QColor(layer.get("color", "#FFFFFF"))
        bg = layer.get("bg", {})
        back = QColor(bg.get("color", "#111114")) if bg.get("on") else QColor(0, 0, 0, 0)
        if bg.get("on"):
            back.setAlpha(int(255 * bg.get("opacity", 85) / 100))
        self.editor.setStyleSheet(f"QPlainTextEdit {{ background: rgba({back.red()},{back.green()},{back.blue()},"
                                  f"{back.alpha()}); color: {color.name()}; border: 1.5px dashed #7C5CFF; "
                                  f"border-radius: 6px; padding: 0; }}")
        self._place_editor(layer)

    def _place_editor(self, layer):
        if not self.editor:
            return
        r = self.to_widget(L.text_rect(layer, self.W, self.H))
        metrics = QFontMetricsF(self.editor.font())
        lines = (self.editor.toPlainText() or " ").split("\n")
        width = max(metrics.horizontalAdvance(line or " ") for line in lines) + metrics.averageCharWidth() * 2 + 8
        height = metrics.lineSpacing() * len(lines) + 8
        self.editor.setGeometry(int(r.left()) - 4, int(r.top()) - 4, int(max(width, 60)), int(height))

    def _typed(self, layer, editor):
        layer["text"] = editor.toPlainText()
        self._place_editor(layer)
        self.edited.emit()
        self.update()

    def finish_text(self):
        if not self.editor:
            return
        editor, self.editor = self.editor, None
        layer = self.layer(self.editing)
        self.editing = None
        editor.removeEventFilter(self)
        editor.deleteLater()
        if layer is not None and not layer.get("text", "").strip():
            self.layers.remove(layer)
            self.select(None)
        self.commit()
        self.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.editor and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.finish_text()
            return True
        if obj is self.editor and event.type() == event.Type.FocusOut:
            QTimer.singleShot(0, lambda: self.editor is obj and not obj.hasFocus() and self.finish_text())
        return False

    # painting -------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        t = self.target()
        clip = QPainterPath()
        clip.addRoundedRect(t, 10, 10)
        p.save()
        p.setClipPath(clip)
        p.fillRect(t, QColor(255, 255, 255, 20))
        if not self.image.isNull():
            p.drawImage(t, self.image)
        p.translate(t.topLeft())
        s = self._scale()
        p.scale(s, s)
        L.paint_all(p, self.visible(), self.W, self.H, self.image, skip=self.editing)
        p.restore()
        layer = self.current
        if layer and self.editing != layer["id"]:
            self._paint_selection(p, layer)
        p.end()

    def _handles(self, layer):
        if layer["type"] in ("arrow", "line") and len(layer["points"]) >= 2:
            a, b = layer["points"][0], layer["points"][-1]
            t, s = self.target(), self._scale()
            return {"end0": QPointF(t.left() + a[0] * self.W * s, t.top() + a[1] * self.H * s),
                    "end1": QPointF(t.left() + b[0] * self.W * s, t.top() + b[1] * self.H * s)}
        r = self.to_widget(L.bounds(layer, self.W, self.H))
        return {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}

    def _paint_selection(self, p, layer):
        r = self.to_widget(L.bounds(layer, self.W, self.H))
        if layer["type"] not in ("arrow", "line"):
            p.setPen(QPen(ACCENT, 1.4, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
        for pt in self._handles(layer).values():
            p.setPen(QPen(ACCENT, 1.6))
            p.setBrush(QColor("white"))
            p.drawEllipse(pt, 5.5, 5.5)

    # mouse ----------------------------------------------------------------

    def _handle_at(self, pos: QPointF):
        layer = self.current
        if not layer:
            return None
        for name, pt in self._handles(layer).items():
            if math.hypot(pos.x() - pt.x(), pos.y() - pt.y()) < 9:
                return name
        return None

    def _hit(self, pos: QPointF):
        img = self.to_img(pos)
        return L.top_hit(self.visible(), img.x(), img.y(), self.W, self.H, slack=6 / self._scale())

    def mousePressEvent(self, e):
        self.setFocus()
        if self.editor:
            self.finish_text()
        pos = e.position()
        img = self.to_img(pos)
        nx, ny = img.x() / self.W, img.y() / self.H
        if e.button() == Qt.MouseButton.RightButton:
            hit = self._hit(pos)
            self.select(hit["id"] if hit else None)
            return
        handle = self._handle_at(pos)
        if handle:
            self._mode = ("handle", handle, nx, ny, copy.deepcopy(self.current))
            return
        hit = self._hit(pos)
        tool = self.tool
        if tool == "select" or (hit and hit["id"] == self.selected and tool not in ("pen", "highlight")):
            if hit:
                self.select(hit["id"])
                self._mode = ("move", nx, ny)
            else:
                self.select(None)
            return
        if tool == "text":
            if hit and hit["type"] == "text":
                self.edit_text(hit)
                return
            layer = L.new("text", points=[[nx, ny]], **self.style_for("text"))
            self.layers.append(layer)
            self.edit_text(layer)
            return
        if tool == "number":
            self.add(L.new("number", points=[[nx, ny]], number=self.next_number(), **self.style_for("number")))
            return
        layer = L.new(tool, points=[[nx, ny], [nx, ny]], **self.style_for(tool))
        if tool == "magnify":
            layer["radius"] = 0.0
        self.layers.append(layer)
        self.select(layer["id"])
        self._mode = ("draw", nx, ny)

    def mouseMoveEvent(self, e):
        pos = e.position()
        img = self.to_img(pos)
        nx, ny = img.x() / self.W, img.y() / self.H
        if not self._mode:
            if self._handle_at(pos):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif self._hit(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor if self.tool == "select" else Qt.CursorShape.CrossCursor)
            return
        layer = self.current
        if layer is None:
            return
        kind = self._mode[0]
        if kind == "move":
            _, ox, oy = self._mode
            L.translate(layer, nx - ox, ny - oy)
            self._mode = ("move", nx, ny)
        elif kind == "draw":
            if layer["type"] in ("pen", "highlight"):
                layer["points"].append([nx, ny])
            elif layer["type"] == "magnify":
                cx, cy = layer["points"][0]
                layer["radius"] = math.hypot((nx - cx) * self.W, (ny - cy) * self.H) / self.W
            else:
                layer["points"][-1] = [nx, ny]
        elif kind == "handle":
            _, name, sx, sy, original = self._mode
            if name in ("end0", "end1"):
                layer["points"][0 if name == "end0" else -1] = [nx, ny]
            else:
                c = L.bounds(original, self.W, self.H).center()
                before = math.hypot(sx * self.W - c.x(), sy * self.H - c.y()) or 1
                after = math.hypot(nx * self.W - c.x(), ny * self.H - c.y())
                restored = copy.deepcopy(original)
                L.scale(restored, max(0.05, after / before), self.W, self.H)
                layer.clear()
                layer.update(restored)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._mode and self._mode[0] == "draw":
            layer = self.current
            if layer:
                pts = layer["points"]
                tiny = (layer["type"] == "magnify" and layer.get("radius", 0) < 0.01) or (
                    layer["type"] not in ("pen", "highlight", "magnify")
                    and math.hypot((pts[0][0] - pts[-1][0]) * self.W, (pts[0][1] - pts[-1][1]) * self.H) < 4)
                if tiny:
                    self.layers.remove(layer)
                    self.select(None)
        if self._mode:
            self._mode = None
            self.commit()

    def mouseDoubleClickEvent(self, e):
        hit = self._hit(e.position())
        if hit and hit["type"] == "text":
            self.edit_text(hit)
        elif hit:
            self.select(hit["id"])

    def contextMenuEvent(self, e):
        hit = self._hit(QPointF(e.pos()))
        if hit:
            self.select(hit["id"])
        if not self.current:
            return
        menu = QMenu(self)
        layer = self.current
        if layer["type"] == "text":
            menu.addAction("Edit text", lambda: self.edit_text(layer))
        menu.addAction("Bigger", lambda: self.resize_by(1.15))
        menu.addAction("Smaller", lambda: self.resize_by(1 / 1.15))
        menu.addAction("Duplicate\tCtrl+D", self.duplicate)
        menu.addSeparator()
        menu.addAction("Bring to front", lambda: self.order(99))
        menu.addAction("Bring forward", lambda: self.order(1))
        menu.addAction("Send backward", lambda: self.order(-1))
        menu.addAction("Send to back", lambda: self.order(-99))
        menu.addSeparator()
        menu.addAction("Delete\tDel", self.delete)
        menu.exec(e.globalPos())

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.Undo):
            self.undo()
        elif e.matches(QKeySequence.StandardKey.Redo):
            self.redo()
        elif e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete()
        elif e.key() == Qt.Key.Key_D and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate()
        elif e.key() == Qt.Key.Key_Escape:
            self.select(None)
        elif e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.current:
            step = (10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
            dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(e.key(), 0) / self.W
            dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(e.key(), 0) / self.H
            L.translate(self.current, dx, dy)
            self.commit()
        else:
            super().keyPressEvent(e)


class LayerList(QListWidget):
    """Layers from back (left) to front (right). Drag to reorder."""

    def __init__(self, canvas: LayerCanvas):
        super().__init__()
        self.canvas = canvas
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setFixedHeight(54)
        self.setSpacing(4)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.model().rowsMoved.connect(self._moved)
        self.itemSelectionChanged.connect(self._picked)
        canvas.edited.connect(self.refresh)
        canvas.selection.connect(lambda layer: self._show_selection(layer))
        self._busy = False

    def refresh(self):
        self._busy = True
        self.clear()
        for layer in self.canvas.layers:
            item = QListWidgetItem(L.name(layer))
            item.setData(Qt.ItemDataRole.UserRole, layer["id"])
            item.setSizeHint(QSize(max(90, 12 + 7 * len(L.name(layer))), 36))
            self.addItem(item)
            if layer["id"] == self.canvas.selected:
                item.setSelected(True)
        self._busy = False

    def _moved(self, *args):
        ids = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        by_id = {x["id"]: x for x in self.canvas.layers}
        self.canvas.layers[:] = [by_id[i] for i in ids if i in by_id]
        self.canvas.commit()

    def _picked(self):
        if self._busy:
            return
        items = self.selectedItems()
        if items:
            self.canvas.select(items[0].data(Qt.ItemDataRole.UserRole))

    def _show_selection(self, layer):
        self._busy = True
        for i in range(self.count()):
            self.item(i).setSelected(bool(layer) and self.item(i).data(Qt.ItemDataRole.UserRole) == layer["id"])
        self._busy = False


class Properties(QWidget):
    """Style of the selected layer, or of the next one drawn with the current tool."""

    def __init__(self, canvas: LayerCanvas):
        super().__init__()
        self.canvas = canvas
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.title = label("", bold=True)
        lay.addWidget(self.title)
        self.colors = Swatches([(c, c) for c in PALETTE], PALETTE[0], size=26, wrap=6)
        self.colors.changed.connect(lambda c: self._set("color", c))
        lay.addWidget(self.colors)
        self.width_row = SliderRow("Thickness", 1, 40, 6, width=86)
        self.width_row.changed.connect(lambda v: self._set("width", v))
        self.size_row = SliderRow("Size", 6, 120, 26, width=86)
        self.size_row.changed.connect(lambda v: self._set("size", v))
        self.zoom_row = SliderRow("Zoom", 11, 60, 20, "×", scale=10, width=86)
        self.zoom_row.changed.connect(lambda v: self._set("zoom", v / 10))
        self.opacity = SliderRow("Opacity", 10, 100, 100, "%", width=86)
        self.opacity.changed.connect(lambda v: self._set("opacity", v))
        for w in (self.width_row, self.size_row, self.zoom_row, self.opacity):
            lay.addWidget(w)
        # text
        self.text_box = QWidget()
        t = QVBoxLayout(self.text_box)
        t.setContentsMargins(0, 4, 0, 0)
        t.setSpacing(7)
        self.font_box = QFontComboBox()
        self.font_box.currentFontChanged.connect(lambda f: self._set("font", f.family()))
        t.addWidget(label("Font", bold=True))
        t.addWidget(self.font_box)
        self.text_size = SliderRow("Size", 10, 400, 55, width=60)
        self.text_size.changed.connect(lambda v: self._set("size", v))
        t.addWidget(self.text_size)
        styles = QHBoxLayout()
        self.bold = QPushButton("B")
        self.italic = QPushButton("I")
        for b, key in ((self.bold, "bold"), (self.italic, "italic")):
            b.setCheckable(True)
            b.setProperty("segment", True)
            b.toggled.connect(lambda on, k=key: self._set(k, on))
            styles.addWidget(b)
        self.align = Segmented([("auto", "Auto"), ("left", "Left"), ("center", "Centre"), ("right", "Right")], "auto")
        self.align.changed.connect(lambda k: self._set("align", k))
        styles.addWidget(self.align)
        t.addLayout(styles)
        self.bg_on = QCheckBox("Background behind the text")
        self.bg_on.toggled.connect(lambda on: self._set_sub("bg", "on", on))
        self.bg_colors = Swatches([(c, c) for c in PALETTE], "#111114", size=24, wrap=6)
        self.bg_colors.changed.connect(lambda c: self._set_sub("bg", "color", c))
        self.bg_opacity = SliderRow("Opacity", 10, 100, 85, "%", width=60)
        self.bg_opacity.changed.connect(lambda v: self._set_sub("bg", "opacity", v))
        self.bg_round = SliderRow("Rounding", 0, 100, 35, width=60)
        self.bg_round.changed.connect(lambda v: self._set_sub("bg", "radius", v))
        self.bg_pad = SliderRow("Padding", 0, 100, 35, width=60)
        self.bg_pad.changed.connect(lambda v: self._set_sub("bg", "padding", v))
        self.sh_on = QCheckBox("Shadow")
        self.sh_on.toggled.connect(lambda on: self._set_sub("shadow", "on", on))
        self.sh_colors = Swatches([(c, c) for c in ("#000000", "#FFFFFF", "#7C5CFF", "#FF3B30")], "#000000", size=24)
        self.sh_colors.changed.connect(lambda c: self._set_sub("shadow", "color", c))
        self.sh_blur = SliderRow("Softness", 0, 40, 4, width=60)
        self.sh_blur.changed.connect(lambda v: self._set_sub("shadow", "blur", v))
        self.sh_dist = SliderRow("Distance", 0, 40, 3, width=60)
        self.sh_dist.changed.connect(lambda v: self._set_sub("shadow", "distance", v))
        self.sh_opacity = SliderRow("Strength", 5, 100, 55, "%", width=60)
        self.sh_opacity.changed.connect(lambda v: self._set_sub("shadow", "opacity", v))
        for w in (self.bg_on, self.bg_colors, self.bg_opacity, self.bg_round, self.bg_pad, self.sh_on, self.sh_colors,
                  self.sh_blur, self.sh_dist, self.sh_opacity):
            t.addWidget(w)
        lay.addWidget(self.text_box)
        lay.addStretch()
        canvas.selection.connect(lambda _: self.load())
        self.load()

    def _target(self) -> dict:
        layer = self.canvas.current
        if layer is not None:
            return layer
        kind = self.canvas.tool if self.canvas.tool != "select" else "arrow"
        if kind not in self.canvas.defaults:
            base = L.new(kind)
            self.canvas.defaults[kind] = {k: v for k, v in base.items() if k not in ("id", "type", "points", "text",
                                                                                       "number")}
        return self.canvas.defaults[kind]

    def _kind(self) -> str:
        layer = self.canvas.current
        return layer["type"] if layer else (self.canvas.tool if self.canvas.tool != "select" else "arrow")

    def _set(self, key, value):
        if self._loading:
            return
        self._target()[key] = value
        self._after()

    def _set_sub(self, group, key, value):
        if self._loading:
            return
        target = self._target()
        target.setdefault(group, {})[key] = value
        self._after()

    def _after(self):
        if self.canvas.editor and self.canvas.current:
            self.canvas._style_editor(self.canvas.current)
        self.canvas.update()
        if self.canvas.current is not None:
            self._commit_soon()

    def _commit_soon(self):
        if not hasattr(self, "_timer"):
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(400)
            self._timer.timeout.connect(self.canvas.commit)
        self._timer.start()

    def load(self):
        self._loading = True
        kind = self._kind()
        t = self._target()
        self.title.setText(("Selected: " + L.name(self.canvas.current)) if self.canvas.current
                           else f"New {L.NAMES.get(kind, kind).lower()}")
        self.colors.select(t.get("color", "#FF3B30"))
        self.width_row.setVisible(kind in ("arrow", "line", "rect", "ellipse", "pen", "highlight"))
        self.width_row.set(t.get("width", 6), quiet=True)
        self.size_row.setVisible(kind == "number")
        self.size_row.set(t.get("size", 26), quiet=True)
        self.zoom_row.setVisible(kind == "magnify")
        self.zoom_row.set(round(t.get("zoom", 2.0) * 10), quiet=True)
        self.opacity.set(t.get("opacity", 100), quiet=True)
        self.text_box.setVisible(kind == "text")
        if kind == "text":
            self.font_box.setCurrentFont(QFont(t.get("font", "Segoe UI")))
            self.text_size.set(round(t.get("size", 55)), quiet=True)
            self.bold.setChecked(bool(t.get("bold")))
            self.italic.setChecked(bool(t.get("italic")))
            self.align.set(t.get("align", "auto"))
            bg, sh = t.get("bg", {}), t.get("shadow", {})
            self.bg_on.setChecked(bool(bg.get("on")))
            self.bg_colors.select(bg.get("color", "#111114"))
            self.bg_opacity.set(bg.get("opacity", 85), quiet=True)
            self.bg_round.set(bg.get("radius", 35), quiet=True)
            self.bg_pad.set(bg.get("padding", 35), quiet=True)
            self.sh_on.setChecked(bool(sh.get("on")))
            self.sh_colors.select(sh.get("color", "#000000"))
            self.sh_blur.set(sh.get("blur", 4), quiet=True)
            self.sh_dist.set(sh.get("distance", 3), quiet=True)
            self.sh_opacity.set(sh.get("opacity", 55), quiet=True)
        self._loading = False


def side_panel(widget: QWidget, width: int = 320) -> QScrollArea:
    inner = card(QWidget())
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(14, 14, 14, 14)
    lay.addWidget(widget)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(inner)
    scroll.setFixedWidth(width)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return scroll


class AnnotateDialog(GlassDialog):
    def __init__(self, paths):
        from spinvert.engines.images import _open, _upright

        super().__init__("Annotate", (1320, 860))
        self.canvas = LayerCanvas(to_qimage(preview_copy(_upright(_open(paths[0])), 1400)))
        self.tools = Segmented(TOOLS, "select")
        self.tools.changed.connect(self._tool)
        picture = QPushButton("+ Picture")
        picture.clicked.connect(self._picture)
        top = QHBoxLayout()
        top.addWidget(self.tools, 1)
        top.addWidget(picture)
        self.props = Properties(self.canvas)
        middle = QHBoxLayout()
        middle.addWidget(self.canvas, 1)
        middle.addWidget(side_panel(self.props))
        self.layer_list = LayerList(self.canvas)
        bottom = QHBoxLayout()
        bottom.addWidget(label("Layers  (back → front)", bold=True))
        bottom.addWidget(self.layer_list, 1)
        for text, fn in (("◀ Back", lambda: self.canvas.order(-1)), ("Front ▶", lambda: self.canvas.order(1)),
                         ("Delete", self.canvas.delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bottom.addWidget(b)
        self.body.addLayout(top)
        self.body.addLayout(middle, 1)
        self.body.addLayout(bottom)
        undo = QPushButton("Undo")
        undo.clicked.connect(self.canvas.undo)
        redo = QPushButton("Redo")
        redo.clicked.connect(self.canvas.redo)
        self.footer_left.addWidget(undo)
        self.footer_left.addWidget(redo)
        self.footer_left.addWidget(label("Double-click text to edit it. Right-click a layer for more.", muted=True))

    def _tool(self, key):
        self.canvas.finish_text()
        self.canvas.tool = key
        if key != "select":
            self.canvas.select(None)
        self.props.load()

    def _picture(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add a picture", "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.heic *.bmp *.gif *.svg)")
        if path:
            img = L._image(path)
            aspect = img.width() / img.height() if not img.isNull() and img.height() else 1.0
            self.canvas.add(L.new("image", path=path, points=[[0.32, 0.3]], w=0.36, aspect=aspect))

    def accept(self):
        self.canvas.finish_text()
        super().accept()


def annotate(paths, parent=None):
    d = AnnotateDialog(paths)
    if not d.run():
        return None
    return {"layers": d.canvas.layers} if d.canvas.layers else None
