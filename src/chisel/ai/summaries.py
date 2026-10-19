"""Scene and part summaries by AI (SPEC "Summaries for long projects").

A generated summary is a PROPOSAL: ``summarize_scene`` returns it verified against the scene
(``core.summaries.verify``: a fact whose quote is not in the scene and a character who is not named
in it are dropped and listed), and the caller saves it only when the author accepts it. The
reply is plain JSON asked for in the prompt (no ``response_format``, never
``provider.require_parameters``: the model may lack structured outputs), parsed tolerantly.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..core import applog, scenemeta
from ..core import summaries as store
from ..core.entities import Entity
from . import relevance
from .budget import Budget, Item, Section, SentReport, fit, preflight
from .client import utility_extra_body
from .stream import stream_text
from .usage import LEDGER, record_response

FEATURE = "summary"
PART_FEATURE = "part summary"

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "characters": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "state": {"type": "string"}},
            "required": ["name", "state"]}},
        "facts": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["text", "quote"]}},
        "threads": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "characters", "facts", "threads"],
}

PART_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "characters": SUMMARY_SCHEMA["properties"]["characters"],
        "threads": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "characters", "threads"],
}

ASK_WORDS = 80          # what the scene prompt asks for; SUMMARY_WORDS (the cap) is only a safety net above it

SYSTEM_PROMPT = f"""\
You write a neutral record of one scene of a novel, for the author's own reference and for
other tools that need to remember what happened. Reply with one JSON object only, no other text:
{json.dumps(SUMMARY_SCHEMA)}

Rules:
- "summary": at most {ASK_WORDS} words, plain, past tense, what happens. No interpretation,
  no judgement, no theme, nothing that is not in the scene.
- "characters": each character who appears, named exactly as the scene writes the name, with their
  state at the END of the scene: where they are, what they know, their condition.
- "facts": things the scene establishes (who did what, who learned what, objects, places, times).
  Every fact MUST carry "quote": ONE unbroken passage copied exactly as written in the scene, with the
  scene's own punctuation. Never join two passages with "...", and never put a pronoun in place of a name.
  A fact you cannot quote is left out.
- "threads": questions or promises the scene leaves open. An empty list is fine.
- Never invent. If the scene is short or unclear, say less.
"""

PART_SYSTEM_PROMPT = f"""\
You write a neutral record of one part (a group of scenes) of a novel, from the summaries of its
scenes. Reply with one JSON object only, no other text:
{json.dumps(PART_SCHEMA)}

Rules:
- "summary": at most 150 words, plain, past tense, what happens across the part, in order.
  No interpretation and nothing that is not in the scene summaries.
