"""Summaries: what happened in each scene, kept in the project for the AI to read.

    .summaries/manuscript__01-the-recall__01-rain.md.json      one scene
    .summaries/_part__01-the-recall.json                       one part, made from its scene summaries

A scene summary is a short past-tense account, the state of each character at the END of the
scene, facts that each carry a verbatim quote, and open threads. Author data, not a cache: it
costs money to make and the author may edit or lock it, so it lives beside ``.comments/`` and
``.drafts/`` (never in ``.chisel/``) and travels with its scene on every move, rename, trash and
restore (``Structure._apply_renames`` stages it). Nothing here calls an AI.

What is summarised is the counted prose: ``scenemeta.strip(drafts.strip_pending(text, originals))``
(details frontmatter and unaccepted AI drafts are not the author's prose). ``verify`` checks a
generated summary against that text: a fact whose quote is not in the scene and a character who
is not named in it are dropped and reported, never kept silently.

``story_so_far`` and ``entity_history`` are read-time rollups over the stored summaries, so there
is no second copy to go stale. Parked scenes are not in the book and are never part of them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from . import drafts, fsutil, scenemeta
from .links import find_all_links

SUMMARIES_DIR = ".summaries"
PART_PREFIX = "_part__"
VERSION = 1
SUMMARY_WORDS = 90           # the prompt asks for at most this many words
PART_SUMMARY_WORDS = 150     # a part summary's cap (the part prompt asks for it; saving refuses more)
MIN_QUOTE = 8                # a quote (or a piece of one, see quote_check) shorter than this proves nothing
QUOTE_GAP_MAX = 2000         # pieces of a quote joined with "..." may be at most this far apart in the scene
CHARS_PER_TOKEN = 4          # the same estimate as ai/budget (core does not import ai)

MISSING, FRESH, STALE, LOCKED = "missing", "fresh", "stale", "locked"
STATUSES = (MISSING, FRESH, STALE, LOCKED)


@dataclass(frozen=True)
class Character:
    name: str
    state: str = ""     # where they are / what they know / their condition at the END of the scene


@dataclass(frozen=True)
class Fact:
    text: str
    quote: str = ""     # verbatim from the scene (parts have none)


@dataclass(frozen=True)
class Summary:
    source_hash: str = ""
    summary: str = ""
    characters: tuple[Character, ...] = ()
    facts: tuple[Fact, ...] = ()
    threads: tuple[str, ...] = ()
    model: str = ""
    created: str = ""
    cost: float = 0.0
    author_edited: bool = False
    locked: bool = False

    @property
    def protected(self) -> bool:
        """The author's own words (edited or locked): never offered for regeneration."""
        return self.locked or self.author_edited

    def as_dict(self) -> dict:
        return {"v": VERSION, "source_hash": self.source_hash, "summary": self.summary,
                "characters": [{"name": c.name, "state": c.state} for c in self.characters],
                "facts": [{"text": f.text, "quote": f.quote} for f in self.facts],
                "threads": list(self.threads), "model": self.model, "created": self.created,
                "cost": self.cost, "author_edited": self.author_edited, "locked": self.locked}


@dataclass(frozen=True)
class PartSummary:
    """A part's summary, made from its scene summaries. ``inputs`` is ((scene file name, digest), ...) of
    the scene summaries it was made from; it is stale when any digest differs or a scene came or went."""
    summary: str = ""
    characters: tuple[Character, ...] = ()
    threads: tuple[str, ...] = ()
    inputs: tuple[tuple[str, str], ...] = ()
    model: str = ""
    created: str = ""
    cost: float = 0.0
    author_edited: bool = False
    locked: bool = False
    trimmed: bool = False   # a proposal's text was cut at the word cap (shown in the review; never stored)

    @property
    def protected(self) -> bool:
        return self.locked or self.author_edited

    def as_dict(self) -> dict:
        return {"v": VERSION, "summary": self.summary,
                "characters": [{"name": c.name, "state": c.state} for c in self.characters],
                "threads": list(self.threads),
                "inputs": [{"scene": s, "hash": h} for s, h in self.inputs],
                "model": self.model, "created": self.created, "cost": self.cost,
                "author_edited": self.author_edited, "locked": self.locked}


