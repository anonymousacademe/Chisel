"""Context budget: how much of the story an AI request may carry, and a report
of what was actually sent (SPEC "Context budget and the sent report").

Pure Python, no network. Every AI context (continuity, canon proposals, the
alias finder, draft / expand / rewrite, the assistant, Brainstorm, Ask-my-notebook)
is assembled as a list of ``Section`` objects and passed through ``fit``:

- sections that are not ``droppable`` (the scene, the question, attachments, the
  subject note) are always kept;
- droppable sections are added in ``priority`` order (lower number = more
  important); a list section (``items``: one canon block per entity, ...) is filled
  item by item, and a single item is trimmed last, at a sentence / line / word
  boundary;
- the result is the fitted sections plus a ``SentReport``: per section what was
  sent, dropped (by name) and trimmed (by name), and the estimated size against the
  model's window. Nothing is dropped or trimmed without appearing in the report;
  never add a silent ``continue`` or ``[:N]`` to a context builder.

Token counts are ESTIMATES (characters / 4); there is no tokenizer here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

CHARS_PER_TOKEN = 4          # the estimate: ~4 characters of English prose per token
# Window assumed when the model's real context length is unknown (the catalogue the
# model picker fetched is not cached, or the model is not in it). Deliberately
# conservative: a request that fits 32k tokens fits nearly every model; a larger known
# window is used as soon as the catalogue has been seen.
DEFAULT_WINDOW = 32_000
DEFAULT_RESERVE = 4_000      # tokens kept free for the model's reply
MIN_WINDOW, MAX_WINDOW = 2_000, 10_000_000
SETTING = "context_window"   # user setting: tokens, for models the catalogue does not know
MIN_ITEM_CHARS = 200         # a trimmed item must keep at least this much, else it is dropped
SECTION_SEP = "\n\n"


class BudgetError(ValueError):
    """The request cannot fit the model's window even without the droppable parts.
    The message tells the author what to do; it is shown as is."""


def estimate_tokens(text: str | None) -> int:
    """Estimated token count of *text*: ``ceil(len / 4)``. A heuristic, not a tokenizer."""
    return -(-len(text) // CHARS_PER_TOKEN) if text else 0


# -- windows ------------------------------------------------------------------------


def validate_window(value) -> int:
    """*value* as a window size in tokens. ValueError unless it is a whole number
    (an int, or a string of digits) between MIN_WINDOW and MAX_WINDOW."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("the context window must be a whole number of tokens")
    try:
        number = int(str(value).strip().replace(",", "").replace("_", ""))
    except ValueError:
        raise ValueError("the context window must be a whole number of tokens") from None
    if not MIN_WINDOW <= number <= MAX_WINDOW:
        raise ValueError(f"the context window must be between {MIN_WINDOW:,} and {MAX_WINDOW:,} tokens")
    return number


def window_for(model_id: str, catalogue=None, settings: Mapping | None = None) -> int:
    """The context window (tokens) to plan for with *model_id*.

    Order: the ``context_window`` setting (a valid override, for local models) >
    the model's ``context_length`` in *catalogue* (an iterable of ``ModelInfo`` or a
    mapping id -> length; by default the catalogue the model picker already fetched,
    see ``client.cached_context_length`` - never fetched here) > ``DEFAULT_WINDOW``.
    An invalid stored override is ignored."""
    if settings is None:
        from ..core import settings as user_settings

        settings = user_settings.load_settings()
    override = settings.get(SETTING)
    if override not in (None, ""):
        try:
            return validate_window(override)
        except ValueError:
            pass
    known = None
    if catalogue is None:
        from .client import cached_context_length

        known = cached_context_length(model_id)
    elif isinstance(catalogue, Mapping):
        known = catalogue.get(model_id)
    else:
        known = next((m.context_length for m in catalogue if m.id == model_id), None)
    try:
        known = int(known) if known is not None and not isinstance(known, bool) else None
    except (TypeError, ValueError):
        known = None
    return known if known is not None and known >= MIN_WINDOW else DEFAULT_WINDOW


@dataclass(frozen=True)
class Budget:
    window_tokens: int
    output_reserve: int = DEFAULT_RESERVE

    @property
    def available(self) -> int:
        """Tokens the request itself may use."""
        return max(0, self.window_tokens - self.output_reserve)

    @classmethod
    def for_model(cls, model_id: str, catalogue=None, settings: Mapping | None = None,
                  reserve: int = DEFAULT_RESERVE) -> "Budget":
        return cls(window_for(model_id, catalogue, settings), reserve)

    @classmethod
    def unbounded(cls) -> "Budget":
        """No window: only the fixed per-item caps apply (the pre-budget behaviour)."""
        return cls(10 ** 9, 0)


