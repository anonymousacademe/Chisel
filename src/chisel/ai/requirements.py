"""AI-suggested requirements from guideline documents (plan: docs/dev/plan-research-waves-d-f.md, wave E).

The model reads the guideline documents the author ticked and proposes rows in the schema of the journal
profile requirements (``core/paper/custom_requirements``). This module never touches a file:
``plan_requirements`` decides what is sent (budget sections, one per guideline, named in the ``SentReport``)
before any network call, ``suggest_requirements`` returns the model's JSON text, and
``parse_requirement_rows`` validates every row exactly as a saved row is validated and sets ``verified``:
the app, never the model, checks that the quoted sentence really occurs in that guideline's text.
"""

from __future__ import annotations

import itertools
import json
import re

from ..core.paper import custom_requirements as cr
from ..core.paper import guidelines, journals
from .budget import Budget, Item, Section, SentReport, fit, preflight, render
from .client import openrouter_extra_body
from .stream import stream_text
from .usage import record_response

FEATURE = "requirements"
MAX_ITEMS = 40
MAX_DROPPED = 40
MAX_GUIDELINES = 8
GUIDELINE_ITEM_CHARS = 12_000       # per guideline document (trimmed and reported)
MIN_QUOTE_CHARS = 25                # a shorter quote is never verified
WHY_MAX = 400
MAX_REPLY_CHARS = 400_000
MAX_JSON_STARTS = 200

SYSTEM_PROMPT = """\
You turn the rules of a guideline document (a journal's instructions for authors, a funder's call) into
machine-checkable requirements for a research paper or proposal. Propose rows as a JSON object and nothing else:
{"items": [ {"id": "abstract-words", "group": "Abstract", "title": "Abstract is at most 250 words",
"kind": "check", "check": "section-words-max", "section": ["abstract"], "max": 250, "severity": "warn",
"source": "guide.pdf", "quote": "The abstract must not exceed 250 words.", "why": "The guide sets the limit."} ]}

Rules:
- Use only the check kinds listed under CHECK KINDS and only the parameters each one takes. If a rule cannot be
  checked by one of them, make it kind "advice" (a reminder, no check).
- source = the exact file name of the guideline document the rule comes from. quote = ONE sentence copied
  word for word from that document (at most 240 characters), the sentence the rule is based on. Never invent or
  paraphrase a quote; if you cannot quote it, leave the rule out.
- Every row has a one-sentence "why" in plain words. id = short lowercase words joined by hyphens.
- section = 1 to 6 short words that appear in the title of the section (lowercase, each at most 60 characters).
- Do not repeat rules the journal requirements below already have. At most 40 rows; prefer few, clear rules.
- severity is "warn" for a hard rule and "info" for a preference. Everything is plain text: no markdown."""

CHECK_KINDS_TEXT = """\
CHECK KINDS (kind "check"; use only these):
- section-present: a section whose title contains one of the section words exists and is not empty. Takes: section.
- section-words-max: that section has at most max words. Takes: section, max (whole number).
- section-no-citations: that section contains no citations. Takes: section.
- list-count: the items of that section's list number between min and max, and each item has at most
  item_chars_max characters. Takes: section, min and/or max, optional item_chars_max (for example keywords).
- last-section: that section is the last one of the document. Takes: section.
- objects-captioned: every figure (object "fig"), table ("tbl") or equation ("eq") has a caption. Takes: object.
- objects-referenced: every figure, table or equation is cited in the text. Takes: object.
- citations-resolved: every citation matches a source note. Takes nothing.
- sources-doi: every cited source has a DOI recorded. Takes nothing.
Kind "advice": a reminder with no check; leave check, section and the numbers out."""

EXAMPLE_ROWS = """\
EXAMPLE ROWS:
{"id": "keywords-count", "group": "Keywords", "title": "3 to 6 keywords, each at most 30 characters",
 "kind": "check", "check": "list-count", "section": ["keywords"], "min": 3, "max": 6, "item_chars_max": 30,
 "severity": "warn", "source": "guide.pdf", "quote": "Provide three to six keywords of at most 30 characters.",
 "why": "The guide limits the keyword list."}
{"id": "cover-letter", "group": "Submission", "title": "Prepare a cover letter", "kind": "advice",
 "severity": "info", "source": "guide.pdf", "quote": "Please include a cover letter with your submission.",
 "why": "It cannot be checked in the text, so it is a reminder."}"""


# -- what is sent ----------------------------------------------------------------------------------------

def _clean_names(names) -> list[str]:
    out: list[str] = []
    for n in names or []:
        n = str(n)
        if n not in out:
            out.append(n)
    if not out:
        raise ValueError("Choose at least one guideline document to read.")
    if len(out) > MAX_GUIDELINES:
        raise ValueError(f"Choose at most {MAX_GUIDELINES} guideline documents for one request.")
    return out


