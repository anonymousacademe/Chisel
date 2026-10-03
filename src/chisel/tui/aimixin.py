"""The AI working state for the terminal app (plan 1.5): every AI call runs
through ``_ai_call``, which shows ``AI: drafting... 12 s (ctrl+x to stop)`` in the
status bar, streams text into a live preview (the chat window, or a strip above
the status bar while drafting) and lets ctrl+x / escape stop it. A stopped call
returns nothing - the caller never inserts, saves or registers anything.

A mixin for ``ChiselApp``; method names start with ``_ai_`` / ``stop_ai`` so
they cannot collide with the app's own.
"""

from __future__ import annotations

import asyncio
import time

from rich.text import Text

from ..ai.stream import Cancelled, CancelToken, call_ai

PREVIEW_CHARS = 700   # the tail of the streamed text shown in the strip


class AiRun:
    """One running AI call: its label, clock, cancel token and streamed text."""

    def __init__(self, label: str, preview: bool, screen=None) -> None:
        self.label = label
        self.preview = preview          # show the strip above the status bar
        self.screen = screen            # an AssistantScreen that shows the text itself
        self.started = time.monotonic()
        self.token = CancelToken()
        self.stopped = asyncio.Event()
        self.text = ""

    def push(self, delta: str) -> None:   # called from the worker thread
        if not self.token.is_set():
            self.text += delta

    @property
    def elapsed(self) -> int:
        return int(time.monotonic() - self.started)


class AiMixin:
    _ai_run: AiRun | None = None
    _ai_timer = None

    # -- state ------------------------------------------------------------------------

    @property
    def ai_running(self) -> bool:
        return self._ai_run is not None

    def check_action(self, action: str, parameters) -> bool | None:
        """Stop keys exist only while a job runs (ctrl+x is cut in the editor otherwise)."""
        if action == "stop_ai":
            return self.ai_running
        return super().check_action(action, parameters)

    def _ai_busy(self) -> bool:
        """True (with a notice) when an AI call is already running."""
        if self._ai_run is None:
            return False
        self.notify("An AI request is already running (ctrl+x to stop it)", severity="warning")
        return True

    def _ai_status_text(self) -> str:
        run = self._ai_run
        if run is None:
            return ""
        return f"AI: {run.label}... {run.elapsed} s (ctrl+x to stop)"

    def _ai_begin(self, label: str, preview: bool = False, screen=None) -> AiRun:
        run = self._ai_run = AiRun(label, preview, screen)
        if self._ai_timer is None:
            self._ai_timer = self.set_interval(0.25, self._ai_tick)
        self._ai_refresh(force=True)
        return run

    def _ai_end(self, run: AiRun) -> None:
        if self._ai_run is not run:      # a newer call took over
            return
        self._ai_run = None
        if self._ai_timer is not None:
            self._ai_timer.stop()
            self._ai_timer = None
        try:
            self._ai_show_preview("")
            if run.screen is not None and run.screen.is_attached:
                run.screen.end_stream()
            self.update_status()
        except Exception:
            pass                          # teardown: nothing left to update

    def _ai_tick(self) -> None:
        self._ai_refresh()

    def _ai_refresh(self, force: bool = False) -> None:
        run = self._ai_run
        if run is None:
            return
        if run.screen is not None and run.screen.is_attached:
            run.screen.show_stream(run.text)
        elif run.preview:
            self._ai_show_preview(run.text)
        if force or run.elapsed != getattr(self, "_ai_shown_s", None):
            self._ai_shown_s = run.elapsed
            self.update_status()

    def _ai_show_preview(self, text: str) -> None:
        strip = self._ai_preview
        if strip is None:
            return
        if not text and (self._ai_run is None or not self._ai_run.preview):
            strip.display = False
            return
        strip.display = True
        tail = text[-PREVIEW_CHARS:]
        strip.update(Text(("..." if len(text) > len(tail) else "") + (tail or "waiting for the first words...")))

    # -- stop ---------------------------------------------------------------------------

    def action_stop_ai(self) -> None:
        run = self._ai_run
        if run is None:
            return
        run.token.set()                   # closes a stream
        run.stopped.set()                 # releases a call waiting on a non-streaming request
        self.notify("Stopped - nothing was inserted or saved", timeout=3)

    # -- the one way to call the AI ---------------------------------------------------------

    async def _ai_call(self, label: str, fn, *args, stream: bool = False, preview: bool = False,
                       screen=None, **kwargs):
        """Run ``fn(*args, **kwargs)`` in a thread under the working-state UI.
        *stream*: pass the text sink and cancel token to *fn* (streaming calls).
        Raises ``Cancelled`` when the author stops it; a non-streaming request is
        abandoned (its answer is dropped when it arrives)."""
        run = self._ai_begin(label, preview, screen)
        task = None
        try:
            if stream:
                work = asyncio.to_thread(call_ai, fn, *args, on_delta=run.push,
                                         cancel=run.token, **kwargs)
            else:
                work = asyncio.to_thread(fn, *args, **kwargs)
            task = asyncio.ensure_future(work)
            waiter = asyncio.ensure_future(run.stopped.wait())
            try:
                await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                waiter.cancel()
            if run.token.is_set():
                _quiet(task)
                raise Cancelled()
            return task.result()
        except asyncio.CancelledError:    # the worker itself was replaced or the app is closing
            run.token.set()
            if task is not None:
                _quiet(task)
            raise
        finally:
            self._ai_end(run)


def _quiet(task: asyncio.Future) -> None:
    """Drop a task's outcome (an abandoned request): never an 'exception was never retrieved'."""
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
