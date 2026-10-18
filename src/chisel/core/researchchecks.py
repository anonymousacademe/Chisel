"""Research checks: a read-only report on a research project's citations, sources, figures, tables and equations
(docs/dev/plan-research-mode.md 6.2). Like the continuity check it only reports; it never writes.

Checks and their kinds (``Flag.kind``):

- ``citation-unresolved`` (blocks export): a citation key with no source note.
- ``ref-missing`` (blocks export): a placement or a reference to a figure, table or equation that does not exist.
- ``source-uncited``: a source note that no scene cites.
- ``source-missing``: a source note whose Zotero item was removed (``zotero_status: missing``).
- ``source-duplicate-key``: two source notes with the same citation key (the second one is flagged).
- ``figure-unplaced`` / ``table-unplaced`` / ``equation-unplaced``: referenced in prose but never placed,
  so the reference has no number.
- ``figure-unreferenced`` / ``table-unreferenced`` / ``equation-unreferenced``: neither placed nor referenced.
- ``image-missing``: a figure whose image file is missing.
- ``duplicate-label``: two objects of one kind whose labels differ only in case (references would be ambiguous
  on a case-insensitive file system).

Only the book is checked (``Project.list_scenes``, the same reading order as numbering). Pending AI drafts,
scene details and math are not scanned (the same blanking as numbering). A story project returns no flags.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import drafts, links, objects, scenemeta
from .entities import resolve_key, source_key
from .paper.types import Flag

_WORD = {"fig": "figure", "tbl": "table", "eq": "equation"}


def _rel(project, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return Path(path).resolve().relative_to(project.root.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _prose(text: str) -> str:
    """The text a check reads: no pending AI text, no scene details, no research math. Same length and newlines
    as *text*, so rows and offsets stay valid."""
    return objects.strip_math(scenemeta.blank(drafts.blank_pending(text)), mode="research")


def _scenes(project) -> list[tuple[str, str]]:
    """(project-relative path, prose) for every scene of the book, in reading order."""
    out = []
    for scene in project.list_scenes():
        try:
            text = scene.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out.append((_rel(project, scene), _prose(text)))
    return out


def run_checks(project) -> list[Flag]:
    """Every research check for *project*. Read-only. Returns [] for a story project."""
    if project.mode != "research":
        return []
    flags: list[Flag] = []
    entities = project.load_entities()
    sources = [e for e in entities if e.is_source]
    objs = objects.list_objects(project)
    scenes = _scenes(project)

    # -- sources ------------------------------------------------------------------
    seen_keys: set[str] = set()
    for entity in sources:
        key = source_key(entity)
        path = _rel(project, entity.path)
        if key in seen_keys:
            flags.append(Flag("source-duplicate-key", path, None,
                              f"Two source notes use the citation key {key}. Give one of them a different key.",
                              False))
        seen_keys.add(key)
        if str(entity.extra.get("zotero_status", "")).lower() == "missing":
            flags.append(Flag("source-missing", path, None,
                              f"The Zotero item for {key} was removed. The note is kept; cite it or remove it.",
                              False))

    # -- citations and references in the scenes -----------------------------------
    cited: set[str] = set()
    placed: set[tuple[str, str]] = set()
    referenced: set[tuple[str, str]] = set()
    known_objects = {(o.kind, o.label) for o in objs}
    for path, text in scenes:
        for citation in links.find_citations(text):
            row = links.offset_to_rowcol(text, citation.start)[0]
            for ref in citation.refs:
                cited.add(ref.key)
                if resolve_key(ref.key, entities) is None:
                    flags.append(Flag("citation-unresolved", path, row,
                                      f"No source note has the citation key {ref.key}. "
                                      "Add the source or fix the key.", True))
        for placement in objects.find_placements(text):
            placed.add((placement.kind, placement.label))
            if (placement.kind, placement.label) not in known_objects:
                row = links.offset_to_rowcol(text, placement.start)[0]
                flags.append(Flag("ref-missing", path, row,
                                  f"The {_WORD[placement.kind]} {placement.label} is placed here but does not "
                                  "exist in the project.", True))
        for ref in objects.find_refs(text):
            referenced.add((ref.kind, ref.label))
            if (ref.kind, ref.label) not in known_objects:
                row = links.offset_to_rowcol(text, ref.start)[0]
                flags.append(Flag("ref-missing", path, row,
                                  f"The reference [[{ref.kind}:{ref.label}]] points to a {_WORD[ref.kind]} that "
                                  "does not exist.", True))

    for entity in sources:
        key = source_key(entity)
        if key not in cited:
            flags.append(Flag("source-uncited", _rel(project, entity.path), None,
                              f"The source {key} is not cited in any scene.", False))

    # -- objects -------------------------------------------------------------------
    labels: Counter = Counter((o.kind, o.label.casefold()) for o in objs)
    counted: Counter = Counter()
    for obj in objs:
        word = _WORD[obj.kind]
        marker = (obj.kind, obj.label.casefold())
        if labels[marker] > 1:
            counted[marker] += 1
            if counted[marker] > 1:
                flags.append(Flag("duplicate-label", obj.path, None,
                                  f"The {word} label {obj.label} is used by more than one file. "
                                  "Rename one of them.", False))
        key = (obj.kind, obj.label)
        if key not in placed:
            if key in referenced:
                flags.append(Flag(f"{word}-unplaced", obj.path, None,
                                  f"The {word} {obj.label} is referenced but never placed in the text, so it "
                                  "has no number. Put it on its own line where it belongs.", False))
            else:
                flags.append(Flag(f"{word}-unreferenced", obj.path, None,
                                  f"The {word} {obj.label} is never placed or referenced.", False))
        if obj.kind == "fig" and obj.status == "missing":
            flags.append(Flag("image-missing", obj.path, None,
                              f"The image for figure {obj.label} is missing from the figures folder.", False))
    return flags


def blocking(flags: list[Flag]) -> bool:
    """True when any flag blocks export (unresolved citations and missing references)."""
    return any(flag.blocking for flag in flags)
