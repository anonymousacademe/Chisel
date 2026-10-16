"""Cache backend: the source notes already in the project, so citations and export work with nothing else.

The project layer (P3) supplies the items through ``provider``; this module only wraps them. Nothing is
fetched, nothing is deleted and no version is reported.
"""

from __future__ import annotations

from typing import Callable, Iterable

from ..paper.types import ZItem
from .base import FetchResult, Scope, Status


class CacheSource:
    name = "cache"

    def __init__(self, provider: Callable[[], Iterable[ZItem]] | Iterable[ZItem]):
        self._provider = provider
        self.warnings: list[str] = []

    def _items(self) -> list[ZItem]:
        src = self._provider
        return list(src() if callable(src) else src)

    def probe(self) -> Status:
        try:
            n = len(self._items())
        except Exception:
            return Status(False, "The source notes in the project could not be read.")
        return Status(n > 0, f"{n} source notes are saved in the project." if n else
                      "There are no saved source notes yet.", None, None, "cache")

    def fetch(self, scope: Scope, since: int | None) -> FetchResult:
        self.warnings = []
        if scope.limited:
            self.warnings.append("Saved source notes cannot be limited to a collection or tag; all are used.")
        return FetchResult("cache", self._items(), [], None, None)
