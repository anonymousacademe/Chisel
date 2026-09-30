"""The project style guide: plain Markdown at <project>/style.md (SPEC §7 M4).

Author-owned and hand-editable; it lives at the project root, never in the
disposable .lorewrite/ cache. Pure Python, no Textual.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

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
    for path in project.list_scenes():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        paras = _paragraphs(text)
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


def style_markdown(fields: dict[str, str], exemplars: str) -> str:
    """Assemble the full style.md from the per-section text and the
    pre-built exemplars section."""
    parts = ["# Style guide", ""]
    for title, key in (("Voice", "voice"), ("Rhythm & syntax", "rhythm"),
                       ("Diction", "diction"), ("Dialogue", "dialogue"),
                       ("Avoid", "avoid")):
        parts += [f"## {title}", "", (fields.get(key) or "").strip(), ""]
    return "\n".join(parts) + "\n" + exemplars
