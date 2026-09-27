"""AI-powered continuity checking: contradiction detection and canon accumulation.

Uses strong models with structured JSON output, validated app-side before
UI rendering. Every contradiction and canon update is suggest-and-confirm —
nothing here edits prose or entity notes unprompted (SPEC §2, §7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.continuity import Contradiction, contradiction_from_dict, locate_evidence
from ..core.jev_interface import pre_screen
from ..core.entities import Entity

CONTRADICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "physical_attribute",
                            "timeline",
                            "character_knowledge",
                            "object_custody",
                            "present_absent",
                            "spelling_drift",
                        ],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["error", "warning", "note"],
                    },
                    "entity": {"type": "string"},
                    "evidence": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": [
                    "id",
                    "type",
                    "severity",
                    "entity",
                    "evidence",
                    "suggested_fix",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["contradictions"],
    "additionalProperties": False,
}

ACCUMULATION_SCHEMA = {
    "type": "object",
    "properties": {
        "updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "existing_canon": {"type": "string"},
                    "new_canon": {"type": "string"},
                    "justification": {"type": "string"},
                },
                "required": [
                    "entity",
                    "existing_canon",
                    "new_canon",
                    "justification",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["updates"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You identify continuity contradictions in fiction manuscripts. Given:
1. Entity canon — attributes established in prior scenes for each entity
2. The current scene text

Find contradictions where the current scene violates established canon:
- Physical attributes that changed (eye color, height, injuries)
- Timeline impossibilities (travel time, event order)
- Character knowing things they shouldn't yet
- Objects being in the wrong place or custody
- Characters acting as present/absent inconsistently
- Name spelling drift across scenes

For every contradiction, the "evidence" field MUST contain the EXACT text
from the scene that conflicts with canon — quote it verbatim so the author
can locate it. Do not paraphrase or summarize the evidence.

Be precise. Do not flag intentional ambiguity, stylistic variation, or
unreliable narrator effects as contradictions.
"""

ACCUMULATION_SYSTEM_PROMPT = """\
You propose canon updates for entity notes based on a new scene.

Given entity names and the scene text, determine what new facts the scene
establishes about each entity that appears in it. Rules:
- Only include facts directly stated or strongly implied by the scene text.
- new_canon must be a FULL replacement of the entity's canon section —
  merge existing canon with new facts, preserving everything that remains
  true and adding what the scene establishes. Do not drop existing canon
  unless the scene explicitly contradicts it.
- No speculation, inference beyond strong implication, or headcanon.
- If the scene establishes nothing new about an entity, omit that entity
  from the response entirely.
"""


@dataclass(frozen=True)
class CanonUpdate:
    entity: str
    existing_canon: str
    new_canon: str
    justification: str


def build_check_prompt(scene_text: str, canon_by_name: dict[str, str]) -> str:
    """The user prompt: canon roster + scene. Pure function."""
    canon_lines = []
    for name, canon in canon_by_name.items():
        canon_lines.append(f"### {name}\n{canon}" if canon else f"### {name}\n(no canon)")
    canon_block = "\n\n".join(canon_lines) if canon_lines else "(no canon)"
    return f"ENTITY CANON:\n{canon_block}\n\nSCENE:\n{scene_text}"


def parse_contradictions(
    raw: str, scene_text: str, scene_rel: str
) -> list[Contradiction]:
    """Parse the model's JSON. Tolerant: returns [] on bad input."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data.get("contradictions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    results: list[Contradiction] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        c = contradiction_from_dict(item, scene=scene_rel)
        if c is None:
            continue
        row = locate_evidence(scene_text, c.evidence)
        results.append(
            Contradiction(
                c.type, c.severity, c.entity, c.evidence,
                c.suggested_fix, c.scene, row,
            )
        )
    return results


def check_scene(
    scene_text: str,
    entities: list[Entity],
    canon_by_name: dict[str, str],
    model: str,
    client=None,
) -> list[Contradiction]:
    """Network call: Jev pre-screen, then strong model for flagged entities.

    Synchronous — run in a worker thread from the TUI.
    """
    flagged = pre_screen(scene_text, entities, canon_by_name)
    if flagged is not None:
        if not flagged:
            return []
        filtered_canon = {
            name: canon
            for name, canon in canon_by_name.items()
            if name in flagged
        }
    else:
        filtered_canon = canon_by_name

    if not filtered_canon:
        return []

    if client is None:
        from .client import make_client

        client = make_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_check_prompt(scene_text, filtered_canon),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "contradictions",
                "strict": True,
                "schema": CONTRADICTION_SCHEMA,
            },
        },
        extra_body={"provider": {"require_parameters": True}},
    )
    raw = response.choices[0].message.content or ""
    return parse_contradictions(raw, scene_text, "")


def parse_canon_updates(raw: str) -> list[CanonUpdate]:
    """Parse the model's JSON. Tolerant: skips malformed items."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    results: list[CanonUpdate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            entity = str(item["entity"])
            existing = str(item["existing_canon"])
            new = str(item["new_canon"])
            justification = str(item["justification"])
        except (KeyError, TypeError):
            continue
        if not entity or not new:
            continue
        results.append(CanonUpdate(entity, existing, new, justification))
    return results


def propose_canon_updates(
    scene_text: str,
    entities: list[Entity],
    model: str,
    client=None,
) -> list[CanonUpdate]:
    """Network call: ask what canon the scene establishes about each entity.

    Synchronous — run in a worker thread from the TUI.
    """
    roster = "\n".join(
        f"- {e.name} ({e.type})"
        + (f" — aliases: {', '.join(e.aliases)}" if e.aliases else "")
        for e in entities
    )
    prompt = f"ENTITIES:\n{roster or '(none)'}\n\nSCENE:\n{scene_text}"

    if client is None:
        from .client import make_client

        client = make_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ACCUMULATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "canon_updates",
                "strict": True,
                "schema": ACCUMULATION_SCHEMA,
            },
        },
        extra_body={"provider": {"require_parameters": True}},
    )
    raw = response.choices[0].message.content or ""
    return parse_canon_updates(raw)
