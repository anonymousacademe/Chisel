"""Api: research notes as documents, the binder group, and the Research question (Wave 3.3)."""

from lorewrite.gui import api as api_module
from tests.test_gui_api import open_api


def test_notes_are_documents_not_indexed_and_listed_in_the_binder(tmp_path):
    api, root = open_api(tmp_path)
    assert api.get_workspace()["workspace"]["research"] == []
    node = next(n for n in api.get_workspace()["workspace"]["binder"] if n["id"] == "group:research")
    assert node == {"id": "group:research", "title": "Research", "kind": "research", "children": []}

    r = api.new_research_note("Tide tables")
    assert r["ok"] and r["id"] == "research/tide-tables.md"
    u = api.new_research_from_url("https://example.org/trams/timetable")
    assert u["ok"] and u["title"] == "example.org - timetable"
    (root / "research" / "tides").mkdir()
    (root / "research" / "tides" / "almanac.md").write_text("# Almanac\n\n[[Mara Vale]] reads it.\n")

    w = api.get_workspace()["workspace"]
    node = next(n for n in w["binder"] if n["id"] == "group:research")
    assert node["meta"] == "3"
    kids = {k["title"]: k for k in node["children"]}
    assert set(kids) == {"Tide tables", "example.org - timetable", "tides"}
    assert kids["tides"]["kind"] == "folder" and kids["tides"]["children"][0]["id"] == "research/tides/almanac.md"
    assert kids["Tide tables"]["kind"] == "document"
    assert [(x["id"], x["folder"]) for x in w["research"]] == [
        ("research/example-org-timetable.md", ""), ("research/tide-tables.md", ""),
        ("research/tides/almanac.md", "tides")]

    doc = api.read_document("research/tides/almanac.md")
    assert doc["ok"] and doc["kind"] == "research" and doc["kicker"] == "RESEARCH" and doc["title"] == "Almanac"
    # links in a note are highlighted but it is not a scene: no mentions, no spelling, no index
    spans = api.link_spans("research/tides/almanac.md", doc["text"])["spans"]
    assert any(s["kind"] in ("link", "mention") for s in spans)
    assert api.spelling("research/tides/almanac.md", "tehe wrongg")["enabled"] is False
    saved = api.save_document("research/tides/almanac.md", "# Almanac\n\nchanged\n", doc["mtime"])
    assert saved["saved"] is True
    assert not any("research" in str(src) for src in _indexed_sources(api))   # never in the link index


def _indexed_sources(api):
    # every file the link index knows about
    return [b.source for e in api.entities for b in api.index.backlinks(e)]


def test_delete_only_research_notes(tmp_path):
    api, root = open_api(tmp_path)
    note = api.new_research_note("Scrap")["id"]
    assert api.delete_research_note("manuscript/01-arrival.md")["ok"] is False
    assert api.delete_research_note(note)["ok"] is True and not (root / note).exists()


def test_research_question_uses_notes_and_canon_and_cites_sources(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    assert "no research notes" in api.research("tides?")["error"]
    (root / "research").mkdir()
    (root / "research" / "tides.md").write_text("# Tides\n\nThe spur floods at dusk.\n")
    (root / "research" / "trams.md").write_text("# Trams\n\nTrams stop at midnight.\n")
    seen = {}

    def fake(prompt, context, model, history=None, client=None):
        seen.update(prompt=prompt, context=context, model=model, history=history)
        return "It floods at dusk [1]."

    monkeypatch.setattr(api_module, "research_writer", fake)
    r = api.research("when does the spur flood?", [{"role": "user", "text": "hi"}])
    assert r["ok"] and r["reply"] == "It floods at dusk [1]."
    assert [s["id"] for s in r["sources"]] == ["research/tides.md"]       # only notes that matched
    assert "[1] Tides" in seen["context"] and "floods at dusk" in seen["context"]
    assert "Trams stop" not in seen["context"]
    assert "Mara Vale" in seen["context"]                                  # the canon travels too
    assert seen["history"] == [{"role": "user", "text": "hi"}]
