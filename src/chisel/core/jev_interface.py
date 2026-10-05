"""Jev pre-screening: cheap gate before spending strong-model tokens (M3).

Uses the local jev CLI (~/.config/jev/jev.py, see ~/.config/jev/GUIDE.md) as
a fast classifier: for each entity with established canon, ask whether the
scene plausibly contradicts it. Only entities that pass the gate get a full
strong-model check. If jev is unavailable, screening is skipped (fail-open:
everything goes to the strong model).

Never print or log the jev key; we only invoke the CLI.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import entities as ent
from .desktop import NO_CONSOLE

JEV_CLI = Path.home() / ".config/jev/jev.py"
MAX_SCREEN_ENTITIES = 20  # beyond this, skip screening (cost > value)
GATE_THRESHOLD = 0.5


def jev_available() -> bool:
    return JEV_CLI.is_file()


def _ask(state: dict, questions: dict) -> dict | None:
    """One jev ask call. Returns parsed JSON or None on any failure."""
    try:
        result = subprocess.run(
            ["python3", str(JEV_CLI), "ask",
             "--state", json.dumps(state),
             "--questions", json.dumps(questions)],
            capture_output=True, text=True, timeout=30, **NO_CONSOLE,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def _contradiction_score(result: dict) -> float | None:
    """The 0..1 contradiction score from a jev ask reply, or None if the
    reply has an unexpected shape (callers then fail open).

    Current jev replies look like
    ``{"answers": {"contradiction": {"type": "noul", "noul": 0.85}}, ...}``;
    older ones put the answer at the top level.
    """
    answer = result.get("answers", result) if isinstance(result, dict) else None
    if not isinstance(answer, dict) or "contradiction" not in answer:
        return None
    value = answer["contradiction"]
    if isinstance(value, dict):
        value = value.get("noul", value.get("value"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pre_screen(
    scene_text: str, entities: list[ent.Entity], canon_by_name: dict[str, str]
) -> list[str] | None:
    """Names of entities worth a strong-model check.

    Returns None if screening can't run (no jev, too many entities) —
    callers treat that as "check everything".
    """
    candidates = [e for e in entities if canon_by_name.get(e.name)]
    if not jev_available() or not candidates or len(candidates) > MAX_SCREEN_ENTITIES:
        return None
    excerpt = scene_text[:4000]
    flagged: list[str] = []
    for entity in candidates:
        canon = canon_by_name[entity.name][:1500]
        state = {
            "canon": {"entity": entity.name, "established": canon},
            "scene_excerpt": excerpt,
        }
        questions = {
            "contradiction": {
                "type": "noul",
                "instructions": "Does the scene excerpt plausibly contradict "
                                "the established canon for this entity?",
                "criteria": {
                    "true": "excerpt states or implies something about the "
                            "entity that conflicts with the canon (attribute, "
                            "timeline, knowledge, location, possession)",
                    "false": "excerpt is consistent with canon or says "
                             "nothing about the entity",
                },
            }
        }
        result = _ask(state, questions)
        score = None if result is None else _contradiction_score(result)
        if score is None:
            return None  # fail-open: screen unusable, check everything
        if score >= GATE_THRESHOLD:
            flagged.append(entity.name)
    return flagged