@dataclass(frozen=True)
class Dropped:
    """Something ``verify`` removed from a generated summary, for the report."""
    kind: str       # "fact" | "character"
    text: str       # the fact text, or the character name
    reason: str


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# -- text and hashes -------------------------------------------------------------------


def prose_of(text: str, originals: dict[str, str] | None = None) -> str:
    """The text a summary is about (and is hashed from): no details block, no pending AI drafts."""
    return scenemeta.strip(drafts.strip_pending(text, originals))


def hash_of(text: str, originals: dict[str, str] | None = None) -> str:
    """sha256 of the counted prose of a scene's *text* (line endings and outer blanks ignored)."""
    prose = prose_of(text, originals).replace("\r\n", "\n").strip()
    return hashlib.sha256(prose.encode("utf-8")).hexdigest()


def _digest(s: Summary) -> str:
    """What a part summary depends on: the scene's text hash and the summary's own words."""
    return hashlib.sha256(f"{s.source_hash}\n{s.summary}".encode("utf-8")).hexdigest()


def _tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN) if text else 0


# -- storage -----------------------------------------------------------------------------


def path_for(project_root: Path, scene: Path) -> Path:
    """The one place a scene's summary file is named (keyed like ``drafts.sidecar_path``)."""
    return project_root / SUMMARIES_DIR / f"{drafts.sidecar_key(project_root, scene)}.json"


def part_path_for(project_root: Path, part: Path) -> Path:
    return project_root / SUMMARIES_DIR / f"{PART_PREFIX}{part.name}.json"


def _text(d: dict, key: str) -> str:
    return d[key].strip() if isinstance(d.get(key), str) else ""


def _characters(raw: object) -> tuple[Character, ...]:
    out = []
    for c in raw if isinstance(raw, list) else []:
        if isinstance(c, dict) and _text(c, "name"):
            out.append(Character(_text(c, "name"), _text(c, "state")))
    return tuple(out)


def _threads(raw: object) -> tuple[str, ...]:
    return tuple(t.strip() for t in raw if isinstance(t, str) and t.strip()) if isinstance(raw, list) else ()


def _cost(raw: object) -> float:
    return float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0.0


def summary_from_dict(d: object) -> Summary | None:
    if not isinstance(d, dict) or not _text(d, "summary"):
        return None
    facts = tuple(Fact(_text(f, "text"), f["quote"] if isinstance(f.get("quote"), str) else "")
                  for f in d.get("facts", []) if isinstance(f, dict) and _text(f, "text")) \
        if isinstance(d.get("facts"), list) else ()
    return Summary(_text(d, "source_hash"), _text(d, "summary"), _characters(d.get("characters")),
                   facts, _threads(d.get("threads")), _text(d, "model"), _text(d, "created"),
                   _cost(d.get("cost")), bool(d.get("author_edited")), bool(d.get("locked")))


def part_from_dict(d: object) -> PartSummary | None:
    if not isinstance(d, dict) or not _text(d, "summary"):
        return None
    inputs = tuple((_text(i, "scene"), _text(i, "hash")) for i in d.get("inputs", [])
                   if isinstance(i, dict) and _text(i, "scene")) \
        if isinstance(d.get("inputs"), list) else ()
    return PartSummary(_text(d, "summary"), _characters(d.get("characters")), _threads(d.get("threads")),
                       inputs, _text(d, "model"), _text(d, "created"), _cost(d.get("cost")),
                       bool(d.get("author_edited")), bool(d.get("locked")))


