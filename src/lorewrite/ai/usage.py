"""AI spend tracking (SPEC §8): a session ledger fed from OpenRouter's usage.

OpenRouter returns ``usage.cost`` (USD) when the request carries
``extra_body={"usage": {"include": True}}`` (see client.usage_extra_body).
Calls run in worker threads, so the ledger is lock-protected.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageEntry:
    model: str
    feature: str
    cost: float | None  # USD; None when the provider didn't report it
    prompt_tokens: int | None
    completion_tokens: int | None
    at: float


class UsageLedger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[UsageEntry] = []

    def record(self, model: str, feature: str, cost: float | None,
               prompt_tokens: int | None = None,
               completion_tokens: int | None = None) -> UsageEntry:
        entry = UsageEntry(model, feature, cost, prompt_tokens,
                           completion_tokens, time.time())
        with self._lock:
            self._entries.append(entry)
        return entry

    def session_total(self) -> float:
        with self._lock:
            return sum(e.cost or 0.0 for e in self._entries)

    def last(self) -> UsageEntry | None:
        with self._lock:
            return self._entries[-1] if self._entries else None

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


LEDGER = UsageLedger()


def _num(value, kind=float):
    try:
        return kind(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _field(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def record_response(response, model: str, feature: str) -> UsageEntry:
    """Record a chat-completion response's usage. Tolerates missing fields."""
    usage = _field(response, "usage")
    cost = _num(_field(usage, "cost")) if usage is not None else None
    entry = LEDGER.record(
        model, feature, cost,
        _num(_field(usage, "prompt_tokens"), int) if usage is not None else None,
        _num(_field(usage, "completion_tokens"), int) if usage is not None else None,
    )
    return entry


def format_cost(cost: float | None) -> str:
    return f"AI ${cost:.4f}" if cost is not None else ""