# -- text trimming ------------------------------------------------------------------

_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*\s")


def trim(text: str, limit: int) -> str:
    """*text* cut to at most *limit* characters. The cut is at a line or sentence end
    (else a word end) and marked with an ellipsis, so a word is never split; only text
    with no such boundary in its second half (one very long word) is cut hard."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    room = limit - 1                        # one character for the ellipsis
    head = text[:room]
    cut = max(head.rfind("\n"), max((m.end() - 1 for m in _SENTENCE_END.finditer(head)), default=-1))
    if cut < room // 2:
        if text[room].isspace():
            cut = room
        else:
            cut = max(cut, max(head.rfind(" "), head.rfind("\t")))
    if cut < room // 2:
        return text[:limit]
    return text[:cut].rstrip() + "…"


# -- sections -----------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One entry of a list section (an entity's canon block, a scene title...).
    ``cap``: a fixed limit on the body in characters (trimmed and reported)."""

    name: str
    body: str = ""
    head: str = ""
    priority: int = 0
    cap: int | None = None
    lead: str = ""      # printed before a non-empty body
    empty: str = ""     # printed after the head when there is no body

    def render(self, body: str | None = None) -> str:
        body = self.body if body is None else body
        if body:
            return f"{self.head}\n{self.lead}{body}" if self.head else f"{self.lead}{body}"
        if self.empty:
            return f"{self.head}\n{self.empty}" if self.head else self.empty
        return self.head


@dataclass(frozen=True)
class Section:
    """A part of an AI request. A plain section is *text*; a list section has *items*
    (then ``head`` + the items joined by ``sep`` is its text). ``visible=False`` counts
    toward the size but is not part of the rendered context (system prompt, question,
    history: they are sent in other message parts)."""

    name: str
    text: str = ""
    priority: int = 0
    droppable: bool = False
    items: tuple[Item, ...] | None = None
    head: str = ""
    sep: str = "\n\n"
    group_cap: int | None = None          # most body characters of the items together
    max_priority: int | None = None       # items with a larger priority are not sent at all
    visible: bool = True


def render(sections: Iterable[Section]) -> str:
    """The context text of fitted sections."""
    return SECTION_SEP.join(s.text for s in sections if s.visible and s.text)


# -- the report ---------------------------------------------------------------------


@dataclass(frozen=True)
class SectionReport:
    name: str
    chars: int
    est_tokens: int
    items_total: int = 0
    items_sent: int = 0
    items_dropped: tuple[str, ...] = ()
    truncated: tuple[str, ...] = ()
    omitted: bool = False
    droppable: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "chars": self.chars, "estTokens": self.est_tokens,
                "itemsTotal": self.items_total, "itemsSent": self.items_sent,
                "itemsDropped": list(self.items_dropped), "truncated": list(self.truncated),
                "omitted": self.omitted}


def fmt_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    value = n / 1_000_000 if n >= 1_000_000 else n / 1000
    text = f"{value:.1f}".removesuffix(".0")
    return text + ("M" if n >= 1_000_000 else "k")


@dataclass(frozen=True)
class SentReport:
    """What one AI request carried (an estimate; see the module docstring)."""

    feature: str
    sections: tuple[SectionReport, ...]
    est_tokens: int
    window: int
    reserve: int
    over_budget: bool = False
    attached: tuple[dict, ...] = ()

    @property
    def dropped(self) -> tuple[str, ...]:
        return tuple(n for s in self.sections for n in s.items_dropped)

    @property
    def truncated(self) -> tuple[str, ...]:
        return tuple(n for s in self.sections for n in s.truncated)

    @property
    def trimmed(self) -> bool:
        return bool(self.dropped or self.truncated or self.over_budget)

    def to_dict(self) -> dict:
        return {"feature": self.feature, "estTokens": self.est_tokens, "window": self.window,
                "reserve": self.reserve, "overBudget": self.over_budget, "trimmed": self.trimmed,
                "sections": [s.to_dict() for s in self.sections],
                "attached": [dict(a) for a in self.attached]}

    def summary(self) -> str:
        """One line for a status bar: 'sent ~3.2k tokens of 200k; 2 dropped'."""
        text = f"sent ~{fmt_tokens(self.est_tokens)} tokens of {fmt_tokens(self.window)}"
        if self.dropped:
            text += f"; {len(self.dropped)} dropped"
        if self.truncated:
            text += f"; {len(self.truncated)} trimmed"
        return text


