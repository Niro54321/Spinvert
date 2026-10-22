"""Photo editors: edit, crop, resize, add a background, redact, collage.
(Annotate is the layer editor in spinvert.editors.annotate.)

Each shows a live preview made by the same functions that save the full-size
copy (spinvert.engines.imaging), so the result matches the preview.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from spinvert.editors.base import (Background, BoxesTool, CropTool, GlassDialog, ImageCanvas, Segmented,
                                   SidePanel, SliderRow, busy, card, label, preview_copy, split, to_qimage)
from spinvert.editors.pickers import Swatches
from spinvert.engines import imaging
from spinvert.engines.images import _open, _upright


def _load(path: Path):
    return _upright(_open(path))


def _many(paths) -> str:
    return f"Applies to all {len(paths)} pictures." if len(paths) > 1 else ""


class _Debounce:
    """Call fn once things stop changing for a moment."""

    def __init__(self, fn, ms: int = 70):
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(ms)
        self.timer.timeout.connect(fn)

    def __call__(self, *args):
        self.timer.start()


def _side_panel(width: int = 330) -> tuple[QScrollArea, QVBoxLayout]:
    inner = card(QWidget())
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(14, 14, 14, 14)
    lay.setSpacing(8)
    return SidePanel(inner), lay


# ------------------------------------------------------------------ edit

class EditDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Edit photo", (1120, 760))
        self.original = preview_copy(_load(paths[0]), 1000)
        self.canvas = ImageCanvas()
        panel, lay = _side_panel()
        lay.addWidget(label("Presets", bold=True))
        self.presets = Segmented([(name, name) for name in imaging.PRESETS], "Original", wrap=3)
        self.presets.changed.connect(self._preset)
        lay.addWidget(self.presets)
        self.sliders = {}
        groups = [("Light", ["exposure", "contrast", "highlights", "shadows", "whites", "blacks"]),
                  ("Colour", ["temperature", "tint", "vibrance", "saturation"]),
                  ("Detail & effects", ["clarity", "dehaze", "sharpness", "noise", "grain", "vignette"])]
        info = {k: (name, lo, hi) for k, name, lo, hi in imaging.ADJUSTMENTS}
        self.render_soon = _Debounce(self._render)
        for title, keys in groups:
            lay.addSpacing(6)
            lay.addWidget(label(title, bold=True))
            for key in keys:
                name, lo, hi = info[key]
                row = SliderRow(name, lo, hi, 0, width=104)
                row.changed.connect(self.render_soon)
                self.sliders[key] = row
                lay.addWidget(row)
        lay.addStretch()
        self.body.addWidget(split(self.canvas, panel), 1)
        compare = QPushButton("Hold to compare")
        compare.pressed.connect(lambda: self.canvas.set_image(to_qimage(self.original)))
        compare.released.connect(self._render)
        reset = QPushButton("Reset")
        reset.clicked.connect(lambda: self._preset("Original"))
        self.footer_left.addWidget(compare)
        self.footer_left.addWidget(reset)
        self.footer_left.addWidget(label(_many(paths), muted=True))
        self._render()

    def values(self) -> dict:
        return {k: s.get() for k, s in self.sliders.items() if s.get()}

    def _preset(self, name):
        self.presets.set(name)
        values = imaging.PRESETS.get(name, {})
        for key, s in self.sliders.items():
            s.set(values.get(key, 0), quiet=True)
        self._render()

    def _render(self):
        self.canvas.set_image(to_qimage(imaging.adjust(self.original, self.values())))


def edit_photo(paths, parent=None):
    d = EditDialog(paths)
    return {"adjust": d.values()} if d.run() else None


# ------------------------------------------------------------------ crop

class CropDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Crop", (1080, 760), "Crop")
        self.full = _load(paths[0])
        self.turns, self.flip = 0, False
        self.canvas = ImageCanvas()
        self.tool = CropTool()
        self.canvas.set_tool(self.tool)
        self.canvas.changed.connect(self._update_info)
        panel, lay = _side_panel(300)
        lay.addWidget(label("Aspect ratio", bold=True))
        self.aspects = Segmented([(k, k) for k in imaging.ASPECTS], "Free", wrap=4)
        self.aspects.changed.connect(self._aspect)
        lay.addWidget(self.aspects)
        lay.addSpacing(6)
        lay.addWidget(label("Rotate and flip", bold=True))
        row = QHBoxLayout()
        for text, fn in [("⟲ Left", lambda: self._rotate(-1)), ("⟳ Right", lambda: self._rotate(1)),
                         ("⇋ Flip", self._flip)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addSpacing(6)
        lay.addWidget(label("Exact output size (pixels)", bold=True))
        self.exact = QCheckBox("Resize the crop to")
        size_row = QHBoxLayout()
        self.out_w, self.out_h = QSpinBox(), QSpinBox()
        for box in (self.out_w, self.out_h):
            box.setRange(1, 20000)
        self.out_w.setValue(1080)
        self.out_h.setValue(1080)
        size_row.addWidget(self.out_w)
        size_row.addWidget(label("×"))
        size_row.addWidget(self.out_h)
        lay.addWidget(self.exact)
        lay.addLayout(size_row)
        self.info = label("", muted=True)
        lay.addWidget(self.info)
        lay.addStretch()
        self.body.addWidget(split(self.canvas, panel), 1)
        self.footer_left.addWidget(label(_many(paths), muted=True))
        self._show()

    def _show(self):
        self.shown = imaging.rotate(self.full, self.turns, self.flip)
        self.canvas.set_image(to_qimage(preview_copy(self.shown, 1000)))
        self.tool.rect = [0.0, 0.0, 1.0, 1.0]
        self._aspect(self.aspects.get() or "Free")

    def _rotate(self, step):
        self.turns = (self.turns + step) % 4
        self._show()

    def _flip(self):
        self.flip = not self.flip
        self._show()

    def _aspect(self, key):
        value = imaging.ASPECTS[key]
        if value == "original":
            value = (self.shown.width, self.shown.height)
        self.tool.set_aspect(value[0] / value[1] if value else None)
        if value and not self.exact.isChecked():
            w = 1080
            self.out_w.setValue(w)
            self.out_h.setValue(round(w * value[1] / value[0]))
        self.canvas.update()
        self._update_info()

    def _update_info(self):
        x0, y0, x1, y1 = self.tool.rect
        w, h = round((x1 - x0) * self.shown.width), round((y1 - y0) * self.shown.height)
        self.info.setText(f"Crop: {w} × {h} px")

    def params(self) -> dict:
        p = {"rect": list(self.tool.rect), "turns": self.turns, "flip": self.flip}
        if self.exact.isChecked():
            p["size"] = [self.out_w.value(), self.out_h.value()]
        return p


def crop_photo(paths, parent=None):
    d = CropDialog(paths)
    return d.params() if d.run() else None


# ---------------------------------------------------------------- resize

class ResizeDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Resize", (620, 520), "Resize")
        im = _load(paths[0])
        self.w, self.h = im.size
        self.body.addWidget(label(f"Now {self.w} × {self.h} px. Upscaling uses high-quality Lanczos "
                                  "resampling with gentle sharpening.", muted=True))
        self.scale = Segmented([("0.25", "25%"), ("0.5", "50%"), ("2", "200%"), ("3", "300%"), ("4", "400%"),
                                ("custom", "Exact size")], "2")
        self.scale.changed.connect(self._update)
        self.body.addWidget(self.scale)
        row = QHBoxLayout()
        self.cw, self.ch = QSpinBox(), QSpinBox()
        for box in (self.cw, self.ch):
            box.setRange(1, 32000)
        self.cw.setValue(self.w * 2)
        self.ch.setValue(self.h * 2)
        self.keep = QCheckBox("Keep proportions")
        self.keep.setChecked(True)
        self.cw.valueChanged.connect(self._width_changed)
        self.ch.valueChanged.connect(self._height_changed)
        row.addWidget(self.cw)
        row.addWidget(label("×"))
        row.addWidget(self.ch)
        row.addWidget(self.keep)
        row.addStretch()
        self.body.addLayout(row)
        self.sharpen = QCheckBox("Sharpen after upscaling")
        self.sharpen.setChecked(True)
        self.body.addWidget(self.sharpen)
        self.result = label("", bold=True)
        self.body.addWidget(self.result)
        self.body.addStretch()
        self.footer_left.addWidget(label(_many(paths), muted=True))
        self._update()

    def _width_changed(self, v):
        if self.keep.isChecked():
            self.ch.blockSignals(True)
            self.ch.setValue(max(1, round(v * self.h / self.w)))
            self.ch.blockSignals(False)
        self.scale.set("custom")
        self._update()

    def _height_changed(self, v):
        if self.keep.isChecked():
            self.cw.blockSignals(True)
            self.cw.setValue(max(1, round(v * self.w / self.h)))
            self.cw.blockSignals(False)
        self.scale.set("custom")
        self._update()

    def _update(self, *_):
        key = self.scale.get()
        if key == "custom":
            w, h = self.cw.value(), self.ch.value()
        else:
            w, h = round(self.w * float(key)), round(self.h * float(key))
        self.result.setText(f"New size: {w} × {h} px")

    def params(self) -> dict:
        key = self.scale.get()
        p = {"sharpen": self.sharpen.isChecked()}
        if key == "custom":
            p["size"] = [self.cw.value(), self.ch.value()]
        else:
            p["scale"] = float(key)
        return p


def resize_photo(paths, parent=None):
    d = ResizeDialog(paths)
    return d.params() if d.run() else None


# ------------------------------------------------------------ background

def background_from_key(key: str) -> dict:
    """A swatch key to a background: a gradient name, 'custom:#a,#b@angle', or a colour."""
    if key.startswith("custom:"):
        colors, _, angle = key[7:].partition("@")
        return {"kind": "gradient", "colors": colors.split(","), "angle": float(angle or 135)}
    if key in imaging.GRADIENTS:
        return {"kind": "gradient", "name": key}
    return {"kind": "solid", "color": key}


class BackgroundDialog(GlassDialog):
    """One picture, or several side by side, on a gradient, a colour, a blurred
    copy of the photo or your own image."""

    def __init__(self, paths):
        super().__init__("Add background", (1140, 800))
        self.pictures = busy(lambda: [preview_copy(_load(p), 700 if len(paths) == 1 else 520) for p in paths])
        self.background = {"kind": "gradient", "name": "Aurora"}
        self.canvas = ImageCanvas()
        panel, lay = _side_panel(360)
        lay.addWidget(label("Gradients", bold=True))
        self.grads = Swatches([(name, colors) for name, colors in imaging.GRADIENTS.items()], "Aurora",
                              size=30, wrap=6, gradient=True)
        lay.addWidget(self.grads)
        lay.addWidget(label("Colours", bold=True))
        self.solids = Swatches([(c, c) for c in imaging.SOLIDS], None, size=30, wrap=6)
        lay.addWidget(self.solids)
        self.grads.changed.connect(lambda k: (self.solids.clear(), self._set(background_from_key(k))))
        self.solids.changed.connect(lambda c: (self.grads.clear(), self._set({"kind": "solid", "color": c})))
        row = QHBoxLayout()
        blur_photo = QPushButton("Blurred photo")
        blur_photo.clicked.connect(lambda: (self.grads.clear(), self.solids.clear(), self._set({"kind": "blur"})))
        pick = QPushButton("Image…")
        pick.clicked.connect(self._pick)
        row.addWidget(blur_photo)
        row.addWidget(pick)
        lay.addLayout(row)
        self.render_soon = _Debounce(self._render)
        self.layout_ = Segmented([("Row", "Side by side"), ("Column", "Stacked"), ("Grid", "Grid")], "Row")
        self.spacing = SliderRow("Spacing", 0, 200, 40, width=80)
        if len(paths) > 1:
            lay.addWidget(label(f"{len(paths)} pictures", bold=True))
            lay.addWidget(self.layout_)
            lay.addWidget(self.spacing)
            self.layout_.changed.connect(self.render_soon)
            self.spacing.changed.connect(self.render_soon)
        lay.addWidget(label("Frame", bold=True))
        self.padding = SliderRow("Padding", 0, 400, 120, width=80)
        self.corners = SliderRow("Corners", 0, 200, 30, width=80)
        self.shadow = SliderRow("Shadow", 0, 100, 30, width=80)
        self.blur = SliderRow("Blur", 0, 100, 0, width=80)
        for s in (self.padding, self.corners, self.shadow, self.blur):
            s.changed.connect(self.render_soon)
            lay.addWidget(s)
        lay.addWidget(label("Ratio", bold=True))
        self.ratio = Segmented([(k, k) for k in imaging.RATIOS], "Auto")
        self.ratio.changed.connect(self.render_soon)
        lay.addWidget(self.ratio)
        lay.addStretch()
        self.body.addWidget(split(self.canvas, panel), 1)
        if len(paths) > 1:
            self.footer_left.addWidget(label("All pictures become one image, in File Explorer's order.", muted=True))
        self._render()

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Background image", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.heic *.bmp *.tif *.tiff)")
        if path:
            self.grads.clear()
            self.solids.clear()
            self._set({"kind": "image", "path": path})

    def _set(self, bg):
        self.background = bg
        if bg["kind"] == "blur" and not self.blur.get():
            self.blur.set(40, quiet=True)
        self._render()

    def params(self) -> dict:
        bg = dict(self.background)
        bg["blur"] = self.blur.get()
        return {"background": bg, "padding": self.padding.get(), "corners": self.corners.get(),
                "shadow": self.shadow.get(), "ratio": self.ratio.get() or "Auto",
                "layout": self.layout_.get() or "Row", "spacing": self.spacing.get()}

    def _render(self):
        pics = self.pictures if len(self.pictures) > 1 else self.pictures[0]
        self.canvas.set_image(to_qimage(imaging.add_background(pics, self.params())))


def add_background(paths, parent=None):
    from spinvert.util import natural_key

    d = BackgroundDialog(sorted(paths, key=natural_key))
    return d.params() if d.run() else None


# ---------------------------------------------------------------- redact

REDACT_COLORS = ["#111114", "#FFFFFF", "#FF3B30", "#7C5CFF", "#FFCC00", "#34C759"]


class RedactDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Redact", (1140, 800))
        self.full = _load(paths[0])
        self.base = preview_copy(self.full, 1100)
        self.style, self.color, self.strength = "blur", "#111114", 60
        self.canvas = ImageCanvas()
        self.tool = BoxesTool(lambda: {"style": self.style, "color": self.color, "strength": self.strength})
        self.canvas.set_tool(self.tool)
        self.canvas.changed.connect(self._render)
        self.styles = Segmented([("blur", "Blur"), ("pixelate", "Pixelate"), ("solid", "Solid colour")], "blur")
        self.styles.changed.connect(lambda k: self._apply("style", k))
        self.colors = Swatches([(c, c) for c in REDACT_COLORS], "#111114", size=26, wrap=8)
        self.colors.changed.connect(lambda c: self._apply("color", c))
        self.strength_row = SliderRow("Strength", 1, 100, 60, "%", width=70)
        self.strength_row.changed.connect(lambda v: self._apply("strength", v))
        faces = QPushButton("Find faces")
        faces.clicked.connect(lambda: self._detect("faces"))
        words = QPushButton("Find text")
        words.clicked.connect(lambda: self._detect("text"))
        delete = QPushButton("Delete box")
        delete.clicked.connect(self._delete)
        row = QHBoxLayout()
        row.addWidget(self.styles)
        row.addWidget(self.strength_row, 1)
        row.addWidget(faces)
        row.addWidget(words)
        row.addWidget(delete)
        self.body.addLayout(row)
        colors_row = QHBoxLayout()
        colors_row.addWidget(label("Colour for Solid"))
        colors_row.addWidget(self.colors)
        colors_row.addStretch()
        self.body.addLayout(colors_row)
        self.status = label("Drag over anything private. Drag a box to move it, its corners to resize it, "
                            "Delete removes it. Faces and text are found on this PC by Windows.", muted=True)
        self.body.addWidget(self.status)
        self.body.addWidget(self.canvas, 1)
        self.worker = Background()
        self.worker.done.connect(self._found)
        self._render()

    def _apply(self, key, value):
        setattr(self, key, value)
        if self.tool.selected is not None:
            self.tool.boxes[self.tool.selected][key] = value
        self._render()

    def _delete(self):
        if self.tool.selected is not None:
            self.tool.boxes.pop(self.tool.selected)
            self.tool.selected = None
            self._render()

    def _detect(self, what):
        from spinvert.engines import ocr

        self.status.setText("Looking…")
        fn = ocr.find_faces if what == "faces" else ocr.text_boxes
        self.worker.start(lambda: fn(self.full))

    def _found(self, boxes, error):
        if error:
            self.status.setText(f"Couldn't search the picture: {error}")
            return
        pad = 0.01
        for b in boxes or []:
            self.tool.boxes.append({"rect": [max(0, b[0] - pad), max(0, b[1] - pad), min(1, b[2] + pad),
                                             min(1, b[3] + pad)], "style": self.style, "color": self.color,
                                    "strength": self.strength})
        self.status.setText(f"Found {len(boxes or [])}. Drag a box to move it, Delete removes it.")
        self._render()

    def _render(self):
        self.canvas.set_image(to_qimage(imaging.redact(self.base, self.tool.boxes)))


def redact(paths, parent=None):
    d = RedactDialog(paths)
    if not d.run():
        return None
    return {"areas": d.tool.boxes} if d.tool.boxes else None


# --------------------------------------------------------------- collage

class CollageTool:
    """Drag inside a cell to choose which part of its picture shows;
    the mouse wheel zooms that picture in or out."""

    def __init__(self, dialog):
        self.dialog = dialog
        self.canvas = None
        self.active = None
        self._last = None

    def _cell(self, pos):
        p = self.dialog.params()
        w, h = p["size"]
        x, y = pos[0] * w, pos[1] * h
        for i, (cx, cy, cw, ch) in enumerate(imaging.collage_cells(len(self.dialog.thumbs), p)):
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                return i, cw / w, ch / h
        return None

    def press(self, pos, e):
        hit = self._cell(pos)
        self.active = hit[0] if hit else None
        self._last = pos
        self.canvas.update()

    def move(self, pos, e):
        if self.active is None or self._last is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor if self._cell(pos) else Qt.CursorShape.ArrowCursor)
            return
        hit = self._cell(self._last) or (self.active, 0.3, 0.3)
        _, cw, ch = hit
        fx, fy = self.dialog.focus[self.active]
        zoom = self.dialog.zoom[self.active]
        k = 1.2 / max(1.0, zoom)
        fx -= (pos[0] - self._last[0]) / max(0.05, cw) * k
        fy -= (pos[1] - self._last[1]) / max(0.05, ch) * k
        self.dialog.focus[self.active] = [min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy))]
        self._last = pos
        self.dialog.render_soon()

    def release(self, pos, e):
        self._last = None

    def wheel(self, pos, delta):
        hit = self._cell(pos)
        if hit:
            i = hit[0]
            self.active = i
            self.dialog.zoom[i] = min(4.0, max(1.0, self.dialog.zoom[i] * (1.1 if delta > 0 else 1 / 1.1)))
            self.dialog.render_soon()

    def paint(self, p, canvas):
        if self.active is None:
            return
        from PySide6.QtGui import QColor, QPen

        params = self.dialog.params()
        w, h = params["size"]
        cells = imaging.collage_cells(len(self.dialog.thumbs), params)
        if self.active < len(cells):
            x, y, cw, ch = cells[self.active]
            r = canvas.norm_rect((x / w, y / h, (x + cw) / w, (y + ch) / h))
            p.setPen(QPen(QColor("#7C5CFF"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 6, 6)


class CollageDialog(GlassDialog):
    def __init__(self, paths):
        super().__init__("Collage", (1140, 800), "Make collage")
        self.thumbs = busy(lambda: [preview_copy(_load(p), 700) for p in paths])
        self.focus = [[0.5, 0.5] for _ in paths]
        self.zoom = [1.0 for _ in paths]
        self.canvas = ImageCanvas()
        self.canvas.set_tool(CollageTool(self))
        panel, lay = _side_panel(330)
        self.render_soon = _Debounce(self._render, 40)
        lay.addWidget(label("Layout", bold=True))
        self.layout_ = Segmented([(k, k) for k in ("Grid", "Row", "Column", "Featured")], "Grid", wrap=2)
        lay.addWidget(self.layout_)
        lay.addWidget(label("Size", bold=True))
        self.size = Segmented([(k, k) for k in imaging.COLLAGE_SIZES], "Square", wrap=2)
        lay.addWidget(self.size)
        self.spacing = SliderRow("Spacing", 0, 60, 12, width=70)
        self.corners = SliderRow("Corners", 0, 80, 16, width=70)
        lay.addWidget(self.spacing)
        lay.addWidget(self.corners)
        lay.addWidget(label("Background", bold=True))
        self.bg = "#FFFFFF"
        colors = Swatches([(c, c) for c in imaging.SOLIDS], "#FFFFFF", size=28, wrap=6)
        colors.changed.connect(lambda c: (setattr(self, "bg", c), self._render()))
        lay.addWidget(colors)
        lay.addWidget(label("Save as", bold=True))
        self.format = Segmented([("jpg", "JPG"), ("png", "PNG")], "jpg")
        lay.addWidget(self.format)
        reset = QPushButton("Reset positions")
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)
        for w in (self.layout_, self.size, self.format):
            w.changed.connect(self.render_soon)
        for s in (self.spacing, self.corners):
            s.changed.connect(self.render_soon)
        lay.addStretch()
        self.body.addWidget(split(self.canvas, panel), 1)
        self.footer_left.addWidget(label("Drag inside a picture to choose the part that shows; "
                                         "scroll to zoom it.", muted=True))
        self._render()

    def _reset(self):
        self.focus = [[0.5, 0.5] for _ in self.thumbs]
        self.zoom = [1.0 for _ in self.thumbs]
        self._render()

    def params(self) -> dict:
        return {"layout": self.layout_.get(), "size": list(imaging.COLLAGE_SIZES[self.size.get()]),
                "spacing": self.spacing.get(), "corners": self.corners.get(), "background": self.bg,
                "format": self.format.get(), "focus": [list(f) for f in self.focus], "zoom": list(self.zoom)}

    def _render(self):
        p = self.params()
        p["size"] = [p["size"][0] // 4, p["size"][1] // 4]
        self.canvas.set_image(to_qimage(imaging.collage(self.thumbs, p)))


def make_collage(paths, parent=None):
    from spinvert.util import natural_key

    paths = sorted(paths, key=natural_key)
    d = CollageDialog(paths)
    return d.params() if d.run() else None
