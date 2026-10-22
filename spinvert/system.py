"""Windows integration: start with Windows, the Send to menu, Show in Explorer."""

from __future__ import annotations

import os
import subprocess
import sys
import winreg
from pathlib import Path

from spinvert.util import CREATE_NO_WINDOW, app_data_dir

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Spinvert"


def launcher() -> tuple[str, list[str]]:
    """The program and arguments that start Spinvert."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    scripts = Path(sys.executable).parent
    exe = scripts / "spinvert.exe"
    if exe.is_file():
        return str(exe), []
    pythonw = scripts / "pythonw.exe"
    return str(pythonw if pythonw.is_file() else sys.executable), ["-m", "spinvert"]


def _command(extra: list[str]) -> str:
    exe, args = launcher()
    return subprocess.list2cmdline([exe, *args, *extra])


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, NAME)
            return True
    except OSError:
        return False


def set_startup(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, _command(["--background"]))
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass


def sendto_link() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "SendTo" / f"{NAME}.lnk"


def sendto_enabled() -> bool:
    return sendto_link().exists()


def set_sendto(on: bool) -> None:
    link = sendto_link()
    if not on:
        link.unlink(missing_ok=True)
        return
    from spinvert.theme import save_ico

    icon = app_data_dir() / "spinvert.ico"
    save_ico(icon)
    exe, args = launcher()

    def q(text: str) -> str:
        return "'" + str(text).replace("'", "''") + "'"

    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({q(link)});"
              f"$s.TargetPath={q(exe)};$s.Arguments={q(subprocess.list2cmdline(args))};"
              f"$s.IconLocation={q(icon)};$s.Description='Convert with Spinvert';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   check=True, creationflags=CREATE_NO_WINDOW, capture_output=True)


def show_in_explorer(path: Path) -> None:
    subprocess.Popen(f'explorer /select,"{path}"')
