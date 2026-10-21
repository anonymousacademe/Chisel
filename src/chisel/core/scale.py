"""When a project has outgrown what the AI can see, say so in plain words (SPEC "Summaries for long projects").

Chisel sends the AI one scene plus the notes about its characters. For a short project that is
everything that matters; for a book it is a small part of the story. ``scale_hint`` compares the
project with the model's context window and the summaries it has, and returns what to tell the
author. Pure Python, no network. It reads every scene (word counts, summary status): compute it off
the UI thread and pass ``words`` / ``coverage`` when the caller already has them.

It never blocks anything and never nags: ``dismissed`` (the level the author last closed, kept per
project by the front end) hides a hint of that level or a milder one, and the stronger hint can
still appear.
"""

from __future__ import annotations

from . import drafts, fsutil
from . import summaries
from .summaries import Coverage

# Tunable (see the baseline results); every number a trigger uses is here.
WORDS_TO_TOKENS = 1.3        # an English word is about 1.3 tokens (the budget's own estimate is chars / 4)
NOTICE_RATIO = 1.5           # prose longer than this many windows
NOTICE_SCENES = 30
NOTICE_ENTITIES = 40
NOTICE_QUIET_COVERAGE = 90   # percent of scenes summarised at which the notice is not shown
STRONG_RATIO = 4             # prose longer than this many windows ...
STRONG_COVERAGE = 50         # ... and fewer than this percent of scenes summarised

# What a continuity request may spend on the story so far: Chisel has no separate cap for it, so the "story so far" section can
# use the whole request budget, which is the model's window minus the room kept for the reply. This mirrors
# ai/budget.DEFAULT_RESERVE (core does not import ai; tests/test_scale.py checks the two stay equal).
CONTINUITY_RESERVE = 4_000

NONE, NOTICE, STRONG = "none", "notice", "strong"
_RANK = {NONE: 0, NOTICE: 1, STRONG: 2}


def count_words(project) -> int:
    """Words of prose in the counted scenes (details and pending AI drafts are not prose)."""
    total = 0
    for path in project.counted_scenes():
        try:
            text = fsutil.read_text_lenient(path)
        except OSError:
            continue
        total += drafts.count_words(text, drafts.load_originals(project.root, path))
    return total


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def scale_hint(project, window: int, *, words: int | None = None, coverage: Coverage | None = None,
               dismissed: str = "") -> dict:
    """``{"level": none|notice|strong, "message": str, "numbers": {...}}`` for *project* and a model
    *window* (tokens). ``numbers`` always has the inputs (words, scenes, entities, window, ratio,
    coverage, ...) so a front end can show them; ``message`` is "" at level none. A research
    project has no story to lose, so it is always none."""
    cov = coverage if coverage is not None else summaries.coverage(project)
    words = count_words(project) if words is None else words
    entities = sum(1 for e in project.load_entities() if not e.is_source)
    scenes = cov.total
    ratio = round(words * WORDS_TO_TOKENS / window, 1) if window > 0 else 0.0
    counts = cov.counts
    numbers = {"words": words, "scenes": scenes, "entities": entities, "window": window,
               "windowWords": int(window / WORDS_TO_TOKENS), "ratio": ratio,
               "coveragePercent": cov.percent, "summarised": scenes - counts[summaries.MISSING],
               "missing": counts[summaries.MISSING], "stale": counts[summaries.STALE]}
    if project.mode == "research" or scenes == 0:
        return {"level": NONE, "message": "", "numbers": numbers, "dismissed": False, "after": None}
    long_book = window > 0 and words * WORDS_TO_TOKENS > NOTICE_RATIO * window
    reasons = []
    if long_book:
        reasons.append(f"it is about {words:,} words, roughly {ratio:g} times what the AI model can "
                       f"read at once (about {numbers['windowWords']:,} words)")
    if scenes >= NOTICE_SCENES:
        reasons.append(f"it has {_plural(scenes, 'scene')}")
    if entities >= NOTICE_ENTITIES:
        reasons.append(f"it has {_plural(entities, 'character, place and object note')}")
    level = NONE
    if reasons and cov.percent < NOTICE_QUIET_COVERAGE:
        level = NOTICE
    if window > 0 and words * WORDS_TO_TOKENS > STRONG_RATIO * window and cov.percent < STRONG_COVERAGE:
        level = STRONG
    hidden = _RANK[level] <= _RANK.get(dismissed, 0) and level != NONE
    if level == NONE or hidden:
        return {"level": NONE, "message": "", "numbers": numbers, "dismissed": hidden,
                "after": _after(project, window, numbers) if level == NONE and not hidden else None}
    return {"level": level, "message": _message(level, numbers), "numbers": numbers,
            "dismissed": False, "after": None}


