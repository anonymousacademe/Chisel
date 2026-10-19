"""Zotero collection listing (core/zotero): paging, paths, fakes only."""

import json

from chisel.core.zotero.web import PAGE_LIMIT, ZoteroLibrary, collection_paths


def row(key, name, parent=False, n=0):
    return {"key": key, "data": {"key": key, "name": name, "parentCollection": parent}, "meta": {"numItems": n}}


class Resp:
    def __init__(self, rows, total):
        self.status, self.headers, self._rows, self._total = 200, {}, rows, total

    def json(self):
        return self._rows

    def int_header(self, name):
        return self._total if name == "Total-Results" else None


class FakeHTTP:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def get(self, path, params=None, headers=None):
        self.calls.append((path, dict(params or {})))
        s = params["start"]
        return Resp(self.rows[s:s + params["limit"]], len(self.rows))


def test_paths_and_counts():
    out = collection_paths([row("B", "WRRI", "A", 7), row("A", "AI and Computing", False, 2), row("C", "x", False, 1)])
    assert [(c["path"], c["items"]) for c in out] == [("AI and Computing", 2), ("AI and Computing / WRRI", 7),
                                                       ("x", 1)]


def test_missing_count_is_none_and_parent_cycle_ends():
    out = collection_paths([{"key": "A", "data": {"name": "a", "parentCollection": "B"}},
                            {"key": "B", "data": {"name": "b", "parentCollection": "A"}}])
    assert len(out) == 2 and all(c["items"] is None for c in out)


def test_pages_through_more_than_a_hundred():
    rows = [row(f"K{i:03d}", f"c{i:03d}") for i in range(PAGE_LIMIT * 2 + 30)]
    http = FakeHTTP(rows)
    got = ZoteroLibrary(http, "/users/0").collections()
    assert len(got) == len(rows)
    assert [c[1]["start"] for c in http.calls] == [0, 100, 200]
    assert http.calls[0][0] == "/users/0/collections"
    json.dumps(got)