- "characters": the characters who matter, with their state at the END of the part.
- "threads": questions or promises still open at the end of the part.
- Never invent.
"""


@dataclass(frozen=True)
class Proposal:
    """A generated scene summary, verified, waiting for the author. ``dropped`` is what verification removed."""
    summary: store.Summary
    dropped: tuple[store.Dropped, ...] = ()
    tolerant: int = 0       # facts kept only by the looser quote rule (for the report; never stored)
    trimmed: bool = False   # the reply was over the word cap and was cut (never stored; the review says so)


# -- planning (before any network call) -------------------------------------------------


def _roster(ranked: list[relevance.Ranked]) -> Section:
    """The names of the entities the scene is about, so the model spells them as the author does."""
    items = tuple(Item(r.entity.name, "", f"- {r.entity.name} ({r.entity.type})"
                       + (f", also written: {', '.join(r.entity.aliases)}" if r.entity.aliases else ""),
                       r.priority) for r in ranked if r.tier < relevance.TIER_REST)
    return Section("Known names", priority=0, droppable=True, items=items, head="KNOWN NAMES:\n", sep="\n")


def plan_summarize(scene_text: str, entities: list[Entity], budget: Budget) -> tuple[list[Entity], SentReport]:
    """What a scene summary sends, decided before any network call: the scene's prose and the names
    of the entities it is about (fitted into *budget*, the rest dropped and reported). Pass the
    returned entities to ``summarize_scene``. Raises ``BudgetError`` when the scene alone does not fit.
    *scene_text* must already be free of pending AI drafts (``drafts.strip_pending``)."""
    ranked = relevance.rank(scene_text, entities)
    sections = [
        Section("Instructions and question", SYSTEM_PROMPT, visible=False),
        _roster(ranked),
        Section("Scene", "SCENE:\n" + scenemeta.strip(scene_text)),
    ]
    fitted, report = fit(sections, budget, FEATURE)
    preflight(report)
    kept = {it.name for it in next(s for s in fitted if s.name == "Known names").items or ()}
    return [r.entity for r in ranked if r.entity.name in kept], report


def build_prompt(scene_text: str, entities: list[Entity]) -> str:
    names = _roster([relevance.Ranked(e, 0, i) for i, e in enumerate(entities)])
    roster = fit([names], Budget.unbounded())[0][0].text
    return (f"{roster}\n\n" if roster else "") + "SCENE:\n" + scenemeta.strip(scene_text)


def plan_summarize_part(title: str, scenes: list[tuple[str, store.Summary]],
                        budget: Budget) -> tuple[list[str], SentReport]:
    """What a part summary sends: the scene summaries of the part (*scenes*: (scene title, summary)),
    earliest first; ones that do not fit are dropped, latest first, and named in the report.
    Returns the titles kept and the report. Raises ``BudgetError`` when even the instructions do not fit."""
    items = tuple(Item(name, _scene_text(s), f"### {name}", i) for i, (name, s) in enumerate(scenes))
    sections = [Section("Instructions and question", PART_SYSTEM_PROMPT, visible=False),
                Section("Scene summaries", priority=0, droppable=True, items=items,
                        head=f"PART: {title}\n\n")]
    fitted, report = fit(sections, budget, PART_FEATURE)
    preflight(report)
    return [it.name for it in next(s for s in fitted if s.name == "Scene summaries").items or ()], report


def _scene_text(s: store.Summary) -> str:
    lines = [s.summary]
    if s.characters:
        lines.append("At the end: " + "; ".join(f"{c.name} - {c.state}" if c.state else c.name
                                                for c in s.characters))
    if s.threads:
        lines.append("Open: " + "; ".join(s.threads))
    return "\n".join(lines)


# -- reading the reply -----------------------------------------------------------------


def _json_object(raw: str) -> dict | None:
    """The first JSON object in *raw* (the model may wrap it in a code fence or a sentence)."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    for start in [m.start() for m in re.finditer(r"\{", raw)][:20]:
        try:
            data, _ = json.JSONDecoder().raw_decode(raw[start:])
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


_SENTENCE_END = re.compile("[.!?][\"'\u201d\u2019)\\]]*(?=\\s|$)")


def _clip(text: str, cap: int = store.SUMMARY_WORDS) -> tuple[str, bool]:
    """(the text, whether it was cut). Over *cap* words it is cut at the last sentence end that fits, so no
    sentence is left in half and no ellipsis is added; with no sentence end inside the cap, at the last word.
    The caller shows the flag (the prompt asks for fewer words, so this is a safety net)."""
    text = text.strip()
    words = text.split()
    if len(words) <= cap:
        return text, False
    head = " ".join(words[:cap])
    ends = [m.end() for m in _SENTENCE_END.finditer(head)]
    return (head[:ends[-1]] if ends else head.rstrip(",;:- ")), True


def parse_summary_flagged(raw: str) -> tuple[store.Summary | None, bool]:
    """``parse_summary`` and whether the summary text was over the word cap and cut."""
    data = _json_object(raw)
    if data is None:
        return None, False
    text, trimmed = _clip(str(data.get("summary") or ""))
    s = store.summary_from_dict({**data, "summary": text})
    return s, trimmed and s is not None


def parse_summary(raw: str) -> store.Summary | None:
    """The model's reply as a (not yet verified) Summary; None when there is no usable summary.
    Tolerant of a code fence, extra text, a missing list or a malformed item."""
    return parse_summary_flagged(raw)[0]


def parse_failure(raw: str) -> str:
    """Which step of reading *raw* failed (for the diagnostic log; no text of the reply)."""
    if not (raw or "").strip():
        return "empty reply"
    data = _json_object(raw)
    if data is None:
        return "no JSON object"
    return "no usable summary" if parse_summary(raw) is None else "none"


def parse_part_summary(raw: str) -> store.PartSummary | None:
    data = _json_object(raw)
    return store.part_from_dict(data) if data is not None else None


# -- network ---------------------------------------------------------------------------


def _ask(system: str, user: str, model: str, client, feature: str, on_delta, cancel
         ) -> tuple[str, float, dict]:
    """One call, streaming when *on_delta* / *cancel* is given. Returns (reply, cost in USD, info), info
    being the finish reason (unknown when streamed) and completion token count for the diagnostic log.
    Raises ``stream.Cancelled`` when stopped. The cost is the ledger's change, so it is only an
    estimate when two AI calls run at once."""
    if client is None:
        from .client import make_client

        client = make_client(model)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    before = LEDGER.session_total()
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, feature, on_delta, cancel, utility=True)
        reason = "unknown"
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=utility_extra_body(model=model))
        record_response(response, model, feature)
        raw = response.choices[0].message.content or ""
        reason = str(getattr(response.choices[0], "finish_reason", None) or "unknown")
    last = LEDGER.last()
    info = {"finish_reason": reason, "completion_tokens": last.completion_tokens if last else None}
    return raw, max(0.0, LEDGER.session_total() - before), info


