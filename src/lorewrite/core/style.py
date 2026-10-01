"""The project style guide: plain Markdown at <project>/style.md (SPEC §7 M4).

Author-owned and hand-editable; it lives at the project root, never in the
disposable .lorewrite/ cache. Pure Python, no Textual.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import scenemeta
from .drafts import count_words, load_originals, strip_pending

STYLE_FILE = "style.md"
BACKUP_FILE = "style.md.bak"
MIN_PARAGRAPH_WORDS = 25
MAX_EXEMPLARS = 3

SECTIONS = (
    ("Voice", "POV, tense, register."),
    ("Rhythm & syntax", "Sentence length, paragraphing, pacing."),
    ("Diction", "Word choice, imagery, recurring vocabulary."),
    ("Dialogue", "Tags, punctuation, how characters sound."),
    ("Avoid", "Things this author never does."),
    ("Exemplars", "Paragraphs quoted verbatim from the manuscript."),
)

STUB_TEMPLATE = "# Style guide\n\n" + "".join(
    f"## {title}\n\n<!-- {hint} -->\n\n" for title, hint in SECTIONS)


def style_path(project) -> Path:
    return project.root / STYLE_FILE


def load_style(project) -> str | None:
    """The style guide text, or None if there is none (or it is blank)."""
    try:
        text = style_path(project).read_text(encoding="utf-8")
    except OSError:
        return None
    return text if text.strip() else None


def save_style(project, text: str, backup: bool = True) -> Path:
    """Write style.md atomically (temp + rename). An existing guide is first
    copied to style.md.bak."""
    path = style_path(project)
    if backup and path.is_file():
        shutil.copyfile(path, project.root / BACKUP_FILE)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def ensure_style_stub(project) -> Path:
    """Create style.md from the stub template if missing; return its path."""
    path = style_path(project)
    if not path.is_file():
        save_style(project, STUB_TEMPLATE, backup=False)
    return path


def _paragraphs(text: str) -> list[str]:
    """Prose paragraphs of a scene: blank-line separated, no headings, and
    long enough to say something about style."""
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        if len(block.split()) < MIN_PARAGRAPH_WORDS:
            continue
        out.append(block)
    return out


def _spread(items: list, count: int) -> list:
    """*count* items at even spacing across the list (order preserved)."""
    if count >= len(items):
        return list(items)
    if count <= 1:
        return [items[len(items) // 2]]
    idx = sorted({round(i * (len(items) - 1) / (count - 1)) for i in range(count)})
    return [items[i] for i in idx]


def sample_manuscript(project, max_words: int = 6000) -> list[tuple[str, str]]:
    """Paragraphs sampled evenly across every scene, up to ~max_words.

    Returns [(scene_rel, paragraph)] in manuscript order. Each scene gets an
    equal share of the word budget, spread through the scene; headings and
    paragraphs under 25 words are skipped.
    """
    per_scene: list[tuple[str, list[str]]] = []
    for path in project.counted_scenes():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        paras = _paragraphs(scenemeta.strip(strip_pending(  # AI text isn't the author's
            text, load_originals(project.root, path))))
        if paras:
            per_scene.append((str(path.relative_to(project.root)), paras))
    if not per_scene:
        return []
    quota = max(max_words // len(per_scene), 1)
    picks: list[tuple[str, list[str]]] = []
    for rel, paras in per_scene:
        avg = sum(len(p.split()) for p in paras) / len(paras)
        chosen = _spread(paras, max(1, round(quota / avg)))
        while len(chosen) > 1 and sum(len(p.split()) for p in chosen) > quota:
            chosen = _spread(chosen, len(chosen) - 1)
        picks.append((rel, chosen))

    def total() -> int:
        return sum(len(p.split()) for _, ps in picks for p in ps)

    while total() > max_words:
        biggest = max(picks, key=lambda pick: len(pick[1]))
        if len(biggest[1]) > 1:
            biggest[1][:] = _spread(biggest[1], len(biggest[1]) - 1)
        elif len(picks) > 1:
            # one paragraph per scene and still too long: thin the scenes
            picks[:] = _spread(picks, len(picks) - 1)
        else:
            break
    return [(rel, p) for rel, ps in picks for p in ps]


def exemplars_section(samples: list[tuple[str, str]], picks: list[int]) -> str:
    """The '## Exemplars' section: each picked paragraph as a blockquote with
    its source scene filename. Out-of-range/duplicate picks are ignored."""
    seen: list[int] = []
    for i in picks:
        if isinstance(i, int) and not isinstance(i, bool) \
                and 0 <= i < len(samples) and i not in seen:
            seen.append(i)
    lines = ["## Exemplars", ""]
    for i in seen[:MAX_EXEMPLARS]:
        rel, paragraph = samples[i]
        quoted = "\n".join(f"> {ln}" if ln else ">" for ln in paragraph.splitlines())
        lines += [quoted, ">", f"> — {Path(rel).name}", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def style_markdown(fields: dict[str, str], exemplars: str,
                   learned: str | None = None) -> str:
    """Assemble the full style.md from the per-section text and the
    pre-built exemplars section. *learned*: a learned_note() line."""
    parts = ["# Style guide", ""]
    if learned:
        parts += [learned, ""]
    for title, key in (("Voice", "voice"), ("Rhythm & syntax", "rhythm"),
                       ("Diction", "diction"), ("Dialogue", "dialogue"),
                       ("Avoid", "avoid")):
        parts += [f"## {title}", "", (fields.get(key) or "").strip(), ""]
    return "\n".join(parts) + "\n" + exemplars


# -- what the guide was learned from ---------------------------------------------

_LEARNED_RE = re.compile(
    r"<!--\s*learned (\d{4}-\d{2}-\d{2}) from ([\d,]+) sampled words;"
    r" manuscript ([\d,]+) words in (\d+) scenes?\s*-->")
STALE_GROWTH = 1.5  # suggest relearning once the manuscript is 50% longer
STALE_MIN_NEW_WORDS = 1000


def manuscript_stats(project) -> tuple[int, int]:
    """(words, scenes) of the author's prose, pending AI drafts excluded."""
    words = scenes = 0
    for path in project.counted_scenes():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        scenes += 1
        words += count_words(text, load_originals(project.root, path))
    return words, scenes


