"""AI relationship suggestions (SPEC "Character relationships").

The author opens a character note and asks for suggestions: the model reads
the note and the roster of the project's other notes, and proposes
relationships from this note's point of view (``[[target]] — label``). The
author ticks what to keep; nothing is written until they accept (the same
rule as every AI feature). Like the alias finder, the request runs through
the context budget and reports what was sent: ``plan_suggestions`` decides
what goes before any network call, then ``suggest_relationships`` makes the
call, then ``apply_suggestions`` writes what the author accepted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.entities import Entity
from ..core.relationships import Rel, parse, set_section
from .budget import Budget, Item, Section, SentReport, fit, preflight
from .client import openrouter_extra_body
from .relevance import rank
from .usage import record_response

SYSTEM_PROMPT = """\
You help a novelist maintain their story bible. You are given one character
note and a roster of the other notes in the project. Propose relationships
the note's text supports, from THIS character's point of view, as short
labels a novelist would write in their notes.

Rules:
- Only propose a relationship the note's text actually supports; do not
  invent backstory.
- The target must be a note from the roster (use its exact name).
- The label is a short phrase (2-8 words), e.g. "father; estranged",
  "former commander", "owes her a favour".
- Do not repeat a relationship the note already declares.
- Output strict JSON, nothing else.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relations"],
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["target", "label"],
                "properties": {
                    "target": {"type": "string", "description": "the other note's exact name"},
                    "label": {"type": "string", "description": "short phrase, this character's point of view"},
                },
            },
        }
    },
}

MAX_LABEL = 120


@dataclass(frozen=True)
class Suggestion:
    target: str  # canonical name of the other note
    label: str


def _roster_line(e: Entity) -> str:
    return f"- {e.name} ({e.type})" + (f" — aliases: {', '.join(e.aliases)}" if e.aliases else "")


def build_prompt(entity: Entity, others: list[Entity]) -> str:
    """The user prompt: the roster of the other notes, then this note.
    Pure function."""
    roster = "\n".join(_roster_line(e) for e in others)
    return (f"OTHER NOTES:\n{roster or '(none)'}\n\n"
            f"THIS NOTE ({entity.name}):\n{entity.body}")


def plan_suggestions(entity: Entity, entities: list[Entity],
                     budget: Budget) -> tuple[list[Entity], SentReport]:
    """What the request sends, decided before any network call.

    Returns (other notes kept, the sent report). The note itself always goes;
    the roster is ranked by how likely it matters (shared mentions in the
    note) and dropped tail-first when it does not fit. Raises ``BudgetError``
    when even the note does not fit. Pass the returned entities to
    ``suggest_relationships``."""
    items = [Item(r.entity.name, head=_roster_line(r.entity), priority=r.priority)
             for r in rank(entity.body, [e for e in entities if e is not entity])]
    fitted, report = fit([
        Section("Instructions and question", SYSTEM_PROMPT + json.dumps(SCHEMA), visible=False),
        Section("Known characters", priority=1, droppable=True, items=tuple(items),
                head="OTHER NOTES:\n", sep="\n"),
        Section("This note", priority=0, droppable=False,
                items=(Item(entity.name, head=entity.body),),
                head=f"THIS NOTE ({entity.name}):\n"),
    ], budget, "relationships")
    preflight(report)
    kept = {it.name for it in next(s for s in fitted if s.name == "Known characters").items}
    return [e for e in entities if e.name in kept and e is not entity], report


def parse_suggestions(raw: str, entity: Entity, others: list[Entity]) -> list[Suggestion]:
    """Parse and validate the model's JSON. Tolerates junk: returns [] on bad
    input; drops unknown targets, repeats of what the note already declares,
    self-references and absurd labels."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    relations = data.get("relations") if isinstance(data, dict) else None
    if not isinstance(relations, list):
        return []
    by_name = {e.name.casefold(): e for e in others}
    existing = {r.target.casefold() for r in parse(entity.body)}
    out: list[Suggestion] = []
    seen: set[str] = set()
    for item in relations:
        if not isinstance(item, dict):
            continue
        target = " ".join(str(item.get("target", "")).split())
        label = " ".join(str(item.get("label", "")).split())
        other = by_name.get(target.casefold())
        if other is None or other is entity:
            continue
        if not label or len(label) > MAX_LABEL:
            continue
        if other.name.casefold() in existing or target.casefold() in seen:
            continue
        seen.add(target.casefold())
        out.append(Suggestion(other.name, label))
    return out


def suggest_relationships(entity: Entity, others: list[Entity],
                          model: str, client=None) -> list[Suggestion]:
    """Network call: ask the model, then parse + validate. Synchronous —
    run it in a worker thread from the TUI; the GUI calls it with the lock
    released (usually inside an AI job)."""
    if client is None:
        from .client import make_client

        client = make_client(model)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(entity, others)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "relationships", "strict": True,
                            "schema": SCHEMA},
        },
        extra_body=openrouter_extra_body({"provider": {"require_parameters": True}}, model=model),
    )
    record_response(response, model, "relationships")
    raw = response.choices[0].message.content or ""
    return parse_suggestions(raw, entity, others)


def apply_suggestions(entity: Entity, accepted: list[Suggestion],
                      save) -> Entity:
    """Merge the accepted suggestions into the note's Relationships section
    (its own declared rows first, then the new ones) and save the note via
    *save* (``core.entities.save_entity``). Returns the updated Entity."""
    merged = [*parse(entity.body), *(Rel(s.target, s.label) for s in accepted)]
    entity.body = set_section(entity.body, merged)
    if entity.path is not None:
        save(entity, entity.path)
    return entity
