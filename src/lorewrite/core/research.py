"""Research notes: plain Markdown under ``<project>/research/`` (any subfolders).

They are the author's reference material - a magazine article on tide tables, a
link, a half-remembered fact. Not scenes (not in the book, not counted, not
read by continuity) and not entities (no frontmatter, not in the link index).
The assistant's *Research* action answers a question from them: keyword
retrieval with a simple score (no embeddings, no web), and it cites the notes it
used. ``project`` arguments are duck-typed: ``root`` only.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

RESEARCH_DIR = "research"
ASSISTANT_NOTES = "assistant-notes.md"   # "Save to notes" appends here (3.4)
EXCERPT_CHARS = 1500
_STOP = frozenset("""a an and are as at be but by can did do does for from had has have how i if in is it its
me my not of on or our so than that the their them then there these they this to us was we were what when
where which who why will with would you your about into over under also any all more most some such""".split())


@dataclass(frozen=True)
class Note:
    path: Path
    rel: str          # path inside research/, "/"-separated ("tides/almanac.md")
    title: str
    words: int


@dataclass(frozen=True)
class Hit:
    note: Note
    score: float
    excerpt: str      # the passage that matched best (capped)


def research_dir(project) -> Path:
    return project.root / RESEARCH_DIR


def is_research_path(project, path: Path | None) -> bool:
    """A Markdown file inside research/ (not a dot-file)."""
    if path is None or path.suffix != ".md" or path.name.startswith("."):
        return False
    try:
        rel = path.resolve().relative_to(research_dir(project).resolve())
    except (OSError, ValueError):
        return False
    return not any(part.startswith(".") for part in rel.parts)


def title_of(path: Path, text: str | None = None) -> str:
    """The first ``# heading``, else the file name de-slugged."""
    if text is None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
    for line in text.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    words = re.split(r"[-_\s]+", path.stem)
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or path.stem


def _note(project, path: Path) -> Note:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    rel = path.relative_to(research_dir(project)).as_posix()
    return Note(path, rel, title_of(path, text), len(text.split()))


def list_notes(project) -> list[Note]:
    """Every research note, folders first-level order then name (stable)."""
    base = research_dir(project)
    if not base.is_dir():
        return []
    paths = [p for p in base.rglob("*.md") if is_research_path(project, p)]
    return [_note(project, p) for p in sorted(paths, key=lambda p: p.relative_to(base).as_posix().casefold())]


def read(project, path: Path) -> str:
    return path.read_text(encoding="utf-8")


# -- creating -------------------------------------------------------------------


def _slug(title: str) -> str:
    return re.sub(r"[\W_]+", "-", title.casefold()).strip("-") or "note"


def _free_path(folder: Path, slug: str) -> Path:
    path = folder / f"{slug}.md"
    n = 1
    while path.exists():
        n += 1
        path = folder / f"{slug}-{n}.md"
    return path


def new_note(project, title: str, body: str = "") -> Path:
    """Create ``research/<slug>.md`` with a ``# title`` heading."""
    title = " ".join((title or "").split())
    if not title:
        raise ValueError("a research note needs a title")
    folder = research_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    path = _free_path(folder, _slug(title))
    path.write_text(f"# {title}\n\n{body.strip()}\n" if body.strip() else f"# {title}\n\n",
                    encoding="utf-8")
    return path


def title_from_url(url: str) -> str:
    """A readable title for a link without fetching it: host plus the last path
    segment (``example.com - tide tables``)."""
    parts = urlparse(url)
    host = (parts.netloc or "").removeprefix("www.")
    last = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1])
    last = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", last)
    last = " ".join(re.split(r"[-_+\s]+", last)).strip()
    return f"{host} - {last}" if host and last else host or url


def looks_like_url(text: str) -> bool:
    text = (text or "").strip()
    if not text or any(c.isspace() for c in text):
        return False
    parts = urlparse(text)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def note_from_url(project, url: str, title: str = "") -> Path:
    """A note holding just the link and a title (nothing is fetched)."""
    url = (url or "").strip()
    if not looks_like_url(url):
        raise ValueError("that is not a web link (it should start with http:// or https://)")
    return new_note(project, title or title_from_url(url), url)


def delete_note(project, path: Path) -> None:
    """Delete a research note for good (the UIs confirm first)."""
    if not is_research_path(project, path) or not path.is_file():
        raise FileNotFoundError("no such research note")
    path.unlink()


# -- retrieval --------------------------------------------------------------------


def tokens(text: str) -> list[str]:
    """Lower-case words of 3+ letters/digits, without stop words."""
    return [w for w in re.findall(r"[^\W_]{3,}", (text or "").casefold()) if w not in _STOP]


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _score_terms(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for w in tokens(text):
        counts[_stem(w)] = counts.get(_stem(w), 0) + 1
    return counts


def _best_passage(text: str, terms: set[str]) -> str:
    """The paragraph with the most query terms (capped), else the opening."""
    best, best_hits = "", 0
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block or block.startswith("#") and "\n" not in block:
            continue
        hits = sum(1 for w in tokens(block) if _stem(w) in terms)
        if hits > best_hits:
            best, best_hits = block, hits
    if not best:
        best = next((b.strip() for b in re.split(r"\n\s*\n", text)
                     if b.strip() and not b.lstrip().startswith("#")), text.strip())
    return best if len(best) <= EXCERPT_CHARS else best[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


def search(project, query: str, limit: int = 5) -> list[Hit]:
    """The notes that best match *query*, best first. Score = for each query
    term, its count in the note (damped) times how rare it is across notes,
    with a bonus for a hit in the title. Zero-score notes are not returned."""
    terms = {_stem(w) for w in tokens(query)}
    notes = list_notes(project)
    if not terms or not notes:
        return []
    docs = []
    for n in notes:
        text = read(project, n.path)
        docs.append((n, text, _score_terms(text), set(_stem(w) for w in tokens(n.title))))
    n_docs = len(docs)
    df = {t: sum(1 for _, _, counts, _ in docs if t in counts) for t in terms}
    hits = []
    for note, text, counts, title_terms in docs:
        score = 0.0
        for t in terms:
            if t not in counts and t not in title_terms:
                continue
            idf = math.log(1 + n_docs / max(1, df[t]))
            score += idf * (1 + math.log(1 + counts.get(t, 0)))
            if t in title_terms:
                score += 2 * idf
        if score > 0:
            hits.append(Hit(note, round(score, 4), _best_passage(text, terms)))
    hits.sort(key=lambda h: (-h.score, h.note.rel.casefold()))
    return hits[:limit]