def _read(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def has_any(project_root: Path) -> bool:
    """The project has at least one stored summary (one directory listing; no scene is read). Callers use it
    to skip all summary work, so a project without summaries sends exactly what it always did."""
    try:
        return any(p.suffix == ".json" for p in (project_root / SUMMARIES_DIR).rglob("*.json"))
    except OSError:
        return False


def load(project_root: Path, scene: Path) -> Summary | None:
    """The stored summary of *scene*, or None (none, or unreadable: never an error)."""
    return summary_from_dict(_read(path_for(project_root, scene)))


def save(project_root: Path, scene: Path, summary: Summary) -> None:
    """Write atomically. The caller decides when: a generated summary is saved only when accepted."""
    _write(path_for(project_root, scene), summary.as_dict())


def delete(project_root: Path, scene: Path) -> None:
    path = path_for(project_root, scene)
    path.unlink(missing_ok=True)
    _rmdir_if_empty(path.parent)


def load_part(project_root: Path, part: Path) -> PartSummary | None:
    return part_from_dict(_read(part_path_for(project_root, part)))


def save_part(project_root: Path, part: Path, summary: PartSummary) -> None:
    _write(part_path_for(project_root, part), summary.as_dict())


def delete_part(project_root: Path, part: Path) -> None:
    path = part_path_for(project_root, part)
    path.unlink(missing_ok=True)
    _rmdir_if_empty(path.parent)


def _rmdir_if_empty(folder: Path) -> None:
    try:
        folder.rmdir()
    except OSError:
        pass


# -- status and coverage -----------------------------------------------------------------


def _scene_text(path: Path) -> str:
    try:
        return fsutil.read_text_lenient(path)
    except OSError:
        return ""


def current_hash(project, scene: Path) -> str:
    return hash_of(_scene_text(scene), drafts.load_originals(project.root, scene))


def _status(stored: Summary | None, now_hash: str) -> str:
    if stored is None:
        return MISSING
    same = stored.source_hash == now_hash
    if stored.locked or (stored.author_edited and not same):
        return LOCKED       # the author's words: offered no regeneration; see changed_since
    return FRESH if same else STALE


def status(project, scene: Path) -> str:
    """missing | fresh | stale | locked. A locked summary, or one the author edited whose scene has
    changed since, is ``locked``: never offered for regeneration (``changed_since`` says if the scene moved on)."""
    return _status(load(project.root, scene), current_hash(project, scene))


def changed_since(project, scene: Path) -> bool:
    """True when a summary exists and the scene's prose is not what it was made from (informational)."""
    stored = load(project.root, scene)
    return stored is not None and stored.source_hash != current_hash(project, scene)


@dataclass(frozen=True)
class Coverage:
    total: int
    ids: dict[str, list[str]]     # status -> scene ids in reading order

    @property
    def counts(self) -> dict[str, int]:
        return {s: len(self.ids[s]) for s in STATUSES}

    @property
    def percent(self) -> int:
        """Share of scenes that have a summary (any status but missing), 0-100."""
        return round(100 * (self.total - len(self.ids[MISSING])) / self.total) if self.total else 100


def coverage(project) -> Coverage:
    """Status of every counted scene (the book minus front matter) in reading order. Reads each
    scene: not for the UI thread of a long book."""
    ids: dict[str, list[str]] = {s: [] for s in STATUSES}
    scenes = project.counted_scenes()
    for path in scenes:
        ids[status(project, path)].append(path.relative_to(project.root).as_posix())
    return Coverage(len(scenes), ids)


# -- verification ------------------------------------------------------------------------


def _squash(text: str) -> str:
    return " ".join(text.split())


_DASHES = re.compile(r"--|\u2013|\u2014")
_ELLIPSIS = re.compile(r"\.\.\.|\[\.\.\.\]")
_EDGE = " .,;:!?\"'-"
NOT_IN_SCENE = "its quote is not in the scene"


def _fold(text: str) -> str:
    """Text for the tolerant test: straight quotes, one dash, ``...`` for the ellipsis character,
    lower case, whitespace collapsed."""
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = _DASHES.sub("-", text).replace("\u2026", "...")
    return _squash(text).lower()


def quote_check(prose: str, quote: str) -> tuple[str, str]:
    """How *quote* stands against *prose*: ("exact", "") when it is in the scene as written (or after
    collapsing whitespace), ("tolerant", "") when it passes the looser rule, else ("", reason).

    The looser rule folds both sides (see ``_fold``), strips punctuation from the quote's ends and splits it
    at ``...`` / ``[...]``. Every piece must be at least MIN_QUOTE characters, occur in the scene in order
    without overlapping, and no two consecutive pieces may be more than QUOTE_GAP_MAX characters apart.
    A quote without an ellipsis is one piece. The words are always the scene's own; the check proves the
    quote exists, never that it supports the fact beside it."""
    if len(_squash(quote)) >= MIN_QUOTE and (quote in prose or _squash(quote) in _squash(prose)):
        return "exact", ""
    pieces = [p for p in (x.strip(_EDGE) for x in _ELLIPSIS.split(_fold(quote))) if p]
    if not pieces:
        return "", NOT_IN_SCENE
    if any(len(p) < MIN_QUOTE for p in pieces):
        return "", NOT_IN_SCENE if len(pieces) == 1 else             f"a piece of its quote (between ...) is shorter than {MIN_QUOTE} characters"
    folded = _fold(prose)
    end, found = 0, []
    for piece in pieces:
        at = folded.find(piece, end)
        if at < 0:
            if len(pieces) == 1:
                return "", NOT_IN_SCENE
            anywhere = folded.find(piece) >= 0
            return "", ("the pieces of its quote are not in the scene in that order" if anywhere
                        else NOT_IN_SCENE)
        if found and at - end > QUOTE_GAP_MAX:
            return "", f"the pieces of its quote are more than {QUOTE_GAP_MAX} characters apart in the scene"
        found.append(at)
        end = at + len(piece)
    return "tolerant", ""


def quote_found(prose: str, quote: str) -> bool:
    """*quote* is in *prose* by ``quote_check``'s exact or tolerant rule."""
    return bool(quote_check(prose, quote)[0])


def name_found(prose: str, name: str) -> bool:
    """*name* occurs in *prose* as a whole word or phrase (case-insensitive)."""
    parts = name.split()
    if not parts:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in parts) + r"(?!\w)"
    return re.search(pattern, prose, re.IGNORECASE) is not None


