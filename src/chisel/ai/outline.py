"""AI outline assistant for research mode (plan: docs/dev/plan-research-waves-d-f.md, wave D).

The model reads the author's scope statement, the project kind and journal requirements, the standard
structure, any guideline documents the author ticked and the current outline, and proposes changes as a list
of items: add / rename / move / keep / advice. This module never touches a file: ``plan_outline`` decides what
is sent (budget sections, named in the ``SentReport``) before any network call, ``suggest_outline`` returns the
model's JSON text, and ``parse_outline_items`` validates every item against the outline and reports what it
dropped and why. Nothing is ever deleted or merged by the assistant (such a request becomes advice).
"""

from __future__ import annotations

import itertools
import json
import re

from ..core.paper import guidelines, outlines
from .budget import Budget, Item, Section, SentReport, fit, preflight, render
from .client import openrouter_extra_body
from .stream import stream_text
from .usage import record_response

FEATURE = "outline"
ACTIONS = ("add", "rename", "move", "keep", "advice")
DELETE_LIKE = ("delete", "remove", "drop", "cut", "merge", "combine", "consolidate", "join", "split")
MAX_ITEMS = 40
MAX_DROPPED = 40
MAX_GUIDELINES = 8
GUIDELINE_ITEM_CHARS = 8_000        # per guideline document (trimmed and reported)
TITLE_MAX = 120
PURPOSE_MAX = 300
WHY_MAX = 400
MAX_REPLY_CHARS = 400_000
MAX_JSON_STARTS = 200

SYSTEM_PROMPT = """\
You help a researcher plan the outline of a paper or a proposal. You are given the author's scope
statement, the project kind and journal requirements, a standard structure for this kind of document,
sometimes guideline documents the author chose to share, and the CURRENT OUTLINE (each section has an id).

Propose changes to the current outline as a JSON object and nothing else:
{"items": [ {"id": "1", "action": "add|rename|move|keep|advice", "title": "...", "section": "...",
"newTitle": "...", "part": "...", "after": "...", "purpose": "...", "why": "..."} ]}

Rules:
- add: a NEW section. title = its title, part = the title of the part it belongs to ("" for the top level),
  after = the id of the section it follows in that part ("" = first in the part), purpose = one line.
- rename: section = the id of an existing section, title = its current title, newTitle = the better title.
- move: section = the id, title = its current title, part and after as for add.
- keep: section = the id, title = its current title: it is right as it is.
- advice: a general remark (title = a short heading, why = the advice). Use it for anything that is not one
  of the four actions above.
- Use only ids that appear in the CURRENT OUTLINE. Never invent an id.
- Never delete, merge or split sections: say so in an advice item instead. The author decides.
- Every item has a one-sentence "why" in plain words. At most 40 items. Prefer few, useful changes;
  mark sections that are fine as keep only when that helps.
- Follow the scope statement and the requirements; do not add sections the requirements rule out.
- Section titles are plain text: no slashes, no markdown."""


# -- what is sent ----------------------------------------------------------------------------------------

def _requirement_lines(profile) -> tuple[Item, ...]:
    rows = []
    for i, r in enumerate(profile.requirements):
        rows.append(Item(r.id, head=f"- {r.title}" + (f" [{r.group}]" if r.group else ""), priority=i))
    return tuple(rows)


def _standard_items(profile) -> tuple[Item, ...]:
    rows = []
    for n, (part, sections) in enumerate(outlines.standard_parts(profile)):
        lines = [f"- {s.title}" + (f": {s.purpose}" if s.purpose else "") for s in sections]
        rows.append(Item(part, "\n".join(lines), f"Part: {part}", n))
    return tuple(rows)


def _outline_text(outline: dict) -> str:
    if not outline["sections"]:
        return "CURRENT OUTLINE:\n(no sections yet)"
    lines = ["CURRENT OUTLINE (id | title | part | words | purpose):"]
    for s in outline["sections"]:
        lines.append(f"- {s['id']} | {s['title']} | {s['partTitle'] or '(top level)'} | {s['words']} words"
                     + (f" | {s['purpose']}" if s["purpose"] else ""))
    return "\n".join(lines)


