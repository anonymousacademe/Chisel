"""User settings store: <state dir>/settings.json (see recents.default_state_dir).

Small JSON dict for app-level preferences (tour seen, etc.).
Project-specific settings live in the project's project.toml instead.
"""

from __future__ import annotations

import json
from pathlib import Path

from .recents import default_state_dir

SETTINGS_FILE = "settings.json"


def load_settings(state_dir: Path | None = None) -> dict:
    state_dir = state_dir or default_state_dir()
    try:
        data = json.loads((state_dir / SETTINGS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict, state_dir: Path | None = None) -> None:
    state_dir = state_dir or default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / SETTINGS_FILE).write_text(json.dumps(settings, indent=2),
                                           encoding="utf-8", newline="\n")


def get(key: str, default=None, state_dir: Path | None = None):
    return load_settings(state_dir).get(key, default)


def set(key: str, value, state_dir: Path | None = None) -> None:
    settings = load_settings(state_dir)
    settings[key] = value
    save_settings(settings, state_dir)
