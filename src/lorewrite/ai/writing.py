"""AI drafting: draft at the cursor, expand a {{expand: …}} marker, rewrite a
selection (SPEC §7 M4).

Plain-text generation with the *writing* model. Nothing here edits a scene:
the caller wraps the result as a pending draft (core.drafts) that the author
must accept.
"""

from __future__ import annotations

import re

from ..core import drafts, scenemeta
from ..core.entities import Entity, resolve
from ..core.links import find_all_links
from .client import usage_extra_body
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
sidecar, so replaced text counts as the accepted prose)."""
    marked = _marked_scene(scene_text, cursor_offset, span, originals)
    before, _, after = marked.partition(CURSOR)
    window = _tail_words(before, CONTEXT_WORDS) + CURSOR + _head_words(
        after, CONTEXT_WORDS)

    sections: list[str] = []
    if style_md and style_md.strip():
        sections.append("STYLE GUIDE:\n" + style_md.strip())

    names = [n for e in entities for n in e.names]
    mentioned: list[Entity] = []
    for link in find_all_links(
            scenemeta.blank(drafts.strip_pending(scene_text, originals),
                            keep=scenemeta.MENTION_FIELDS), names):
        entity = resolve(link.target, entities)
        if entity is not None and entity not in mentioned:
            mentioned.append(entity)
    notes: list[str] = []
    used = 0
    for entity in mentioned:
        note = (canon_by_name.get(entity.name) or entity.body or "").strip()
        note = note[:ENTITY_CHARS]
        if not note or used + len(note) > ENTITY_TOTAL_CHARS:
            continue
        used += len(note)
        notes.append(f"### {entity.name} ({entity.type})\n{note}")
    if notes:
        sections.append("CHARACTERS AND PLACES:\n" + "\n\n".join(notes))

    if voice_samples:
        sections.append(
            "THE AUTHOR'S OWN PROSE (match this voice; do not reuse its content):\n"
            + "\n\n".join(para for _, para in voice_samples))

    details = scenemeta.header(scene_text)
    if details:
        sections.append("SCENE DETAILS (the author's plan for this scene):\n" + details)

    sections.append("SCENE (the new text goes at " + CURSOR + "):\n" + window)
    return "\n\n".join(sections)


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


def generate(
    mode: str,
    instruction: str,
    context: str,
    model: str,
    client=None,
    selection: str | None = None,
) -> str:
    """Network call: produce prose for *mode* (draft | expand | rewrite).

    Synchronous — run it in a worker thread from the TUI. Raises ValueError
    for an unknown mode or an empty reply.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    if client is None:
        from .client import make_client

        client = make_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": _user_prompt(mode, instruction, context, selection)},
        ],
        extra_body=usage_extra_body(),
    )
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
- Never write HTML comments or the text "<!--".
"""

PROJECT_CONTEXT_CHARS = 12000
HISTORY_TURNS = 6
HISTORY_CHARS = 1500


def build_project_context(
    scene_titles: list[str],
    entities: list[Entity],
    canon_by_name: dict[str, str],
    style_md: str | None,
) -> str:
    """Context for project-wide questions: style guide, every scene title in
    order, and the canon of every entity (each capped, total capped)."""
    sections: list[str] = []
    if style_md and style_md.strip():
        sections.append("STYLE GUIDE:\n" + style_md.strip())
    if scene_titles:
        sections.append("SCENES (in order):\n" + "\n".join(
            f"{i}. {t}" for i, t in enumerate(scene_titles, 1)))
    notes: list[str] = []
    used = 0
    for entity in entities:
        note = (canon_by_name.get(entity.name) or entity.body or "").strip()[:ENTITY_CHARS]
        if used + len(note) > PROJECT_CONTEXT_CHARS:
            continue
        used += len(note)
        heading = f"### {entity.name} ({entity.type})"
        notes.append(f"{heading}\n{note}" if note else heading)
    if notes:
        sections.append("CHARACTERS AND PLACES:\n" + "\n\n".join(notes))
    return "\n\n".join(sections) or "(the project is empty)"


def ask(
    prompt: str,
    context: str,
    model: str,
    history: list[dict] | None = None,
    client=None,
) -> str:
    """Network call: answer *prompt* in chat. Never touches the manuscript.

    *history*: earlier turns as ``{"role": "user"|"assistant", "text": ...}``
    (the last few are sent). Synchronous — run it off the UI thread. Raises
    ValueError for an empty prompt or reply.
    """
    if not prompt.strip():
        raise ValueError("ask something first")
    if client is None:
        from .client import make_client

        client = make_client()
    turns = []
    for turn in (history or [])[-HISTORY_TURNS:]:
        role = turn.get("role")
        text = str(turn.get("text") or "")[:HISTORY_CHARS]
        if role in ("user", "assistant") and text:
            turns.append({"role": role, "content": text})
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ASK_SYSTEM_PROMPT},
            *turns,
            {"role": "user", "content": f"{context}\n\nQUESTION:\n{prompt.strip()}"},
        ],
        extra_body=usage_extra_body(),
    )
    record_response(response, model, "ask")
    reply = (response.choices[0].message.content or "").replace("<!--", "<!-").strip()
    if not reply:
        raise ValueError("the model returned no text")
    return reply