def summarize_scene(scene_text: str, entities: list[Entity], model: str, client=None,
                    on_delta=None, cancel=None,
                    originals: dict[str, str] | None = None) -> Proposal:
    """Network call: propose a summary of one scene. *scene_text* is the file's text (details and
    pending AI drafts are removed here, and the summary is hashed from what is left); *entities* are the ones
    ``plan_summarize`` chose. The result is verified against the scene; nothing is saved.
    A reply with no usable summary is asked for once more (both costs are recorded and added up); the
    second failure raises ValueError. ``stream.Cancelled`` when stopped (never retried).
    Synchronous: run it in a worker."""
    prose = store.prose_of(scene_text, originals)
    prompt = build_prompt(prose, entities)
    cost, parsed, trimmed = 0.0, None, False
    for attempt in (1, 2):
        raw, spent, info = _ask(SYSTEM_PROMPT, prompt, model, client, FEATURE, on_delta, cancel)
        cost += spent
        parsed, trimmed = parse_summary_flagged(raw)
        if parsed is not None:
            break
        applog.log_exc(f"summary reply unusable (attempt {attempt}): step={parse_failure(raw)} "
                       f"finish_reason={info['finish_reason']} completion_tokens={info['completion_tokens']} "
                       f"reply_chars={len(raw or '')}", level=logging.WARNING)
    if parsed is None:
        raise ValueError("The model's reply did not contain a summary. Nothing was saved; try again.")
    parsed = store.Summary(store.hash_of(scene_text, originals), parsed.summary, parsed.characters,
                           parsed.facts, parsed.threads, model, store.now(), cost)
    clean, dropped, tolerant = store.verify_counted(parsed, scene_text, originals)
    return Proposal(clean, tuple(dropped), tolerant, trimmed)


def summarize_part(title: str, scenes: list[tuple[str, store.Summary]], model: str,
                   inputs: tuple[tuple[str, str], ...] = (), client=None,
                   on_delta=None, cancel=None) -> store.PartSummary:
    """Network call: propose a summary of a part from its scenes' summaries (*scenes*, as in
    ``plan_summarize_part``; pass the ones it kept). *inputs* is ``core.summaries.part_inputs`` so the
    part knows when it goes stale. Raises ValueError for an unusable reply."""
    body = "\n\n".join(f"### {name}\n{_scene_text(s)}" for name, s in scenes)
    raw, cost, _ = _ask(PART_SYSTEM_PROMPT, f"PART: {title}\n\n{body}", model, client, PART_FEATURE,
                     on_delta, cancel)
    parsed = parse_part_summary(raw)
    if parsed is None:
        raise ValueError("The model's reply did not contain a summary. Nothing was saved; try again.")
    text, trimmed = _clip(parsed.summary, store.PART_SUMMARY_WORDS)
    return store.PartSummary(text, parsed.characters, parsed.threads, tuple(inputs),
                             model, store.now(), cost, trimmed=trimmed)
