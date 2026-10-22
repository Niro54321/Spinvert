"""Microsoft Office, when it is installed, for the best Word, PowerPoint and
Excel to PDF output. Runs one Office job at a time and never closes an Office
window the user already had open."""

from __future__ import annotations

import functools
import gc
import threading
from pathlib import Path

from spinvert.util import ConversionError

PROGIDS = {"word": "Word.Application", "powerpoint": "PowerPoint.Application",
           "excel": "Excel.Application"}
NO_PASSWORD = "spinvert-no-password"  # makes locked files fail instead of prompting

_lock = threading.Lock()


@functools.cache
def available(name: str) -> bool:
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROGIDS[name] + r"\CLSID"))
        import comtypes.client  # noqa: F401
        return True
    except (OSError, ImportError):
        return False


def _with_office(name: str, work):
    if not available(name):
        raise ConversionError(f"Microsoft {name.capitalize()} is needed for this conversion.")
    import comtypes
    import comtypes.client

    with _lock:
        comtypes.CoInitialize()
        try:
            app = comtypes.client.CreateObject(PROGIDS[name])
            try:
                return work(app)
            finally:
                del app
                gc.collect()
        except ConversionError:
            raise
        except Exception as e:
            message = getattr(e, "text", None) or str(e)
            raise ConversionError(f"{name.capitalize()} couldn't convert it: {message}"[:300]) from e
        finally:
            gc.collect()
            comtypes.CoUninitialize()


def word_to_pdf(src: Path, out: Path) -> None:
    def work(app):
        fresh = app.Documents.Count == 0
        if fresh:
            app.Visible = False
        app.DisplayAlerts = 0
        doc = app.Documents.Open(FileName=str(src), ConfirmConversions=False, ReadOnly=True,
                                 AddToRecentFiles=False, PasswordDocument=NO_PASSWORD,
                                 Visible=False)
        try:
            doc.ExportAsFixedFormat(OutputFileName=str(out), ExportFormat=17)
        finally:
            doc.Close(SaveChanges=0)
            del doc
        if fresh and app.Documents.Count == 0:
            app.Quit()
    _with_office("word", work)


def powerpoint_export(src: Path, fmt: str, out: Path | None = None,
                      folder: Path | None = None, progress=None) -> list[Path]:
    """PDF into out, or one PNG/JPG per slide into folder."""
    def work(app):
        fresh = app.Presentations.Count == 0
        pres = app.Presentations.Open(FileName=str(src), ReadOnly=-1, Untitled=0, WithWindow=0)
        made = []
        try:
            if fmt == "pdf":
                pres.SaveAs(str(out), 32)
                made.append(out)
            else:
                width = 1920
                height = int(width * pres.PageSetup.SlideHeight / pres.PageSetup.SlideWidth)
                count = pres.Slides.Count
                digits = len(str(count))
                for i in range(1, count + 1):
                    target = folder / f"{src.stem}-slide{i:0{digits}d}.{fmt}"
                    pres.Slides.Item(i).Export(str(target), fmt.upper(), width, height)
                    made.append(target)
                    if progress:
                        progress(i / count)
        finally:
            pres.Close()
            del pres
        if fresh and app.Presentations.Count == 0:
            app.Quit()
        return made
    return _with_office("powerpoint", work)


def excel_save(src: Path, out: Path, kind: str) -> None:
    """kind: 'pdf' or 'xlsx'."""
    def work(app):
        fresh = app.Workbooks.Count == 0
        if fresh:
            app.Visible = False
        app.DisplayAlerts = False
        book = app.Workbooks.Open(Filename=str(src), UpdateLinks=0, ReadOnly=True,
                                  Password=NO_PASSWORD)
        try:
            if kind == "pdf":
                book.ExportAsFixedFormat(Type=0, Filename=str(out))
            else:
                book.SaveAs(Filename=str(out), FileFormat=51)
        finally:
            book.Close(SaveChanges=False)
            del book
        if fresh and app.Workbooks.Count == 0:
            app.Quit()
    _with_office("excel", work)
