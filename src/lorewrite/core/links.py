"""Parsing and locating [[wiki-links]] in manuscript text.

Syntax (minimal Obsidian subset, see SPEC.md §5):
    [[Name]]            link by entity name or alias
    [[Name|display]]    link with display text
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


@dataclass(frozen=True)
class Link:
    """A wiki-link occurrence in a text."""

    target: str  # the entity name/alias inside the brackets
    display: str | None  # text after |, if any
    start: int  # absolute offset of the opening [[
    end: int  # absolute offset one past the closing ]]

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


def link_at(text: str, offset: int) -> Link | None:
    """Return the link containing absolute *offset*, or None."""
    for link in find_links(text):
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
