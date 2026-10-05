"""Character relationships (SPEC "Character relationships").

A note declares its relationships in a ``## Relationships`` section of its
body, one per line::

    ## Relationships

    - [[Rook Tanaka]] — father; estranged
    - [[Imogen Sallow]] — employer

The section is plain Markdown: the author can edit it like any other prose,
and the app parses it for display and rewrites it only when the author accepts
an AI suggestion. Inverses are derived at read time - when another note's
section links here, that side is shown as a derived row; nothing is ever
written into the other note.

Labels are free text read from the author's point of view. An unresolved
``[[link]]`` is kept (Trash, not created yet) and reported as unresolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING = "## Relationships"

# a list item: "- " or "* ", then the first [[link]], then an optional label
# after a separator (" — ", " -- ", " - ", ": " or just spaces)
_ITEM = re.compile(r"^\s*[-*]\s+\[\[([^\[\]]+)\]\]\s*(?:[—–:\-]\s*)?(.*)$")

_SEPARATORS = "—–:-"


@dataclass(frozen=True)
class Rel:
    target: str  # the raw link text (a name or alias)
    label: str  # free text from this note's point of view, "" if none


def _sections(body: str) -> list[tuple[int, int, int]]:
    """Every Relationships section as ``(heading_start, content_start, content_end)``.

    Content runs from after the heading line to the next heading of any level
    or the end of the text."""
    out = []
    for m in re.finditer(r"^##\s+Relationships\s*$", body, re.MULTILINE | re.IGNORECASE):
        nl = body.find("\n", m.end())
        h1 = nl + 1 if nl != -1 else len(body)
        nxt = re.search(r"^#{1,6}\s", body[h1:], re.MULTILINE)
        end = h1 + nxt.start() if nxt else len(body)
        out.append((m.start(), h1, end))
    return out


def _section_span(body: str) -> tuple[int, int, int] | None:
    """The first section, or None."""
    sections = _sections(body)
    return sections[0] if sections else None


def parse(body: str) -> list[Rel]:
    """The relationships a note declares (all its Relationships sections).
    Tolerates anything: junk lines, missing links and unknown formats are
    skipped, never raised."""
    rels: list[Rel] = []
    seen: set[str] = set()
    for _h0, h1, c1 in _sections(body):
        for line in body[h1:c1].splitlines():
            m = _ITEM.match(line)
            if not m:
                continue
            target = " ".join(m.group(1).split())
            if not target or target.casefold() in seen:
                continue
            label = " ".join(m.group(2).split()).lstrip(_SEPARATORS).strip()
            rels.append(Rel(target, label))
            seen.add(target.casefold())
    return rels


def render(rels: list[Rel]) -> str:
    """The section text for *rels* (deduped, in the given order)."""
    lines, seen = [], set()
    for r in rels:
        target = " ".join(str(r.target).split())
        if not target or target.casefold() in seen:
            continue
        label = " ".join(str(r.label).split())
        seen.add(target.casefold())
        lines.append(f"- [[{target}]] — {label}" if label else f"- [[{target}]]")
    if not lines:
        return ""
    return f"{HEADING}\n\n" + "\n".join(lines) + "\n"


def set_section(body: str, rels: list[Rel]) -> str:
    """The note body with its Relationships section set to *rels*.

    The first section is replaced in place (later headings and prose are
    kept); any further sections are left alone. With no section, one is
    appended at the end. With nothing to write, the section (heading
    included) is removed. *body* is a note body without frontmatter
    (``Entity.body``)."""
    span = _section_span(body)
    text = render(rels)
    if span is None:
        if not text:
            return body
        return f"{body.rstrip(chr(10))}\n\n{text}" if body.strip() else text
    h0, h1, c1 = span
    if not text:
        head = body[:h0].rstrip("\n")
        tail = body[c1:].lstrip("\n")
        if head and tail:
            return f"{head}\n\n{tail}"
        return f"{head}\n" if head else tail
    return body[:h1] + text + body[c1:]


def rows(entity, entities: list) -> list[dict]:
    """The relationship rows shown for *entity*: what its own note declares
    (``side: "declared"``) plus derived inverses - other notes whose section
    links here (``side: "derived"``, labelled with the other note's words).

    Targets resolve by name or alias; a link with no note yet is kept as
    ``resolved: false`` and shows the raw target. ``other`` is the resolved
    note's canonical name (``""`` when unresolved)."""
    from . import entities as ent  # local: entities imports nothing from here

    out: list[dict] = []
    seen: set[str] = set()

    def add(other_name: str, target: str, label: str, side: str, resolved: bool) -> None:
        key = (side, (other_name or target).casefold(), label.casefold())
        if key in seen:
            return
        seen.add(key)
        out.append({"other": other_name, "target": target, "label": label,
                    "side": side, "resolved": resolved})

    for rel in parse(entity.body):
        other = ent.resolve(rel.target, [e for e in entities if e is not entity])
        if other is not None:
            add(other.name, rel.target, rel.label, "declared", True)
        else:
            add("", rel.target, rel.label, "declared", False)
    for other in entities:
        if other is entity or (other.path is not None and other.path == entity.path):
            continue
        for rel in parse(other.body):
            if ent.resolve(rel.target, [e for e in entities if e is not other]) is entity:
                add(other.name, other.name, rel.label, "derived", True)
    return out
