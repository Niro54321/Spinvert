"""Microsoft Office, when it is installed, for the best Word, PowerPoint and
Excel to PDF output. Runs one Office job at a time and never closes an Office
window the user already had open."""

from __future__ import annotations

import functools
import gc
import subprocess
import threading
from pathlib import Path

from spinvert.util import CREATE_NO_WINDOW, ConversionError

PROGIDS = {"word": "Word.Application", "powerpoint": "PowerPoint.Application",
           "excel": "Excel.Application"}
EXES = {"word": "WINWORD.EXE", "powerpoint": "POWERPNT.EXE", "excel": "EXCEL.EXE"}
NO_PASSWORD = "spinvert-no-password"  # makes locked files fail instead of prompting
TIMEOUT = 180  # seconds before a frozen Office copy is closed

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


def _pids(exe: str) -> set[int]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, creationflags=CREATE_NO_WINDOW).stdout
    return {int(row.split('","')[1]) for row in out.splitlines() if row.startswith('"')}


def _with_office(name: str, work):
    """Run work(app) in a hidden copy of an Office app. If that copy stops
    responding (an unexpected dialog can freeze it), close it after TIMEOUT
    seconds instead of waiting forever. Never touches a copy the user opened."""
    if not available(name):
        raise ConversionError(f"Microsoft {name.capitalize()} is needed for this conversion.")
    import comtypes
    import comtypes.client

    exe = EXES[name]
    with _lock:
        comtypes.CoInitialize()
        timed_out = threading.Event()
        watchdog = None
        try:
            before = _pids(exe)
            app = comtypes.client.CreateObject(PROGIDS[name])
            ours = _pids(exe) - before
            if len(ours) == 1:
                pid = ours.pop()

                def kill():
                    timed_out.set()
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                                   creationflags=CREATE_NO_WINDOW)

                watchdog = threading.Timer(TIMEOUT, kill)
                watchdog.daemon = True
                watchdog.start()
            try:
                return work(app)
            finally:
                del app
                gc.collect()
        except ConversionError:
            raise
        except Exception as e:
            if timed_out.is_set():
                raise ConversionError(f"{name.capitalize()} stopped responding, so Spinvert closed it.") from e
            message = getattr(e, "text", None) or str(e)
            raise ConversionError(f"{name.capitalize()} couldn't convert it: {message}"[:300]) from e
        finally:
            if watchdog:
                watchdog.cancel()
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
