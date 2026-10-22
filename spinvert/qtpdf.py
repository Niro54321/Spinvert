"""HTML to PDF with Qt's text engine. The fallback when Word is not installed."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument


def html_to_pdf(html: str, base_dir: Path, out: Path) -> None:
    writer = QPdfWriter(str(out))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)
    writer.setResolution(300)
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Segoe UI", 11))
    doc.setBaseUrl(QUrl.fromLocalFile(str(base_dir) + "/"))
    doc.setHtml(html)
    doc.print_(writer)