def verify(summary: Summary, scene_text: str,
           originals: dict[str, str] | None = None) -> tuple[Summary, list[Dropped]]:
    """The summary with every unverifiable claim removed, and what was removed (names, for the
    report). A fact stays only if its quote is in the scene's prose (``quote_check``); a character stays only
    if the name occurs in it. *scene_text* is the file's text (details and pending drafts are ignored)."""
    clean, dropped, _ = verify_counted(summary, scene_text, originals)
    return clean, dropped


def verify_counted(summary: Summary, scene_text: str, originals: dict[str, str] | None = None
                   ) -> tuple[Summary, list[Dropped], int]:
    """``verify`` plus how many kept facts needed the tolerant quote rule."""
    prose = prose_of(scene_text, originals)
    facts, characters, dropped, tolerant = [], [], [], 0
    for f in summary.facts:
        rule, reason = quote_check(prose, f.quote)
        if rule:
            facts.append(f)
            tolerant += rule == "tolerant"
        else:
            dropped.append(Dropped("fact", f.text, reason if f.quote.strip() else "it has no quote"))
    for c in summary.characters:
        if name_found(prose, c.name):
            characters.append(c)
        else:
            dropped.append(Dropped("character", c.name, "the name does not occur in the scene"))
    return replace(summary, facts=tuple(facts), characters=tuple(characters)), dropped, tolerant


# -- part summaries ----------------------------------------------------------------------


def part_inputs(project, part: Path) -> tuple[tuple[str, str], ...]:
    """(scene file name, digest) of every scene of *part* that has a summary, in reading order. Names,
    not ids, so moving the whole part does not make its summary stale."""
    out = []
    for path in project.part_scenes(part):
        s = load(project.root, path)
        if s is not None:
            out.append((path.name, _digest(s)))
    return tuple(out)


