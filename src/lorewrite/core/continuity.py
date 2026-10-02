"""Continuity checking: contradiction data, waivers, canon accumulation.

This module is the M3 contract anchor (docs/specification-guide.md §2.1).
Pure Python, no AI calls — ai/continuity.py builds on these types.

- Contradiction: one flagged continuity issue
- waivers: .lorewrite/waivers.json — waived flags, never re-reported
- canon section: a managed "## Canon (auto)" section in entity notes that
  the Contextual Tracker updates (author-reviewable)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import entities as ent

TYPES = (
    "physical_attribute",
    "timeline",
    "character_knowledge",
    "object_custody",
    "present_absent",
    "spelling_drift",
)
SEVERITIES = ("error", "warning", "note")

WAIVERS_FILE = "waivers.json"
CANON_HEADER = "## Canon (auto)"


@dataclass(frozen=True)
class Contradiction:
    type: str
    severity: str
    entity: str
    evidence: str
    suggested_fix: str
    scene: str = ""  # project-relative path of the offending scene
    row: int | None = None  # 0-based line in that scene, if locatable

    def waiver_key(self) -> str:
        """Stable identity for waivers — survives re-checks even if the
        model phrases its id differently next time."""
        normalized = " ".join(self.evidence.casefold().split())
        raw = f"{self.type}|{self.entity.casefold()}|{normalized}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def contradiction_from_dict(
    data: dict, scene: str = "", row: int | None = None
) -> Contradiction | None:
    """Validate one model-supplied contradiction dict. None if unusable."""
    try:
        ctype = str(data["type"])
        severity = str(data["severity"])
        entity = str(data["entity"])
        evidence = str(data["evidence"])
        fix = str(data["suggested_fix"])
    except (KeyError, TypeError):
        return None
    if ctype not in TYPES or severity not in SEVERITIES:
        return None
    if not entity or not evidence:
        return None
    return Contradiction(ctype, severity, entity, evidence, fix, scene, row)


# -- waivers ---------------------------------------------------------------


def _waivers_path(project_root: Path) -> Path:
    return project_root / ".lorewrite" / WAIVERS_FILE


def _read_waivers(project_root: Path) -> dict:
    try:
        data = json.loads(_waivers_path(project_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_waivers(project_root: Path) -> set[str]:
    waived = _read_waivers(project_root).get("waived", [])
    return set(waived) if isinstance(waived, list) else set()


def _load_scenes(project_root: Path) -> dict[str, str]:
    scenes = _read_waivers(project_root).get("scenes", {})
    return dict(scenes) if isinstance(scenes, dict) else {}


def save_waiver(project_root: Path, waiver_key: str,
                scene: str | None = None) -> None:
    """Waive *waiver_key*; *scene* (project-relative path) records where, so
    the scene's waivers can be restored later."""
    waived = load_waivers(project_root)
    waived.add(waiver_key)
    scenes = _load_scenes(project_root)
    if scene:
        scenes[waiver_key] = scene
    _write_waivers(project_root, waived, scenes)


def remove_waiver(project_root: Path, waiver_key: str) -> None:
    waived = load_waivers(project_root)
    waived.discard(waiver_key)
    scenes = _load_scenes(project_root)
    scenes.pop(waiver_key, None)
    _write_waivers(project_root, waived, scenes)


def clear_scene_waivers(project_root: Path, scene: str) -> int:
    """Un-waive every issue waived in *scene*; returns how many. (Waivers
    made before scenes were recorded can't be attributed and stay.)"""
    scenes = _load_scenes(project_root)
    keys = {k for k, s in scenes.items() if s == scene}
    if not keys:
        return 0
    waived = load_waivers(project_root) - keys
    for k in keys:
        scenes.pop(k)
    _write_waivers(project_root, waived, scenes)
    return len(keys)


def _write_waivers(project_root: Path, waived: set[str],
                   scenes: dict[str, str] | None = None) -> None:
    path = _waivers_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"waived": sorted(waived)}
    if scenes:
        data["scenes"] = {k: v for k, v in sorted(scenes.items()) if k in waived}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def filter_waived(
    contradictions: list[Contradiction], waived: set[str]
) -> list[Contradiction]:
    return [c for c in contradictions if c.waiver_key() not in waived]


# -- canon section in entity notes ------------------------------------------


def get_canon(body: str) -> str:
    """The managed canon section of a note body ('' if absent)."""
    m = re.search(
        rf"^{re.escape(CANON_HEADER)}\s*\n(.*?)(?=^## |\Z)",
        body, re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def set_canon(body: str, canon_text: str) -> str:
    """Replace the managed canon section, or append one. Author text outside
    the section is never touched."""
    section = f"{CANON_HEADER}\n\n{canon_text.strip()}\n"
    if CANON_HEADER in body:
        return re.sub(
            rf"^{re.escape(CANON_HEADER)}\s*\n.*?(?=^## |\Z)",
            section + ("\n" if not section.endswith("\n\n") else ""),
            body, flags=re.MULTILINE | re.DOTALL,
        )
    body = body.rstrip("\n")
    return f"{body}\n\n{section}" if body else section


def _fact_key(text: str) -> str:
    return " ".join(text.casefold().lstrip("-*• ").rstrip(" .").split())


def add_canon_facts(body: str, facts: list[str]) -> str:
    """Append '- fact' bullets to the managed canon section (creating it if
    missing). Existing lines are never removed or rewritten; facts already
    present (case-insensitive) are skipped; author text stays untouched."""
    existing = get_canon(body)
    known = {_fact_key(ln) for ln in existing.splitlines() if ln.strip()}
    new_lines = []
    for fact in facts:
        fact = " ".join(str(fact).split()).lstrip("-*• ").strip()
        key = _fact_key(fact)
        if not key or key in known:
            continue
        known.add(key)
        new_lines.append(f"- {fact}")
    if not new_lines:
        return body
    text = existing + ("\n" if existing else "") + "\n".join(new_lines)
    return set_canon(body, text)


def apply_canon_update(entity: ent.Entity, new_facts: list[str]) -> None:
    """Append new canon facts to an entity's note and save it (additions only)."""
    entity.body = add_canon_facts(entity.body, list(new_facts))
    if entity.path is not None:
        ent.save_entity(entity, entity.path)


def canon_map(entities: list[ent.Entity]) -> dict[str, str]:
    """Established canon per entity: the managed section, else the note body
    (capped). What the AI is shown as the story bible."""
    canon = {}
    for e in entities:
        managed = get_canon(e.body)
        canon[e.name] = managed if managed else e.body[:1500]
    return canon


def locate_evidence(scene_text: str, evidence: str) -> int | None:
    """Best-effort row (0-based) of an evidence snippet in the scene.

    Tries single lines first; then the whole text with any whitespace (so a
    quote that spans hard-wrapped lines is still found)."""
    snippet = " ".join(evidence.split())[:80]
    if not snippet:
        return None
    for i, line in enumerate(scene_text.splitlines()):
        if snippet[:40] in " ".join(line.split()):
            return i
    words = snippet[:40].split()
    if words:
        pattern = r"\s+".join(re.escape(w) for w in words)
        m = re.search(pattern, scene_text)
        if m:
            return scene_text.count("\n", 0, m.start())
    return None