def read_guideline_sources(project, names: list[str]) -> list:
    """The chosen guideline files' bytes (quick: run under the project lock). ``GuidelineError`` /
    ``FileNotFoundError`` for a name that is not a guideline file here."""
    names = _clean_names(names)
    return [guidelines.open_source(project, n) for n in names]


def _clean_names(names) -> list[str]:
    out: list[str] = []
    for n in names or []:
        n = str(n)
        if n not in out:
            out.append(n)
    if len(out) > MAX_GUIDELINES:
        raise ValueError(f"Choose at most {MAX_GUIDELINES} guideline documents for one outline request.")
    return out


def plan_outline(project, scope: str, instruction: str, guideline_names: list[str],
                 budget: Budget | None = None, outline: dict | None = None,
                 sources: list | None = None, model: str = "") -> tuple[str, SentReport]:
    """What the outline call sends, decided before any network call: (context text, ``SentReport``).
    Guideline text is extracted here (outside the project lock: pass *sources* read under it). Chosen
    guidelines are one capped, named list section; everything cut or dropped is in the report. Raises
    ``BudgetError`` when even the parts that cannot be dropped exceed the window, ``GuidelineError`` for a
    guideline that cannot be read."""
    names = _clean_names(guideline_names)
    outline = outline if outline is not None else outlines.current_outline(project)
    if budget is None:
        budget = Budget.for_model(model) if model else Budget.unbounded()
    profile = outlines.standard_profile(project)
    journal = project.research_profile()

    sections: list[Section] = [Section("Instructions and question", SYSTEM_PROMPT, visible=False)]
    kind_line = f"PROJECT KIND: {project.research_kind}"
    if journal is not None:
        kind_line += f"\nJOURNAL OR FUNDER: {journal.name}" + (f" ({journal.publisher})" if journal.publisher else "")
    else:
        kind_line += "\nJOURNAL OR FUNDER: none chosen (use the generic structure)"
    sections.append(Section("Project kind", kind_line))
    if scope and scope.strip():
        sections.append(Section("Scope statement", "SCOPE STATEMENT (the author's own words):\n" + scope.strip()))
    if instruction and instruction.strip():
        sections.append(Section("Author's request", "AUTHOR'S REQUEST:\n" + instruction.strip()))
    if journal is not None and journal.requirements:
        sections.append(Section("Journal requirements", priority=1, droppable=True,
                                items=_requirement_lines(journal), head="JOURNAL REQUIREMENTS:\n", sep="\n"))
    if profile is not None and profile.outline:
        sections.append(Section("Standard structure", priority=0, droppable=True,
                                items=_standard_items(profile),
                                head=f"STANDARD STRUCTURE ({profile.name}):\n"))
    if names:
        # one section per chosen document, so the report NAMES each one that was sent (a list section only
        # names what it dropped or trimmed); each is capped, and the budget drops whole documents if needed
        for i, src in enumerate(sources if sources is not None else read_guideline_sources(project, names)):
            text, truncated, note = guidelines.extract(project, src)
            sections.append(Section(
                f"Guideline: {src.path.name}", priority=2 + i, droppable=True,
                items=(Item(src.path.name, text.strip(), cap=GUIDELINE_ITEM_CHARS),),
                head=f"GUIDELINE DOCUMENT {src.path.name} (the author's reference, shared on purpose):\n"))
    sections.append(Section("Current outline", _outline_text(outline)))
    fitted, report = fit(sections, budget, FEATURE)
    preflight(report)
    return render(fitted), report


# -- the call --------------------------------------------------------------------------------------------

