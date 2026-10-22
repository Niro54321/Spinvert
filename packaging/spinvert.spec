# PyInstaller recipe, run by packaging/build.py. Makes dist/Spinvert with
# Spinvert.exe and spinvert-selftest.exe sharing one _internal folder; the
# self-test checks the build and is left out of the installer.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build"
PATHS = [str(ROOT), str(ROOT / "tests")]
HIDDEN = collect_submodules("spinvert")  # editors are imported by name when a tool opens
DATAS = collect_data_files("pypandoc")  # pandoc.exe
EXCLUDES = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
            "PySide6.Qt3DCore", "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtDesigner"]


def analysis(script, hidden=()):
    return Analysis([str(ROOT / "packaging" / script)], pathex=PATHS, datas=DATAS,
                    hiddenimports=HIDDEN + list(hidden), excludes=EXCLUDES, noarchive=False)


app = analysis("launcher.py")
test = analysis("selftest.py", ["smoke_test"])

app_exe = EXE(PYZ(app.pure), app.scripts, [], exclude_binaries=True, name="Spinvert",
              icon=str(BUILD / "spinvert.ico"), version=str(BUILD / "version.txt"),
              console=False, upx=False)
test_exe = EXE(PYZ(test.pure), test.scripts, [], exclude_binaries=True, name="spinvert-selftest",
               icon=str(BUILD / "spinvert.ico"), console=True, upx=False)

COLLECT(app_exe, app.binaries, app.datas, test_exe, test.binaries, test.datas,
        name="Spinvert", upx=False)
