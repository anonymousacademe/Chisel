"""Research usability slice 1 (Python half): opening note, citation spans, source search/card, open in Zotero."""

import os

from chisel.core import desktop
from chisel.core import entities as ent
from chisel.core.links import find_citations
from chisel.core.project import SAMPLE_RESEARCH_SCENE, SAMPLE_SCENE, Project
from chisel.core.spans import compute_spans
from chisel.gui import research_sources_api as mod
from chisel.gui import workspace as ws
from chisel.gui.api import Api


def make(tmp_path):
    project = Project.create(tmp_path / "paper", "Paper", "research")
    csl = {"title": "Digital twins for water", "container-title": "Water Research", "DOI": "10.1/x",
           "issued": {"date-parts": [[2024]]}}
    notes = [
        ent.Entity(name="daneshgar2024", type="source", aliases=["Daneshgar et al. 2024"],
                   extra={"key": "daneshgar2024", "zotero_key": "ABCD1234", "title": "Digital twins for water",
                          "authors": "Daneshgar, S.", "year": 2024, "csl": csl}),
        ent.Entity(name="lee2020", type="source", aliases=["Lee 2020"],
                   extra={"key": "lee2020", "zotero_key": "bad", "title": "Sludge", "year": 2020}),
    ]
    for n in notes:
        ent.save_entity(n, project.root / "entities" / "sources" / f"{n.name}.md")
    api = Api()
    api._load(project)
    return api, project


def test_sample_opening_note(tmp_path):
    assert find_citations(SAMPLE_RESEARCH_SCENE) == []
    assert len(SAMPLE_RESEARCH_SCENE.splitlines()) < 25
    project = Project.create(tmp_path / "p", "P", "research")
    assert (project.root / "manuscript" / "01-opening.md").read_text(encoding="utf-8") == SAMPLE_RESEARCH_SCENE
    story = Project.create(tmp_path / "s", "S")
    assert (story.root / "manuscript" / "01-opening.md").read_text(encoding="utf-8") == SAMPLE_SCENE


def test_citation_spans(tmp_path):
    api, project = make(tmp_path)
    text = "See [[@daneshgar2024]] and [[@daneshgar2024; @nope]] \U0001F600 [[+@lee2020, p. 3]]."
    spans = [s for s in api.link_spans("manuscript/01-opening.md", text)["spans"] if s["kind"] == "citation"]
    assert [s["status"] for s in spans] == ["resolved", "unresolved", "resolved"]
    assert spans[0]["label"] == "Daneshgar et al. 2024" and spans[0]["title"] == "Digital twins for water"
    assert spans[1]["keys"] == ["daneshgar2024", "nope"] and spans[1]["label"] == "Daneshgar et al. 2024; nope"
    assert spans[1]["title"] == ""
    units = text.encode("utf-16-le")
    assert units[spans[2]["start"] * 2:spans[2]["end"] * 2].decode("utf-16-le").startswith("[[+@lee")


def test_story_spans_unchanged():
    spans = compute_spans("A [[@x]] b", [])
    assert all(s["kind"] != "citation" for s in spans)


def test_search_and_card(tmp_path):
    api, _ = make(tmp_path)
    assert [s["key"] for s in api.search_sources("")["sources"]] == ["daneshgar2024", "lee2020"]
    assert [s["key"] for s in api.search_sources("TWINS 2024")["sources"]] == ["daneshgar2024"]
    assert api.search_sources("zzz")["sources"] == []
    card = api.source_card("entities/sources/daneshgar2024.md")
    assert card["citeAs"] == "[[@daneshgar2024]]" and card["zoteroKey"] == "ABCD1234"
    assert card["venue"] == "Water Research" and card["doi"] == "10.1/x" and card["year"] == "2024"
    assert api.source_card("manuscript/01-opening.md")["ok"] is False


def test_list_sources_display(tmp_path):
    api, _ = make(tmp_path)
    row = api.list_sources()["sources"][0]
    assert row["title"] == "Daneshgar et al. 2024"
    assert row["description"] == "daneshgar2024 - Digital twins for water"
    rows = [e for e in ws.entity_summaries(api.project, api.entities) if e["type"] == "source"]
    assert rows[0]["display"] == "Daneshgar et al. 2024"


def test_open_in_zotero(tmp_path, monkeypatch):
    api, _ = make(tmp_path)
    seen = []
    monkeypatch.setattr(mod, "open_uri", lambda u: seen.append(u) or True)
    assert api.open_in_zotero("entities/sources/daneshgar2024.md")["ok"] is True
    assert seen == ["zotero://select/library/items/ABCD1234"]
    assert api.open_in_zotero("entities/sources/lee2020.md")["ok"] is False
    assert len(seen) == 1


def test_open_uri_validation(monkeypatch):
    seen = []
    monkeypatch.setattr(os, "startfile", seen.append, raising=False)
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda *a, **k: seen.append(a[0]))
    for bad in ("https://x.org", "zotero://select/library/items/abc", "zotero://select/library/items/ABCD1234/x",
                "zotero://select/library/items/ABCD1234\n", "file:///c:/x"):
        assert desktop.open_uri(bad) is False
    assert seen == []
    assert desktop.open_uri("zotero://select/library/items/ABCD1234") is True
    assert len(seen) == 1


def test_item_collections(tmp_path, monkeypatch):
    api, _ = make(tmp_path)

    class Resp:
        status = 200

        def json(self):
            return {"data": {"collections": ["C1", "C9"]}}

    class Http:
        def get(self, path, params=None, headers=None):
            assert path == "/users/0/items/ABCD1234"
            return Resp()

    class Lib:
        http = Http()
        user_path = "/users/0"

        def _ok(self, resp, what):
            pass

        def collections(self):
            return [{"key": "C1", "path": "A / B"}]

    class Src:
        name = "local"
        _lib = Lib()

        def probe(self):
            return type("S", (), {"ok": True})()

    monkeypatch.setattr(mod.zotero, "open_sources", lambda s: [Src()])
    out = api.zotero_item_collections("entities/sources/daneshgar2024.md")
    assert out["collections"] == ["A / B", "C9"]
    monkeypatch.setattr(mod.zotero, "open_sources", lambda s: [])
    assert api.zotero_item_collections("entities/sources/daneshgar2024.md")["ok"] is False