def part_status(project, part: Path) -> str:
    """missing | fresh | stale | locked, as for scenes: stale when a scene summary it was made from
    changed, or one was added or removed."""
    stored = load_part(project.root, part)
    if stored is None:
        return MISSING
    same = stored.inputs == part_inputs(project, part)
    if stored.locked or (stored.author_edited and not same):
        return LOCKED
    return FRESH if same else STALE


# -- rollups -----------------------------------------------------------------------------


def _earlier(project, scene_id: str, through: bool = False) -> tuple[list[Path], str, str]:
    """The book scenes before *scene_id* that count as earlier (front matter excluded), with the mode
    (``chronological`` | ``reading-order``) and its sentence. By story time when the project has any
    (``timeline.scenes_up_to``), else reading order; never re-sorted. *through* keeps *scene_id* itself."""
    from . import timeline
    found = timeline.scenes_up_to(project, scene_id)
    paths = [t.path for t in found.scenes
             if (through or t.id != scene_id) and not project.is_front_matter(t.path)]
    return paths, found.mode, found.sentence


def _scene_block(project, path: Path, s: Summary) -> str:
    lines = [f"{project.scene_title(path)}: {s.summary}"]
    if s.characters:
        lines.append("  At the end: " + "; ".join(
            f"{c.name} - {c.state}" if c.state else c.name for c in s.characters))
    if s.threads:
        lines.append("  Open: " + "; ".join(s.threads))
    return "\n".join(lines)


@dataclass(frozen=True)
class StoryBlock:
    name: str                 # what the sent report calls it: a part title or a scene title
    text: str
    kind: str                 # "part" | "scene"
    scenes: tuple[str, ...]   # scene ids it covers
    stale: bool = False       # a part summary older than its scene summaries


@dataclass(frozen=True)
class StorySoFar:
    blocks: tuple[StoryBlock, ...] = ()           # oldest first, newest last
    missing: tuple[str, ...] = ()                 # earlier scenes with no summary (titles)
    dropped: tuple[str, ...] = ()                 # left out to fit cap_tokens (names, oldest first)
    mode: str = "reading-order"
    sentence: str = ""

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


def story_so_far(project, up_to_scene: str, cap_tokens: int | None = None,
                 through: bool = False) -> StorySoFar:
    """The book before *up_to_scene* (a scene id), from the stored summaries. Earlier parts are one
    block each (the part summary if there is one, else its scene summaries joined); the current
    part's earlier scenes are one block each, newest last. Scenes with no summary are named in
    ``missing``. With *cap_tokens* the oldest blocks are dropped first and named in ``dropped``.
    ``mode`` / ``sentence`` say whether story time or reading order decided what is earlier.
    *through* includes *up_to_scene* itself (the whole book up to its last scene)."""
    paths, mode, sentence = _earlier(project, up_to_scene, through)
    target = project.root / up_to_scene
    current = project.part_of(target)
    groups: list[tuple[Path | None, list[Path]]] = []
    for path in paths:
        part = project.part_of(path)
        if not groups or groups[-1][0] != part:
            groups.append((part, []))
        groups[-1][1].append(path)
    blocks: list[StoryBlock] = []
    missing: list[str] = []
    for part, members in groups:
        stored = {p: load(project.root, p) for p in members}
        missing += [project.scene_title(p) for p, s in stored.items() if s is None]
        have = [(p, s) for p, s in stored.items() if s is not None]
        ids = tuple(p.relative_to(project.root).as_posix() for p, _ in have)
        if part is not None and part != current and (ps := load_part(project.root, part)) is not None:
            blocks.append(StoryBlock(project.part_title(part), f"{project.part_title(part)}: {ps.summary}",
                                     "part", ids, part_status(project, part) == STALE))
        elif part is not None and part != current and have:
            blocks.append(StoryBlock(project.part_title(part),
                                     "\n".join(_scene_block(project, p, s) for p, s in have), "part", ids))
        else:
            blocks += [StoryBlock(project.scene_title(p), _scene_block(project, p, s), "scene",
                                  (p.relative_to(project.root).as_posix(),)) for p, s in have]
    dropped: list[str] = []
    if cap_tokens is not None:
        kept, used = [], 0
        for b in reversed(blocks):          # newest first
            cost = _tokens(b.text)
            if dropped or used + cost > cap_tokens:
                dropped.append(b.name)
            else:
                kept.append(b)
                used += cost
        blocks, dropped = kept[::-1], dropped[::-1]
    return StorySoFar(tuple(blocks), tuple(missing), tuple(dropped), mode, sentence)


