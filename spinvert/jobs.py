"""Runs jobs on worker threads and reports back to the UI thread."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from spinvert.core import Context, run_op
from spinvert.util import Cancelled, ConversionError


class JobManager(QObject):
    progressed = Signal(int, float)
    finished = Signal(int, list, str)  # job id, output paths, error ("" = ok, "cancelled")

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spinvert-job")
        self.next_id = 1
        self.cancels: dict[int, threading.Event] = {}

    def submit(self, op, inputs, params=None) -> int:
        job_id = self.next_id
        self.next_id += 1
        event = threading.Event()
        self.cancels[job_id] = event
        ctx = Context(inputs=list(inputs), settings=self.controller.settings,
                      engines=dict(self.controller.engines), params=params or {},
                      on_progress=lambda f, j=job_id: self.progressed.emit(j, f),
                      cancel_event=event)
        self.pool.submit(self._run, job_id, op, ctx)
        return job_id

    def _run(self, job_id, op, ctx):
        try:
            outputs = run_op(op, ctx)
            self.finished.emit(job_id, [str(p) for p in outputs], "")
        except Cancelled:
            self.finished.emit(job_id, [], "cancelled")
        except ConversionError as e:
            self.finished.emit(job_id, [], str(e) or "Failed")
        except Exception as e:  # never let a worker die silently
            self.finished.emit(job_id, [], f"Unexpected error: {e}")
        finally:
            self.cancels.pop(job_id, None)

    def cancel(self, job_id: int) -> None:
        event = self.cancels.get(job_id)
        if event:
            event.set()

    def busy(self) -> bool:
        return bool(self.cancels)

    def shutdown(self) -> None:
        for event in list(self.cancels.values()):
            event.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
