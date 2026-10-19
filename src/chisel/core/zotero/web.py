"""Zotero Web API v3 client (read-only, standard library only; plan 4.1, 4.3, 10).

``ZoteroHTTP`` is the protocol engine shared with the local API (``local.py``): it owns the rules that
bit other clients (``Backoff`` on any response, ``Retry-After`` on 429, 50 keys per request, ``limit`` at
most 100, ``304`` with ``If-Modified-Since-Version``, restart when the library version moves mid-run).

The API key is a parameter. It is sent only in the ``Zotero-API-Key`` header, never put in a URL, a log
line or an error message.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from typing import Callable

from ..paper.types import Annotation, ZItem
from .base import FetchResult, Scope, Status, ZoteroError

WEB_BASE = "https://api.zotero.org"
PAGE_LIMIT = 100
KEYS_PER_REQUEST = 50
_MAX_RETRIES = 3
_MAX_WAIT = 300.0
_NON_TOP = ("note", "attachment", "annotation")
_EXTRA_KEY = re.compile(r"^\s*citation\s*key\s*:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)


def citation_key_of(data: dict) -> str | None:
    """data.citationKey, else ``Citation Key: x`` in Extra (older libraries); None when neither is set."""
    key = data.get("citationKey")
    if isinstance(key, str) and key.strip():
        return key.strip()
    m = _EXTRA_KEY.search(data.get("extra") or "")
    return m.group(1) if m else None


class _Response:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: dict[str, str], body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ZoteroError("Zotero sent a reply that could not be read.") from exc

    def int_header(self, name: str) -> int | None:
        try:
            return int(self.headers.get(name.lower(), ""))
        except ValueError:
            return None


class ZoteroHTTP:
    """Rate-limit-aware GET client. ``sleep`` and ``clock`` are injectable for tests."""

    def __init__(self, base: str, *, key: str | None = None, timeout: float = 20.0,
                 opener: urllib.request.OpenerDirector | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.base = base.rstrip("/")
        self._key = key or None
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener()
        self._sleep = sleep
        self._clock = clock
        self._quiet_until = 0.0

    def get(self, path: str, params: dict | None = None, headers: dict | None = None) -> _Response:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        hdrs = {"Zotero-API-Version": "3", "User-Agent": "Chisel", "Accept": "application/json"}
        if self._key:
            hdrs["Zotero-API-Key"] = self._key
        hdrs.update(headers or {})
        for attempt in range(_MAX_RETRIES + 1):
            wait = self._quiet_until - self._clock()
            if wait > 0:
                self._sleep(wait)
            resp = self._once(url, hdrs)
            backoff = resp.int_header("Backoff")
            if backoff:
                self._quiet_until = self._clock() + min(float(backoff), _MAX_WAIT)
            if resp.status == 429 or (resp.status == 503 and resp.headers.get("retry-after")):
                if attempt == _MAX_RETRIES:
                    raise ZoteroError("Zotero is rate limiting requests; try again in a few minutes.")
                retry = resp.int_header("Retry-After") or 5
                self._quiet_until = max(self._quiet_until, self._clock() + min(float(retry), _MAX_WAIT))
                continue
            return resp
        raise ZoteroError("Zotero is rate limiting requests; try again in a few minutes.")  # pragma: no cover

    def _once(self, url: str, hdrs: dict) -> _Response:
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return _Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
        except urllib.error.HTTPError as exc:
            headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
            body = b""
            try:
                body = exc.read()
            except Exception:
                pass
            if exc.code in (304, 429, 503):
                return _Response(exc.code, headers, body)
            if exc.code in (401, 403):
                raise ZoteroError("Zotero refused the request (check the API key and its read access).") from None
            if exc.code == 404:
                return _Response(404, headers, body)
            raise ZoteroError(f"Zotero answered with an error (HTTP {exc.code}).") from None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ZoteroError(f"Zotero could not be reached ({type(reason).__name__}).") from None


def csl_of(row: dict, key: str, data: dict) -> dict:
    """The item's CSL JSON as a dict. The web API sends an object; the local API sends a JSON *string* holding a
    one-item array (seen on Zotero 10.0.6). Anything else falls back to a minimal record."""
    raw = row.get("csljson")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, dict) and raw:
        return raw
    return {"id": key, "type": data.get("itemType", ""), "title": data.get("title", "")}


def collection_paths(rows: list[dict]) -> list[dict]:
    """Collection rows from the API to [{key, path, items}] sorted by path; parents joined with " / "."""
    data = {}
    for r in rows:
        d = r.get("data") if isinstance(r.get("data"), dict) else {}
        key = str(r.get("key") or d.get("key") or "")
        if not key:
            continue
        parent = d.get("parentCollection")
        meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
        n = meta.get("numItems")
        data[key] = (str(d.get("name") or key), str(parent) if parent else "",
                     n if isinstance(n, int) and not isinstance(n, bool) else None)

    def path(key: str) -> str:
        parts, seen = [], set()
        while key in data and key not in seen:
            seen.add(key)
            name, parent, _ = data[key]
            parts.append(name)
            key = parent
        return " / ".join(reversed(parts))

    out = [{"key": k, "path": path(k), "items": v[2],
            "parent": v[1] if v[1] and v[1] in data else None} for k, v in data.items()]
    out.sort(key=lambda c: (c["path"].casefold(), c["key"]))
    return out


class ZoteroLibrary:
    """Items, children and deletions of one library on one Zotero API server (web or local)."""

    def __init__(self, http: ZoteroHTTP, user_path: str):
        self.http = http
        self.user_path = user_path           # "/users/42" or "/users/0"
        self.warnings: list[str] = []
        self._expand_failed = False
        # Zotero 10.0.6's local API returns no annotations from /items/<pdf>/children (they exist: the library-wide
        # listing has them, each naming its PDF as parentItem), so the local backend reads them from the listing.
        self.annotations_by_listing = False
        self._annotation_rows_cache: dict[str, list[dict]] | None = None

    def collections(self) -> list[dict]:
        """Every collection as {key, path ("A / B / C"), items (int or None)}, sorted by path. Read-only,
        paged (a page holds at most PAGE_LIMIT collections)."""
        rows: list[dict] = []
        start = 0
        while True:
            resp = self.http.get(self.user_path + "/collections",
                                 {"limit": PAGE_LIMIT, "start": start, "format": "json"})
            self._ok(resp, "the collections")
            page = resp.json()
            if not isinstance(page, list):
                raise ZoteroError("Zotero returned the collections in an unexpected shape.")
            rows.extend(r for r in page if isinstance(r, dict))
            start += len(page)
            total = resp.int_header("Total-Results")
            if not page or (total is not None and start >= total) or (total is None and len(page) < PAGE_LIMIT):
                break
        return collection_paths(rows)

    # -- plumbing ------------------------------------------------------------------------------------
    def _ok(self, resp: _Response, what: str) -> _Response:
        if resp.status >= 400:
            raise ZoteroError(f"Zotero could not provide {what} (HTTP {resp.status}).")
        return resp

    def _pages(self, path: str, params: dict, since: int | None):
        """Yield (version, rows) per page; ``None`` rows for 304. Restarts if the version moves."""
        for _restart in range(_MAX_RETRIES):
            start, version, rows_all, changed = 0, None, [], False
            while True:
                p = dict(params, limit=PAGE_LIMIT, start=start)
                hdrs = {}
                if since is not None and start == 0:
                    hdrs["If-Modified-Since-Version"] = str(since)
                resp = self.http.get(self.user_path + path, p, hdrs)
                if resp.status == 304:
                    return None, [], True
                self._ok(resp, "the library")
                v = resp.int_header("Last-Modified-Version")
                if version is None:
                    version = v
                elif v is not None and v != version:
                    changed = True
                    break
                rows = resp.json()
                rows_all.extend(rows)
                total = resp.int_header("Total-Results")
                start += len(rows)
                if not rows or total is None or start >= total:
                    break
            if not changed:
                return version, rows_all, False
        raise ZoteroError("The Zotero library kept changing while it was read; try again.")

    # -- fetch ---------------------------------------------------------------------------------------
    def _expand_collections(self, keys: tuple[str, ...]) -> list[str]:
        """*keys* plus every subcollection of each (parents first, no repeats)."""
        try:
            rows = self.collections()
        except ZoteroError:
            self._expand_failed = True      # fetch() turns this into a warning; the ticked ones are still read
            return list(keys)
        children: dict[str, list[str]] = {}
        for r in rows:
            if r.get("parent"):
                children.setdefault(r["parent"], []).append(r["key"])
        out: list[str] = []

        def add(k: str) -> None:
            if k in out:
                return
            out.append(k)
            for c in children.get(k, []):
                add(c)

        for k in keys:
            add(k)
        return out

    def fetch(self, scope: Scope, since: int | None, backend: str,
              server_id: str | None = None) -> FetchResult:
        """One read of the library, or of each ticked collection (and its subcollections) merged by item key."""
        keys = scope.collection_keys
        if not keys:
            return self._fetch_one(scope, since, backend, server_id)
        if scope.include_subcollections:
            self._expand_failed = False
            keys = tuple(self._expand_collections(keys))
        merged: dict[str, ZItem] = {}
        deleted: list[str] = []
        version = None
        warnings = ["Zotero did not list the subcollections; only the ticked collections were read."] \
            if scope.include_subcollections and self._expand_failed else []
        for k in keys:
            part = self._fetch_one(replace(scope, collection=k, collections=()), since, backend, server_id)
            warnings.extend(w for w in self.warnings if w not in warnings)
            for it in part.items:
                merged.setdefault(it.key, it)
            deleted.extend(d for d in part.deleted_keys if d not in deleted)
            if version is None:
                version = part.library_version
        self.warnings = warnings
        # An item that left a ticked collection is simply absent: only deleted keys ever become "missing".
        return FetchResult(backend, list(merged.values()), deleted, version, server_id)

    def _fetch_one(self, scope: Scope, since: int | None, backend: str,
                   server_id: str | None = None) -> FetchResult:
        self.warnings = []
        self._annotation_rows_cache = None
        base = "/items"
        if scope.collection:
            base = "/collections/" + urllib.parse.quote(scope.collection, safe="") + "/items"
        params = {"include": "data,csljson", "format": "json"}
        if scope.tag:
            params["tag"] = scope.tag
        if since is not None:
            params["since"] = since
        version, rows, unchanged = self._pages(base, params, since)
        if unchanged:
            return FetchResult(backend, [], [], since, server_id)

        by_key = {r["key"]: r for r in rows if isinstance(r, dict) and "key" in r}
        tops: dict[str, dict] = {k: r for k, r in by_key.items()
                                 if r.get("data", {}).get("itemType") not in _NON_TOP}
        children: dict[str, dict] = {k: r for k, r in by_key.items() if k not in tops}

        # Parents of changed children that are not in the result (a note edited, its parent unchanged).
        grouped: dict[str, list[dict]] = {}
        for k, row in children.items():
            top = self._top_of(k, by_key)
            if top:
                grouped.setdefault(top, []).append(row)
        need = set(grouped)
        missing = [k for k in need if k not in tops]
        if missing:
            for r in self._by_keys(missing):
                if r.get("data", {}).get("itemType") not in _NON_TOP:
                    tops[r["key"]] = r
        # With "since" or a scope the children listing is partial: read each parent's children whole.
        notes_of: dict[str, list[str]] = {}
        annots_of: dict[str, list[Annotation]] = {}
        refetch = since is not None or scope.limited
        for key, row in tops.items():
            notes_of[key], annots_of[key] = self._kids_of(key, row, grouped.get(key, []), refetch)

        items: list[ZItem] = []
        for key, row in tops.items():
            data = row.get("data", {})
            csl = csl_of(row, key, data)
            items.append(ZItem(
                key=key, version=row.get("version"), csl=csl, citation_key=citation_key_of(data),
                notes=notes_of.get(key, []), annotations=annots_of.get(key, []),
                deleted=bool(data.get("deleted"))))

        deleted: list[str] = []
        if since is not None:
            deleted = self._deleted(since)
        return FetchResult(backend, items, deleted, version, server_id)

    def _top_of(self, key: str, by_key: dict) -> str | None:
        seen = 0
        cur = by_key.get(key)
        while cur is not None and seen < 4:
            parent = cur.get("data", {}).get("parentItem")
            if not parent:
                return cur["key"] if cur.get("data", {}).get("itemType") not in _NON_TOP else None
            nxt = by_key.get(parent)
            if nxt is None:
                fetched = self._by_keys([parent])
                if not fetched:
                    return None
                by_key[parent] = nxt = fetched[0]
            cur, seen = nxt, seen + 1
        return None

    def _by_keys(self, keys: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(keys), KEYS_PER_REQUEST):
            chunk = keys[i:i + KEYS_PER_REQUEST]
            resp = self.http.get(self.user_path + "/items", {
                "itemKey": ",".join(chunk), "include": "data,csljson", "format": "json",
                "limit": PAGE_LIMIT})
            out.extend(self._ok(resp, "items by key").json())
        return out

    def _children(self, key: str) -> list[dict]:
        resp = self.http.get(self.user_path + f"/items/{urllib.parse.quote(key, safe='')}/children",
                             {"include": "data", "format": "json", "limit": PAGE_LIMIT})
        if resp.status == 404:
            return []
        return self._ok(resp, "an item's notes").json()

    def _kids_of(self, key, row, listed, refetch):
        notes: list[str] = []
        annots: list[Annotation] = []
        if refetch:
            if (row.get("meta") or {}).get("numChildren", 0) == 0:
                return notes, annots
            kids = self._children(key)
            atts = [k for k in kids if k.get("data", {}).get("itemType") == "attachment"]
            for att in atts:
                if self.annotations_by_listing:
                    kids.extend(self._annotation_rows().get(att["key"], []))
                else:
                    kids.extend(self._children(att["key"]))
        else:
            kids = listed
        for k in kids:
            d = k.get("data", {})
            t = d.get("itemType")
            if t == "note" and d.get("note"):
                notes.append(d["note"])
            elif t == "annotation" and (d.get("annotationText") or d.get("annotationComment")):
                annots.append(Annotation(id=k["key"], text=d.get("annotationText", ""),
                                         comment=d.get("annotationComment", ""),
                                         page=str(d.get("annotationPageLabel", ""))))
        return notes, annots

    def _annotation_rows(self) -> dict[str, list[dict]]:
        """Every annotation in the library, grouped by the PDF attachment it belongs to (read once per fetch)."""
        if self._annotation_rows_cache is None:
            _version, rows, _unchanged = self._pages(
                "/items", {"itemType": "annotation", "include": "data", "format": "json"}, None)
            grouped: dict[str, list[dict]] = {}
            for r in rows:
                parent = r.get("data", {}).get("parentItem") if isinstance(r, dict) else None
                if parent:
                    grouped.setdefault(parent, []).append(r)
            self._annotation_rows_cache = grouped
        return self._annotation_rows_cache

    def _deleted(self, since: int) -> list[str]:
        resp = self.http.get(self.user_path + "/deleted", {"since": since})
        if resp.status == 404:
            self.warnings.append("This Zotero server does not report removed items, so removals were not checked.")
            return []
        data = self._ok(resp, "removed items").json()
        keys = data.get("items", []) if isinstance(data, dict) else []
        return [k for k in keys if isinstance(k, str)]


class WebSource:
    """The Zotero Web API (api.zotero.org) with a read-only API key."""

    name = "web"

    def __init__(self, api_key: str, *, user_id: str | int | None = None, base: str = WEB_BASE,
                 timeout: float = 20.0, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        if not api_key:
            raise ZoteroError("No Zotero API key is set.")
        self._http = ZoteroHTTP(base, key=api_key, timeout=timeout, sleep=sleep, clock=clock)
        self._user_id = str(user_id) if user_id else None
        self._lib: ZoteroLibrary | None = None
        self.warnings: list[str] = []

    def __repr__(self) -> str:  # never show the key
        return f"WebSource(user_id={self._user_id!r})"

    def _library(self) -> ZoteroLibrary:
        if self._lib is None:
            if self._user_id is None:
                resp = self._http.get("/keys/current")
                if resp.status >= 400:
                    raise ZoteroError("Zotero did not recognise the API key.")
                uid = resp.json().get("userID")
                if not uid:
                    raise ZoteroError("The Zotero API key does not name a user.")
                self._user_id = str(uid)
            self._lib = ZoteroLibrary(self._http, f"/users/{self._user_id}")
        return self._lib

    def probe(self) -> Status:
        try:
            lib = self._library()
            resp = self._http.get(lib.user_path + "/items", {"limit": 1, "format": "json"})
            if resp.status >= 400:
                return Status(False, f"Zotero web answered with HTTP {resp.status}.")
            return Status(True, "Zotero web is reachable.", resp.int_header("Last-Modified-Version"),
                          None, f"web:users/{self._user_id}")
        except ZoteroError as exc:
            return Status(False, str(exc))

    def collections(self) -> list[dict]:
        return self._library().collections()

    def fetch(self, scope: Scope, since: int | None) -> FetchResult:
        lib = self._library()
        result = lib.fetch(scope, since, "web")
        self.warnings = lib.warnings
        return result