def merge_attached(report: SentReport, rows: list[dict]) -> SentReport:
    """Fold the attachments report (core.attach.build) into *report*: its
    "Attachments" section gets the per-item counts and the rows are kept as ``attached``."""
    rows = [dict(r) for r in rows or []]
    if not rows:
        return report
    dropped = tuple(str(r.get("title") or r.get("id")) for r in rows if r.get("skipped"))
    cut = tuple(str(r.get("title") or r.get("id")) for r in rows if r.get("truncated"))
    mine = SectionReport("Attachments", 0, 0, len(rows), len(rows) - len(dropped), dropped, cut,
                         droppable=False)
    sections, found = [], False
    for s in report.sections:
        if s.name == "Attachments":
            found = True
            s = replace(s, items_total=mine.items_total, items_sent=mine.items_sent,
                        items_dropped=dropped, truncated=cut)
        sections.append(s)
    if not found:
        sections.append(mine)
    return replace(report, sections=tuple(sections), attached=tuple(rows))


def preflight(report: SentReport) -> SentReport:
    """Raise ``BudgetError`` (before any network call) when even the parts that cannot be
    dropped exceed the window; otherwise return *report*."""
    if not report.over_budget:
        return report
    fixed = sorted((s for s in report.sections if not s.droppable and not s.omitted),
                   key=lambda s: -s.est_tokens)
    biggest = ", ".join(f"{s.name} (~{fmt_tokens(s.est_tokens)})" for s in fixed[:3])
    advice = ["choose a model with a bigger context window"]
    names = " ".join(s.name.lower() for s in fixed)
    if any(w in names for w in ("scene", "selection", "passage")):
        advice.append("shorten the scene or the selection")
    if "attach" in names:
        advice.append("remove attachments")
    if "about" in names:
        advice.append("turn off the About chip")
    to_do = advice[0] if len(advice) == 1 else (
        ", ".join(advice[:-1]) + (", or " if len(advice) > 2 else " or ") + advice[-1])
    raise BudgetError(
        f"This request is too large for the model's context window: about "
        f"{fmt_tokens(report.est_tokens)} tokens are needed, and {fmt_tokens(report.window)} "
        f"minus {fmt_tokens(report.reserve)} kept for the reply is available. "
        f"The largest parts are {biggest or 'the request itself'}. "
        f"To fix it: {to_do}. "
        + (f"(The window is assumed to be {fmt_tokens(DEFAULT_WINDOW)} because this model's real size is "
           "not known yet: open the model list in Settings once and it is remembered.) "
           if report.window == DEFAULT_WINDOW else "")
        + "Nothing was sent.")


# -- fitting ------------------------------------------------------------------------


