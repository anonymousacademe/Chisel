"""Diagnostic log for failures that are deliberately not shown to the author.

Logger ``chisel``; a rotating file ``<state dir>/log/chisel.log`` (the state dir honours
CHISEL_STATE_DIR). Nothing here ever raises. It records the context and the exception's
class and a short, key-scrubbed message, never scene text, notes or API keys.
"""
from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

NAME = "chisel"
MAX_MESSAGE = 200
_KEY = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|Bearer\s+\S+)")

_handler: logging.Handler | None = None
_handler_dir: Path | None = None


def log_path() -> Path:
    from .recents import default_state_dir
    return default_state_dir() / "log" / "chisel.log"


def _ensure_handler() -> None:
    global _handler, _handler_dir
    path = log_path()
    if _handler is not None and _handler_dir == path:
        return
    logger = logging.getLogger(NAME)
    if _handler is not None:
        logger.removeHandler(_handler)
        try:
            _handler.close()
        except Exception:
            pass
        _handler = None
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=256_000, backupCount=2, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    _handler, _handler_dir = handler, path


def scrub(text: str) -> str:
    text = _KEY.sub("[redacted]", " ".join(str(text).split()))
    return text if len(text) <= MAX_MESSAGE else text[:MAX_MESSAGE] + "..."


def log_exc(context: str, exc: BaseException | None = None, *, level: int = logging.DEBUG) -> None:
    """Record that ``context`` failed with ``exc``; never raises."""
    try:
        _ensure_handler()
        what = f"{type(exc).__name__}: {scrub(str(exc))}" if exc is not None else ""
        logging.getLogger(NAME).log(level, "%s %s", scrub(context), what)
    except Exception:
        pass


def close() -> None:
    """Detach and close the file handler (tests; lets a temp dir be removed)."""
    global _handler, _handler_dir
    try:
        if _handler is not None:
            logging.getLogger(NAME).removeHandler(_handler)
            _handler.close()
    except Exception:
        pass
    _handler, _handler_dir = None, None
