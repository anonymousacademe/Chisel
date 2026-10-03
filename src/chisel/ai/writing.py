"""AI drafting: draft at the cursor, expand a {{expand: …}} marker, rewrite a
selection (SPEC §7 M4).

Plain-text generation with the *writing* model. Nothing here edits a scene:
the caller wraps the result as a pending draft (core.drafts) that the author
must accept.
"""

from __future__ import annotations

import re

from ..core import drafts, research as research_notes, scenemeta
from ..core.entities import Entity
from . import relevance
from .budget import Budget, Item, Section, SentReport, fit, fit_text, render
from .client import usage_extra_body
from .stream import stream_text
from .usage import record_response

CURSOR = "<<CURSOR>>"
CONTEXT_WORDS = 500  # each side of the cursor
ENTITY_CHARS = 1200
ENTITY_TOTAL_CHARS = 6000
MODES = ("draft", "expand", "rewrite")

SYSTEM_PROMPT = """\
You are a ghostwriter helping a novelist. You write ONLY the requested prose.

Rules:
- Match the author's style guide exactly (voice, tense, rhythm, diction).
- Stay consistent with the story context and the character/place notes given.
- Output the prose and nothing else: no commentary, no preamble, no titles,
  no quotation marks around the whole thing, no Markdown code fences.
- Never write HTML comments or the text "<!--".
- Continue naturally at <<CURSOR>>; do not repeat the surrounding text.
- When passages of the author's own prose are given, they are the voice to
  match: imitate their sentence rhythm, paragraph shape, diction and
  punctuation habits. Never copy their events, images or sentences.
"""


def _tail_words(s: str, n: int) -> str:
    words = list(re.finditer(r"\S+", s))
    if len(words) <= n:
        return s
    return "…" + s[words[-n].start():]


def _head_words(s: str, n: int) -> str:
    words = list(re.finditer(r"\S+", s))
    if len(words) <= n:
        return s
    return s[:words[n - 1].end()] + "…"


def _marked_scene(scene_text: str, cursor_offset: int,
                  span: tuple[int, int] | None,
                  originals: dict[str, str] | None = None) -> str:
    """The scene with the CURSOR sentinel placed and pending AI drafts
    removed (unaccepted AI text is not context). *span*, if given, is text
    that is being replaced (a selection or an expand marker): it is cut out
    and the sentinel stands in its place."""
    head = scenemeta.body_offset(scene_text)  # the details block is not prose
    if head:
        scene_text = scene_text[head:]
        cursor_offset = max(0, cursor_offset - head)
        if span is not None:
            span = (max(0, span[0] - head), max(0, span[1] - head))
    if span is not None:
        start, end = span
        text = scene_text[:start] + CURSOR + scene_text[end:]
        cursor = start
    else:
        cursor = max(0, min(cursor_offset, len(scene_text)))
        for p in drafts.find_pending(scene_text):
            if p.start < cursor < p.end:
                cursor = p.start  # cursor inside a draft: mark just before it
        text = scene_text[:cursor] + CURSOR + scene_text[cursor:]
    # the sentinel never lands inside a pending span, so stripping is safe
    return drafts.strip_pending(text, originals)


def build_context_sections(
    scene_text: str,
    cursor_offset: int,
    entities: list[Entity],
    canon_by_name: dict[str, str],
    style_md: str | None,
    span: tuple[int, int] | None = None,
    originals: dict[str, str] | None = None,
    voice_samples: list[tuple[str, str]] | None = None,
) -> list[Section]:
    """The parts of a draft / chat context (see ``build_context``), for ``budget.fit``:
    the scene window and its details are always kept; the style guide, the entity notes
    (best first: named in the prose, then the POV / place) and the voice samples are droppable."""
    marked = _marked_scene(scene_text, cursor_offset, span, originals)
    before, _, after = marked.partition(CURSOR)
    window = _tail_words(before, CONTEXT_WORDS) + CURSOR + _head_words(
        after, CONTEXT_WORDS)

    sections: list[Section] = []
    if style_md and style_md.strip():
        sections.append(Section("Style guide", "STYLE GUIDE:\n" + style_md.strip(),
                                priority=0, droppable=True))

    ranked = relevance.in_scene(
        relevance.rank(drafts.strip_pending(scene_text, originals), entities))
    notes: list[Item] = []
    for r in ranked:
        entity = r.entity
        note = (canon_by_name.get(entity.name) or entity.body or "").strip()
        if note:
            notes.append(Item(entity.name, note, f"### {entity.name} ({entity.type})",
                              r.priority, ENTITY_CHARS))
    if notes:
        sections.append(Section("Characters and places", priority=1, droppable=True,
                                items=tuple(notes), head="CHARACTERS AND PLACES:\n",
                                group_cap=ENTITY_TOTAL_CHARS))

    if voice_samples:
        sections.append(Section(
            "Your own prose", priority=2, droppable=True,
            items=tuple(Item(title or f"passage {i}", para, priority=i)
                        for i, (title, para) in enumerate(voice_samples, 1)),
            head="THE AUTHOR'S OWN PROSE (match this voice; do not reuse its content):\n"))

    details = scenemeta.header(scene_text)
    if details:
        sections.append(Section(
            "Scene details", "SCENE DETAILS (the author's plan for this scene):\n" + details))

    sections.append(Section("Scene", "SCENE (the new text goes at " + CURSOR + "):\n" + window))
    return sections


