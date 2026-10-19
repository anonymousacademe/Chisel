"""AI-powered continuity checking: contradiction detection and canon accumulation.

Uses strong models with structured JSON output, validated app-side before
UI rendering. Every contradiction and canon update is suggest-and-confirm —
nothing here edits prose or entity notes unprompted (SPEC §2, §7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from ..core import scenemeta
from ..core import summaries as summary_store
from ..core.continuity import (
    Contradiction,
    contradiction_from_dict,
    get_canon,
    locate_evidence,
    set_canon,
)
from ..core.jev_interface import pre_screen
from ..core.entities import Entity
from . import relevance
from .budget import Budget, Item, Section, SentReport, fit, preflight, render, trim
from .client import utility_extra_body
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

# Added to the continuity check's instructions ONLY when stored summaries reach the request (a project without any sends
# exactly the instructions it always did). It makes the earlier-scene sections count as canon. The canon-proposal prompt is
# left alone: it only adds facts, and its existing-canon rule already keeps it from restating them.
HISTORY_ADDENDUM = """
The request may also hold STORY SO FAR, EARLIER SCENES INVOLVING ... and ESTABLISHED FACTS ABOUT ... sections. They are
the record of earlier scenes and count as established canon too. Flag a statement in the current scene that conflicts
with a fact in them exactly like a canon conflict. "evidence" is still the exact text of the current scene; in
"suggested_fix" start with "earlier: " and quote, from the section, the earlier statement it conflicts with.
The scene may legitimately change things (a character may learn, move or be injured): do not flag a change the scene
itself shows happening. When unsure, do not flag.
"""

CANON_CAP = 1500   # an entity's existing canon in a canon proposal
NOTE_CAP = 1500    # canon taken from a note body (a note with no managed canon section)


@dataclass(frozen=True)
class CanonUpdate:
    """New facts to append to one entity's managed canon section."""

    entity: str
    new_facts: tuple[str, ...]
    evidence: str = ""
    existing_canon: str = ""  # for display only; filled app-side


def _details_block(scene_text: str) -> str:
    """The scene's author-set details (POV, place, purpose) as a prompt
    section; the frontmatter itself is never sent as prose."""
    header = scenemeta.header(scene_text)
    if not header:
        return ""
    return ("SCENE DETAILS (the author's plan for this scene - not prose; "
            "e.g. the POV character can only know what they could have "
            f"learned):\n{header}\n\n")


@dataclass(frozen=True)
class History:
    """What the stored summaries add to a request (``core.summaries``): the story so far before the
    scene, and, per main character, the earlier scenes they are in. Empty = nothing is added."""

    story: summary_store.StorySoFar | None = None
    earlier: tuple[tuple[str, summary_store.EntityHistory], ...] = ()   # (entity name, its history)
    facts: tuple[tuple[str, summary_store.EntityFacts], ...] = ()       # (entity name, its facts ledger)

    @property
    def present(self) -> bool:
        """Something from the summaries reaches the request (so the instructions get ``HISTORY_ADDENDUM``)."""
        return bool((self.story and self.story.blocks) or any(h.items for _, h in self.earlier)
                    or any(f.items for _, f in self.facts))


HISTORY_ENTITIES = 8        # the characters (most mentioned first) whose facts ledger is added
EARLIER_ENTITIES = 3        # ... of whom this many (the same top ones) also get "Earlier scenes involving" (the expensive section)
HISTORY_FACTS_TOTAL = 160   # the most ledger facts in one request, shared across the characters
HISTORY_SCENES = 3          # earlier scenes per character: the first appearance and the newest


# What reaches a continuity check from the stored summaries: "summaries" (the story so far and the earlier scenes of the
# main characters: summary prose), "facts" (the verified-facts ledger of the main characters only) or "both". The
# default is this one constant; it stays "summaries" until the experiment says otherwise.
HISTORY_MODES = ("summaries", "facts", "both")
HISTORY_MODE = "summaries"


def _shares(needs: list[int], total: int) -> list[int]:
    """How many facts each character may list when *needs* (in order, most mentioned first) together exceed *total*: an equal
    share, what a character does not need goes to the others, and any rest goes to the most mentioned first."""
    quota = [0] * len(needs)
    todo, left = list(range(len(needs))), total
    while todo and left > 0:
        share = left // len(todo)
        if share == 0:
            for i in todo[:left]:
                quota[i] += 1
            break
        small = [i for i in todo if needs[i] - quota[i] <= share]
        if not small:
            for i in todo:
                quota[i] += share
            left -= share * len(todo)
            continue
        for i in small:
            left -= needs[i] - quota[i]
            quota[i] = needs[i]
        todo = [i for i in todo if i not in small]
    return quota


