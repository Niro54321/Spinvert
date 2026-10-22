"""The job context every engine receives, and the function that runs a job.

No Qt in here, so the engines can be tested without a screen.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from spinvert.settings import Settings
from spinvert.util import (CREATE_NO_WINDOW, Cancelled, ConversionError,
                           unique_dir, unique_path)


@dataclass
class Context:
    inputs: list[Path]
    settings: Settings
    engines: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    on_progress: Callable[[float], None] = lambda f: None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created: list[Path] = field(default_factory=list)
    _last: tuple = (0.0, -1.0)

    # progress and cancel

    def progress(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        now = time.monotonic()
        last_time, last_value = self._last
        if fraction >= 1.0 or fraction - last_value >= 0.01 or now - last_time > 0.25:
            self._last = (now, fraction)
            self.on_progress(fraction)

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    # outputs

    def output(self, stem: str, ext: str, folder: Path | None = None) -> Path:
        """A new file path beside the first input. Removed if the job fails."""
        folder = folder or self.inputs[0].parent
        path = unique_path(folder, stem, ext)
        self.created.append(path)
        return path

    def output_dir(self, name: str, folder: Path | None = None) -> Path:
        folder = folder or self.inputs[0].parent
        try:
            path = unique_dir(folder, name)
        except OSError as e:
            raise ConversionError(f"Can't create a folder here: {e.strerror or e}") from e
        self.created.append(path)
        return path

    def cleanup(self) -> None:
        for path in reversed(self.created):
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink()
            except OSError:
                pass

    # external programs

    def run(self, cmd: list, on_line: Callable[[str], None] | None = None,
            capture: bool = False, cwd: Path | None = None) -> str:
        """Run a program without a console window. Kills it on cancel.

        Returns stdout when capture is set. Raises ConversionError with the
        last line of stderr when the program fails.
        """
        self.check()
        lines: list[str] = []
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(
                [str(c) for c in cmd], cwd=str(cwd) if cwd else None,
                stdin=subprocess.DEVNULL, stderr=err,
                stdout=subprocess.PIPE if (on_line or capture) else subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW, text=True, encoding="utf-8", errors="replace")

            def killer():
                while proc.poll() is None:
                    if self.cancel_event.wait(0.2):
                        proc.kill()
                        return

            threading.Thread(target=killer, daemon=True).start()
            if proc.stdout:
                for line in proc.stdout:
                    if capture:
                        lines.append(line)
                    if on_line:
                        on_line(line)
            proc.wait()
            if self.cancel_event.is_set():
                raise Cancelled()
            if proc.returncode != 0:
                err.seek(0)
                text = err.read().decode("utf-8", "replace").strip().splitlines()
                last = text[-1].strip() if text else f"exit code {proc.returncode}"
                raise ConversionError(last[:300])
        return "".join(lines)


def run_op(op, ctx: Context) -> list[Path]:
    """Run one operation. On failure or cancel, remove what it created."""
    try:
        outputs = op.func(ctx)
        ctx.progress(1.0)
        return outputs
    except (Cancelled, ConversionError):
        ctx.cleanup()
        raise
    except PermissionError as e:
        ctx.cleanup()
        raise ConversionError("Permission denied. Is the file open in another app, "
                              "or is the folder read-only?") from e
    except MemoryError as e:
        ctx.cleanup()
        raise ConversionError("Not enough memory for this file.") from e
    except Exception as e:
        ctx.cleanup()
        raise ConversionError(f"{type(e).__name__}: {e}"[:300]) from e
