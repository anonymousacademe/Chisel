"""Rendered clips, so a passage heard twice is not rendered (or paid for) twice.

``<state dir>/speech/clips/<sha256>.wav`` (``CHISEL_STATE_DIR`` in tests), keyed by everything that changes the
sound: engine, model, voice, speed and the text. Personal and disposable, never in the project folder; trimmed to
``LIMIT`` bytes, oldest first."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from ..core import fsutil
from ..core.recents import default_state_dir

LIMIT = 200 * 1024 * 1024


def clips_dir() -> Path:
    return default_state_dir() / "speech" / "clips"


def key(engine: str, model: str, voice: str, speed: float, text: str) -> str:
    raw = json.dumps([engine, model, voice, round(float(speed), 2), text], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(clip_key: str) -> bytes | None:
    path = clips_dir() / f"{clip_key}.wav"
    try:
        data = path.read_bytes()
        path.touch()                    # recently heard: kept longest
        return data
    except OSError:
        return None


def put(clip_key: str, data: bytes) -> None:
    folder = clips_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"{clip_key}.{threading.get_ident()}.tmp"     # a prefetch and a play may write the same clip
        tmp.write_bytes(data)
        fsutil.replace(tmp, folder / f"{clip_key}.wav")
        prune()
    except OSError:
        pass                            # a cache that cannot be written only costs a re-render


def prune(limit: int = LIMIT) -> None:
    files = []
    for p in clips_dir().glob("*.wav"):
        try:
            st = p.stat()
        except OSError:
            continue
        files.append((st.st_mtime, st.st_size, p))
    total = sum(f[1] for f in files)
    for _mtime, size, p in sorted(files):
        if total <= limit:
            break
        try:
            p.unlink()
            total -= size
        except OSError:
            pass


def clear() -> int:
    """Delete every cached clip; returns how many."""
    n = 0
    for p in clips_dir().glob("*.wav"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n