def history_for(project, scene_rel: str, scene_text: str, entities: list[Entity],
                mode: str = HISTORY_MODE, max_entities: int = HISTORY_ENTITIES,
                max_facts: int = HISTORY_FACTS_TOTAL) -> History | None:
    """The stored summaries a continuity check or canon proposal of the scene *scene_rel* may add. *mode*:
    "summaries" = the story so far before it and, for the ``EARLIER_ENTITIES`` characters it names most, their earlier scenes;
    "facts" = the ledger of verified facts of earlier scenes (``core.summaries.entity_facts``) for up to *max_entities* of
    the characters the scene names, most mentioned first (name or alias occurrences in the prose, POV and place from the
    details once; ties by ``relevance.rank``); "both" (the earlier scenes then use the same top ``EARLIER_ENTITIES``).
    Why so many characters: a contradiction about a character the ledger does not cover can never be found, however well
    the model reads. The ledgers share *max_facts* in all (an equal share, what a character does not need goes to the
    others, the rest to the most mentioned); each keeps its first and newest facts, and what was left out is named in the
    sent report (counts and scene titles). None when the project has no summaries at all (nothing is read, the request is
    exactly what it always was). Reads sidecars and earlier scenes: call it outside the project lock. *scene_text* has no
    pending AI drafts. ValueError for another mode."""
    if mode not in HISTORY_MODES:
        raise ValueError(f"history mode must be one of {', '.join(HISTORY_MODES)}")
    if not summary_store.has_any(project.root):
        return None
    named = [r.entity for r, _ in relevance.by_mentions(scene_text, entities)]
    story, earlier, facts = None, (), ()
    if mode in ("summaries", "both"):
        story = summary_store.story_so_far(project, scene_rel)
        earlier = tuple((e.name, summary_store.entity_history(project, e, scene_rel, limit=HISTORY_SCENES))
                        for e in named[:min(EARLIER_ENTITIES, max_entities)])
    if mode in ("facts", "both"):
        full = [(e.name, summary_store.entity_facts(project, e, scene_rel, limit=10 ** 9)) for e in named[:max_entities]]
        needs = [min(len(f.items), summary_store.FACTS_PER_ENTITY) for _, f in full]
        quota = needs if sum(needs) <= max_facts else _shares(needs, max_facts)
        facts = tuple((name, summary_store.cap_facts(f, min(q, summary_store.FACTS_PER_ENTITY)))
                      for (name, f), q in zip(full, quota))
    return History(story, earlier, facts)


def _story_section(story: summary_store.StorySoFar | None) -> Section | None:
    """"Story so far": the summaries of the earlier scenes, the newest kept first when the budget is tight."""
    if story is None or not story.blocks:
        return None
    head = ("STORY SO FAR (summaries of the earlier part of the book, " + story.sentence.lower()
            + "; they are the record of what happened, the scene below is what is being checked):\n")
    if story.missing:
        head += f"(no summary yet for: {', '.join(story.missing)})\n"
    n = len(story.blocks)
    items = tuple(Item(b.name, b.text, "", n - 1 - i) for i, b in enumerate(story.blocks))
    return Section("Story so far", priority=2, droppable=True, items=items, head=head)


def _earlier_section(earlier: tuple[tuple[str, summary_store.EntityHistory], ...]) -> Section | None:
    """"Earlier scenes involving <names>": each main character's first appearance, then their newest scenes."""
    rows = [(i, name, h) for i, (name, h) in enumerate(earlier) if h.items]
    if not rows:
        return None
    items = tuple(Item(f"{name}: {it.title}", it.summary, f"### {name} - {it.title}", it.rank * 100 + i)
                  for i, name, h in rows for it in h.items)
    names = ", ".join(name for _, name, _ in rows)
    return Section(f"Earlier scenes involving {names}", priority=3, droppable=True, items=items,
                   head=f"EARLIER SCENES INVOLVING {names.upper()}:\n")


def _fact_line(it: summary_store.FactItem) -> str:
    more = f"; stated in {it.count} scenes" if it.count > 1 else ""
    return f"- {it.text} ({it.title}{more})"


