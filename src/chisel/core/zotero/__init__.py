"""Zotero client (contract "Zotero client", owner P2). Read-only; web, local, file, cache.

Settings read by ``open_sources`` (a mapping or any object with ``.get``):

- ``zotero_web_key``: the Web API key (supplied by the keyring layer, never stored in the project);
  ``zotero_web_user_id`` (optional, read from the key otherwise); ``zotero_web_base`` (tests).
- ``zotero_local`` (default True) and ``zotero_local_base``.
- ``zotero_file``: path of a Better BibTeX CSL JSON auto-export.
- ``zotero_cache``: the cached ZItems (list or callable) from the project's source notes.

Sync state is ``{state_key: library_version}`` with the keys ``Status.state_key`` gives
("web:users/42", "local:<server id>"); it is never shared between backends. ``chain_fetch`` does not
modify it: the caller records a version only after the author applied the sync.
"""

from __future__ import annotations

from .base import FetchResult, Scope, Status, ZoteroError, ZoteroSource
from .cache import CacheSource
from .file import FileSource
from .html2md import annotation_to_markdown, html_to_markdown
from .local import LOCAL_BASE, LocalSource
from .web import WEB_BASE, WebSource, citation_key_of

__all__ = ["FetchResult", "Scope", "Status", "ZoteroError", "ZoteroSource", "open_sources", "chain_fetch",
           "html_to_markdown", "annotation_to_markdown", "citation_key_of",
           "WebSource", "LocalSource", "FileSource", "CacheSource"]

_LABEL = {"web": "Zotero web", "local": "Zotero on this computer", "file": "the Better BibTeX export file",
          "cache": "the saved source notes"}


def _get(settings, key, default=None):
    try:
        v = settings.get(key, default)
    except Exception:
        return default
    return default if v is None else v


def open_sources(settings) -> list[ZoteroSource]:
    """The configured backends in fall-through order: web, local, file, cache."""
    out: list[ZoteroSource] = []
    key = _get(settings, "zotero_web_key", "")
    if key:
        out.append(WebSource(key, user_id=_get(settings, "zotero_web_user_id") or None,
                             base=_get(settings, "zotero_web_base", WEB_BASE)))
    if _get(settings, "zotero_local", True):
        out.append(LocalSource(_get(settings, "zotero_local_base", LOCAL_BASE)))
    path = _get(settings, "zotero_file", "")
    if path:
        out.append(FileSource(path))
    cache = _get(settings, "zotero_cache")
    if cache is not None:
        out.append(CacheSource(cache))
    return out


def chain_fetch(sources, scope: Scope | None, state) -> tuple[FetchResult, list[str]]:
    """Try each source in order; the first that answers wins. Returns (result, report in plain words).

    ``since`` comes from ``state[status.state_key]`` of that same backend only. When nothing answers the
    result is empty with backend "none".
    """
    scope = scope or Scope()
    state = state or {}
    report: list[str] = []
    for src in sources:
        label = _LABEL.get(src.name, src.name)
        st = src.probe()
        if not st.ok:
            report.append(f"Could not use {label}: {st.message}".rstrip())
            continue
        since = state.get(st.state_key) if st.state_key else None
        try:
            result = src.fetch(scope, since if isinstance(since, int) else None)
        except ZoteroError as exc:
            report.append(f"Could not use {label}: {exc}")
            continue
        for w in getattr(src, "warnings", []) or []:
            report.append(w)
        if result.library_version is not None and result.library_version == since and not result.items:
            report.append(f"{label.capitalize()}: nothing has changed since the last sync.")
        else:
            report.append(f"Read {len(result.items)} items from {label}.")
        if report and len(report) > 1 and any(r.startswith("Could not use") for r in report):
            report.append(f"Used {label} instead.")
        return result, report
    report.append("No Zotero source answered; nothing was read.")
    return FetchResult("none", [], [], None, None), report