def build_context(
    scene_text: str,
    cursor_offset: int,
    entities: list[Entity],
    canon_by_name: dict[str, str],
    style_md: str | None,
    span: tuple[int, int] | None = None,
    originals: dict[str, str] | None = None,
    voice_samples: list[tuple[str, str]] | None = None,
) -> str:
    """The prompt context: full style guide, the author's own prose as voice
    examples (*voice_samples*, from core.style.select_voice_samples), ±500 words around the cursor
    (cut at word boundaries, CURSOR sentinel at the insertion point), and
    notes/canon of the entities the scene mentions (1200 chars each, 6000
    total). Pending AI drafts are stripped (*originals*: the scene's draft
    sidecar, so replaced text counts as the accepted prose). Only the fixed caps
    apply here; what is sent to a model goes through ``fit_context`` (the window
    limit and the report of what was left out) using ``build_context_sections``."""
    return render(fit(build_context_sections(
        scene_text, cursor_offset, entities, canon_by_name, style_md, span, originals,
        voice_samples), Budget.unbounded())[0])


def instructions(system: str, *parts: str) -> Section:
    """The part of a request that is not context (system prompt, task, question,
    history): counted in the size, never dropped, not part of the rendered context."""
    return Section("Instructions and question", "\n\n".join([system, *parts]), visible=False)


def fit_context(sections: list[Section], model: str, feature: str,
                budget: Budget | None = None) -> tuple[str, SentReport]:
    """Fit *sections* into *model*'s window (``budget.window_for``): the context text and
    the report of what it carries. Raises ``budget.BudgetError`` (before any network call)
    when even the parts that cannot be dropped do not fit."""
    return fit_text(sections, budget or Budget.for_model(model), feature)


_FENCE_RE = re.compile(r"\A\s*```[^\n]*\n(.*?)\n?```\s*\Z", re.DOTALL)
_LABEL_RE = re.compile(
    r"\A\s*(?:here(?:'s| is| are)\b[^\n:]{0,80}|draft|rewrite|rewritten"
    r"(?: text| passage| version)?|revised(?: text| passage)?|output|result|"
    r"paragraph|expansion)\s*:\s*\n?",
    re.IGNORECASE,
)
_QUOTE_PAIRS = {'"': '"', "“": "”", "'": "'", "‘": "’"}


def clean_output(raw: str, selection: str | None = None) -> str:
    """Strip what chat models wrap around prose: code fences, a leading label
    ("Here's the paragraph:"), and one pair of quotes around the whole reply
    (only for multi-sentence text with no inner quotes, and never when the
    text being rewritten was itself quoted — a single line of dialogue is
    legitimate output). HTML comment openers are removed outright.
    Raises ValueError if nothing is left."""
    text = (raw or "").strip()
    fence = _FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()
    text = _LABEL_RE.sub("", text, count=1).strip()
    if len(text) >= 2 and text[0] in _QUOTE_PAIRS and text[-1] == _QUOTE_PAIRS[text[0]]:
        inner = text[1:-1]
        multi_sentence = re.search(r"[.!?…][\"”’']?\s+\S", inner) is not None
        no_inner_quotes = not any(q in inner for q in '"“”')
        selection_quoted = bool(selection) and selection.lstrip()[:1] in _QUOTE_PAIRS
        if multi_sentence and no_inner_quotes and not selection_quoted:
            text = inner.strip()
    text = text.replace("<!--", "").strip()
    if not text:
        raise ValueError("the model returned no text")
    return text