def _facts_section(facts: tuple[tuple[str, summary_store.EntityFacts], ...]) -> Section | None:
    """"Established facts about <names>": the verified facts of earlier scenes, one compact line each with its scene,
    grouped per entity and per scene (so the report can name scenes). Priority 1: after the entity canon (0), before the
    story so far (2). Inside it the NEWEST scenes' facts are dropped first, so first appearances survive."""
    rows = [(name, f) for name, f in facts if f.items]
    if not rows:
        return None
    items = []
    for name, f in rows:
        blocks: list[list[summary_store.FactItem]] = []
        for it in f.items:
            if blocks and blocks[-1][0].scene_id == it.scene_id:
                blocks[-1].append(it)
            else:
                blocks.append([it])
        for k, block in enumerate(blocks):
            items.append(Item(f"{name}: {block[0].title}", "\n".join(_fact_line(it) for it in block),
                              f"### {name}" if k == 0 else "", k))
    names = ", ".join(name for name, _ in rows)
    return Section(f"Established facts about {names}", priority=1, droppable=True, items=tuple(items), sep="\n",
                   head=f"ESTABLISHED FACTS ABOUT {names.upper()} (facts recorded from the summaries of earlier scenes, "
                        "each with the scene it comes from):\n")


def _history_sections(history: History | None) -> list[Section]:
    return [s for s in (_facts_section(history.facts), _story_section(history.story), _earlier_section(history.earlier))
            if s is not None] if history is not None else []


def _with_cap_notes(report: SentReport, history: History | None) -> SentReport:
    """What the per-entity cap of the facts ledger left out is named in the report too ("X: 12 facts from Chapter V,
    Chapter VI (over the cap of 60)"): counts and scene titles, because a fact has no short name."""
    if history is None:
        return report
    notes = tuple(f"{name}: {f.omitted} fact{'s' if f.omitted != 1 else ''} from {', '.join(f.omitted_scenes)} "
                  f"(over the limit of {f.limit} for them)" for name, f in history.facts if f.omitted)
    if not notes:
        return report
    rows = tuple(replace(r, items_dropped=r.items_dropped + notes) if r.name.startswith("Established facts about") else r
                 for r in report.sections)
    return replace(report, sections=rows)


def _history_text(fitted: list[Section], history: History | None) -> str:
    names = {s.name for s in _history_sections(history)}
    return render(s for s in fitted if s.name in names)


def build_check_prompt(scene_text: str, canon_by_name: dict[str, str], history: str = "") -> str:
    """The user prompt: canon roster + (summaries, if any) + scene. Pure function."""
    canon_lines = []
    for name, canon in canon_by_name.items():
        canon_lines.append(f"### {name}\n{canon}" if canon else f"### {name}\n(no canon)")
    canon_block = "\n\n".join(canon_lines) if canon_lines else "(no canon)"
    return (f"ENTITY CANON:\n{canon_block}\n\n{history + chr(10) * 2 if history else ''}"
            f"{_details_block(scene_text)}SCENE:\n{scenemeta.strip(scene_text)}")


def plan_check(scene_text: str, entities: list[Entity], canon_by_name: dict[str, str],
               budget: Budget) -> tuple[list[Entity], dict[str, str], SentReport]:
    """What a continuity check sends, decided before any network call: the entities the
    scene is about (named in it, then its POV / place; every entity for a project with fewer
    than ``relevance.ALL_MAX``), their canon fitted into *budget*, and the report. Pass the
    returned entities and canon to ``check_scene``. Raises ``BudgetError`` when the scene
    alone does not fit."""
    return plan_check_history(scene_text, entities, canon_by_name, budget)[:3]


