"""Zotero local API (loopback, read-only; plan 4.1).

Needs "Allow other applications on this computer to communicate with Zotero". Its versions have no relation
to the web API's, so sync state is kept per ``Zotero-Server-ID`` and never shared with the web backend.
"""

from __future__ import annotations

import time
import urllib.request
from typing import Callable

from .base import FetchResult, Scope, Status, ZoteroError
from .web import ZoteroHTTP, ZoteroLibrary

LOCAL_BASE = "http://127.0.0.1:23119/api"


class LocalSource:
    name = "local"

    # A probe is a quick "is it there"; the first real read on a cold Zotero took more than 5 s on Zotero 10.
    FETCH_TIMEOUT = 60.0

    def __init__(self, base: str = LOCAL_BASE, *, timeout: float = 5.0,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        # No proxy for loopback: a system proxy must never see library data.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._http = ZoteroHTTP(base, timeout=timeout, opener=opener, sleep=sleep, clock=clock)
        self._lib = ZoteroLibrary(self._http, "/users/0")
        self._server_id: str | None = None
        self.warnings: list[str] = []

    def probe(self) -> Status:
        try:
            resp = self._http.get("/users/0/items", {"limit": 1, "format": "json"})
        except ZoteroError as exc:
            return Status(False, "Zotero is not answering on this computer (is it open, with other "
                                 "applications allowed to communicate?). " + str(exc))
        if resp.status == 403:
            return Status(False, "Zotero refused the local connection: turn on 'Allow other applications "
                                 "on this computer to communicate with Zotero'.")
        if resp.status >= 400:
            return Status(False, f"The local Zotero answered with HTTP {resp.status}.")
        self._server_id = resp.headers.get("zotero-server-id") or None
        sid = self._server_id or "unknown"
        return Status(True, "Local Zotero is reachable.", resp.int_header("Last-Modified-Version"),
                      self._server_id, f"local:{sid}")

    def fetch(self, scope: Scope, since: int | None) -> FetchResult:
        if self._server_id is None:
            self.probe()
        quick, self._http.timeout = self._http.timeout, max(self._http.timeout, self.FETCH_TIMEOUT)
        try:
            result = self._lib.fetch(scope, since, "local", self._server_id)
        finally:
            self._http.timeout = quick
        self.warnings = self._lib.warnings
        return result