def _user_prompt(mode: str, instruction: str, context: str,
                 selection: str | None) -> str:
    if mode == "rewrite":
        return (f"{context}\n\nTASK: Rewrite the passage below. It currently "
                f"stands at {CURSOR}. Keep its meaning and events; change the "
                f"prose as instructed. Return only the rewritten passage.\n\n"
                f"INSTRUCTION: {instruction}\n\nPASSAGE:\n{selection or ''}")
    if mode == "expand":
        return (f"{context}\n\nTASK: Write the prose that replaces the "
                f"placeholder at {CURSOR}, fulfilling this note from the "
                f"author. Return only the new prose.\n\n"
                f"AUTHOR'S NOTE: {instruction}")
    return (f"{context}\n\nTASK: Write new prose to be inserted at {CURSOR}.\n\n"
            f"INSTRUCTION: {instruction}")


def generate_instructions(mode: str, instruction: str, selection: str | None = None) -> Section:
    """The non-context part of a draft / expand / rewrite request (counted, never dropped)."""
    return instructions(SYSTEM_PROMPT, _user_prompt(mode, instruction, "", selection))


def generate(
    mode: str,
    instruction: str,
    context: str,
    model: str,
    client=None,
    selection: str | None = None,
    on_delta=None,
    cancel=None,
) -> str:
    """Network call: produce prose for *mode* (draft | expand | rewrite).

    Synchronous — run it in a worker thread from the TUI. Raises ValueError
    for an unknown mode or an empty reply. With *on_delta* / *cancel* (a
    ``stream.CancelToken``) the call streams: each text delta goes to
    *on_delta*, and cancelling raises ``stream.Cancelled`` with nothing returned.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    if client is None:
        from .client import make_client

        client = make_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": _user_prompt(mode, instruction, context, selection)},
    ]
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, mode, on_delta, cancel)
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=usage_extra_body())
        record_response(response, model, mode)
        raw = response.choices[0].message.content or ""
    return clean_output(raw, selection)


# -- chat: ask the assistant (the GUI's composer) --------------------------------

ASK_SYSTEM_PROMPT = """\
You are a writing assistant inside a novelist's manuscript editor. Answer the
author's question using the style guide, the story notes and the scene text you
are given. In the scene text, <<CURSOR>> marks where the author's cursor is.

Rules:
- Reply in plain text: short paragraphs, or a short numbered list for options.
- You can only suggest. Never say or imply that you changed the manuscript.
- When you propose prose, write it so the author could paste it in as-is.
- Be concrete and brief; do not repeat the question.
- Sections that start with ATTACHED are material the author chose to share for
  this conversation (scenes, notes, research, comments): use them.
- Never write HTML comments or the text "<!--".
"""

PROJECT_CONTEXT_CHARS = 12000
HISTORY_TURNS = 6
HISTORY_CHARS = 1500


def _entity_items(entities: list[Entity], canon_by_name: dict[str, str]) -> tuple[Item, ...]:
    return tuple(Item(e.name, (canon_by_name.get(e.name) or e.body or "").strip(),
                      f"### {e.name} ({e.type})", i, ENTITY_CHARS)
                 for i, e in enumerate(entities))


def build_project_context_sections(
    scene_titles: list[str],
    entities: list[Entity],
    canon_by_name: dict[str, str],
    style_md: str | None,
) -> list[Section]:
    """The parts of a project-wide context, all droppable: style guide, scene titles
    in order, entity notes (in the project's order)."""
    sections: list[Section] = []
    if style_md and style_md.strip():
        sections.append(Section("Style guide", "STYLE GUIDE:\n" + style_md.strip(),
                                priority=0, droppable=True))
    if scene_titles:
        sections.append(Section(
            "Scene titles", priority=2, droppable=True, head="SCENES (in order):\n", sep="\n",
            items=tuple(Item(t, head=f"{i}. {t}", priority=i)
                        for i, t in enumerate(scene_titles, 1))))
    if entities:
        sections.append(Section("Characters and places", priority=1, droppable=True,
                                items=_entity_items(entities, canon_by_name),
                                head="CHARACTERS AND PLACES:\n", group_cap=PROJECT_CONTEXT_CHARS))
    return sections


def build_project_context(
    scene_titles: list[str],
    entities: list[Entity],
    canon_by_name: dict[str, str],
    style_md: str | None,
) -> str:
    """Context for project-wide questions: style guide, every scene title in
    order, and the canon of every entity (each capped, total capped). Only the fixed caps
    apply; what is sent goes through ``fit_context`` (``build_project_context_sections``)."""
    return render(fit(build_project_context_sections(
        scene_titles, entities, canon_by_name, style_md), Budget.unbounded())[0]) \
        or "(the project is empty)"


def _turns(history: list[dict] | None) -> list[dict]:
    """The last few chat turns as messages (each capped)."""
    turns = []
    for turn in (history or [])[-HISTORY_TURNS:]:
        role = turn.get("role")
        text = str(turn.get("text") or "")[:HISTORY_CHARS]
        if role in ("user", "assistant") and text:
            turns.append({"role": role, "content": text})
    return turns


def chat_instructions(system: str, prompt: str, history: list[dict] | None = None) -> Section:
    """The non-context part of a chat request: system prompt, the earlier turns that are
    sent, and the question."""
    return instructions(system, *[t["content"] for t in _turns(history)], prompt.strip())


def _chat_reply(client, model: str, feature: str, messages: list[dict],
                on_delta, cancel) -> str:
    """One chat call (streaming when asked to), the reply with ``<!--`` defused."""
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, feature, on_delta, cancel)
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=usage_extra_body())
        record_response(response, model, feature)
        raw = response.choices[0].message.content or ""
    return raw.replace("<!--", "<!-").strip()


