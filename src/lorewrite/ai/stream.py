"""Streaming chat completions and the cancel token (plan 1.5).

``stream_text`` is the streaming twin of one ``chat.completions.create`` call:
it hands each text delta to *on_delta*, reads the cost from the final chunk
(OpenRouter sends ``usage`` last when ``usage.include`` is set) into the spend
ledger, and honours a ``CancelToken``: cancelling closes the HTTP stream and
raises ``Cancelled``. A cancelled call returns nothing, so callers can never
insert, save or register a partial result.
"""

from __future__ import annotations

import inspect
import threading
from typing import Callable

from .client import usage_extra_body
from .usage import record_response


class Cancelled(Exception):
    """The author stopped an AI job; its result (if any) must be discarded."""


class CancelToken(threading.Event):
    """A threading.Event whose ``set()`` also runs the registered closers, so a
    stream blocked waiting for its next chunk is closed at once instead of when
    the next chunk happens to arrive."""

    def __init__(self) -> None:
        super().__init__()
        self._closers: list[Callable[[], None]] = []
        self._closers_lock = threading.Lock()

    def add_closer(self, closer: Callable[[], None]) -> None:
        with self._closers_lock:
            self._closers.append(closer)
            already = self.is_set()
        if already:
            self._run(closer)

    @staticmethod
    def _run(closer: Callable[[], None]) -> None:
        try:
            closer()
        except Exception:
            pass  # closing a stream that is already gone is fine

    def set(self) -> None:  # noqa: A003 - Event API
        super().set()
        with self._closers_lock:
            closers, self._closers = self._closers, []
        for closer in closers:
            self._run(closer)

    def raise_if_set(self) -> None:
        if self.is_set():
            raise Cancelled()


def stream_text(client, model: str, messages: list[dict], feature: str,
                on_delta: Callable[[str], None] | None = None,
                cancel: threading.Event | None = None) -> str:
    """Run one streaming chat call and return the whole reply text.

    Raises ``Cancelled`` when *cancel* is set before or during the stream (the
    stream is closed; the cost is recorded only when the provider had already
    reported it)."""
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    stream = client.chat.completions.create(
        model=model, messages=messages, stream=True,
        extra_body=usage_extra_body())
    if isinstance(cancel, CancelToken):
        cancel.add_closer(getattr(stream, "close", lambda: None))
    parts: list[str] = []
    usage = None
    cancelled = False
    try:
        for chunk in stream:
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage
            choices = getattr(chunk, "choices", None) or []
            delta = getattr(getattr(choices[0], "delta", None), "content", None) if choices else None
            if delta:
                parts.append(delta)
                if on_delta is not None:
                    on_delta(delta)
    except Exception:
        if cancel is not None and cancel.is_set():
            cancelled = True  # closing the stream under the reader raises; that is the stop
        else:
            raise
    finally:
        try:
            stream.close()
        except Exception:
            pass
    if cancel is not None and cancel.is_set():
        cancelled = True
    if cancelled:
        if usage is not None:
            record_response({"usage": usage}, model, feature)
        raise Cancelled()
    record_response({"usage": usage}, model, feature)
    return "".join(parts)


def call_ai(fn, *args, on_delta=None, cancel=None, **kwargs):
    """Call an AI function, passing ``on_delta`` / ``cancel`` only if it takes
    them (test and mock fakes with the older signature keep working)."""
    if on_delta is not None or cancel is not None:
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            params = {}
        var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        if on_delta is not None and (var_kw or "on_delta" in params):
            kwargs["on_delta"] = on_delta
        if cancel is not None and (var_kw or "cancel" in params):
            kwargs["cancel"] = cancel
    return fn(*args, **kwargs)
