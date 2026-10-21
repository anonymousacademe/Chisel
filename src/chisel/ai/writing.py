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
from .client import openrouter_extra_body
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


SCRIPT_SYSTEM_PROMPT = """\
You are a ghostwriter helping a screenwriter. You write ONLY the requested script text, in Fountain.

Format (Fountain, plain text):
- A scene heading is one line: INT. or EXT., a location, a dash and the time (INT. KITCHEN - DAY), in capitals.
- Action is plain present-tense text: only what can be seen or heard, in short paragraphs, with no camera
  directions unless the style guide uses them. Do not hard-wrap lines.
- A character cue is the character's name in capitals on its own line, followed directly (no blank line) by
  the dialogue. A parenthetical goes on its own line in parentheses between the cue and the speech; use them rarely.
- Use character and place names exactly as the notes give them (the cue is the name in capitals).
- Write a transition (CUT TO:) only when asked. Put one blank line between elements.
- Emphasis is *italics*, **bold** or _underline_ only. No Markdown headings, bullets, bold cues or code fences.
- Never write notes ([[ ]] or <!-- -->) or /* */.

Rules:
- Match the author's style guide exactly (the voice of the action lines, how the characters talk).
- Stay consistent with the story context and the character/place notes given.
- Output the script text and nothing else: no commentary, no preamble, no title, no quotation marks around it.
- Continue naturally at <<CURSOR>>; do not repeat the surrounding text and do not write past the request.
- When passages of the author's own writing are given, they are the voice to match; never copy their events
  or lines.
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


STORY_PRIORITY = 2          # after the style guide (0) and the entity notes (1); with the author's own prose
STORY_PROJECT_PRIORITY = 1  # in a whole-project context the story is worth more than the scene titles (2)


def story_section(story, priority: int = STORY_PRIORITY, group_cap: int | None = None) -> Section | None:
    """"Story so far" for a chat, Brainstorm or description: the stored summaries of the scenes before the
    open one (*story*, ``core.summaries.StorySoFar``), droppable, the oldest first when the budget is tight
    (and named in the report). None when there is nothing to say, so a project without summaries is unchanged."""
    if story is None or not story.blocks:
        return None
    head = ("STORY SO FAR (summaries of the earlier part of the book, " + story.sentence.lower() + "):\n")
    if story.missing:
        head += f"(no summary yet for: {', '.join(story.missing)})\n"
    n = len(story.blocks)
    return Section("Story so far", priority=priority, droppable=True, head=head, group_cap=group_cap,
                   items=tuple(Item(b.name, b.text, "", n - 1 - i) for i, b in enumerate(story.blocks)))


def build_context_sections(
    scene_text: str,
    cursor_offset: int,
    entities: list[Entity],
    canon_by_name: dict[str, str],
    style_md: str | None,
    span: tuple[int, int] | None = None,
    originals: dict[str, str] | None = None,
    voice_samples: list[tuple[str, str]] | None = None,
    story=None,
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

    if (section := story_section(story)) is not None:
        sections.append(section)

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


_SCRIPT_NOTE_RE = re.compile(r"\[\[.*?\]\]|/\*.*?\*/", re.DOTALL)
_BOLD_LINE_RE = re.compile(r"^[ \t]*\*\*([^*\n]+)\*\*[ \t]*$", re.MULTILINE)


def clean_script_output(text: str) -> str:
    """What a model's script text needs on top of ``clean_output``: no notes or boneyard (a ``[[x]]`` would
    become a link to a missing note), no bold around a whole line (cues are plain capitals), and no more
    than one blank line in a row. Raises ValueError if nothing is left."""
    text = _SCRIPT_NOTE_RE.sub("", text)
    text = _BOLD_LINE_RE.sub(r"\1", text)
    text = re.sub(r"\n[ \t]*(?:\n[ \t]*){2,}", "\n\n", text).strip()
    if not text:
        raise ValueError("the model returned no text")
    return text


def _user_prompt(mode: str, instruction: str, context: str,
                 selection: str | None, script: bool = False) -> str:
    if script:
        if mode == "rewrite":
            return (f"{context}\n\nTASK: Rewrite the passage below (Fountain). It currently stands at "
                    f"{CURSOR}. Keep its meaning and events, and its structure (scene headings, cues, who "
                    f"speaks) unless the instruction says otherwise; change the writing as instructed. "
                    f"Return only the rewritten passage as Fountain.\n\n"
                    f"INSTRUCTION: {instruction}\n\nPASSAGE:\n{selection or ''}")
        if mode == "expand":
            return (f"{context}\n\nTASK: Write the script text (Fountain) that replaces the placeholder at "
                    f"{CURSOR}, fulfilling this note from the author. Return only the new script text.\n\n"
                    f"AUTHOR'S NOTE: {instruction}")
        return (f"{context}\n\nTASK: Write new script text (Fountain) to be inserted at {CURSOR}. Begin with a "
                f"new element; do not continue a half-finished line.\n\nINSTRUCTION: {instruction}")
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


def generate_instructions(mode: str, instruction: str, selection: str | None = None,
                          script: bool = False) -> Section:
    """The non-context part of a draft / expand / rewrite request (counted, never dropped)."""
    return instructions(SCRIPT_SYSTEM_PROMPT if script else SYSTEM_PROMPT,
                        _user_prompt(mode, instruction, "", selection, script))


def generate(
    mode: str,
    instruction: str,
    context: str,
    model: str,
    client=None,
    selection: str | None = None,
    on_delta=None,
    cancel=None,
    script: bool = False,
) -> str:
    """Network call: produce prose for *mode* (draft | expand | rewrite). With *script* (a script project)
    the model writes Fountain: its own system prompt, and its reply is cleaned of notes and bold cues.

    Synchronous — run it in a worker thread from the TUI. Raises ValueError
    for an unknown mode or an empty reply. With *on_delta* / *cancel* (a
    ``stream.CancelToken``) the call streams: each text delta goes to
    *on_delta*, and cancelling raises ``stream.Cancelled`` with nothing returned.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    if client is None:
        from .client import make_client

        client = make_client(model)
    messages = [
        {"role": "system", "content": SCRIPT_SYSTEM_PROMPT if script else SYSTEM_PROMPT},
        {"role": "user",
         "content": _user_prompt(mode, instruction, context, selection, script)},
    ]
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, mode, on_delta, cancel)
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=openrouter_extra_body(model=model))
        record_response(response, model, mode)
        raw = response.choices[0].message.content or ""
    text = clean_output(raw, selection)
    return clean_script_output(text) if script else text


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

