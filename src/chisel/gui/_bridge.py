"""The ``@bridge`` decorator shared by Api and its mixins (api.py re-exports it)."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from ..ai.budget import BudgetError
from ..core import fsutil, sync

log = logging.getLogger("chisel")

# Errors the core raises on purpose, with a message written for the author:
# shown as-is. Anything else keeps its class name (it is a bug worth reporting).
USER_ERRORS = (ValueError, FileNotFoundError, FileExistsError, LookupError, IndexError, RuntimeError,
               sync.GitError, fsutil.NotUtf8Error, BudgetError)


def bridge(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Wrap an Api method: exceptions become ``{"ok": False, "error": ...}``."""

    @functools.wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> dict:
        try:
            result = fn(self, *args, **kwargs)
        except Exception as exc:  # the bridge never raises
            if type(exc) in USER_ERRORS:
                message = str(exc)
            else:
                log.warning("bridge method %s failed", fn.__name__, exc_info=True)  # a bug: keep the traceback
                message = f"{type(exc).__name__}: {exc}"
            return {"ok": False, "error": message}
        if not isinstance(result, dict):
            result = {"value": result}
        result.setdefault("ok", True)
        return result

    wrapper.__bridge__ = True  # type: ignore[attr-defined]
    return wrapper
