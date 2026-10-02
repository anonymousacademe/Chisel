"""AI jobs for the desktop bridge (plan 1.5): a slow AI call runs in a worker
thread; the UI polls it for the text written so far, then for the result, and
can stop it. Streaming kinds push text deltas into the job; the others are
abandoned on Stop (the request finishes unseen and its result is dropped).
No pywebview import; unit-testable. Modelled on ``gui/exports.py``."""

from __future__ import annotations

import itertools
import threading
import time
from typing import Callable

from ..ai.stream import Cancelled, CancelToken

RETENTION_SECONDS = 300  # a finished job stays pollable this long (a late poll still answers)

_local = threading.local()


def current() -> "Job | None":
    """The job whose worker thread is running this code, if any."""
    return getattr(_local, "job", None)


def checkpoint() -> None:
    """Raise ``Cancelled`` if the current job was stopped. Call it before any
    step that would change author data after a slow AI call."""
    job = current()
    if job is not None:
        job.cancel.raise_if_set()


class Job:
    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.cancel = CancelToken()
        self.state = "running"          # running | done | cancelled | error
        self.started = time.monotonic()
        self.finished: float | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self.cost: float | None = None
        self._text: list[str] = []
        self._length = 0
        self._lock = threading.Lock()

    def push(self, delta: str) -> None:
        """Streaming kinds call this with each text delta (ignored once stopped)."""
        if self.cancel.is_set():
            return
        with self._lock:
            self._text.append(delta)
            self._length += len(delta)

    def text_from(self, since: int) -> tuple[str, int]:
        with self._lock:
            whole = "".join(self._text)
        return whole[max(0, since):], len(whole)

    def elapsed(self) -> float:
        return round((self.finished or time.monotonic()) - self.started, 1)


class AiJobs:
    def __init__(self, retention: float = RETENTION_SECONDS) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._ids = itertools.count(1)
        self._retention = retention

    def start(self, work: Callable[[Job], dict]) -> str:
        """Run ``work(job)`` on a worker thread; it returns the result dict (the
        same dict the synchronous bridge method returns, ``ok`` included)."""
        with self._lock:
            self._prune()
            job = Job(f"a{next(self._ids)}")
            self._jobs[job.id] = job

        def finish(state: str, **fields) -> None:
            with self._lock:
                if job.state != "running":      # stopped while it ran: stays stopped
                    return
                job.state = state
                job.finished = time.monotonic()
                for k, v in fields.items():
                    setattr(job, k, v)

        def run() -> None:
            _local.job = job
            try:
                result = work(job)
            except Cancelled:
                finish("cancelled")
            except Exception as exc:  # the job reports it; the thread never dies loudly
                if job.cancel.is_set():
                    finish("cancelled")
                else:
                    finish("error", error=_message(exc))
            else:
                if job.cancel.is_set():
                    finish("cancelled")     # a stopped job keeps no result
                elif isinstance(result, dict) and result.get("ok") is False:
                    finish("error", error=str(result.get("error") or "the AI call failed"))
                else:
                    cost = result.get("cost") if isinstance(result, dict) else None
                    finish("done", result=result,
                           cost=cost if isinstance(cost, (int, float)) else None)
            finally:
                _local.job = None

        threading.Thread(target=run, name=f"ai-{job.id}", daemon=True).start()
        return job.id

    def get(self, job_id: str) -> Job:
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
        if job is None:
            raise LookupError("unknown AI job (it may have expired)")
        return job

    def poll(self, job_id: str, since: int = 0) -> dict:
        job = self.get(job_id)
        text, length = job.text_from(int(since or 0))
        out: dict = {"state": job.state, "text": text, "length": length,
                     "elapsed": job.elapsed(), "cost": job.cost}
        if job.state == "done":
            out["result"] = job.result
        elif job.state == "error":
            out["error"] = job.error
        return out

    def cancel(self, job_id: str) -> dict:
        """Stop a job (idempotent): closes a stream, drops the result."""
        job = self.get(job_id)
        with self._lock:
            if job.state in ("running", "done", "error"):
                job.state = "cancelled"
                job.result = job.error = None
                if job.finished is None:
                    job.finished = time.monotonic()
        job.cancel.set()
        return {"state": "cancelled"}

    def _prune(self) -> None:
        now = time.monotonic()
        for job_id in [i for i, j in self._jobs.items()
                       if j.finished is not None and now - j.finished > self._retention]:
            del self._jobs[job_id]


def _message(exc: Exception) -> str:
    from .api import USER_ERRORS  # late: api imports this module

    return str(exc) if type(exc) in USER_ERRORS else f"{type(exc).__name__}: {exc}"
