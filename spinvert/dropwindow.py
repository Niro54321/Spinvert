"""The drop window, drawn as a liquid-glass card over the screen behind it."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from spinvert import APP_NAME
from spinvert.glassui import HEADER, MARGIN, GlassFrame
from spinvert.theme import ACCENT, app_icon, draw_mark, soft_text
from spinvert.wheel import KEY_NAMES


class DropWindow(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(500, 430)
        self.frame = GlassFrame(self, APP_NAME)
        self.over = False

        settings = QPushButton("Settings")
        settings.clicked.connect(controller.show_settings)
        hide = QPushButton("Hide to tray")
        hide.clicked.connect(self.hide)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(self.frame.close_button(self.hide))
        bottom = QHBoxLayout()
        bottom.addWidget(settings)
        bottom.addStretch()
        bottom.addWidget(hide)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MARGIN + 14, MARGIN + 10, MARGIN + 16, MARGIN + 14)
        layout.addLayout(top)
        layout.addStretch()
        layout.addLayout(bottom)
        self.frame.style_children()

    def refresh_backdrop(self) -> None:
        self.frame.refresh_backdrop()

    def place(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)

    # window events

    def moveEvent(self, event):
        self.frame.moved()

    def resizeEvent(self, event):
        self.frame.resized()

    def mousePressEvent(self, event):
        self.frame.press(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.controller.note_still_running()

    # dropping files

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.over = True
            self.update()

    def dragMoveEvent(self, event):
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.over = False
        self.update()

    def dropEvent(self, event):
        self.over = False
        self.update()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if paths:
            # Open the wheel after the drop finishes, so Explorer is not kept waiting.
            QTimer.singleShot(0, lambda: self.controller.open_files(paths))

    # painting

    def paintEvent(self, event):
        p = QPainter(self)
        self.frame.paint(p)
        look = self.frame.look
        card = self.frame.card()

        zone = QRectF(card.left() + 18, card.top() + HEADER + 4, card.width() - 36, card.height() - HEADER - 130)
        accent = ACCENT["convert"]
        fill = QColor(accent) if self.over else QColor(look.segment)
        if self.over:
            fill.setAlpha(70)
        edge = QColor(accent) if self.over else QColor(look.text)
        edge.setAlpha(230 if self.over else 120)
        pen = QPen(edge, 1.6, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.setBrush(fill)
        p.drawRoundedRect(zone, 18, 18)
        size = 54
        draw_mark(p, QRectF(zone.center().x() - size / 2, zone.top() + 22, size, size))
        font = QFont(self.font())
        font.setPixelSize(19)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        soft_text(p, QRectF(zone.left(), zone.top() + 86, zone.width(), 28), "Drop files here",
                  look.text, look.text_shadow)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        soft_text(p, QRectF(zone.left(), zone.top() + 114, zone.width(), 20),
                  "then pick a format on the wheel", look.muted, look.text_shadow)

        s = self.controller.settings
        tip = (f"Faster: start dragging any file in File Explorer, then press "
               f"{KEY_NAMES[s.convert_key]} to convert or {KEY_NAMES[s.tools_key]} for tools. "
               f"Let go over a format. Esc cancels.")
        soft_text(p, QRectF(card.left() + 20, zone.bottom() + 12, card.width() - 40, 46), tip,
                  look.text, look.text_shadow, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
        p.end()