def ask(
    prompt: str,
    context: str,
    model: str,
    history: list[dict] | None = None,
    client=None,
    on_delta=None,
    cancel=None,
) -> str:
    """Network call: answer *prompt* in chat. Never touches the manuscript.
    Streams when *on_delta* / *cancel* is given (see ``generate``).

    *history*: earlier turns as ``{"role": "user"|"assistant", "text": ...}``
    (the last few are sent). Synchronous — run it off the UI thread. Raises
    ValueError for an empty prompt or reply.
    """
    if not prompt.strip():
        raise ValueError("ask something first")
    if client is None:
        from .client import make_client

        client = make_client()
    reply = _chat_reply(client, model, "ask", [
        {"role": "system", "content": ASK_SYSTEM_PROMPT},
        *_turns(history),
        {"role": "user", "content": f"{context}\n\nQUESTION:\n{prompt.strip()}"},
    ], on_delta, cancel)
    if not reply:
        raise ValueError("the model returned no text")
    return reply


RESEARCH_SYSTEM_PROMPT = """\
You answer a novelist's research question using ONLY the numbered research notes
and the project canon given below.

Rules:
- Cite the research notes you rely on inline as [1], [2] (their numbers). Cite
  nothing else; never invent a source, a quotation or a fact.
- If the notes do not cover the question, say so plainly and say what the author
  could look up. Do not fill the gap from memory as if it were in the notes.
- Sections that start with ATTACHED are extra material the author shared; use
  them, but cite only the numbered research notes.
- The canon is the author's fiction. Use it to connect the facts to the story,
  but it is not a source: do not cite it.
- Be concise. Plain text, no Markdown headings.
- Never write HTML comments or the text "<!--".
"""

RESEARCH_NOTE_CHARS = 1500
RESEARCH_TOTAL_CHARS = 9000


def build_research_sections(notes: list[tuple[str, str]], canon: list[Section]) -> list[Section]:
    """The numbered research notes ((title, excerpt) in citation order; the number is part
    of each note, so a dropped note never renumbers the others) followed by the canon parts."""
    items = tuple(Item(title, excerpt.strip(), f"[{i}] {title}", i, RESEARCH_NOTE_CHARS)
                  for i, (title, excerpt) in enumerate(notes, 1))
    if items:
        head = Section("Research notes", priority=0, droppable=True, items=items,
                       head="RESEARCH NOTES:\n", group_cap=RESEARCH_TOTAL_CHARS)
    else:
        head = Section("Research notes",
                       "RESEARCH NOTES: (none of the author's notes matched this question)")
    return [head, *canon]


def build_research_context(notes: list[tuple[str, str]], canon_context: str) -> str:
    """The numbered research notes ((title, excerpt) in citation order, each
    and the total capped) followed by the project canon."""
    canon = [Section("Characters and places", canon_context)] if canon_context else []
    return render(fit(build_research_sections(notes, canon), Budget.unbounded())[0])


def research_sections(project, entities: list[Entity], canon_by_name: dict[str, str],
                      question: str) -> tuple[list[Section], list[research_notes.Hit]]:
    """The parts of the context for a research *question* (for ``fit_context``) and the
    notes it was given, in citation order. Raises ValueError when the project has no
    research notes at all (no AI call is worth making)."""
    if not research_notes.list_notes(project):
        raise ValueError("Your notebook is empty. Add some notes under Notebook "
                         "(a new note, or a pasted link) and ask again.")
    hits = research_notes.search(project, question)
    canon = build_project_context_sections([], entities, canon_by_name, None) or [
        Section("Characters and places", "(the project is empty)")]
    return build_research_sections([(h.note.title, h.excerpt) for h in hits], canon), hits


