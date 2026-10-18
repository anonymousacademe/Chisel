"""Hand a file or folder to the desktop's default application.

One helper for every platform: ``os.startfile`` on Windows, ``open`` on macOS,
``xdg-open`` elsewhere. Only ever called from an explicit click or palette pick.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Pass to every subprocess call (`subprocess.run(..., **NO_CONSOLE)`): on Windows the
# windowed app has no console, so each child would flash a console window of its own
# (the "screen jitter" while git status runs in the background). Empty elsewhere.
NO_CONSOLE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def open_path(path: Path | str) -> bool:
    """Open *path* with the desktop; False when that cannot be done."""
    target = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]  # Windows only
            return True
        command = ["open" if sys.platform == "darwin" else "xdg-open", target]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        return False
    return True


_ZOTERO_URI = re.compile(r"^zotero://select/library/items/[A-Za-z0-9]{8}$")


def open_uri(uri: str) -> bool:
    """Open a ``zotero://select/library/items/<8 characters>`` link in Zotero; any other uri is refused
    (False). Only ever called from an explicit click."""
    if not isinstance(uri, str) or not _ZOTERO_URI.fullmatch(uri):
        return False
    try:
        if sys.platform == "win32":
            os.startfile(uri)  # type: ignore[attr-defined]  # Windows only
            return True
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", uri],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True
