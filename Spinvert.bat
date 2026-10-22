@echo off
rem Starts Spinvert. The first run sets it up (needs Python 3.10 or newer).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\spinvert.exe" (
    echo First run: setting up Spinvert. This takes a minute or two...
    if not exist ".venv\Scripts\python.exe" (
        py -3 -m venv .venv 2>nul || python -m venv .venv
    )
    if not exist ".venv\Scripts\python.exe" (
        echo Python 3.10 or newer is needed: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e .
    if errorlevel 1 (
        echo Setup failed. See the messages above.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\spinvert.exe" %*
