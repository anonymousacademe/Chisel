"""Recent-projects store: ~/.local/state/lorewrite/recent.json.

A small JSON list, most-recent first, deduped by path, capped at 10.
User state, not project data — the projects themselves stay the truth.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

RECENTS_FILE = "recent.json"
MAX_RECENTS = 10


def default_state_dir() -> Path:
    """State dir; LOREWRITE_STATE_DIR overrides (used by tests)."""
    override = os.environ.get("LOREWRITE_STATE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local/state/lorewrite"


@dataclass(frozen=True)
class Recent:
    path: Path
    title: str
    opened_at: float


def load_recents(state_dir: Path | None = None) -> list[Recent]:
    state_dir = state_dir or default_state_dir()
    try:
        data = json.loads((state_dir / RECENTS_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    recents = []
    for item in data:
        try:
            recents.append(
                Recent(Path(item["path"]), str(item["title"]), float(item["opened_at"]))
            )
        except (KeyError, TypeError, ValueError):
            continue
    return recents


def add_recent(path: Path, title: str, state_dir: Path | None = None) -> None:
    state_dir = state_dir or default_state_dir()
    path = path.expanduser().resolve()
    recents = [r for r in load_recents(state_dir) if r.path != path]
    recents.insert(0, Recent(path, title, time.time()))
    recents = recents[:MAX_RECENTS]
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = [
        {"path": str(r.path), "title": r.title, "opened_at": r.opened_at}
        for r in recents
    ]
    (state_dir / RECENTS_FILE).write_text(json.dumps(payload, indent=2),
                                          encoding="utf-8")


def remove_recent(path: Path, state_dir: Path | None = None) -> None:
    state_dir = state_dir or default_state_dir()
    path = path.expanduser().resolve()
    recents = [r for r in load_recents(state_dir) if r.path != path]
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = [
        {"path": str(r.path), "title": r.title, "opened_at": r.opened_at}
        for r in recents
    ]
    (state_dir / RECENTS_FILE).write_text(json.dumps(payload, indent=2),
                                          encoding="utf-8")
