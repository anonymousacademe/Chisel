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


def load_waivers(project_root: Path) -> set[str]:
    try:
        data = json.loads(_waivers_path(project_root).read_text(encoding="utf-8"))
        return set(data.get("waived", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


def save_waiver(project_root: Path, waiver_key: str) -> None:
    waived = load_waivers(project_root)
    waived.add(waiver_key)
    _write_waivers(project_root, waived)


def remove_waiver(project_root: Path, waiver_key: str) -> None:
    waived = load_waivers(project_root)
    waived.discard(waiver_key)
    _write_waivers(project_root, waived)


def _write_waivers(project_root: Path, waived: set[str]) -> None:
    path = _waivers_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"waived": sorted(waived)}, indent=2),
                    encoding="utf-8")


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


def apply_canon_update(entity: ent.Entity, new_canon: str) -> None:
    """Set an entity's canon section and save the note."""
    entity.body = set_canon(entity.body, new_canon)
    if entity.path is not None:
        ent.save_entity(entity, entity.path)


def locate_evidence(scene_text: str, evidence: str) -> int | None:
    """Best-effort row (0-based) of an evidence snippet in the scene."""
    snippet = " ".join(evidence.split())[:80]
    if not snippet:
        return None
    for i, line in enumerate(scene_text.splitlines()):
        if snippet[:40] in " ".join(line.split()):
            return i
    return None
