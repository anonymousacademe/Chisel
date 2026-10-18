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
from .paper.types import CiteRef, Citation

WIKILINK_RE = re.compile(r"(?<!\\)\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


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


# Targets owned by other parsers (research mode): citations and object references. The link
# parser must never see them, or they would show as unresolved links, be indexed as folded
# targets, be offered for "create note" and be touched by rename and backlinks.
_OBJECT_PREFIXES = ("fig:", "tbl:", "eq:")


def is_foreign_target(target: str) -> bool:
    """True for a ``[[...]]`` target that is a citation or an object reference, not a link."""
    t = target.strip()
    return (t.startswith(("@", "-@", "+@")) or " @" in t or t.startswith(_OBJECT_PREFIXES))


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
        if not is_foreign_target(m.group(1))
    ]


# -- citations (research mode; docs/dev/research-mode-contracts.md "Parsing") ----------------

# a backslash before a bracket makes it literal (the Zotero note sanitiser writes \[ and \])
_BRACKETED_RE = re.compile(r"(?<!\\)\[\[([^\[\]]+?)\]\]")
_PANDOC_RE = re.compile(r"(?<![\[\\])\[([^\[\]]*@[^\[\]]*?)(?<!\\)\](?![\[(\]])")
# pandoc keys: a word character, then word characters and internal punctuation, ending in a word char
_KEY = r"\w(?:[\w:.#$%&\-+?<>~/]*\w)?"
_REF_RE = re.compile(rf"^(?P<prefix>.*?)(?P<neg>-)?(?<![\w])@(?P<key>{_KEY})(?P<rest>.*)$", re.DOTALL)
_NUM = r"(?:\d+[A-Za-z]?|[IVXLC]+(?![A-Za-z]))"
_LOCATOR_RE = re.compile(
    rf"^(?P<loc>(?:[A-Za-z]{{1,8}}\.?\s*|[§¶]\s*)?{_NUM}(?:\s*[-–—,&]\s*{_NUM})*)(?P<suf>.*)$", re.DOTALL)


def _parse_ref(part: str) -> CiteRef | None:
    m = _REF_RE.match(part)
    if not m:
        return None
    rest = m.group("rest").strip()
    locator = suffix = ""
    if rest.startswith(","):
        after = rest[1:].strip()
        lm = _LOCATOR_RE.match(after)
        if lm:
            locator = lm.group("loc").strip()
            suffix = lm.group("suf").strip().lstrip(",").strip()
        else:
            suffix = after
    else:
        suffix = rest
    return CiteRef(key=m.group("key"), prefix=m.group("prefix").strip(), locator=locator,
                   suffix=suffix, suppress_author=bool(m.group("neg")))


def _parse_refs(content: str) -> list[CiteRef]:
    refs = []
    for part in content.split(";"):
        ref = _parse_ref(part)
        if ref is not None:
            refs.append(ref)
    return refs


def find_citations(text: str) -> list[Citation]:
    """Every citation in *text*, in document order: ``[[@k]]``, ``[[+@k]]`` (narrative),
    ``[[see @a, p. 12; @b]]``, ``[[-@k]]`` and plain pandoc ``[@k; @j]``. Keys are case-sensitive.
    Offsets are code points. The only citation parser; ``find_links`` ignores these."""
    if "@" not in text:
        return []
    found: list[Citation] = []
    taken: list[tuple[int, int]] = []
    for m in _BRACKETED_RE.finditer(text):
        inner = m.group(1)
        if not is_foreign_target(inner.split("|", 1)[0]):
            continue
        t = inner.strip()
        if t.startswith(_OBJECT_PREFIXES):
            continue
        narrative = t.startswith("+@")
        refs = _parse_refs(t[1:] if narrative else t)
        if not refs:
            continue
        found.append(Citation(refs=refs, start=m.start(), end=m.end(), raw=m.group(0),
                              kind="narrative" if narrative else "bracketed"))
        taken.append((m.start(), m.end()))
    for m in _PANDOC_RE.finditer(text):
        if any(s < m.end() and m.start() < e for s, e in taken):
            continue
        refs = _parse_refs(m.group(1))
        if refs:
            found.append(Citation(refs=refs, start=m.start(), end=m.end(), raw=m.group(0),
                                  kind="pandoc"))
    return sorted(found, key=lambda c: c.start)


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
    taken = sorted([(l.start, l.end) for l in find_links(text)]
                   + [(c.start, c.end) for c in find_citations(text)])
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
