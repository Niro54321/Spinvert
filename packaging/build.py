"""Builds the Windows installer.

    .venv\\Scripts\\python.exe packaging\\build.py [--skip-test]

1. icon, version info and third-party notices into build/
2. PyInstaller: dist/Spinvert (the app, plus a self-test exe)
3. the self-test: every conversion and tool, and video playback, in the packaged app
4. Inno Setup: dist/Spinvert-Setup-<version>.exe

Needs PyInstaller in the venv and Inno Setup 6 (winget install JRSoftware.InnoSetup).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD, DIST = ROOT / "build", ROOT / "dist"
sys.path.insert(0, str(ROOT))

from spinvert import __version__  # noqa: E402

# Tools that build or check the app; none of them ship.
NOT_SHIPPED = {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes", "pip",
               "setuptools", "packaging", "pyflakes", "spinvert"}


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def prepare() -> None:
    from PySide6.QtGui import QGuiApplication

    from spinvert.theme import save_ico

    BUILD.mkdir(exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(["build"])  # noqa: F841 (icons need Qt)
    save_ico(BUILD / "spinvert.ico")
    nums = ", ".join((__version__.split(".") + ["0"] * 4)[:4])
    (BUILD / "version.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums})),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Niro54321'),
    StringStruct('FileDescription', 'Spinvert'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('LegalCopyright', 'MIT License'),
    StringStruct('ProductName', 'Spinvert'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")


def notices(target: Path) -> None:
    """THIRD-PARTY-NOTICES.txt and every bundled package's own licence files."""
    licenses = target / "licenses"
    shutil.rmtree(licenses, ignore_errors=True)
    lines = ["Spinvert is MIT licensed (see LICENSE). The installer also contains the",
             "open-source software below, each under its own licence; the full texts are",
             "in the licenses folder next to this file.", "",
             f"Python {sys.version.split()[0]}  PSF-2.0  https://www.python.org/"]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        (licenses / "Python").mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_license, licenses / "Python" / "LICENSE.txt")
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name.lower() in NOT_SHIPPED:
            continue
        licence = dist.metadata.get("License-Expression") or next(
            (c.split("::")[-1].strip() for c in dist.metadata.get_all("Classifier") or [] if c.startswith("License ::")),
            (dist.metadata.get("License") or "see licence file").splitlines()[0][:60])
        url = next((u.split(",", 1)[-1].strip() for u in dist.metadata.get_all("Project-URL") or []
                    if u.lower().startswith(("source", "repository", "homepage", "code"))),
                   dist.metadata.get("Home-page") or "")
        lines.append(f"{name} {dist.version}  {licence}  {url}".rstrip())
        for f in dist.files or []:
            if any(part.lower().startswith(("license", "licence", "copying", "notice", "authors"))
                   for part in Path(f).parts[-1:]) or "licenses" in Path(f).parts:
                src = Path(dist.locate_file(f))
                if src.is_file():
                    dest = licenses / name / Path(f).name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
    import pypandoc

    pandoc_copyright = Path(pypandoc.__file__).parent / "files" / "COPYRIGHT.txt"
    if pandoc_copyright.is_file():
        (licenses / "Pandoc").mkdir(parents=True, exist_ok=True)
        shutil.copy2(pandoc_copyright, licenses / "Pandoc" / "COPYRIGHT.txt")
    lines += ["",
              "Bundled programs and libraries inside the packages above:",
              "- Pandoc (inside pypandoc-binary), GPL-2.0-or-later; source:",
              "  https://github.com/jgm/pandoc/releases",
              "- Qt 6 and its FFmpeg-based multimedia backend (inside PySide6), LGPL-3.0; source:",
              "  https://download.qt.io/official_releases/qt/ and https://code.qt.io/",
              "- libheif, libde265, x265 and friends (inside pillow-heif); source:",
              "  https://github.com/bigcat88/pillow_heif",
              "- PDFium (inside pypdfium2), BSD-3-Clause / Apache-2.0.",
              "",
              "FFmpeg is not included. The installer can download it for you with winget",
              "(Gyan.FFmpeg); it runs as a separate program under its own licence."]
    (target / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def pyinstaller() -> Path:
    shutil.rmtree(DIST / "Spinvert", ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"),
                    str(ROOT / "packaging" / "spinvert.spec")], check=True)
    out = DIST / "Spinvert"
    shutil.copy2(ROOT / "LICENSE", out / "LICENSE.txt")
    notices(out)
    return out


def selftest(out: Path) -> None:
    exe = out / "spinvert-selftest.exe"
    work = Path(tempfile.mkdtemp(prefix="spinvert-selftest-"))
    subprocess.run([str(exe), str(work)], check=True)
    video = next(work.rglob("clip.mp4"))
    subprocess.run([str(exe), "--player", str(video)], check=True)


def inno() -> Path:
    candidates = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
                  Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
                  Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe"]
    iscc = next((c for c in candidates if c.is_file()), None) or shutil.which("ISCC")
    if not iscc:
        sys.exit("Inno Setup 6 not found: winget install JRSoftware.InnoSetup")
    subprocess.run([str(iscc), f"/DAppVersion={__version__}", str(ROOT / "packaging" / "spinvert.iss")],
                   check=True)
    return DIST / f"Spinvert-Setup-{__version__}.exe"


def main() -> None:
    step(f"Spinvert {__version__}: icon and version info")
    prepare()
    step("PyInstaller")
    out = pyinstaller()
    if "--skip-test" not in sys.argv:
        step("Self-test in the packaged app")
        selftest(out)
    step("Inno Setup")
    setup = inno()
    print(f"\nDone: {setup} ({setup.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
