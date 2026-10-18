"""Shapes seen against a real Zotero 10.0.6 local API (2026-10-18) that the fake-server tests did not cover."""

import json

from chisel.core.zotero.local import LocalSource
from chisel.core.zotero.web import csl_of

ITEM = {"id": "ENCWRRI", "type": "webpage", "citation-key": "ENCWRRI", "title": "ENCWRRI"}


def test_csl_of_accepts_a_dict_the_web_api_shape():
    assert csl_of({"csljson": ITEM}, "K", {}) == ITEM


def test_csl_of_parses_the_local_api_json_string_holding_an_array():
    raw = json.dumps([ITEM], indent="\t")          # the local API sends tabs and newlines inside a string
    assert csl_of({"csljson": raw}, "K", {}) == ITEM


def test_csl_of_falls_back_to_a_minimal_record():
    for raw in (None, "", "not json", "[]", [], {}, 5):
        out = csl_of({"csljson": raw}, "K1", {"itemType": "book", "title": "T"})
        assert out == {"id": "K1", "type": "book", "title": "T"}


def test_local_fetch_allows_a_slow_cold_read_but_restores_the_short_probe_timeout():
    src = LocalSource(timeout=5.0)
    seen = []

    class Lib:
        warnings = []

        def fetch(self, *args):
            seen.append(src._http.timeout)
            return "result"

    src._lib = Lib()
    src._server_id = "sid"
    assert src.fetch(None, None) == "result"
    assert seen == [LocalSource.FETCH_TIMEOUT]
    assert src._http.timeout == 5.0