def suggest_outline(context: str, model: str, client=None, cancel=None, on_delta=None) -> str:
    """Network call: the model's reply (JSON text) for *context* (from ``plan_outline``). Streams when
    *on_delta* / *cancel* is given (a stopped call raises ``stream.Cancelled`` and returns nothing). Run
    the reply through ``parse_outline_items``: nothing here changes any file."""
    if client is None:
        from .client import make_client

        client = make_client(model)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": context}]
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, FEATURE, on_delta, cancel)
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=openrouter_extra_body(model=model))
        record_response(response, model, FEATURE)
        raw = response.choices[0].message.content or ""
    if not raw.strip():
        raise ValueError("the model returned no text")
    return raw


# -- reading the reply -----------------------------------------------------------------------------------

_FENCE = re.compile(r"```[a-zA-Z]*\n?")
_PATH_SEPS = re.compile(r"[\\/]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_ITEMS_OBJECT = re.compile(r'\{\s*"items"\s*:')


def _find_json(text: str):
    """The first JSON value in *text* that holds the items: an object with an "items" list, or a list of
    objects. Tolerates prose around it, code fences and trailing text. None when there is none."""
    text = _FENCE.sub("", text[:MAX_REPLY_CHARS])
    decoder = json.JSONDecoder()
    for m in itertools.islice(_ITEMS_OBJECT.finditer(text), MAX_JSON_STARTS):   # the usual shape first
        try:
            value, _ = decoder.raw_decode(text, m.start())
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return value["items"]
    starts = 0
    for m in re.finditer(r"[{\[]", text):
        starts += 1
        if starts > MAX_JSON_STARTS:
            break
        try:
            value, _ = decoder.raw_decode(text, m.start())
        except (ValueError, RecursionError):      # not JSON here (or nested absurdly deep): try the next start
            continue
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return value["items"]
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value) \
                and any("action" in v for v in value):
            return value
    return None


def clean_title(value, limit: int = TITLE_MAX) -> str:
    """A section title the structure functions can use: one line, no path separators, no heading marks."""
    text = _CONTROL.sub(" ", str(value if value is not None else ""))
    text = _PATH_SEPS.sub(" ", text).replace("[[", "").replace("]]", "")
    while True:                     # no comment or marker fragment may survive (even one made by removing another)
        before = text
        for frag in ("<!--", "-->", "{{", "}}"):
            text = text.replace(frag, "")
        if text == before:
            break
    text = " ".join(text.split()).lstrip("# ").strip()
    return text[:limit].strip()


def _line(value, limit: int) -> str:
    return " ".join(_CONTROL.sub(" ", str(value if value is not None else "")).split())[:limit].strip()


def _by_id(outline: dict) -> dict[str, dict]:
    return {s["id"]: s for s in outline["sections"]}


def clean_item(raw, outline: dict, taken_titles: set[str], index: int = 0) -> tuple[dict | None, str]:
    """Validate one item against *outline*. (item, "") when it is good; (None, reason) when it is dropped.
    *taken_titles* (case-folded) holds titles already claimed by earlier "add" / "rename" items of the same
    reply; a good add or rename adds its title. Delete-like or merge actions come back as advice items."""
    if not isinstance(raw, dict):
        return None, "It is not an item."
    action = str(raw.get("action") or "").strip().casefold()
    title = clean_title(raw.get("title"))
    why = _line(raw.get("why"), WHY_MAX)
    base = {"id": _line(raw.get("id"), 40), "action": action, "title": title, "section": "", "newTitle": "",
            "part": "", "after": "", "purpose": "", "why": why}
    sections = _by_id(outline)
    have = {s["title"].casefold() for s in outline["sections"]} | taken_titles

    if action in DELETE_LIKE:
        note = (f"The assistant suggested to {action} this, which Chisel never does for you: "
                "it is advice only.")
        sec = sections.get(str(raw.get("section") or ""))
        shown = (sec["title"] if sec else title) or "Outline"
        return {**base, "action": "advice", "title": shown, "why": f"{note} {why}".strip()}, ""
    if action not in ACTIONS:
        return None, f"Unknown action {action or '(none)'!r}."

    if action == "advice":
        if not (title or why):
            return None, "An advice item with no text."
        return {**base, "title": title or "Advice"}, ""

    if action == "add":
        if not title:
            return None, "An add item without a title."
        if title.casefold() in have:
            return None, f"There is already a section called {title}."
        part = clean_title(raw.get("part"))
        after = str(raw.get("after") or "").strip()
        reason = _after_problem(after, part, outline, sections, None)
        if reason:
            return None, reason
        taken_titles.add(title.casefold())
        return {**base, "part": part, "after": after, "purpose": _line(raw.get("purpose"), PURPOSE_MAX)}, ""

    sid = str(raw.get("section") or "").strip()
    sec = sections.get(sid)
    if sec is None:
        return None, f"Section {sid or '(none)'} is not in the outline."
    current = sec["title"]
    base.update(section=sid, title=current)
    if action == "keep":
        return base, ""
    if action == "rename":
        new = clean_title(raw.get("newTitle"))
        if not new:
            return None, f"A rename of {current} without a new title."
        if new.casefold() == current.casefold():
            return None, f"{current} already has that title."
        if new.casefold() in have:
            return None, f"There is already a section called {new}."
        taken_titles.add(new.casefold())
        return {**base, "newTitle": new}, ""
    # move
    part = clean_title(raw.get("part"))
    after = str(raw.get("after") or "").strip()
    reason = _after_problem(after, part, outline, sections, sid)
    if reason:
        return None, reason
    return {**base, "part": part, "after": after}, ""