@dataclass(frozen=True)
class HistoryItem:
    scene_id: str
    title: str
    summary: str              # the block text (summary, end states, open threads)
    rank: int                 # 0 = first appearance, then 1, 2, ... newest first


@dataclass(frozen=True)
class EntityHistory:
    items: tuple[HistoryItem, ...] = ()            # reading order
    missing: tuple[str, ...] = ()                  # earlier scenes naming them that have no summary (titles)
    omitted: tuple[str, ...] = ()                  # earlier scenes naming them left out by *limit* (titles)
    mode: str = "reading-order"
    sentence: str = ""


def mentions(project, scene: Path, entity) -> bool:
    """*entity* (name or alias) is named in the scene's prose, or is its POV or place."""
    text = scenemeta.blank(prose_with_details(scene, project), keep=scenemeta.MENTION_FIELDS)
    return any(entity.matches(link.target) for link in find_all_links(text, entity.names))


def prose_with_details(scene: Path, project) -> str:
    """The scene's text without pending AI drafts but WITH its details block (for mention scans)."""
    return drafts.strip_pending(_scene_text(scene), drafts.load_originals(project.root, scene))


def entity_history(project, entity, up_to_scene: str, limit: int = 5) -> EntityHistory:
    """Summaries of the earlier scenes that name *entity*: the first appearance always, then the
    newest, at most *limit* in all. A first appearance with no summary is named in ``missing``
    (it cannot be shown). Items are in reading order; ``rank`` is their importance."""
    paths, mode, sentence = _earlier(project, up_to_scene)
    hits = [p for p in paths if mentions(project, p, entity)]
    chosen: list[Path] = []
    if hits:
        chosen = [hits[0]] + hits[1:][::-1][:max(0, limit - 1)]
    left_out = tuple(project.scene_title(p) for p in hits if p not in chosen)
    items, missing = [], []
    for rank, path in enumerate(chosen):
        s = load(project.root, path)
        if s is None:
            missing.append(project.scene_title(path))
        else:
            items.append(HistoryItem(path.relative_to(project.root).as_posix(), project.scene_title(path),
                                     _scene_block(project, path, s), rank))
    items.sort(key=lambda i: [p.relative_to(project.root).as_posix() for p in paths].index(i.scene_id))
    return EntityHistory(tuple(items), tuple(missing), left_out, mode, sentence)


# -- the facts ledger --------------------------------------------------------------------

FACTS_PER_ENTITY = 60       # the most facts a ledger lists per entity (the rest is counted, never silently cut)
FACTS_FIRST = 10            # of those, this many are the earliest (first appearances); the others are the newest


@dataclass(frozen=True)
class FactItem:
    text: str
    scene_id: str
    title: str
    count: int = 1            # how many earlier scenes state exactly this text (the earliest one is kept)


@dataclass(frozen=True)
class EntityFacts:
    items: tuple[FactItem, ...] = ()               # reading order
    total: int = 0                                 # facts after merging duplicates, before the cap
    omitted: int = 0                               # left out by the cap (total - len(items))
    omitted_scenes: tuple[str, ...] = ()           # titles of the scenes the omitted facts came from
    mode: str = "reading-order"
    sentence: str = ""
    limit: int = 0                                 # the cap that was applied (0: none)