SCRIPT_ASK_SYSTEM_PROMPT = ASK_SYSTEM_PROMPT.replace(
    "inside a novelist's manuscript editor", "inside a screenwriter's script editor").replace(
    "- When you propose prose, write it so the author could paste it in as-is.",
    "- The scene text is Fountain. When you propose script text, write valid Fountain so the author could paste\n"
    "  it in as-is: scene headings in capitals (INT. KITCHEN - DAY), character cues in capitals on their own\n"
    "  line directly above their dialogue, no Markdown.")


def ask_system_prompt(script: bool = False) -> str:
    """The chat system prompt for a story or (*script*) a script project."""
    return SCRIPT_ASK_SYSTEM_PROMPT if script else ASK_SYSTEM_PROMPT


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
    story=None,
) -> list[Section]:
    """The parts of a project-wide context, all droppable: style guide, the story so far (when the
    project has summaries), scene titles in order, entity notes (in the project's order)."""
    sections: list[Section] = []
    if style_md and style_md.strip():
        sections.append(Section("Style guide", "STYLE GUIDE:\n" + style_md.strip(),
                                priority=0, droppable=True))
    if (section := story_section(story, STORY_PROJECT_PRIORITY)) is not None:
        sections.append(section)
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
            model=model, messages=messages, extra_body=openrouter_extra_body(model=model))
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

        client = make_client(model)
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

        client = make_client(model)
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


# -- brainstorm about a passage the author selected ------------------------------------------

FOCUS_CHARS = 6000          # a longer selection is trimmed (an Item cap: reported, never silent)

