"""Parsing and locating [[wiki-links]] in manuscript text.

Syntax (minimal Obsidian subset, see SPEC.md §5):
    [[Name]]            link by entity name or alias
    [[Name|display]]    link with display text

Brackets are optional: once an entity note exists, plain-text mentions of its
name or aliases are found by find_mentions() and treated as links (implicit
mentions). Files are never rewritten to add brackets.
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache

from .entities import _QUOTES

WIKILINK_RE =re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


@dataclass(frozen=True)
class Link:
    """A wiki-link occurrence in a text."""

    target: str  # the entity name/alias inside the brackets
    display: str | None  # text after |, if any
    start: int  # absolute offset of the opening [[
    end: int  # absolute offset one past the closing ]]
    explicit: bool = True  # False: plain-text mention of a known name

    @property
    def text(self) -> str:
        return self.display if self.display else self.target


def find_links(text: str) -> list[Link]:
    """Return all wiki-links in *text*, in document order."""
    return [
        Link(
            target=m.group(1).strip(),
            display=m.group(2).strip() if m.group(2) else None,
            start=m.start(),
            end=m.end(),
        )
        for m in WIKILINK_RE.finditer(text)
    ]


MIN_MENTION_LENGTH = 2


def _nfd(text: str) -> str:
    """Matching form: curly quotes straight, canonically decomposed."""
    return unicodedata.normalize("NFD", text.translate(_QUOTES))


def _norm_with_map(text: str) -> tuple[str, list[int] | None]:
    """(matching form of *text*, normalized index -> original index). The map
    has len+1 entries; it is None when the text needs no normalizing."""
    if text.isascii():
        return text, None
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        piece = ch if ch.isascii() else _nfd(ch)
        out.append(piece)
        idx.extend([i] * len(piece))
    idx.append(len(text))
    return "".join(out), idx


@lru_cache(maxsize=16)
def _mention_re(names: tuple[str, ...]) -> re.Pattern | None:
    variants: set[str] = set()
    for name in names:
        name = _nfd(name.strip())
        if len(name) < MIN_MENTION_LENGTH:
            continue
        variants.add(name)
        variants.add(name[0].upper() + name[1:])  # "the captain" at sentence start
    if not variants:
        return None
    # Longest first so "Elara Vance" wins over "Elara" at the same start.
    # Zero-width lookahead so overlapping candidates are all reported.
    alternation = "|".join(
        re.escape(v) for v in sorted(variants, key=len, reverse=True))
    word = r"[\ẁ-ͯ]"  # combining accents belong to their letter
    return re.compile(rf"(?=(?<!{word})({alternation})(?!{word}))")


def find_mentions(text: str, names: list[str]) -> list[Link]:
    """Plain-text mentions of *names* (entity names/aliases) outside [[links]].

    Case-sensitive as written in the note (so the name "Will" doesn't match
    "will"), except that a leading capital is allowed for sentence starts.
    Overlapping candidates resolve to the longest ("the Hollow Market" with
    names "the Hollow" and "Hollow Market" yields "Hollow Market").
    """
    pattern = _mention_re(tuple(sorted(set(names))))
    if pattern is None:
        return []
    # Disjoint intervals kept sorted by start: an overlap test only needs the
    # one interval starting last before the candidate's end (was O(n^2)).
    taken = sorted((l.start, l.end) for l in find_links(text))
    starts = [s for s, _ in taken]
    norm, idx = _norm_with_map(text)
    spans = ((m.start(1), m.end(1)) for m in pattern.finditer(norm))
    if idx is not None:  # report offsets against the ORIGINAL text
        spans = ((idx[s], idx[e - 1] + 1) for s, e in spans)
    candidates = sorted(
        spans,
        key=lambda span: (span[0] - span[1], span[0]),  # longest, then leftmost
    )
    chosen = []
    for start, end in candidates:
        i = bisect_left(starts, end)
        if i and taken[i - 1][1] > start:
            continue
        at = bisect_left(starts, start)
        starts.insert(at, start)
        taken.insert(at, (start, end))
        chosen.append((start, end))
    return [Link(target=text[start:end], display=None, start=start, end=end,
                 explicit=False) for start, end in sorted(chosen)]


def find_all_links(text: str, names: list[str] | None = None) -> list[Link]:
    """Explicit [[links]] plus, if *names* given, implicit mentions; in order."""
    links = find_links(text)
    if names:
        links = sorted(links + find_mentions(text, names), key=lambda l: l.start)
    return links


def link_at(text: str, offset: int, names: list[str] | None = None) -> Link | None:
    """Return the link (or, with *names*, mention) containing *offset*."""
    for link in find_all_links(text, names):
        if link.start <= offset <= link.end:
            return link
    return None


def offset_to_rowcol(text: str, offset: int) -> tuple[int, int]:
    """Convert an absolute offset to a (row, col) pair, 0-based."""
    row = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset) + 1
    return row, offset - line_start


def rowcol_to_offset(text: str, row: int, col: int) -> int:
    """Convert a 0-based (row, col) pair to an absolute offset."""
    if row == 0:
        return min(col, len(text))
    pos = -1
    for _ in range(row):
        pos = text.find("\n", pos + 1)
        if pos == -1:
            return len(text)
    return min(pos + 1 + col, len(text))
