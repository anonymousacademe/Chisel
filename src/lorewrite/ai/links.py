"""AI-assisted linking: find entity mentions in a scene that should be [[links]].

The LLM proposes mentions with character offsets; every offset is validated
app-side before anything is shown to the author (SPEC §M2). Nothing here ever
modifies text by itself — apply_suggestions is only called with accepted
suggestions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.entities import Entity
from ..core.links import find_links

SCHEMA = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "surface": {"type": "string"},
                },
                "required": ["entity", "start", "end", "surface"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mentions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You find mentions of known fictional characters and places in prose.
You are given a list of known entities (with aliases) and a scene.

Return EVERY mention of those entities that is NOT already wrapped in
[[double brackets]] — including alias and pronoun-free descriptive mentions
(e.g. "the old smith" if that is a listed alias). Do not invent entities.
Do not mention pronouns (he/she/they) unless unambiguous and the author
would plausibly want them linked.

Offsets are 0-based character offsets into the scene: start inclusive,
end exclusive. The surface must EXACTLY match the scene text at
[start, end). Do not include surrounding whitespace or punctuation.
"""


@dataclass(frozen=True)
class Suggestion:
    entity: str  # canonical entity name
    start: int
    end: int
    surface: str


def build_prompt(scene_text: str, entities: list[Entity]) -> str:
    """The user prompt: entity roster + scene. Pure function."""
    roster = "\n".join(
        f"- {e.name} ({e.type})"
        + (f" — aliases: {', '.join(e.aliases)}" if e.aliases else "")
        for e in entities
    )
    return f"KNOWN ENTITIES:\n{roster or '(none)'}\n\nSCENE:\n{scene_text}"


def parse_suggestions(raw: str) -> list[dict]:
    """Parse the model's JSON. Tolerates junk: returns [] on bad input."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    mentions = data.get("mentions") if isinstance(data, dict) else None
    if not isinstance(mentions, list):
        return []
    return [m for m in mentions if isinstance(m, dict)]


def validate_suggestions(
    scene_text: str, raw_mentions: list[dict], entities: list[Entity]
) -> list[Suggestion]:
    """Drop anything that doesn't check out: bad offsets, surface mismatch,
    already-linked spans, unknown entities, overlapping existing links."""
    by_name = {e.name.casefold(): e for e in entities}
    for e in entities:
        for alias in e.aliases:
            by_name.setdefault(alias.casefold(), e)
    existing_links = find_links(scene_text)

    def inside_existing(start: int, end: int) -> bool:
        return any(
            start < link.end and end > link.start for link in existing_links
        )

    valid: list[Suggestion] = []
    for m in raw_mentions:
        try:
            start, end = int(m["start"]), int(m["end"])
            surface = str(m["surface"])
            entity_name = str(m["entity"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= start < end <= len(scene_text)):
            continue
        if scene_text[start:end] != surface:
            continue  # offset drift — drop, never guess
        entity = by_name.get(entity_name.casefold())
        if entity is None:
            continue
        if scene_text[max(0, start - 2):start] == "[[":
            continue
        if inside_existing(start, end):
            continue
        valid.append(Suggestion(entity.name, start, end, surface))
    valid.sort(key=lambda s: s.start)
    # drop overlaps between accepted suggestions (keep the earlier one)
    deduped: list[Suggestion] = []
    last_end = -1
    for s in valid:
        if s.start >= last_end:
            deduped.append(s)
            last_end = s.end
    return deduped


def apply_suggestions(scene_text: str, suggestions: list[Suggestion]) -> str:
    """Wrap accepted spans in [[...]]. Applied back-to-front so offsets hold."""
    text = scene_text
    for s in sorted(suggestions, key=lambda s: s.start, reverse=True):
        text = text[:s.start] + "[[" + s.surface + "]]" + text[s.end:]
    return text


def suggest_links(
    scene_text: str,
    entities: list[Entity],
    model: str,
    client=None,
) -> list[Suggestion]:
    """Network call: ask the model, then parse + validate. Synchronous —
    run it in a worker thread from the TUI."""
    if client is None:
        from .client import make_client

        client = make_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(scene_text, entities)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "link_mentions", "strict": True,
                            "schema": SCHEMA},
        },
        extra_body={"provider": {"require_parameters": True}},
    )
    raw = response.choices[0].message.content or ""
    return validate_suggestions(scene_text, parse_suggestions(raw), entities)