def _round(n: int) -> int:
    """About: to the nearest 100 from 1,000 up, else the nearest 10."""
    step = 100 if n >= 1000 else 10
    return max(step, round(n / step) * step) if n else 0


def _after(project, window: int, numbers: dict) -> str | None:
    """A quiet statement of what the AI still does NOT see once summaries cover the book (shown in the Summaries panel, never as a
    banner): None when there are no summaries or coverage is below ``NOTICE_QUIET_COVERAGE`` (the notice speaks then). The number is
    the estimated size (characters / 4, the budget's own estimate) of the story so far before the LAST scene, cut oldest-first to
    what a continuity request could hold (``window`` minus ``CONTINUITY_RESERVE``: the continuity code has no smaller cap), also given
    in words so "token" is never unexplained. No network."""
    have, total = numbers["summarised"], numbers["scenes"]
    if have == 0 or numbers["coveragePercent"] < NOTICE_QUIET_COVERAGE:
        return None
    scenes = project.counted_scenes()
    if not scenes:
        return None
    story = summaries.story_so_far(project, scenes[-1].relative_to(project.root).as_posix(),
                                   cap_tokens=max(0, window - CONTINUITY_RESERVE) if window > 0 else None)
    if not story.blocks:
        return None
    tokens = -(-len(story.text) // summaries.CHARS_PER_TOKEN)
    approx = f"about {_round(tokens):,} tokens, roughly {_round(int(tokens / WORDS_TO_TOKENS)):,} words"
    cover = "Summaries cover your whole book." if have == total else "Summaries cover most of your book."
    return (f"{cover} When you check a scene, Chisel sends a short story so far ({approx}, for your last scene) and what is "
            "recorded about the characters in it, not the full text of earlier chapters.")


MAX_MESSAGE_WORDS = 60


def coverage_phrase(n: dict) -> str:
    """"None of your 41 scenes has a summary yet" / "12 of your 41 scenes have a summary" (never "only 0 of 41")."""
    have, total = n["summarised"], n["scenes"]
    if have == 0:
        return f"None of your {total} scenes has a summary yet" if total != 1 else "Your scene has no summary yet"
    if have == total:
        return f"All {total} of your scenes have a summary"
    return f"{have} of your {total} scenes {'has' if have == 1 else 'have'} a summary"


def _message(level: str, n: dict) -> str:
    """The notice: two or three short sentences, at most MAX_MESSAGE_WORDS words. It says what is true: Chisel sends the scene
    being worked on and the notes about its characters, not the rest of the book; summaries help with that (never "fix": the
    experiments do not justify the word); the author reviews each;
    the cost is shown first. The two levels differ in emphasis only."""
    cov = coverage_phrase(n)
    if level == STRONG:
        lead = "The AI cannot see most of your book: Chisel sends it only the scene you are working on and its characters’ notes."
    else:
        lead = "Chisel sends the AI the scene you are working on and its characters’ notes, not the rest of the book, so it cannot see earlier chapters."
    return (f"{lead} {cov}. A short summary of each scene helps with that; you review each before it is kept, "
            "and the cost is shown first.")