BRAINSTORM_FOCUS_SYSTEM_PROMPT = """\
You help a novelist think about one passage of their work: the FOCUS PASSAGE, which
the author selected in {where}. Using the story notes, the style guide and the other
context you are given, propose between 3 and 5 ideas about that passage.

Make the ideas different from each other. {angles}

Rules:
- Be concrete and specific to THIS passage and THIS story: tie ideas to the
  characters, places and events the notes mention when you can. No generic
  writing advice.
- Keep to what the notes establish; if an idea would change an established fact,
  say so plainly in the idea.
- If the author gives a direction, follow it.
- One to three sentences per idea. Do not rewrite the passage and do not write
  prose for the book; the author decides what to use.
- Reply as a numbered list ("1. ..."), nothing before or after it.
- Never write HTML comments or the text "<!--".
"""

FOCUS_ANGLES = {
    "character": ("Draw them from angles such as: something in their past that would explain this; what they "
                  "want, fear or hide; a contradiction that makes them more human; a relationship with another "
                  "character this could touch; an event in the story this could set up or pay off; a question "
                  "the passage leaves open."),
    "place": ("Draw them from angles such as: the place's history; who uses it and how; how it looks, sounds "
              "and smells; a secret it keeps; how it could matter to the plot or to a character."),
    "thing": ("Draw them from angles such as: where it came from and who has had it; what it means to the "
              "people around it; a secret or flaw it has; how it could move the plot."),
    "scene": ("Draw them from angles such as: a what-if question about this moment; a complication or reversal; "
              "a sensory detail or image not used yet; a pressure point on one of the characters; something "
              "from the story notes that has not come into play yet."),
    "notebook": ("Draw them from angles such as: what this means for the story; a character or event it could "
                 "connect to; a scene it could feed; a question worth looking into next."),
}


def focus_section(passage: str) -> Section:
    """The selected passage as context: never dropped, capped at ``FOCUS_CHARS`` (the cap is reported)."""
    return Section("Focus passage", head="FOCUS PASSAGE (selected by the author):\n",
                   items=(Item("the selected passage", body=passage.strip(), cap=FOCUS_CHARS),))


def brainstorm_focus_prompts(kind: str, where: str, direction: str = "") -> tuple[str, str]:
    """(system prompt, request) for a Brainstorm about the focus passage. *kind*: character, place, thing,
    scene or notebook (the angles); *where*: what the passage was selected in ("the character note “Derek”")."""
    system = BRAINSTORM_FOCUS_SYSTEM_PROMPT.format(where=where, angles=FOCUS_ANGLES.get(kind, FOCUS_ANGLES["thing"]))
    ask = "Give me ideas about the focus passage."
    if direction.strip():
        ask += f"\nMy direction: {' '.join(direction.split())}"
    return system, ask


def brainstorm_focus_instructions(kind: str, where: str, direction: str = "") -> Section:
    """The non-context part of a focused Brainstorm (counted, never dropped)."""
    return instructions(*brainstorm_focus_prompts(kind, where, direction))


def brainstorm(context: str, model: str, client=None, on_delta=None, cancel=None,
               system: str | None = None, ask: str | None = None) -> list[str]:
    """Network call: 3-5 "unstuck" ideas for the scene in *context* (see
    ``build_context`` / ``build_project_context``). Chat text only; never
    touches the manuscript. Synchronous - run it off the UI thread. Raises
    ValueError when the model returns nothing usable. Streams when *on_delta* /
    *cancel* is given (see ``generate``; the deltas are the raw numbered list). *system* / *ask*
    replace the prompt and the request (``brainstorm_focus_prompts``: ideas about a selected passage)."""
    if client is None:
        from .client import make_client

        client = make_client(model)
    messages = [
        {"role": "system", "content": system or BRAINSTORM_SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}\n\n{ask or 'Give me ideas to get unstuck.'}"},
    ]
    if on_delta is not None or cancel is not None:
        raw = stream_text(client, model, messages, "brainstorm", on_delta, cancel)
    else:
        response = client.chat.completions.create(
            model=model, messages=messages, extra_body=openrouter_extra_body(model=model))
        record_response(response, model, "brainstorm")
        raw = response.choices[0].message.content or ""
    ideas = parse_ideas(raw)
    if not ideas:
        raise ValueError("the model returned no ideas")
    return ideas