def read_guideline_sources(project, names: list[str]) -> list:
    """The chosen guideline files' bytes (quick: run under the project lock). ``GuidelineError`` /
    ``FileNotFoundError`` for a name that is not a guideline file here."""
    return [guidelines.open_source(project, n) for n in _clean_names(names)]


def load_texts(project, sources: list) -> dict[str, str]:
    """{file name: extracted text} of the sources (outside the project lock). ``GuidelineError`` when one
    cannot be read."""
    return {src.path.name: guidelines.extract(project, src)[0].strip() for src in sources}


def plan_requirements(project, instruction: str, guideline_names: list[str], model: str = "",
                      budget: Budget | None = None, sources: list | None = None,
                      texts: dict[str, str] | None = None) -> tuple[str, SentReport]:
    """What the request sends, decided before any network call: (context text, ``SentReport``). One section
    per chosen guideline named "Guideline: <file>" and capped (``GUIDELINE_ITEM_CHARS``); a cut or dropped
    document is in the report. Pass *texts* ({name: text}) to avoid extracting twice. ``BudgetError`` when even
    the parts that cannot be dropped exceed the window, ``GuidelineError`` for a document that cannot be read."""
    names = _clean_names(guideline_names)
    if budget is None:
        budget = Budget.for_model(model) if model else Budget.unbounded()
    if texts is None:
        texts = load_texts(project, sources if sources is not None else read_guideline_sources(project, names))
    journal = project.research_profile()

    sections: list[Section] = [Section("Instructions and question", SYSTEM_PROMPT, visible=False)]
    kind_line = f"PROJECT KIND: {project.research_kind}"
    if journal is not None:
        kind_line += f"\nJOURNAL OR FUNDER: {journal.name}" + (f" ({journal.publisher})" if journal.publisher else "")
    else:
        kind_line += "\nJOURNAL OR FUNDER: none chosen"
    sections.append(Section("Project kind", kind_line))
    sections.append(Section("Check kinds", CHECK_KINDS_TEXT + "\n\n" + EXAMPLE_ROWS))
    if instruction and instruction.strip():
        sections.append(Section("Author's request", "AUTHOR'S REQUEST:\n" + instruction.strip()))
    if journal is not None and journal.requirements:
        rows = tuple(Item(r.id, head=f"- {r.title}" + (f" [{r.group}]" if r.group else ""), priority=i)
                     for i, r in enumerate(journal.requirements))
        sections.append(Section("Journal requirements", priority=1, droppable=True, items=rows,
                                head="JOURNAL REQUIREMENTS (already checked; do not repeat):\n", sep="\n"))
    for i, name in enumerate(names):
        sections.append(Section(
            f"Guideline: {name}", priority=2 + i, droppable=True,
            items=(Item(name, texts.get(name, ""), cap=GUIDELINE_ITEM_CHARS),),
            head=f"GUIDELINE DOCUMENT {name} (the author's reference, shared on purpose):\n"))
    fitted, report = fit(sections, budget, FEATURE)
    preflight(report)
    return render(fitted), report


# -- the call --------------------------------------------------------------------------------------------

def suggest_requirements(context: str, model: str, client=None, cancel=None, on_delta=None) -> str:
    """Network call: the model's reply (JSON text) for *context* (from ``plan_requirements``). Streams when
    *on_delta* / *cancel* is given. Run the reply through ``parse_requirement_rows``: nothing here changes
    any file."""
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
_ITEMS_OBJECT = re.compile(r'\{\s*"items"\s*:')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_SLUG_BAD = re.compile(r"[^a-z0-9]+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
                         "—": "-", " ": " "})


def _find_json(text: str):
    text = _FENCE.sub("", text[:MAX_REPLY_CHARS])
    decoder = json.JSONDecoder()
    for m in itertools.islice(_ITEMS_OBJECT.finditer(text), MAX_JSON_STARTS):
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
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return value["items"]
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value) \
                and any("check" in v or "quote" in v for v in value):
            return value
    return None


def clean_text(value, limit: int) -> str:
    """One plain line: no control characters and no marker fragment (comments, expand marks, links)."""
    text = _CONTROL.sub(" ", str(value if value is not None else ""))
    while True:                     # a fragment made by removing another must not survive either
        before = text
        for frag in ("<!--", "-->", "{{", "}}", "[[", "]]"):
            text = text.replace(frag, "")
        if text == before:
            break
    return " ".join(text.split())[:limit].strip()


def normalise(text: str) -> str:
    """Whitespace collapsed, case folded, typographic quotes and dashes straightened: how a quote is matched."""
    return " ".join(str(text).translate(_QUOTES).casefold().split())


