"""AI-powered continuity checking: contradiction detection and canon accumulation.

Uses strong models with structured JSON output, validated app-side before
UI rendering. Every contradiction and canon update is suggest-and-confirm —
nothing here edits prose or entity notes unprompted (SPEC §2, §7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.continuity import (
    Contradiction,
    contradiction_from_dict,
    get_canon,
    locate_evidence,
)
from ..core.jev_interface import pre_screen
from ..core.entities import Entity
from .client import usage_extra_body
from .usage import record_response

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
                    "new_facts": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "string"},
                },
                "required": ["entity", "new_facts", "evidence"],
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
You propose ADDITIONS to entity notes based on a new scene.

You are given each entity's existing canon and the scene text. List only NEW
facts the scene establishes about an entity that are not already in its
existing canon. Rules:
- One short, self-contained fact per item in new_facts.
- Only facts directly stated or strongly implied by the scene text.
- Never restate, reword, merge or "correct" existing canon; you cannot remove
  or change it, only add.
- No speculation, inference beyond strong implication, or headcanon.
- evidence: a brief quote or paraphrase from the scene supporting the facts.
- If the scene establishes nothing new about an entity, omit that entity.
"""

CANON_CAP = 1500


@dataclass(frozen=True)
class CanonUpdate:
    """New facts to append to one entity's managed canon section."""

    entity: str
    new_facts: tuple[str, ...]
    evidence: str = ""
    existing_canon: str = ""  # for display only; filled app-side


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
        extra_body=usage_extra_body({"provider": {"require_parameters": True}}),
    )
    record_response(response, model, "continuity")
    raw = response.choices[0].message.content or ""
    return parse_contradictions(raw, scene_text, "")


def _fact_key(fact: str) -> str:
    return " ".join(fact.casefold().lstrip("-*• ").rstrip(" .").split())


def clean_fact(fact: str) -> str:
    """One-line fact without a leading bullet marker."""
    return " ".join(str(fact).split()).lstrip("-*• ").strip()


def parse_canon_updates(
    raw: str, entities: list[Entity] | None = None
) -> list[CanonUpdate]:
    """Parse and validate the model's JSON. Tolerant: skips malformed items.

    With *entities*: unknown entities are dropped, names are canonicalized,
    and facts already present in an entity's canon (case-insensitive) or
    repeated within the reply are dropped. Empty facts are always dropped.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data.get("updates") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    by_name = {}
    for e in entities or []:
        for n in e.names:
            by_name.setdefault(n.casefold(), e)
    results: list[CanonUpdate] = []
    seen: dict[str, set[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            name = str(item["entity"])
            facts = item["new_facts"]
        except (KeyError, TypeError):
            continue
        if not name or not isinstance(facts, list):
            continue
        existing = ""
        if entities is not None:
            entity = by_name.get(name.casefold())
            if entity is None:
                continue
            name = entity.name
            existing = get_canon(entity.body)
        known = seen.setdefault(
            name, {_fact_key(ln) for ln in existing.splitlines() if ln.strip()})
        kept: list[str] = []
        for fact in facts:
            fact = clean_fact(fact) if isinstance(fact, str) else ""
            key = _fact_key(fact)
            if not key or key in known:
                continue
            known.add(key)
            kept.append(fact)
        if kept:
            results.append(CanonUpdate(name, tuple(kept),
                                       str(item.get("evidence") or ""),
                                       existing))
    return results


def propose_canon_updates(
    scene_text: str,
    entities: list[Entity],
    model: str,
    client=None,
) -> list[CanonUpdate]:
    """Network call: ask what NEW canon the scene establishes per entity.

    Additions only: each entity's existing canon is sent so the model can skip
    known facts, and the reply is validated app-side against it.
    Synchronous — run in a worker thread from the TUI.
    """
    roster = []
    for e in entities:
        line = f"- {e.name} ({e.type})"
        if e.aliases:
            line += f" — aliases: {', '.join(e.aliases)}"
        canon = get_canon(e.body)[:CANON_CAP]
        line += f"\n  existing canon:\n{canon}" if canon else "\n  existing canon: (none)"
        roster.append(line)
    prompt = (f"ENTITIES:\n{chr(10).join(roster) or '(none)'}\n\n"
              f"SCENE:\n{scene_text}")

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
        extra_body=usage_extra_body({"provider": {"require_parameters": True}}),
    )
    record_response(response, model, "canon")
    raw = response.choices[0].message.content or ""
    return parse_canon_updates(raw, entities)