def _mentions_name(text: str, entity) -> bool:
    return any(name_found(text, name) for name in entity.names)


def entity_facts(project, entity, up_to_scene: str, limit: int = FACTS_PER_ENTITY) -> EntityFacts:
    """The verified facts of the EARLIER scenes (never the scene itself or later ones) that are about *entity*: those of
    a scene summary that lists the entity among its characters, and any fact whose text names it (its name or an
    alias, as a whole word). Reading order; a fact stated with exactly the same text in several scenes is listed once
    (the earliest) with its ``count``. Over *limit* the earliest ``FACTS_FIRST`` and the newest rest are kept, so first
    appearances survive; ``omitted`` / ``omitted_scenes`` say what the cap left out. Reads sidecars: not for the UI thread."""
    paths, mode, sentence = _earlier(project, up_to_scene)
    merged: dict[str, int] = {}
    items: list[FactItem] = []
    for path in paths:
        s = load(project.root, path)
        if s is None or not s.facts:
            continue
        listed = any(entity.matches(c.name) for c in s.characters)
        scene_id, title = path.relative_to(project.root).as_posix(), project.scene_title(path)
        for f in s.facts:
            text = _squash(f.text)
            if not text or not (listed or _mentions_name(text, entity)):
                continue
            if text in merged:
                i = merged[text]
                items[i] = replace(items[i], count=items[i].count + 1)
            else:
                merged[text] = len(items)
                items.append(FactItem(text, scene_id, title))
    return cap_facts(EntityFacts(tuple(items), len(items), 0, (), mode, sentence), limit)


def cap_facts(full: EntityFacts, limit: int) -> EntityFacts:
    """*full* (an uncapped ledger) cut to *limit* facts: the earliest ``FACTS_FIRST`` and the newest rest, so first appearances
    survive; ``omitted`` / ``omitted_scenes`` say what was left out (counts and scene titles: a fact has no short name)."""
    items = list(full.items)
    total = len(items)
    if total <= limit:
        return replace(full, limit=limit)
    first = min(FACTS_FIRST, limit)
    kept = items[:first] + (items[total - (limit - first):] if limit > first else [])
    dropped = items[first:total - (limit - first)]
    titles = tuple(dict.fromkeys(i.title for i in dropped))
    return EntityFacts(tuple(kept), total, len(dropped), titles, full.mode, full.sentence, limit)


# -- moves with the scene (same pattern as comments / snapshots) -------------------------


def stage(project_root: Path, scene: Path, tag: str) -> Path | None:
    old = path_for(project_root, scene)
    if not old.is_file():
        return None
    tmp = old.with_name(f".mv{tag}-{old.name}")
    fsutil.replace(old, tmp)
    return tmp


def unstage(project_root: Path, staged: Path, new_scene: Path) -> None:
    new = path_for(project_root, new_scene)
    new.parent.mkdir(parents=True, exist_ok=True)
    fsutil.replace(staged, new)


def archive(project_root: Path, scene: Path, dest: Path) -> None:
    """Move the summary to *dest* (the Trash keeps a deleted scene's summary)."""
    old = path_for(project_root, scene)
    if old.is_file():
        fsutil.replace(old, dest)
        _rmdir_if_empty(old.parent)


def unarchive(project_root: Path, src: Path, scene: Path) -> None:
    if src.is_file():
        new = path_for(project_root, scene)
        new.parent.mkdir(parents=True, exist_ok=True)
        fsutil.replace(src, new)


def stage_part(project_root: Path, part: Path, tag: str) -> Path | None:
    old = part_path_for(project_root, part)
    if not old.is_file():
        return None
    tmp = old.with_name(f".mv{tag}-{old.name}")
    fsutil.replace(old, tmp)
    return tmp


def unstage_part(project_root: Path, staged: Path, new_part: Path) -> None:
    fsutil.replace(staged, part_path_for(project_root, new_part))
