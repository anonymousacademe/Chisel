"""Better BibTeX auto-export file (CSL JSON) backend: offline, no key, the author's real citation keys.

The file is a full export, so ``since`` is ignored and no version is reported (``library_version`` is None).
It has no notes or highlights and cannot tell what was removed; the sync plan compares against the notes
already in the project. BibTeX files are not read (point Better BibTeX at a "CSL JSON" auto-export).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..paper.types import ZItem
from .base import FetchResult, Scope, Status, ZoteroError
from .web import citation_key_of


class FileSource:
    name = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.warnings: list[str] = []

    def _load(self) -> list[dict]:
        if self.path.suffix.lower() in (".bib", ".bibtex"):
            raise ZoteroError("That file is BibTeX; export CSL JSON from Better BibTeX instead.")
        try:
            raw = self.path.read_text(encoding="utf-8-sig")
        except OSError:
            raise ZoteroError("The Zotero export file could not be read.") from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise ZoteroError("The Zotero export file is not valid CSL JSON.") from None
        if isinstance(data, dict):
            data = data.get("items", [])
        if not isinstance(data, list):
            raise ZoteroError("The Zotero export file is not a list of CSL items.")
        return [d for d in data if isinstance(d, dict)]

    def probe(self) -> Status:
        try:
            n = len(self._load())
        except ZoteroError as exc:
            return Status(False, str(exc))
        return Status(True, f"The Zotero export file lists {n} items.", None, None, "file")

    def fetch(self, scope: Scope, since: int | None) -> FetchResult:
        self.warnings = []
        if scope.limited:
            self.warnings.append("The export file cannot be limited to a collection or tag; all items are read.")
        items: list[ZItem] = []
        seen: set[str] = set()
        for row in self._load():
            ckey = row.get("citation-key") or row.get("id")
            ckey = str(ckey).strip() if ckey is not None else ""
            zkey = str(row.get("zotero-key") or ckey)
            if not zkey or zkey in seen:
                if zkey:
                    self.warnings.append(f"The export lists the key {zkey} more than once; the first was kept.")
                continue
            seen.add(zkey)
            ckey = ckey or citation_key_of({"extra": row.get("note", "")}) or ""
            items.append(ZItem(key=zkey, version=None, csl=row, citation_key=ckey or None))
        return FetchResult("file", items, [], None, None)
