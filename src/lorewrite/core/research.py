"""Notebook notes: plain Markdown under ``<project>/notebook/`` (any subfolders).

(Called "research notes" before the Notebook rename; the module and the bridge
kind keep that name. A project's old ``research/`` folder is moved to
``notebook/`` on open by ``migrate_folder``; if both folders exist, both are read.)

They are the author's notes about anything that is not the manuscript - ideas,
world-building, an outline, a magazine article on tide tables, a link. Not scenes (not in the book, not counted, not
read by continuity) and not entities (no frontmatter, not in the link index).
The assistant's *Ask my notebook* action answers a question from them: keyword
retrieval with a simple score (no embeddings, no web), and it cites the notes it
used. ``project`` arguments are duck-typed: ``root`` only (deleting needs a real
``Project``: notes go to its Trash).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import fsutil

TEMPLATES = {
    "blank": ("Blank", ""),
    "idea": ("Idea", "**The idea**\n\n\n**Why it matters**\n\n\n**Where it could go**\n"),
    "location": ("Location", "**What it looks like**\n\n\n**Who is there**\n\n\n**History**\n\n\n**Scenes set here**\n"),
    "timeline": ("Timeline", "| When | What happens | Where |\n| --- | --- | --- |\n|  |  |  |\n|  |  |  |\n"),
}

NOTEBOOK_DIR = "notebook"
LEGACY_DIR = "research"       # read (and migrated) for projects made before the rename
RESEARCH_DIR = NOTEBOOK_DIR   # old name
CLIPPINGS = "clippings.md"                # "Send selection to notebook" appends here
ASSISTANT_NOTES = "assistant-notes.md"   # "Save to notes" appends here (3.4)
EXCERPT_CHARS = 1500
_STOP = frozenset("""a an and are as at be but by can did do does for from had has have how i if in is it its
me my not of on or our so than that the their them then there these they this to us was we were what when
where which who why will with would you your about into over under also any all more most some such""".split())


@dataclass(frozen=True)
class Note:
    path: Path
    rel: str          # path inside its folder, "/"-separated ("tides/almanac.md")
    title: str
    words: int
    base: str = NOTEBOOK_DIR   # notebook, or research for a legacy folder that still exists

    @property
    def id(self) -> str:
        """Project-relative id ("notebook/tides/almanac.md")."""
        return f"{self.base}/{self.rel}"


@dataclass(frozen=True)
class Hit:
    note: Note
    score: float
    excerpt: str      # the passage that matched best (capped)


def research_dir(project) -> Path:
    """The folder new notes go to."""
    return project.root / NOTEBOOK_DIR


def note_dirs(project) -> list[Path]:
    """Folders read for notes: notebook/, plus a legacy research/ when it exists."""
    dirs = [project.root / NOTEBOOK_DIR]
    legacy = project.root / LEGACY_DIR
    if legacy.is_dir():
        dirs.append(legacy)
    return dirs


def _relative(project, path: Path) -> tuple[Path, Path] | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for base in note_dirs(project):
        try:
            return base, resolved.relative_to(base.resolve())
        except (OSError, ValueError):
            continue
    return None


def is_research_path(project, path: Path | None) -> bool:
    """A Markdown file inside notebook/ (or a legacy research/), not a dot-file."""
    if path is None or path.suffix != ".md" or path.name.startswith("."):
        return False
    found = _relative(project, path)
    return found is not None and not any(part.startswith(".") for part in found[1].parts)


def migrate_folder(root: Path) -> int:
    """Move ``research/`` into ``notebook/`` (project open). Idempotent; never
    overwrites: a file whose name is taken in notebook/ stays in research/, which
    is then kept and still read. Returns how many files were moved."""
    old, new = root / LEGACY_DIR, root / NOTEBOOK_DIR
    if not old.is_dir() or old.is_symlink():
        return 0
    moved = 0
    try:
        if not new.exists():
            fsutil.replace(old, new)
            return sum(1 for p in new.rglob("*") if p.is_file())
        for src in sorted(p for p in old.rglob("*") if p.is_file() and not p.is_symlink()):
            dest = new / src.relative_to(old)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            fsutil.replace(src, dest)
            moved += 1
        for folder in sorted((p for p in old.rglob("*") if p.is_dir()), reverse=True):
            try:
                folder.rmdir()
            except OSError:
                pass
        try:
            old.rmdir()
        except OSError:
            pass
    except OSError:
        pass   # a locked file: the next open tries again; research/ is still read meanwhile
    return moved


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
    base, inner = _relative(project, path)
    return Note(path, inner.as_posix(), title_of(path, text), len(text.split()), base.name)


def list_notes(project) -> list[Note]:
    """Every note, folders first-level order then name (stable); notebook/ first."""
    out: list[Note] = []
    for base in note_dirs(project):
        if not base.is_dir():
            continue
        paths = [p for p in base.rglob("*.md") if is_research_path(project, p)]
        out += [_note(project, p) for p in sorted(paths, key=lambda p: p.relative_to(base).as_posix().casefold())]
    return out


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


def new_note(project, title: str, body: str = "", template: str = "") -> Path:
    """Create ``notebook/<slug>.md`` with a ``# title`` heading; *template* (a key
    of ``TEMPLATES``) fills the body when no *body* is given."""
    title = " ".join((title or "").split())
    if not title:
        raise ValueError("a note needs a title")
    if template and template not in TEMPLATES:
        raise ValueError("unknown note template")
    if not body.strip() and template:
        body = TEMPLATES[template][1]
    folder = research_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    path = _free_path(folder, _slug(title))
    text = body.strip("\n")
    path.write_text(f"# {title}\n\n{text}\n" if body.strip() else f"# {title}\n\n",
                    encoding="utf-8", newline="\n")
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


def delete_note(project, path: Path) -> Path:
    """Move a notebook note to the project Trash (``.trash/``; restore it from
    the Trash view). Returns its new path. The UIs confirm first."""
    return project.trash_research(path)


def append_assistant_note(project, prompt: str, reply: str, when: datetime | None = None) -> Path:
    """Save an assistant reply (*Save to notes*): append it, with the date and the
    prompt, to ``notebook/assistant-notes.md`` (created with a heading). It is an
    ordinary note afterwards - Ask my notebook can find it again."""
    reply = (reply or "").strip()
    if not reply:
        raise ValueError("there is nothing to save")
    prompt = " ".join((prompt or "").split())
    when = when or datetime.now()
    folder = research_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ASSISTANT_NOTES
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        existing = "# Assistant notes\n\nAnswers saved from the assistant, newest last.\n\n"
    heading = prompt if len(prompt) <= 70 else prompt[:69].rstrip() + "…"
    entry = f"## {when:%Y-%m-%d} - {heading or 'Saved reply'}\n\n"
    if prompt:
        entry += f"**Prompt:** {prompt}\n\n"
    entry += f"{reply}\n"
    text = existing.rstrip("\n") + "\n\n" + entry
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)
    return path


def append_clipping(project, text: str, source: str = "", when: datetime | None = None) -> Path:
    """Send a passage to the notebook (*Send selection to notebook*): append it,
    quoted, with the date and where it came from, to ``notebook/clippings.md``
    (created with a heading). The scene is never touched; the passage is a copy."""
    text = (text or "").strip()
    if not text:
        raise ValueError("select some text first")
    when = when or datetime.now()
    folder = research_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / CLIPPINGS
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        existing = "# Clippings\n\nPassages sent from the manuscript, newest last.\n\n"
    source = " ".join((source or "").split())
    entry = f"## {when:%Y-%m-%d}" + (f" - from {source}" if source else "") + "\n\n"
    entry += "\n".join(f"> {line}" if line.strip() else ">" for line in text.splitlines()) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(existing.rstrip("\n") + "\n\n" + entry, encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)
    return path


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
