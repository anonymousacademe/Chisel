"""File-system helpers: rename and replace that survive a briefly locked file.

On Windows ``Path.replace`` / ``rename`` raise PermissionError while another
process (an antivirus scan, a sync client, a second window) has the file open.
The lock is almost always gone a moment later, so we retry a few times.
"""

from __future__ import annotations

import time
from pathlib import Path

ATTEMPTS = 5
DELAY = 0.05  # seconds between attempts


def _retry(action, src: Path, dst: Path):
    for attempt in range(ATTEMPTS):
        try:
            return action(dst)
        except PermissionError:
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(DELAY)


def replace(src: Path, dst: Path) -> Path:
    """``src.replace(dst)`` with a short retry on PermissionError."""
    return _retry(src.replace, src, dst)


def read_text_lenient(path: Path) -> str:
    """UTF-8 text with undecodable bytes replaced: for scans (index, workspace)
    that must not fail on one stray file. Never write the result back."""
    return path.read_text(encoding="utf-8", errors="replace")


class NotUtf8Error(ValueError):
    """An existing file is not valid UTF-8, so rewriting it from text read
    leniently would destroy its bytes. Message is written for the author."""

    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"{self.path.name} is not valid UTF-8 (probably saved as "
                         "Latin-1/Windows-1252); convert it to UTF-8 before editing in the app")


def is_valid_utf8(path: Path) -> bool:
    """True when *path* is missing (nothing to destroy) or decodes as UTF-8."""
    try:
        data = Path(path).read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def ensure_utf8(path: Path) -> None:
    """Raise NotUtf8Error if rewriting *path* from text would lose its bytes."""
    if not is_valid_utf8(path):
        raise NotUtf8Error(path)


def rename(src: Path, dst: Path) -> Path:
    """``src.rename(dst)`` with a short retry on PermissionError."""
    return _retry(src.rename, src, dst)
