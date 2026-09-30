"""AI alias finder: descriptive references to known entities ("the old smith").

Plain names and aliases are already recognized without AI (core.links). The
LLM's job is the rest: other ways the prose refers to known entities. It
proposes spans with character offsets; every offset is validated app-side
before anything is shown (SPEC §7 M2). This module never touches scene text —
accepted suggestions become aliases in entity notes, nothing more.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.entities import Entity
from ..core.links import find_links, find_mentions
from .client import usage_extra_body
from .usage import record_response

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
You find alternative ways a piece of prose refers to known fictional characters
and places — descriptive references such as "the old smith" for Borin or
"the captain's daughter" for Elara.
You are given a list of known entities (with their names and aliases) and a
scene.

Return every descriptive reference in the scene that clearly points at one of
the known entities and is NOT already one of that entity's names or aliases.
Skip exact names and aliases (the app already recognizes those), skip
pronouns (he, she, they, him, her, it, ...), and never invent entities.
Only include references the author would plausibly want to teach the app as
a new alias: short noun phrases, not whole clauses.

Offsets are 0-based character offsets into the scene: start inclusive,
end exclusive. The surface must EXACTLY match the scene text at
[start, end). Do not include surrounding whitespace or punctuation.
"""

PRONOUNS = frozenset({
    "he", "she", "they", "him", "her", "them", "his", "hers", "their",
    "theirs", "it", "its", "i", "me", "you",
})
MIN_SURFACE = 2
MAX_SURFACE = 40
_LEADING_WORDS = ("the", "a", "an", "his", "her", "their", "that", "this")


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
    unknown entities, spans that are already links or known names/aliases,
    pronouns, absurd lengths, duplicates and overlaps."""
    by_name = {e.name.casefold(): e for e in entities}
    for e in entities:
        for alias in e.aliases:
            by_name.setdefault(alias.casefold(), e)
    known = [n for e in entities for n in e.names]
    links = [(l.start, l.end) for l in find_links(scene_text)]
    mentions = [(m.start, m.end) for m in find_mentions(scene_text, known)]

    def already_recognized(start: int, end: int) -> bool:
        """Touches an explicit link, or lies within a known name/alias."""
        return (any(start < e and end > s for s, e in links)
                or any(s <= start and end <= e for s, e in mentions))

    valid: list[Suggestion] = []
    seen: set[tuple[str, str]] = set()
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
        if not (MIN_SURFACE <= len(surface) <= MAX_SURFACE):
            continue
        if surface.strip().casefold() in PRONOUNS:
            continue
        entity = by_name.get(entity_name.casefold())
        if entity is None:
            continue
        if surface.casefold() in by_name:
            continue  # already a name/alias of some entity
        if already_recognized(start, end):
            continue
        key = (surface.casefold(), entity.name)
        if key in seen:
            continue
        seen.add(key)
        valid.append(Suggestion(entity.name, start, end, surface))
    valid.sort(key=lambda s: s.start)
    # drop overlaps between suggestions (keep the earlier one)
    deduped: list[Suggestion] = []
    last_end = -1
    for s in valid:
        if s.start >= last_end:
            deduped.append(s)
            last_end = s.end
    return deduped


def alias_form(surface: str) -> str:
    """The alias to store for an accepted surface.

    A capitalized article/determiner at a sentence start ("The old smith") is
    stored lowercase so the alias also matches mid-sentence; mention matching
    already tolerates a capital at sentence starts.
    """
    surface = surface.strip()
    first, _, rest = surface.partition(" ")
    if rest and first.casefold() in _LEADING_WORDS and first[:1].isupper():
        return first[0].lower() + first[1:] + " " + rest
    return surface


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
        extra_body=usage_extra_body({"provider": {"require_parameters": True}}),
    )
    record_response(response, model, "links")
    raw = response.choices[0].message.content or ""
    return validate_suggestions(scene_text, parse_suggestions(raw), entities)
