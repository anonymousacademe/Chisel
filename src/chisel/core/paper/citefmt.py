"""On-screen display strings for citations (research mode), an approximation of APA author-year.

The export uses the real CSL style; this text is only what the editor shows in place of ``[[@key]]``.
Pure: it takes the parsed ``Citation`` and a ``{key: CiteSource}`` map built from the source notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .types import Citation, CiteRef


@dataclass(frozen=True)
class CiteSource:
    names: list[str] = field(default_factory=list)   # family name, or the literal/corporate name, per author
    year: str = ""                                    # "" when the CSL has no issued date
    title: str = ""


def _names(csl: dict) -> list[str]:
    out = []
    for a in csl.get("author") or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("family") or a.get("literal") or a.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def csl_year(csl: dict) -> int | None:
    """The issued year of a CSL dict: date-parts first, then a four-digit year in raw / literal."""
    issued = csl.get("issued") if isinstance(csl, dict) else None
    if isinstance(issued, dict):
        try:
            return int(issued["date-parts"][0][0])
        except (TypeError, ValueError, IndexError, KeyError):
            pass
        m = re.search(r"\b(\d{4})\b", str(issued.get("raw") or issued.get("literal") or ""))
        if m:
            return int(m.group(1))
    return None


def _year(csl: dict) -> str:
    y = csl_year(csl)
    return "" if y is None else str(y)


def source_record(csl: dict | None, title: str = "") -> CiteSource:
    """A ``CiteSource`` from a note's CSL dict (anything unusable gives an empty record)."""
    csl = csl if isinstance(csl, dict) else {}
    return CiteSource(_names(csl), _year(csl), str(title or csl.get("title") or ""))


def _letter(i: int) -> str:
    """0 -> a ... 25 -> z, 26 -> aa, 27 -> ab ..."""
    return chr(ord("a") + i) if i < 26 else _letter(i // 26 - 1) + chr(ord("a") + i % 26)


def _short_title(title: str) -> str:
    words = title.split()[:3]
    return '"' + " ".join(words) + '"' if words else ""


def _who(s: CiteSource, narrative: bool) -> str:
    """The author part as displayed: the names, or a short quoted title when the source has no authors."""
    return _authors(s, narrative) or _short_title(s.title)


def suffixes(sources: dict[str, CiteSource]) -> dict[str, str]:
    """``{key: "a"|"b"|...}`` for sources whose displayed author text and year are the same as another's.
    Sharers are ordered by title then key, so adding an unrelated source never changes a letter."""
    groups: dict[tuple[str, str], list[str]] = {}
    for key, s in sources.items():
        who = _who(s, False)
        if who and s.year:
            groups.setdefault((who.casefold(), s.year), []).append(key)
    out: dict[str, str] = {}
    for keys in groups.values():
        if len(keys) < 2:
            continue
        keys.sort(key=lambda k: (sources[k].title.casefold(), k))
        for i, k in enumerate(keys):
            out[k] = _letter(i)
    return out


def _authors(s: CiteSource, narrative: bool) -> str:
    if not s.names:
        return ""
    if len(s.names) == 1:
        return s.names[0]
    if len(s.names) == 2:
        return f"{s.names[0]} {'and' if narrative else '&'} {s.names[1]}"
    return f"{s.names[0]} et al."


def format_citation(citation: Citation, sources: dict[str, CiteSource],
                    letters: dict[str, str] | None = None) -> str:
    """The display string of one citation group. *letters* may be passed to avoid recomputing
    ``suffixes(sources)`` for every citation of a document."""
    letters = suffixes(sources) if letters is None else letters
    narrative = citation.kind == "narrative"
    parts = [_one(ref, sources.get(ref.key), letters.get(ref.key, ""), narrative) for ref in citation.refs]
    return "; ".join(parts) if narrative else "(" + "; ".join(parts) + ")"


def _one(ref: CiteRef, s: CiteSource | None, letter: str, narrative: bool) -> str:
    if s is None:
        return ref.key
    year = (s.year + letter) if s.year else "n.d."
    tail = year + (f", {ref.locator.strip()}" if ref.locator.strip() else "")
    who = _who(s, narrative)
    if narrative:
        return f"{who} ({tail})" if who and not ref.suppress_author else f"({tail})"
    prefix = (ref.prefix.strip() + " ") if ref.prefix.strip() else ""
    if ref.suppress_author or not who:
        return prefix + tail
    return f"{prefix}{who}, {tail}"