def plan_check_history(scene_text: str, entities: list[Entity], canon_by_name: dict[str, str],
                       budget: Budget, history: History | None = None
                       ) -> tuple[list[Entity], dict[str, str], SentReport, str]:
    """``plan_check`` plus the summaries: *history* adds the droppable "Story so far" and "Earlier
    scenes involving ..." sections (after the entity canon, before the scene), fitted into *budget* like
    everything else and named in the report. The fourth value is the text of what was kept: pass it to
    ``check_scene(..., history=)``. With no history it is ``""`` and the rest is exactly ``plan_check``."""
    items = []
    for r in relevance.rank(scene_text, entities):
        e = r.entity
        if e.name in canon_by_name:
            managed = bool(get_canon(e.body))   # a managed canon section is not capped
            items.append(Item(e.name, canon_by_name[e.name], f"### {e.name}", r.priority,
                              None if managed else NOTE_CAP, empty="(no canon)"))
    sections = [
        Section("Instructions and question",
                SYSTEM_PROMPT + (HISTORY_ADDENDUM if history is not None and history.present else "")
                + json.dumps(CONTRADICTION_SCHEMA), visible=False),
        Section("Entity canon", priority=0, droppable=True, items=tuple(items),
                head="ENTITY CANON:\n", max_priority=relevance.priority_limit(entities)),
    ]
    sections += _history_sections(history)
    details = _details_block(scene_text).strip()
    if details:
        sections.append(Section("Scene details", details))
    sections.append(Section("Scene", "SCENE:\n" + scenemeta.strip(scene_text)))
    fitted, report = fit(sections, budget, "continuity")
    preflight(report)
    canon = {it.name: it.body for it in next(s for s in fitted if s.name == "Entity canon").items}
    return [e for e in entities if e.name in canon], canon, _with_cap_notes(report, history), _history_text(fitted, history)


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
    history: str = "",
) -> list[Contradiction]:
    """Network call: Jev pre-screen, then strong model for flagged entities. *history* is the summaries
    text ``plan_check_history`` kept ("" = none).

    Synchronous — run in a worker thread from the TUI.
    """
    flagged = pre_screen(scenemeta.strip(scene_text), entities, canon_by_name)
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

        client = make_client(model)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + (HISTORY_ADDENDUM if history else "")},
            {
                "role": "user",
                "content": build_check_prompt(scene_text, filtered_canon, history),
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
        extra_body=utility_extra_body({"provider": {"require_parameters": True}}, model=model),
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


def _canon_section(ranked: list[relevance.Ranked], max_priority: int | None = None) -> Section:
    """The entity roster of a canon proposal: name, type, aliases and existing canon each."""
    items = []
    for r in ranked:
        e = r.entity
        line = f"- {e.name} ({e.type})"
        if e.aliases:
            line += f" — aliases: {', '.join(e.aliases)}"
        items.append(Item(e.name, get_canon(e.body), line, r.priority, CANON_CAP,
                          lead="  existing canon:\n", empty="  existing canon: (none)"))
    return Section("Entity notes", priority=0, droppable=True, items=tuple(items), head="ENTITIES:\n",
                   sep="\n", max_priority=max_priority)


def plan_canon(scene_text: str, entities: list[Entity], budget: Budget) -> tuple[list[Entity], SentReport]:
    """What a canon proposal sends, decided before any network call: the entities the scene
    is about (see ``plan_check``), each with its existing canon fitted into *budget*. Pass the
    returned entities to ``propose_canon_updates`` (one whose canon had to be cut further than
    its usual cap is a copy carrying the cut text). Raises ``BudgetError`` when the scene alone
    does not fit."""
    return plan_canon_history(scene_text, entities, budget)[:2]


def plan_canon_history(scene_text: str, entities: list[Entity], budget: Budget,
                       history: History | None = None) -> tuple[list[Entity], SentReport, str]:
    """``plan_canon`` plus the summaries (see ``plan_check_history``); the third value goes to
    ``propose_canon_updates(..., history=)``."""
    sections = [
        Section("Instructions and question", ACCUMULATION_SYSTEM_PROMPT + json.dumps(ACCUMULATION_SCHEMA),
                visible=False),
        _canon_section(relevance.rank(scene_text, entities), relevance.priority_limit(entities)),
        *_history_sections(history),
    ]
    details = _details_block(scene_text).strip()
    if details:
        sections.append(Section("Scene details", details))
    sections.append(Section("Scene", "SCENE:\n" + scenemeta.strip(scene_text)))
    fitted, report = fit(sections, budget, "canon")
    report = _with_cap_notes(report, history)
    preflight(report)
    by_name = {e.name: e for e in entities}
    out = []
    for item in next(s for s in fitted if s.name == "Entity notes").items:
        e = by_name[item.name]
        full = get_canon(e.body)
        usual = trim(full, CANON_CAP) if len(full) > CANON_CAP else full
        out.append(e if item.body == usual else replace(e, body=set_canon("", item.body)))
    return out, report, _history_text(fitted, history)


def propose_canon_updates(
    scene_text: str,
    entities: list[Entity],
    model: str,
    client=None,
    history: str = "",
) -> list[CanonUpdate]:
    """Network call: ask what NEW canon the scene establishes per entity. *history* is the summaries
    text ``plan_canon_history`` kept ("" = none).

    Additions only: each entity's existing canon is sent so the model can skip
    known facts, and the reply is validated app-side against it. Every entity given is
    sent (canon capped at ``CANON_CAP``): choose and fit them with ``plan_canon`` first.
    Synchronous — run in a worker thread from the TUI.
    """
    roster = render(fit([_canon_section([relevance.Ranked(e, 0, i) for i, e in enumerate(entities)])],
                        Budget.unbounded())[0])
    roster = roster or "ENTITIES:\n(none)"
    prompt = (f"{roster}\n\n{history + chr(10) * 2 if history else ''}"
              f"{_details_block(scene_text)}SCENE:\n{scenemeta.strip(scene_text)}")

    if client is None:
        from .client import make_client

        client = make_client(model)
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
        extra_body=utility_extra_body({"provider": {"require_parameters": True}}, model=model),
    )
    record_response(response, model, "canon")
    raw = response.choices[0].message.content or ""
    return parse_canon_updates(raw, entities)
