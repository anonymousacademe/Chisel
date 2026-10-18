"""CSL JSON bibliography for a research export (docs/dev/plan-research-mode.md 6.3).

Built offline from the ``csl:`` data stored in each source note (the Zotero item's CSL JSON, verbatim), for the
sources a manuscript actually cites and no others. pandoc's citeproc reads the result. A note with no stored
CSL still gets a minimal entry from its derived display fields (title, authors, year), so a hand-made source
cites too. Pure Python: no network, no pandoc.
"""

from __future__ import annotations

import json

from ..entities import resolve_key, source_key

DEFAULT_TYPE = "document"


def _name(text: str) -> dict:
    """``"Smith, Jane"`` -> CSL name; a text without a comma is a literal (an organisation)."""
    family, sep, given = str(text).partition(",")
    if sep and family.strip():
        return {"family": family.strip(), "given": given.strip()}
    return {"literal": str(text).strip()}


def _fallback(entity) -> dict:
    """A minimal CSL item from a source note's display fields (used when ``csl:`` is absent or not a map)."""
    extra = entity.extra
    item: dict = {"type": DEFAULT_TYPE, "title": str(extra.get("title") or entity.name)}
    authors = extra.get("authors")
    if isinstance(authors, str):
        authors = [authors]
    names = [_name(a) for a in authors or [] if str(a).strip()]
    if names:
        item["author"] = names
    year = extra.get("year")
    try:
        item["issued"] = {"date-parts": [[int(year)]]}
    except (TypeError, ValueError):
        pass
    return item


def entry_for(entity, key: str | None = None) -> dict:
    """The CSL JSON item for one source note, its ``id`` set to the citation *key* (what the manuscript
    writes after ``@``) whatever id Zotero gave it. The stored data is copied, never changed."""
    key = key if key is not None else source_key(entity)
    raw = entity.extra.get("csl")
    item = dict(raw) if isinstance(raw, dict) and raw else _fallback(entity)
    item["id"] = key
    if not isinstance(item.get("type"), str) or not item["type"]:
        item["type"] = DEFAULT_TYPE
    return item


def build(entities, keys) -> tuple[list[dict], list[str]]:
    """``(entries, unresolved)``: the CSL items of the sources *keys* name, once each, in the order of first
    use, and the keys no source note answers to (case-sensitive; only source notes match)."""
    entities = list(entities)
    entries: list[dict] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        entity = resolve_key(key, entities)
        if entity is None:
            unresolved.append(key)
        else:
            entries.append(entry_for(entity, key))
    return entries, unresolved


def dumps(entries: list[dict]) -> str:
    """The JSON text pandoc's ``--bibliography`` reads (UTF-8, deterministic order of keys as stored)."""
    return json.dumps(entries, ensure_ascii=False, indent=1, default=str) + "\n"
