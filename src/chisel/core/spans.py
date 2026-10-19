"""Link/draft spans of a text, for editors that decorate it (the GUI).

One pass over core.links and core.drafts describes everything an editor needs
to style: plain-name mentions, explicit [[links]] (resolved or not, with the
visible inner range so brackets and ``Name|`` can be hidden), pending AI drafts
and ``{{expand: …}}`` markers. Matching stays here; front ends never redo it.

Offsets are code points (Python str indexes); ``to_utf16`` converts them for
JavaScript editors, whose offsets are UTF-16 code units.
"""

from __future__ import annotations

from . import drafts
from . import entities as ent
from . import scenemeta
from .links import WIKILINK_RE, find_all_links

_OFFSET_KEYS = ("start", "end", "innerStart", "innerEnd", "bodyStart", "bodyEnd")


def compute_spans(text: str, entities: list[ent.Entity], *,
                  mentions: bool = True, script: bool = False,
                  citations: bool = False) -> list[dict]:
    """Spans in document order. *mentions*: also report plain-text mentions of
    entity names/aliases (scenes do; entity notes and the style guide only
    show explicit links). Links and mentions inside pending AI drafts are
    ignored: unaccepted text is not canon. With *script* (a scene of a script project) the speaker of
    every character cue also counts as a mention (``KEITH`` is the character Keith), and one
    ``{"kind": "script", "element", ...}`` span per formatted line is added (core/fountain.py)."""
    pending = drafts.find_pending(text)
    names = [n for e in entities for n in e.names] if mentions else None
    spans: list[dict] = []
    scan = drafts.blank_pending(text)
    if mentions:  # scenes: the frontmatter block is not prose
        scan = scenemeta.blank(scan)
    for link in find_all_links(scan, names):
        entity = ent.resolve(link.target, entities)
        span: dict = {
            "kind": "mention" if not link.explicit
            else ("link" if entity else "unresolved"),
            "start": link.start, "end": link.end, "target": link.target,
        }
        if link.explicit:
            m = WIKILINK_RE.match(text, link.start)
            inner = (m.start(2), m.end(2)) if m and m.group(2) else (
                (m.start(1), m.end(1)) if m else (link.start, link.end))
            span["innerStart"], span["innerEnd"] = inner
        if entity is not None:
            span["entity"] = entity.name
            span["etype"] = entity.type
        spans.append(span)
    for p in pending:
        spans.append({"kind": "pending", "start": p.start, "end": p.end,
                      "bodyStart": p.body_start, "bodyEnd": p.body_end,
                      "id": p.id})
    for marker in drafts.find_expand_markers(drafts.blank_pending(text)):
        spans.append({"kind": "expand", "start": marker.start,
                      "end": marker.end, "instruction": marker.instruction})
    if citations:
        spans += _citation_spans(scan, entities)
    if script:
        from . import fountain
        spans += _cue_mentions(text, entities, spans, pending) if mentions else []
        spans += fountain.spans(text)
    spans.sort(key=lambda s: (s["start"], s["end"]))
    return spans


def _citation_spans(scan: str, entities: list[ent.Entity]) -> list[dict]:
    """One ``citation`` span per ``[[@key]]`` group (research projects): resolved when every key names a
    source note; ``label`` is the author-year display (several joined with "; "), ``title`` the paper title."""
    from .links import find_citations
    from .paper import citefmt
    found = find_citations(scan)
    records = {}
    if found:
        records = {ent.source_key(e): citefmt.source_record(e.extra.get("csl"), source_title(e))
                   for e in entities if e.is_source}
    letters = citefmt.suffixes(records)
    out = []
    for cite in found:
        keys, labels, titles, ok = [], [], [], True
        for ref in cite.refs:
            keys.append(ref.key)
            source = ent.resolve_key(ref.key, entities)
            if source is None:
                ok = False
                labels.append(ref.key)
                continue
            labels.append(source.aliases[0] if source.aliases else ref.key)
            titles.append(source_title(source))
        out.append({"kind": "citation", "start": cite.start, "end": cite.end,
                    "status": "resolved" if ok else "unresolved", "keys": keys,
                    "label": "; ".join(labels),
                    "display": citefmt.format_citation(cite, records, letters),
                    "title": "; ".join(t for t in titles if t) if ok else ""})
    return out


def source_title(source: ent.Entity) -> str:
    """The paper title of a source note (frontmatter ``title``, else the CSL title, else "")."""
    title = source.extra.get("title")
    if not title and isinstance(source.extra.get("csl"), dict):
        title = source.extra["csl"].get("title")
    return str(title or "")


def _cue_mentions(text: str, entities: list[ent.Entity], spans: list[dict], pending) -> list[dict]:
    """Mention spans for the speakers of character cues that name an entity (case-insensitive), skipping a cue
    that already carries a link or mention and cues inside pending AI drafts."""
    from . import fountain
    taken = [(s["start"], s["end"]) for s in spans if s["kind"] in ("mention", "link", "unresolved")]
    out = []
    for start, end, name in fountain.cues(text):
        if any(p.start <= start < p.end for p in pending) or any(a < end and start < b for a, b in taken):
            continue
        entity = ent.resolve(name, entities)
        if entity is None:
            continue
        out.append({"kind": "mention", "start": start, "end": end, "target": name,
                    "entity": entity.name, "etype": entity.type})
    return out


def to_utf16(text: str, spans: list[dict]) -> list[dict]:
    """Convert span offsets from code points to UTF-16 code units."""
    if all(ord(c) <= 0xFFFF for c in text):
        return spans
    units = [0]
    for c in text:
        units.append(units[-1] + (2 if ord(c) > 0xFFFF else 1))
    out = []
    for span in spans:
        span = dict(span)
        for key in _OFFSET_KEYS:
            if key in span:
                span[key] = units[span[key]]
        out.append(span)
    return out


def utf16_len(s: str) -> int:
    """Length of *s* in UTF-16 code units (what JavaScript calls .length)."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def from_utf16(text: str, offset: int) -> int:
    """Code-point index of a UTF-16 offset into *text* (clamped)."""
    if all(ord(c) <= 0xFFFF for c in text):
        return max(0, min(offset, len(text)))
    units = 0
    for i, c in enumerate(text):
        if units >= offset:
            return i
        units += 2 if ord(c) > 0xFFFF else 1
    return len(text)


def index_to_utf16(text: str, index: int) -> int:
    """UTF-16 offset of the code-point *index* in *text*."""
    return utf16_len(text[:index])
