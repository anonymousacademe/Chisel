"""Export jobs for the desktop bridge (SPEC M7): an export runs in a worker
thread and the UI polls its progress. No pywebview import; unit-testable."""

from __future__ import annotations

import itertools
import threading

from ..core import export as exporting
from ..core.export.manuscript import ExportOptions


class ExportJobs:
    """At most one export at a time; finished jobs are kept for polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def start(self, project, options: ExportOptions) -> str:
        with self._lock:
            if any(j["state"] == "running" for j in self._jobs.values()):
                raise RuntimeError("An export is already running.")
            job_id = f"x{next(self._ids)}"
            job = self._jobs[job_id] = {"state": "running", "stage": "Starting", "fraction": 0.0}

        def progress(stage: str, fraction: float) -> None:
            job["stage"], job["fraction"] = stage, fraction

        def work() -> None:
            try:
                result = exporting.run_export(project, options, progress)
            except Exception as exc:  # the job reports it; the thread never dies loudly
                message = str(exc) if isinstance(exc, (ValueError, RuntimeError, OSError)) \
                    else f"{type(exc).__name__}: {exc}"
                job.update(state="error", error=message)
            else:
                job.update(state="done", result=result.to_dict())

        threading.Thread(target=work, name=f"export-{job_id}", daemon=True).start()
        return job_id

    def status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError("unknown export")
        return dict(job)
