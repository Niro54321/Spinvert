"""Spreadsheets: XLSX with openpyxl, CSV and TSV with the csv module,
XLS and PDF output through Excel."""

from __future__ import annotations

import csv
import datetime as dt
import re
import tempfile
from pathlib import Path

from spinvert.engines import office
from spinvert.util import ConversionError, ext_of, safe_name

INT = re.compile(r"^-?(0|[1-9]\d{0,14})$")
FLOAT = re.compile(r"^-?(0|[1-9]\d*)?\.\d+$")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _read_delimited(path: Path, delimiter: str | None):
    text = _read_text(path)
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    return [row for row in csv.reader(text.splitlines(), delimiter=delimiter)]


def _cell_out(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat(sep=" ")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def parse_cell(text: str):
    """Numbers stay numbers in a spreadsheet; '01234' stays text."""
    if INT.match(text):
        return int(text)
    if FLOAT.match(text):
        return float(text)
    return text


def read_sheets(ctx, path: Path) -> list[tuple[str, list[list]]]:
    kind = ext_of(path)
    if kind == "csv":
        return [(path.stem, _read_delimited(path, None))]
    if kind == "tsv":
        return [(path.stem, _read_delimited(path, "\t"))]
    if kind == "ods":
        return _read_ods(path)
    if kind == "xls":
        with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
            xlsx = Path(tmp) / f"{path.stem}.xlsx"
            office.excel_save(path, xlsx, "xlsx")
            return read_sheets(ctx, xlsx)
    from openpyxl import load_workbook

    try:
        book = load_workbook(str(path), read_only=True, data_only=True)
    except Exception as e:
        raise ConversionError(f"Can't read {path.name}: {e}") from e
    sheets = []
    for ws in book.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        while rows and all(v is None for v in rows[-1]):
            rows.pop()
        sheets.append((ws.title, rows))
    book.close()
    return sheets


def write_xlsx(sheets, out: Path) -> None:
    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets:
        ws = book.create_sheet(safe_name(name)[:31])
        for row in rows:
            ws.append([parse_cell(v) if isinstance(v, str) else v for v in row])
    if not book.worksheets:
        book.create_sheet("Sheet1")
    book.save(str(out))


def to_delimited(ext: str):
    delimiter = "\t" if ext == "tsv" else ","

    def run(ctx):
        src = ctx.inputs[0]
        sheets = [s for s in read_sheets(ctx, src) if s[1]] or [(src.stem, [])]
        outs = []
        for name, rows in sheets:
            stem = src.stem if len(sheets) == 1 else f"{src.stem} - {safe_name(name)}"
            out = ctx.output(stem, ext)
            with open(out, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh, delimiter=delimiter)
                for row in rows:
                    writer.writerow([_cell_out(v) for v in row])
            outs.append(out)
        return outs
    return run


# ODS (OpenDocument, LibreOffice's format) is a zip with the cells in
# content.xml. Simple enough to read and write here, without another library.

NS = {"office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
      "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
      "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"
MAX_REPEAT = 1000  # empty filler cells/rows can repeat a million times


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _read_ods(path: Path):
    import xml.etree.ElementTree as ET
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("content.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ConversionError(f"Can't read {path.name}: not a valid ODS file.") from e
    sheets = []
    for table in root.iter(_q("table", "table")):
        rows = []
        for row in table.iter(_q("table", "table-row")):
            cells = []
            for cell in row:
                if cell.tag not in (_q("table", "table-cell"), _q("table", "covered-table-cell")):
                    continue
                kind = cell.get(_q("office", "value-type"))
                if kind in ("float", "percentage", "currency"):
                    value = parse_cell(cell.get(_q("office", "value"), ""))
                elif kind == "date":
                    value = cell.get(_q("office", "date-value"))
                elif kind == "boolean":
                    value = cell.get(_q("office", "boolean-value")) == "true"
                else:
                    value = "\n".join("".join(p.itertext()) for p in cell.iter(_q("text", "p"))) or None
                repeat = int(cell.get(_q("table", "number-columns-repeated"), "1"))
                cells.extend([value] * (min(repeat, MAX_REPEAT) if value is not None else min(repeat, 1)))
            while cells and cells[-1] is None:
                cells.pop()
            repeat = int(row.get(_q("table", "number-rows-repeated"), "1"))
            rows.extend([cells] * (min(repeat, MAX_REPEAT) if cells else min(repeat, 1)))
        while rows and not rows[-1]:
            rows.pop()
        sheets.append((table.get(_q("table", "name"), "Sheet"), rows))
    return sheets


def write_ods(sheets, out: Path) -> None:
    import zipfile
    from xml.sax.saxutils import escape, quoteattr

    parts = []
    for name, rows in sheets or [("Sheet1", [])]:
        parts.append(f"<table:table table:name={quoteattr(safe_name(name)[:31])}>")
        for row in rows or [[]]:
            parts.append("<table:table-row>")
            for value in row:
                value = parse_cell(value) if isinstance(value, str) else value
                if isinstance(value, bool) or value is None:
                    parts.append("<table:table-cell/>" if value is None else
                                 f'<table:table-cell office:value-type="boolean" '
                                 f'office:boolean-value="{str(value).lower()}"><text:p>'
                                 f"{str(value).upper()}</text:p></table:table-cell>")
                elif isinstance(value, (int, float)):
                    parts.append(f'<table:table-cell office:value-type="float" office:value="{value}">'
                                 f"<text:p>{value}</text:p></table:table-cell>")
                else:
                    parts.append('<table:table-cell office:value-type="string"><text:p>'
                                 f"{escape(_cell_out(value))}</text:p></table:table-cell>")
            parts.append("</table:table-row>")
        parts.append("</table:table>")
    xmlns = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())
    content = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {xmlns} '
               f'office:version="1.2"><office:body><office:spreadsheet>{"".join(parts)}'
               f"</office:spreadsheet></office:body></office:document-content>")
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
                'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
                f'<manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="{ODS_MIME}"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                "</manifest:manifest>")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), ODS_MIME, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", manifest)
        zf.writestr("content.xml", content)


def to_ods(ctx):
    src = ctx.inputs[0]
    out = ctx.output(src.stem, "ods")
    write_ods(read_sheets(ctx, src), out)
    return [out]


def to_xlsx(ctx):
    src = ctx.inputs[0]
    out = ctx.output(src.stem, "xlsx")
    if ext_of(src) == "xls":
        office.excel_save(src, out, "xlsx")
    else:
        write_xlsx(read_sheets(ctx, src), out)
    return [out]


def to_pdf(ctx):
    src = ctx.inputs[0]
    out = ctx.output(src.stem, "pdf")
    if ext_of(src) in ("xlsx", "xls", "ods"):
        office.excel_save(src, out, "pdf")
        return [out]
    with tempfile.TemporaryDirectory(prefix="spinvert-") as tmp:
        xlsx = Path(tmp) / f"{src.stem}.xlsx"
        write_xlsx(read_sheets(ctx, src), xlsx)
        office.excel_save(xlsx, out, "pdf")
    return [out]