@dataclass
class _Slot:
    index: int
    section: Section
    kept: dict[int, str] = field(default_factory=dict)      # item index -> rendered text
    static_dropped: set[int] = field(default_factory=set)
    dropped: set[int] = field(default_factory=set)
    truncated: set[int] = field(default_factory=set)
    bodies: dict[int, str] = field(default_factory=dict)    # after fixed caps
    omitted: bool = False

    @property
    def is_list(self) -> bool:
        return self.section.items is not None

    def eligible(self) -> list[int]:
        items = self.section.items or ()
        return sorted((i for i in range(len(items)) if i not in self.static_dropped),
                      key=lambda i: (items[i].priority, i))

    def prepare(self) -> None:
        """Fixed caps (item cap, group cap, max priority) that do not depend on the window."""
        if not self.is_list:
            return
        items, sec = self.section.items, self.section
        for i, it in enumerate(items):
            if sec.max_priority is not None and it.priority > sec.max_priority:
                self.static_dropped.add(i)
                continue
            body = it.body
            if it.cap is not None and len(body) > it.cap:
                body = trim(body, it.cap)
                self.truncated.add(i)
            self.bodies[i] = body
        if sec.group_cap is not None:
            used = 0
            for i in self.eligible():
                size = len(self.bodies[i])
                if used + size > sec.group_cap:
                    self.static_dropped.add(i)
                    self.truncated.discard(i)
                else:
                    used += size

    def text_of(self, i: int) -> str:
        return self.section.items[i].render(self.bodies[i])

    def rendered(self) -> str:
        sec = self.section
        if self.omitted:
            return ""
        if not self.is_list:
            return sec.text
        if not self.kept:
            return ""
        return sec.head + sec.sep.join(self.kept[i] for i in sorted(self.kept))

    def cost(self) -> int:
        text = self.rendered()
        return len(text) + (len(SECTION_SEP) if text and self.section.visible else 0)

    def commit_all(self) -> None:
        if self.is_list:
            self.kept = {i: self.text_of(i) for i in self.eligible()}

    def fill(self, room: int) -> None:
        """Add this droppable section's content, best first, into *room* characters."""
        sec = self.section
        if not self.is_list:
            if sec.text and len(sec.text) + (len(SECTION_SEP) if sec.visible else 0) > room:
                self.omitted = True
            return
        left = room - len(SECTION_SEP) * sec.visible - len(sec.head)
        order = self.eligible()
        for n, i in enumerate(order):
            rendered = self.text_of(i)
            gap = len(sec.sep) if self.kept else 0
            if len(rendered) + gap <= left:
                self.kept[i] = rendered
                left -= len(rendered) + gap
                continue
            trimmed = self._trim_last(i, left - gap)
            self.dropped.update(order[n + 1:] if trimmed else order[n:])
            break

    def _trim_last(self, i: int, left: int) -> bool:
        """The last resort: keep item *i* trimmed to the *left* characters that remain."""
        item, body = self.section.items[i], self.bodies[i]
        space = left - (len(item.render("x")) - 1)
        if not body or space < MIN_ITEM_CHARS:
            return False
        cut = trim(body, space)
        if cut == body:
            return False
        self.bodies[i] = cut
        self.truncated.add(i)
        self.kept[i] = item.render(cut)
        return True

    def report(self) -> SectionReport | None:
        sec = self.section
        if not self.is_list:
            if not sec.text:
                return None
            sent = not self.omitted
            return SectionReport(sec.name, len(sec.text) if sent else 0,
                                 estimate_tokens(sec.text) if sent else 0, 1, int(sent),
                                 () if sent else (sec.name,), (), self.omitted, sec.droppable)
        items = sec.items
        gone = self.static_dropped | self.dropped
        text = self.rendered()
        return SectionReport(
            sec.name, len(text), estimate_tokens(text), len(items), len(self.kept),
            tuple(items[i].name for i in sorted(gone)),
            tuple(items[i].name for i in sorted(self.truncated) if i in self.kept),
            not self.kept and bool(items), sec.droppable)


def fit(sections: Iterable[Section], budget: Budget, feature: str = "") -> tuple[list[Section], SentReport]:
    """Fit *sections* into *budget*; returns the fitted sections (``text`` is what is sent,
    use ``render``; a list section's ``items`` are the ones kept, with their final, possibly
    trimmed, body) and the ``SentReport``. Deterministic: the same
    input always gives the same output. Does not raise when the fixed parts are too
    big - the report says ``over_budget`` and ``preflight`` raises."""
    slots = [_Slot(i, s) for i, s in enumerate(sections)]
    room = budget.available * CHARS_PER_TOKEN
    used = 0
    for slot in slots:
        slot.prepare()
        if not slot.section.droppable:
            slot.commit_all()
            used += slot.cost()
    over = used > room
    for slot in sorted((s for s in slots if s.section.droppable),
                       key=lambda s: (s.section.priority, s.index)):
        slot.fill(room - used)
        used += slot.cost()
    fitted: list[Section] = []
    reports: list[SectionReport] = []
    for slot in slots:
        sec = slot.section
        text = slot.rendered()
        kept = (tuple(replace(sec.items[i], body=slot.bodies[i]) for i in sorted(slot.kept))
                if slot.is_list else None)
        fitted.append(Section(sec.name, text, sec.priority, sec.droppable, items=kept,
                              visible=sec.visible))
        row = slot.report()
        if row is not None:
            reports.append(row)
    report = SentReport(feature, tuple(reports), -(-used // CHARS_PER_TOKEN), budget.window_tokens,
                        budget.output_reserve, over)
    return fitted, report


def fit_text(sections: Iterable[Section], budget: Budget, feature: str = "") -> tuple[str, SentReport]:
    """``fit`` + ``preflight`` + ``render``: the context text, or BudgetError."""
    fitted, report = fit(sections, budget, feature)
    preflight(report)
    return render(fitted), report
