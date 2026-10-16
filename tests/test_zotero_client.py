"""Zotero client against a fake loopback server (no real network, no real Zotero, scrubbed JSON)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from chisel.core.paper.types import ZItem
from chisel.core.zotero import (CacheSource, FileSource, LocalSource, Scope, WebSource, ZoteroError,
                                chain_fetch, open_sources)
from chisel.core.zotero.web import citation_key_of

KEY = "SECRETKEY123"


def item(key, title="T", ckey=None, extra="", **data):
    d = {"key": key, "itemType": "journalArticle", "title": title, "extra": extra, **data}
    if ckey:
        d["citationKey"] = ckey
    return {"key": key, "version": 5, "data": d, "meta": {"numChildren": 0},
            "csljson": {"id": key, "type": "article-journal", "title": title}}


def child(key, parent, itemType, **data):
    return {"key": key, "version": 6, "data": {"key": key, "itemType": itemType, "parentItem": parent, **data}}


class Fake:
    """A scripted Zotero server. ``routes`` maps a path to a function(query, headers, n) -> reply."""

    def __init__(self):
        self.routes = {}
        self.log = []          # (path, query, headers)
        self.extra_headers = {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                hdrs = {k.lower(): v for k, v in self.headers.items()}
                outer.log.append((u.path, q, hdrs))
                fn = outer.routes.get(u.path)
                if fn is None:
                    status, h, body = 404, {}, b"{}"
                else:
                    status, h, body = fn(q, hdrs, sum(1 for p, _, _ in outer.log if p == u.path))
                self.send_response(status)
                for k, v in {**outer.extra_headers, **h}.items():
                    self.send_header(k, str(v))
                if not isinstance(body, bytes):
                    body = json.dumps(body).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()

    def ok(self, rows, version=10, total=None, **h):
        return 200, {"Last-Modified-Version": version, "Total-Results": len(rows) if total is None else total,
                     **h}, rows


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.close()


class Clock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def web(fake, clock=None, user=42):
    c = clock or Clock()
    return WebSource(KEY, user_id=user, base=fake.base, sleep=c.sleep, clock=c.now), c


def test_full_fetch_with_citation_keys_and_extra_fallback(fake):
    rows = [item("AAA", ckey="smith2020"), item("BBB", extra="foo\nCitation Key: old2015\nbar"),
            item("CCC")]
    fake.routes["/users/42/items"] = lambda q, h, n: fake.ok(rows, version=77)
    src, _ = web(fake)
    res = src.fetch(Scope(), None)
    assert res.backend == "web" and res.library_version == 77
    assert {i.key: i.citation_key for i in res.items} == {"AAA": "smith2020", "BBB": "old2015", "CCC": None}
    assert res.items[0].csl["title"] == "T" and res.deleted_keys == []
    # key goes in the header only, never the URL
    assert all(h.get("zotero-api-key") == KEY for _, _, h in fake.log)
    assert all(KEY not in p and KEY not in json.dumps(q) for p, q, _ in fake.log)


def test_citation_key_prefers_field_over_extra():
    assert citation_key_of({"citationKey": "a", "extra": "Citation Key: b"}) == "a"
    assert citation_key_of({"extra": "citation key:  X_1 "}) == "X_1"
    assert citation_key_of({"extra": ""}) is None


def test_304_means_unchanged(fake):
    fake.routes["/users/42/items"] = lambda q, h, n: (304, {"Last-Modified-Version": 10}, b"")
    src, _ = web(fake)
    res = src.fetch(Scope(), 10)
    assert res.items == [] and res.library_version == 10
    _, q, h = fake.log[-1]
    assert h["if-modified-since-version"] == "10" and q["since"] == "10"
    assert all(p != "/users/42/deleted" for p, _, _ in fake.log)


def test_429_waits_retry_after_then_succeeds(fake):
    def route(q, h, n):
        if n == 1:
            return 429, {"Retry-After": 7}, b"{}"
        return fake.ok([item("AAA")])
    fake.routes["/users/42/items"] = route
    src, clock = web(fake)
    res = src.fetch(Scope(), None)
    assert len(res.items) == 1
    assert clock.slept and clock.slept[0] >= 7


def test_429_gives_up_with_plain_error(fake):
    fake.routes["/users/42/items"] = lambda q, h, n: (429, {"Retry-After": 1}, b"{}")
    src, _ = web(fake)
    with pytest.raises(ZoteroError) as e:
        src.fetch(Scope(), None)
    assert "rate" in str(e.value) and KEY not in str(e.value)


def test_backoff_header_on_a_200_delays_next_request(fake):
    fake.routes["/users/42/items"] = lambda q, h, n: fake.ok([item("AAA")], Backoff=30)
    src, clock = web(fake)
    src.fetch(Scope(), None)                       # first response sets Backoff 30
    assert clock.slept == []
    src.probe()                                    # next request must wait it out
    assert clock.slept and clock.slept[0] >= 29


def test_pagination_follows_total_results(fake):
    pages = [[item(f"K{i}") for i in range(100)], [item(f"K{i}") for i in range(100, 130)]]

    def route(q, h, n):
        start = int(q.get("start", 0))
        assert int(q["limit"]) <= 100
        return fake.ok(pages[start // 100], total=130)
    fake.routes["/users/42/items"] = route
    src, _ = web(fake)
    res = src.fetch(Scope(), None)
    assert len(res.items) == 130


def test_version_change_mid_run_restarts(fake):
    calls = {"n": 0}

    def route(q, h, n):
        calls["n"] += 1
        start = int(q.get("start", 0))
        if calls["n"] == 1:
            return fake.ok([item("A")] * 100, version=10, total=101)
        if calls["n"] == 2:                     # second page: version moved
            return fake.ok([item("B")], version=11, total=101)
        return fake.ok([item("C")], version=11)
    fake.routes["/users/42/items"] = route
    src, _ = web(fake)
    res = src.fetch(Scope(), None)
    assert [i.key for i in res.items] == ["C"] and res.library_version == 11


def test_deleted_keys_and_trashed_flag(fake):
    fake.routes["/users/42/items"] = lambda q, h, n: fake.ok([item("AAA", deleted=1)], version=12)
    fake.routes["/users/42/deleted"] = lambda q, h, n: (200, {}, {"items": ["GONE1", "GONE2"], "collections": []})
    src, _ = web(fake)
    res = src.fetch(Scope(), 10)
    assert res.deleted_keys == ["GONE1", "GONE2"] and res.items[0].deleted is True
    assert fake.log[-1][1]["since"] == "10"


def test_notes_and_highlights_attach_to_top_item(fake):
    top = item("AAA", ckey="a1")
    top["meta"]["numChildren"] = 2
    rows = [top, child("N1", "AAA", "note", note="<p>hi</p>"),
            child("ATT", "AAA", "attachment"),
            child("AN1", "ATT", "annotation", annotationText="quote", annotationComment="why",
                  annotationPageLabel="12")]
    fake.routes["/users/42/items"] = lambda q, h, n: fake.ok(rows)
    src, _ = web(fake)
    it = src.fetch(Scope(), None).items
    assert [i.key for i in it] == ["AAA"]
    assert it[0].notes == ["<p>hi</p>"]
    assert (it[0].annotations[0].text, it[0].annotations[0].page) == ("quote", "12")


def test_changed_note_pulls_unchanged_parent_by_key_and_all_children(fake):
    parent = item("PAR", ckey="p1")
    parent["meta"]["numChildren"] = 2
    fake.routes["/users/42/items"] = lambda q, h, n: (
        fake.ok([parent]) if "itemKey" in q else fake.ok([child("N2", "PAR", "note", note="<p>new</p>")], version=20))
    fake.routes["/users/42/items/PAR/children"] = lambda q, h, n: fake.ok(
        [child("N1", "PAR", "note", note="<p>old</p>"), child("N2", "PAR", "note", note="<p>new</p>")])
    src, _ = web(fake)
    fake.routes["/users/42/deleted"] = lambda q, h, n: (200, {}, {"items": []})
    res = src.fetch(Scope(), 10)
    assert [i.key for i in res.items] == ["PAR"]
    assert res.items[0].notes == ["<p>old</p>", "<p>new</p>"]


def test_fetch_by_key_is_chunked_to_50(fake):
    from chisel.core.zotero.web import ZoteroHTTP, ZoteroLibrary
    seen = []

    def route(q, h, n):
        keys = q["itemKey"].split(",")
        seen.append(len(keys))
        return fake.ok([item(k) for k in keys])
    fake.routes["/users/42/items"] = route
    lib = ZoteroLibrary(ZoteroHTTP(fake.base), "/users/42")
    rows = lib._by_keys([f"K{i}" for i in range(120)])
    assert seen == [50, 50, 20] and len(rows) == 120


def test_scope_collection_and_tag(fake):
    fake.routes["/users/42/collections/COL1/items"] = lambda q, h, n: fake.ok([item("AAA")])
    src, _ = web(fake)
    assert len(src.fetch(Scope(collection="COL1", tag="x"), None).items) == 1
    assert fake.log[-1][1]["tag"] == "x"


def test_user_id_read_from_key(fake):
    fake.routes["/keys/current"] = lambda q, h, n: (200, {}, {"userID": 42, "access": {}})
    fake.routes["/users/42/items"] = lambda q, h, n: fake.ok([item("AAA")], version=3)
    src = WebSource(KEY, base=fake.base)
    st = src.probe()
    assert st.ok and st.state_key == "web:users/42" and st.version == 3


def test_forbidden_is_plain_and_keyless(fake):
    fake.routes["/users/42/items"] = lambda q, h, n: (403, {}, b"{}")
    src, _ = web(fake)
    st = src.probe()
    assert not st.ok and KEY not in st.message
    assert KEY not in repr(src)


def test_local_probe_server_id_and_state_key(fake):
    fake.extra_headers = {"Zotero-Server-ID": "srv-1"}
    fake.routes["/users/0/items"] = lambda q, h, n: fake.ok([item("AAA", ckey="k")], version=900)
    src = LocalSource(fake.base)
    st = src.probe()
    assert st.ok and st.server_id == "srv-1" and st.state_key == "local:srv-1"
    res = src.fetch(Scope(), None)
    assert res.backend == "local" and res.server_id == "srv-1" and "zotero-api-key" not in fake.log[-1][2]


def test_local_without_deleted_route_warns(fake):
    fake.routes["/users/0/items"] = lambda q, h, n: fake.ok([item("AAA")], version=901)
    src = LocalSource(fake.base)
    res = src.fetch(Scope(), 900)
    assert res.deleted_keys == [] and any("removed" in w for w in src.warnings)


def test_local_refused_message_mentions_setting(fake):
    fake.routes["/users/0/items"] = lambda q, h, n: (403, {}, b"{}")
    st = LocalSource(fake.base).probe()
    assert not st.ok and "communicate" in st.message


def test_local_unreachable():
    st = LocalSource("http://127.0.0.1:1/api", timeout=1).probe()
    assert not st.ok


# -- file backend ----------------------------------------------------------------------------------------

def test_file_backend_csl_json(tmp_path):
    p = tmp_path / "lib.json"
    p.write_text(json.dumps([{"id": "smith2020", "type": "book", "title": "B"},
                             {"id": "smith2020", "title": "dup"}, {"id": "x", "title": "X"}]), encoding="utf-8")
    src = FileSource(p)
    assert src.probe().ok
    res = src.fetch(Scope(), 5)
    assert [i.citation_key for i in res.items] == ["smith2020", "x"]
    assert res.library_version is None and res.items[0].csl["type"] == "book"
    assert any("more than once" in w for w in src.warnings)


def test_file_backend_rejects_bibtex_and_garbage(tmp_path):
    assert not FileSource(tmp_path / "a.bib").probe().ok
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert not FileSource(bad).probe().ok
    assert not FileSource(tmp_path / "missing.json").probe().ok


# -- chain -----------------------------------------------------------------------------------------------

def test_chain_order_and_fall_through(fake, tmp_path):
    p = tmp_path / "lib.json"
    p.write_text(json.dumps([{"id": "k1", "title": "t"}]), encoding="utf-8")
    fake.routes["/users/42/items"] = lambda q, h, n: (403, {}, b"{}")      # web fails
    settings = {"zotero_web_key": KEY, "zotero_web_user_id": 42, "zotero_web_base": fake.base,
                "zotero_local": True, "zotero_local_base": "http://127.0.0.1:1/api",
                "zotero_file": str(p), "zotero_cache": [ZItem("c", None, {}, "c")]}
    srcs = open_sources(settings)
    assert [s.name for s in srcs] == ["web", "local", "file", "cache"]
    res, report = chain_fetch(srcs, Scope(), {})
    assert res.backend == "file"
    text = " ".join(report)
    assert "Zotero web" in text and "Zotero on this computer" in text and KEY not in text


def test_chain_uses_only_that_backends_state(fake):
    fake.extra_headers = {"Zotero-Server-ID": "srv-1"}
    fake.routes["/users/0/items"] = lambda q, h, n: (304, {"Last-Modified-Version": 5}, b"")
    local = LocalSource(fake.base)
    # a web version of 999 must not leak into the local request
    res, report = chain_fetch([local], Scope(), {"web:users/42": 999, "local:srv-1": 5})
    assert fake.log[-1][2]["if-modified-since-version"] == "5"
    assert res.backend == "local" and "nothing has changed" in " ".join(report)


def test_chain_nothing_answers():
    res, report = chain_fetch([CacheSource([])], Scope(), {})
    assert res.backend == "none" and res.items == [] and "No Zotero source answered" in report[-1]


def test_chain_cache_last_resort():
    res, report = chain_fetch([CacheSource(lambda: [ZItem("k", None, {}, "k")])], None, None)
    assert res.backend == "cache" and len(res.items) == 1


def test_open_sources_defaults():
    assert [s.name for s in open_sources({})] == ["local"]
    assert open_sources({"zotero_local": False}) == []