def learned_note(sampled_words: int, manuscript: tuple[int, int], day: str) -> str:
    """The provenance line written into a learned style.md (an HTML comment,
    hidden in Markdown previews)."""
    words, scenes = manuscript
    return (f"<!-- learned {day} from {sampled_words:,} sampled words;"
            f" manuscript {words:,} words in {scenes} scene"
            f"{'' if scenes == 1 else 's'} -->")


def style_info(project) -> dict:
    """Whether a style guide exists, when it was learned and from how much
    text, and whether the manuscript has grown enough to relearn."""
    words_now, scenes_now = manuscript_stats(project)
    info = {"exists": False, "learned": None, "sampledWords": None,
            "manuscriptWordsThen": None, "manuscriptWords": words_now,
            "scenes": scenes_now, "stale": False}
    text = load_style(project)
    if text is None:
        return info
    info["exists"] = True
    m = _LEARNED_RE.search(text)
    if m:
        then = int(m.group(3).replace(",", ""))
        info.update(learned=m.group(1),
                    sampledWords=int(m.group(2).replace(",", "")),
                    manuscriptWordsThen=then,
                    stale=(words_now >= then * STALE_GROWTH
                           and words_now - then >= STALE_MIN_NEW_WORDS))
    return info


# -- the author's own prose as examples for drafting ----------------------------

VOICE_SAMPLE_WORDS = 2000
_QUOTED_RE = re.compile(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d')


def _dialogue_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(len(m.group(0)) for m in _QUOTED_RE.finditer(text)) / len(text)


def select_voice_samples(project, scene_path: Path | None, scene_text: str,
                         entities, budget_words: int = VOICE_SAMPLE_WORDS
                         ) -> list[tuple[str, str]]:
    """~budget_words of the author's own paragraphs to show the model as
    examples of their voice: from *other* scenes, preferring passages that
    involve the same characters/places as *scene_text* and have a similar
    share of dialogue. Returns [(scene_rel, paragraph)] in manuscript order.
    Pending AI drafts are never used (they are not the author's prose)."""
    from .entities import resolve
    from .links import find_all_links

    names = [n for e in entities for n in e.names]

    def who(text: str) -> set[str]:
        out = set()
        for link in find_all_links(text, names):
            entity = resolve(link.target, entities)
            if entity is not None:
                out.add(entity.name)
        return out

    focus = scenemeta.strip(strip_pending(scene_text))
    focus_who, focus_dialogue = who(focus), _dialogue_ratio(focus)
    current = scene_path.resolve() if scene_path else None
    pool: list[tuple[int, str, str]] = []  # (order, rel, paragraph)
    for path in project.counted_scenes():
        if current is not None and path.resolve() == current:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(path.relative_to(project.root))
        for para in _paragraphs(scenemeta.strip(
                strip_pending(text, load_originals(project.root, path)))):
            pool.append((len(pool), rel, para))
    if not pool and focus:
        # a one-scene project: the rest of this scene is all the author has
        pool = [(i, str(scene_path.relative_to(project.root)) if scene_path else "",
                 p) for i, p in enumerate(_paragraphs(focus))]

    def score(item: tuple[int, str, str]) -> float:
        para = item[2]
        return (2 * len(who(para) & focus_who)
                + 1 - abs(_dialogue_ratio(para) - focus_dialogue))

    chosen, used = [], 0
    for item in sorted(pool, key=score, reverse=True):
        n = len(item[2].split())
        if chosen and used + n > budget_words:
            continue
        chosen.append(item)
        used += n
        if used >= budget_words:
            break
    return [(rel, para) for _, rel, para in sorted(chosen)]
