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
from dataclasses import dataclass
from functools import lru_cache

WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


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


@lru_cache(maxsize=16)
def _mention_re(names: tuple[str, ...]) -> re.Pattern | None:
    variants: set[str] = set()
    for name in names:
        name = name.strip()
        if len(name) < MIN_MENTION_LENGTH:
            continue
        variants.add(name)
        variants.add(name[0].upper() + name[1:])  # "the captain" at sentence start
    if not variants:
        return None
    # Longest first so "Elara Vance" wins over "Elara".
    alternation = "|".join(
        re.escape(v) for v in sorted(variants, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternation})(?!\w)")


def find_mentions(text: str, names: list[str]) -> list[Link]:
    """Plain-text mentions of *names* (entity names/aliases) outside [[links]].

    Case-sensitive as written in the note (so the name "Will" doesn't match
    "will"), except that a leading capital is allowed for sentence starts.
    """
    pattern = _mention_re(tuple(sorted(set(names))))
    if pattern is None:
        return []
    explicit = [(l.start, l.end) for l in find_links(text)]
    mentions = []
    for m in pattern.finditer(text):
        if any(s < m.end() and m.start() < e for s, e in explicit):
            continue
        mentions.append(Link(target=m.group(0), display=None,
                             start=m.start(), end=m.end(), explicit=False))
    return mentions


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
