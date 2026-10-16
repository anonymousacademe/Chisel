"""Shared types of research mode (docs/dev/research-mode-contracts.md, "Types").

Frozen once the work packages start: a package that needs a change reports instead of editing this file.
Offsets are code points; UTF-16 conversion happens only at the GUI bridge (``core/spans.py``).

The package is ``core/paper/`` because ``core/research.py`` already holds the Notebook notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ObjectKind = Literal["fig", "tbl", "eq"]
ObjectStatus = Literal["current", "stale", "failed", "missing"]


@dataclass(frozen=True)
class CiteRef:
    key: str                        # case-sensitive, exactly as written after @
    prefix: str = ""                # text before the key inside the citation ("see")
    locator: str = ""               # "p. 12"
    suffix: str = ""
    suppress_author: bool = False   # -@key


@dataclass(frozen=True)
class Citation:
    refs: list[CiteRef]
    start: int                      # code point offsets of the whole [[...]] or [@...]
    end: int
    raw: str
    kind: Literal["bracketed", "narrative", "pandoc"]   # [[@k]] / [[+@k]] / [@k]


@dataclass(frozen=True)
class Placement:                    # ![[fig:x]] alone on a line
    kind: ObjectKind
    label: str                      # the file-name stem without the kind prefix ("flow-model")
    start: int
    end: int


@dataclass(frozen=True)
class ObjectRef:                    # [[fig:x]] in prose
    kind: ObjectKind
    label: str
    start: int
    end: int


@dataclass(frozen=True)
class Num:
    seq: int                        # order of appearance within its kind, 1-based
    display: str                    # "2", "2.1", "S1"


Numbering = dict[str, Num]          # key "fig:flow-model" -> Num


@dataclass(frozen=True)
class RefObject:
    kind: ObjectKind
    label: str
    path: str                       # project-relative path of the .md
    caption: str
    source: Literal["static", "script", "data"]
    file: str | None                # figure image path, table csv path, None for equations
    width: float | None             # inches
    alt: str
    status: ObjectStatus


@dataclass(frozen=True)
class Annotation:
    id: str                         # Zotero annotation key, stable across syncs
    text: str
    comment: str
    page: str


@dataclass(frozen=True)
class ZItem:
    key: str                        # Zotero item key (not the citation key)
    version: int | None             # meaningful only for the backend that produced it
    csl: dict                       # the item's full CSL JSON, verbatim
    citation_key: str | None        # data.citationKey, or from Extra on older libraries
    notes: list[str] = field(default_factory=list)          # note HTML, unsanitised (the sanitiser is P2)
    annotations: list[Annotation] = field(default_factory=list)
    deleted: bool = False


@dataclass(frozen=True)
class Flag:                         # a research-check finding
    kind: str                       # "citation-unresolved", "source-uncited", "ref-missing", ...
    path: str
    row: int | None
    message: str
    blocking: bool
