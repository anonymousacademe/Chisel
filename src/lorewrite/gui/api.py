"""The bridge between the React UI and the Python core.

Every public method of Api is callable from JavaScript (pywebview's js_api, or
the devserver's POST /api/<method>). Contract: JSON in, JSON out, always
``{"ok": true, ...}`` or ``{"ok": false, "error": "..."}`` — never raise across
the bridge. No pywebview import here, so this is unit-testable.
"""

from __future__ import annotations

import functools
import threading
from typing import Any, Callable


def bridge(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Wrap an Api method: exceptions become ``{"ok": False, "error": ...}``."""

    @functools.wraps(fn)
    def wrapper(self: "Api", *args: Any, **kwargs: Any) -> dict:
        try:
            result = fn(self, *args, **kwargs)
        except Exception as exc:  # the bridge never raises
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"value": result}
        result.setdefault("ok", True)
        return result

    wrapper.__bridge__ = True  # type: ignore[attr-defined]
    return wrapper


class Api:
    def __init__(self) -> None:
        self._lock = threading.RLock()  # guards every project write
        self._window: Any = None  # set by gui.app once the window exists

    @bridge
    def ping(self) -> dict:
        return {"pong": True}

    # -- window ---------------------------------------------------------------

    @bridge
    def minimize(self) -> dict:
        if self._window is not None:
            self._window.minimize()
        return {}

    @bridge
    def toggle_maximize(self) -> dict:
        w = self._window
        if w is not None:
            # pywebview has no "is maximized"; track it ourselves
            if getattr(self, "_maximized", False):
                w.restore()
            else:
                w.maximize()
            self._maximized = not getattr(self, "_maximized", False)
        return {}

    @bridge
    def close(self) -> dict:
        if self._window is not None:
            self._window.destroy()
        return {}

    def bridge_methods(self) -> list[str]:
        return sorted(n for n in dir(type(self))
                      if getattr(getattr(type(self), n), "__bridge__", False))