def quote_in(quote: str, text: str) -> bool:
    q = normalise(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in normalise(text)


def _slug(value: str) -> str:
    return _SLUG_BAD.sub("-", value.casefold()).strip("-")[:48].strip("-")


def _number(value):
    """A whole number from an int, an integral float or a digit string; anything else is returned as is."""
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        return int(value)
    return value


def _clean_row(raw, texts: dict[str, str], taken: set[str]) -> tuple[dict | None, str]:
    if not isinstance(raw, dict):
        return None, "It is not a row."
    candidate = {k: raw.get(k) for k in cr.KEYS}
    for key in ("min", "max", "item_chars_max"):
        candidate[key] = _number(candidate[key])
    for key in ("title", "group"):
        candidate[key] = clean_text(candidate[key], 10_000)
    candidate["kind"] = str(candidate["kind"] or ("check" if candidate["check"] else "advice")).strip().casefold()
    candidate["check"] = str(candidate["check"] or "").strip()
    if isinstance(candidate["section"], list):
        candidate["section"] = [clean_text(p, 10_000) for p in candidate["section"] if isinstance(p, (str, int))]
    candidate["severity"] = str(candidate["severity"] or "warn").strip().casefold()
    candidate["source"] = clean_text(candidate["source"], 10_000)
    candidate["quote"] = clean_text(candidate["quote"], cr.QUOTE_MAX)
    if candidate["kind"] == "advice":
        candidate["check"] = ""
    # the id: the model's when it is plain and free, else made from the title
    rid = str(raw.get("id") or "").strip().casefold()
    if not journals.is_plain_id(rid) or rid in taken:
        base = _slug(str(raw.get("id") or "")) or _slug(candidate["title"]) or "requirement"
        rid = base
        n = 2
        while rid in taken or not journals.is_plain_id(rid):
            rid = f"{base}-{n}"[:64]
            n += 1
    candidate["id"] = rid
    try:
        row = cr.validate_row(candidate)
    except ValueError as exc:
        return None, str(exc)
    source = row.get("source", "")
    quote = row.get("quote", "")
    if source not in texts:                  # the model named no (or another) file: find where the quote is
        hits = [n for n, t in texts.items() if quote and quote_in(quote, t)]
        if len(hits) == 1:
            source = hits[0]
        elif len(texts) == 1:
            source = next(iter(texts))
        else:
            source = ""
    verified = bool(source and quote and quote_in(quote, texts.get(source, "")))
    row["source"] = source
    row["quote"] = quote
    taken.add(rid)
    item = {
        "id": row["id"], "group": row["group"], "title": row["title"], "kind": row["kind"],
        "check": row.get("check", ""), "section": list(row.get("section", [])),
        "min": row.get("min"), "max": row.get("max"), "item_chars_max": row.get("item_chars_max"),
        "object": row.get("object", ""), "severity": row["severity"], "source": source, "quote": quote,
        "why": clean_text(raw.get("why"), WHY_MAX), "verified": verified}
    return item, ""


def parse_requirement_rows(text: str, guideline_texts: dict[str, str],
                           taken_ids=()) -> tuple[list[dict], list[dict]]:
    """(items, dropped): the reply as clean items for the review list, and the rows that were dropped with a
    reason ({"id", "title", "reason"}). Never raises. Every row passes ``custom_requirements.validate_row``
    (an invented check kind, a number out of range, too many section words: dropped with the reason); ids
    are made unique (also against *taken_ids*); ``verified`` is true only when the quote (25 characters or
    more) occurs in the text of the row's guideline after normalising whitespace and case. At most
    ``MAX_ITEMS`` items."""
    raw_items = _find_json(text or "")
    if raw_items is None:
        return [], [{"id": "", "title": "", "reason": "The reply could not be read as a list of requirements."}]
    items: list[dict] = []
    dropped: list[dict] = []
    taken = {str(t) for t in taken_ids}
    extra = 0
    for n, raw in enumerate(raw_items, 1):
        label = clean_text(raw.get("title") or raw.get("id"), 60) if isinstance(raw, dict) else ""
        reason = ""
        item = None
        if len(items) >= MAX_ITEMS:
            reason = f"Only the first {MAX_ITEMS} rows are shown."
        else:
            try:
                item, reason = _clean_row(raw, guideline_texts, taken)
            except Exception:                       # a hostile or odd reply must never break the list
                item, reason = None, "It could not be read."
        if item is None:
            if len(dropped) < MAX_DROPPED:
                dropped.append({"id": str(n), "title": label, "reason": reason})
            else:
                extra += 1
            continue
        items.append(item)
    if extra:
        dropped.append({"id": "", "title": "", "reason": f"{extra} more rows were dropped."})
    return items, dropped


__all__ = ["plan_requirements", "suggest_requirements", "parse_requirement_rows", "read_guideline_sources",
           "load_texts", "quote_in", "normalise", "MAX_ITEMS", "FEATURE"]