def research_context(project, entities: list[Entity], canon_by_name: dict[str, str],
                     question: str) -> tuple[str, list[research_notes.Hit]]:
    """Everything the model is given for a research *question*: the best matching
    notes (numbered, in citation order) and the project canon. Raises ValueError
    when the project has no research notes at all (no AI call is worth making)."""
    sections, hits = research_sections(project, entities, canon_by_name, question)
    return render(fit(sections, Budget.unbounded())[0]), hits


def research_answer(
    prompt: str,
    context: str,
    model: str,
    history: list[dict] | None = None,
    client=None,
    on_delta=None,
    cancel=None,
) -> str:
    """Network call: answer a research question from *context* (see
    ``build_research_context``). Chat text only; never touches the manuscript.
    Streams when *on_delta* / *cancel* is given (see ``generate``).
    Raises ValueError for an empty prompt or reply."""
    if not prompt.strip():
        raise ValueError("ask a research question first")
    if client is None:
        from .client import make_client

        client = make_client()
    reply = _chat_reply(client, model, "research", [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        *_turns(history),
        {"role": "user", "content": f"{context}\n\nQUESTION:\n{prompt.strip()}"},
    ], on_delta, cancel)
    if not reply:
        raise ValueError("the model returned no text")
    return reply


# -- brainstorm: "unstuck" ideas (Wave 4.3) ---------------------------------------------

BRAINSTORM_SYSTEM_PROMPT = """\
You help a novelist who is stuck in the middle of a scene. Using the style guide,
the story notes and the scene text you are given (<<CURSOR>> marks the author's
cursor), propose between 3 and 5 ideas to get the writing moving again.

Make the ideas different from each other. Draw them from angles such as:
- a what-if question about this moment;
- a complication or reversal the scene could take;
- a sensory detail or image the scene has not used;
- a pressure point on one of the characters (what they want, fear or hide);
- something from the story notes that has not come into play yet.

Rules:
- Be concrete and specific to THIS scene and THESE characters; no generic
  writing advice.
- One or two sentences per idea. Do not write the scene's prose and do not
  continue the text; the author decides what to use.
- Reply as a numbered list ("1. ..."), nothing before or after it.
- Never write HTML comments or the text "<!--".
"""

BRAINSTORM_MIN, BRAINSTORM_MAX = 3, 5
IDEA_CHARS = 600
_NUMBERED = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+(.*\S)\s*$")


def parse_ideas(raw: str) -> list[str]:
    """The ideas in a model reply: numbered (or bulleted) items, continuation
    lines joined, at most five. Without any list markers each paragraph is an
    idea. Markdown emphasis and ``<!--`` are stripped."""
    ideas: list[str] = []
    for line in (raw or "").replace("<!--", "<!-").splitlines():
        m = _NUMBERED.match(line)
        if m:
            ideas.append(m.group(1).strip())
        elif line.strip() and ideas and not ideas[-1].endswith(":") and not line.lstrip().startswith("#"):
            ideas[-1] += " " + line.strip()
    if not ideas:
        ideas = [" ".join(p.split()) for p in re.split(r"\n\s*\n", raw or "") if p.strip()]
    cleaned = []
    for idea in ideas:
        idea = re.sub(r"\*\*(.+?)\*\*", r"\1", idea).strip()
        if idea:
            cleaned.append(idea[:IDEA_CHARS])
    return cleaned[:BRAINSTORM_MAX]


def brainstorm_instructions() -> Section:
    """The non-context part of a Brainstorm request (counted, never dropped)."""
    return instructions(BRAINSTORM_SYSTEM_PROMPT, "Give me ideas to get unstuck.")


def brainstorm(context: str, model: str, client=None, on_delta=None, cancel=None) -> list[str]:
    """Network call: 3-5 "unstuck" ideas for the scene in *context* (see
    ``build_context`` / ``build_project_context``). Chat text only; never
    touches the manuscript. Synchronous - run it off the UI thread. Raises
    ValueError when the model returns nothing usable. Streams when *on_delta* /
    *cancel* is given (see ``generate``; the deltas are the raw numbered list)."""
    if client is None:
        from .client import make_client

        client = make_client()
    messages = [
        {"role": "system", "content": BRAINSTORM_SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}\n\nGive me ideas to get unstuck."},
    ]
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, "brainstorm", on_delta, cancel)
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=usage_extra_body())
        record_response(response, model, "brainstorm")
        raw = response.choices[0].message.content or ""
    ideas = parse_ideas(raw)
    if not ideas:
        raise ValueError("the model returned no ideas")
    return ideas