def _after_problem(after: str, part: str, outline: dict, sections: dict, moving: str | None) -> str:
    """Why the placement is refused, or "": the section to follow must exist, be another section and lie in
    the named part (case-insensitive)."""
    if not after:
        return ""
    ref = sections.get(after)
    if ref is None:
        return f"It is to follow section {after}, which is not in the outline."
    if moving is not None and after == moving:
        return "A section cannot follow itself."
    if ref["partTitle"].casefold() != part.casefold():
        return f"It is to follow {ref['title']}, which is not in the part {part or '(top level)'}."
    return ""


def parse_outline_items(text: str, outline: dict) -> tuple[list[dict], list[dict]]:
    """(items, dropped): the model's reply as clean items for the review list, and what was dropped with the
    reason ({"id", "title", "reason"}) for the author to see. Never raises. Ids that do not exist, onto
    existing titles and unknown actions are dropped; delete-like actions become advice; titles are trimmed,
    capped and lose path separators; at most ``MAX_ITEMS`` items."""
    raw_items = _find_json(text or "")
    if raw_items is None:
        return [], [{"id": "", "title": "", "reason": "The reply could not be read as an outline."}]
    items: list[dict] = []
    dropped: list[dict] = []
    taken: set[str] = set()
    used_ids: set[str] = set()
    extra_dropped = 0
    for n, raw in enumerate(raw_items, 1):
        label = _line(raw.get("title") or raw.get("newTitle") or raw.get("section"), 60) \
            if isinstance(raw, dict) else ""
        if len(items) >= MAX_ITEMS:
            if len(dropped) < MAX_DROPPED:
                dropped.append({"id": str(n), "title": label,
                                "reason": f"Only the first {MAX_ITEMS} items are shown."})
            else:
                extra_dropped += 1
            continue
        try:
            item, reason = clean_item(raw, outline, taken, n)
        except Exception:                           # a hostile or odd reply must never break the list
            item, reason = None, "It could not be read."
        if item is None:
            if len(dropped) < MAX_DROPPED:
                dropped.append({"id": str(n), "title": label, "reason": reason})
            else:
                extra_dropped += 1
            continue
        iid = item["id"] if item["id"] and item["id"] not in used_ids else f"o{n}"
        while iid in used_ids:
            iid += "x"
        used_ids.add(iid)
        item["id"] = iid
        items.append(item)
    if extra_dropped:
        dropped.append({"id": "", "title": "", "reason": f"{extra_dropped} more items were dropped."})
    return items, dropped


__all__ = ["plan_outline", "suggest_outline", "parse_outline_items", "clean_item", "clean_title",
           "read_guideline_sources", "MAX_ITEMS", "FEATURE"]
