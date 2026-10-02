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


def rename(src: Path, dst: Path) -> Path:
    """``src.rename(dst)`` with a short retry on PermissionError."""
    return _retry(src.rename, src, dst)
