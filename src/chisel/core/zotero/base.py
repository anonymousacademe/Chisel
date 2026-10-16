"""Shared types of the Zotero client (contract: docs/dev/research-mode-contracts.md, "Zotero client")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ..paper.types import ZItem


class ZoteroError(Exception):
    """A backend could not answer. The message is plain words and never contains a key."""


@dataclass(frozen=True)
class Scope:
    """What to pull: the whole library, or one collection and/or one tag."""

    collection: str | None = None
    tag: str | None = None

    @property
    def limited(self) -> bool:
        return bool(self.collection or self.tag)


@dataclass(frozen=True)
class Status:
    ok: bool
    message: str = ""
    version: int | None = None       # the backend's own library version (never comparable across backends)
    server_id: str | None = None     # local API Zotero-Server-ID
    state_key: str = ""              # key under which this backend's sync state is kept ("web:users/42")


@dataclass(frozen=True)
class FetchResult:
    backend: str
    items: list[ZItem]
    deleted_keys: list[str]
    library_version: int | None
    server_id: str | None = None


class ZoteroSource(Protocol):
    name: Literal["web", "local", "file", "cache"]

    def probe(self) -> Status: ...

    def fetch(self, scope: Scope, since: int | None) -> FetchResult: ...
