"""Api: research notes as documents, the binder group, and the Research question (Wave 3.3)."""

from chisel.gui import api as api_module
from tests.test_gui_api import open_api


def test_notes_are_documents_not_indexed_and_listed_in_the_binder(tmp_path):
    api, root = open_api(tmp_path)
    assert api.get_workspace()["workspace"]["research"] == []
    node = next(n for n in api.get_workspace()["workspace"]["binder"] if n["id"] == "group:research")
    assert node == {"id": "group:research", "title": "Notebook", "kind": "research", "children": []}

    r = api.new_research_note("Tide tables")
    assert r["ok"] and r["id"] == "notebook/tide-tables.md"
    u = api.new_research_from_url("https://example.org/trams/timetable")
    assert u["ok"] and u["title"] == "example.org - timetable"
    (root / "notebook" / "tides").mkdir()
    (root / "notebook" / "tides" / "almanac.md").write_text("# Almanac\n\n[[Mara Vale]] reads it.\n")

    w = api.get_workspace()["workspace"]
    node = next(n for n in w["binder"] if n["id"] == "group:research")
    assert node["meta"] == "3"
    kids = {k["title"]: k for k in node["children"]}
    assert set(kids) == {"Tide tables", "example.org - timetable", "tides"}
    assert kids["tides"]["kind"] == "folder" and kids["tides"]["children"][0]["id"] == "notebook/tides/almanac.md"
    assert kids["Tide tables"]["kind"] == "document"
    assert [(x["id"], x["folder"]) for x in w["research"]] == [
        ("notebook/example-org-timetable.md", ""), ("notebook/tide-tables.md", ""),
        ("notebook/tides/almanac.md", "tides")]

    doc = api.read_document("notebook/tides/almanac.md")
    assert doc["ok"] and doc["kind"] == "research" and doc["kicker"] == "NOTEBOOK" and doc["title"] == "Almanac"
    # links in a note are highlighted but it is not a scene: no mentions, no spelling, no index
    spans = api.link_spans("notebook/tides/almanac.md", doc["text"])["spans"]
    assert any(s["kind"] in ("link", "mention") for s in spans)
    assert api.spelling("notebook/tides/almanac.md", "tehe wrongg")["enabled"] is False
    saved = api.save_document("notebook/tides/almanac.md", "# Almanac\n\nchanged\n", doc["mtime"])
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


def test_deleting_a_research_note_goes_to_the_trash_and_restores(tmp_path):
    api, root = open_api(tmp_path)
    note = api.new_research_note("Scrap")["id"]
    assert api.get_workspace()["workspace"]["status"]["trashCount"] == 0
    assert api.delete_research_note(note)["ok"]
    assert api.get_workspace()["workspace"]["status"]["trashCount"] == 1
    (item,) = api.list_trash()["items"]
    assert item["kind"] == "research" and item["title"] == "Scrap" and item["original"] == note
    r = api.restore_trash(item["name"])
    assert r["ok"] and r["id"] == note and r["kind"] == "research" and r["unplaced"] is False
    assert (root / note).is_file() and api.list_trash()["items"] == []
    api.delete_research_note(note)
    (item,) = api.list_trash()["items"]
    assert api.delete_forever(item["name"])["ok"] and api.list_trash()["items"] == []
    assert not (root / note).exists()


def test_research_question_uses_notes_and_canon_and_cites_sources(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    assert "notebook is empty" in api.research("tides?")["error"]
    (root / "notebook").mkdir()
    (root / "notebook" / "tides.md").write_text("# Tides\n\nThe spur floods at dusk.\n")
    (root / "notebook" / "trams.md").write_text("# Trams\n\nTrams stop at midnight.\n")
    seen = {}

    def fake(prompt, context, model, history=None, client=None):
        seen.update(prompt=prompt, context=context, model=model, history=history)
        return "It floods at dusk [1]."

    monkeypatch.setattr(api_module, "research_writer", fake)
    r = api.research("when does the spur flood?", [{"role": "user", "text": "hi"}])
    assert r["ok"] and r["reply"] == "It floods at dusk [1]."
    assert [s["id"] for s in r["sources"]] == ["notebook/tides.md"]       # only notes that matched
    assert "[1] Tides" in seen["context"] and "floods at dusk" in seen["context"]
    assert "Trams stop" not in seen["context"]
    assert "Mara Vale" in seen["context"]                                  # the canon travels too
    assert seen["history"] == [{"role": "user", "text": "hi"}]


def test_templates_and_send_selection_to_the_notebook(tmp_path):
    api, root = open_api(tmp_path)
    r = api.new_research_note("Harbour", "location")
    assert r["ok"] and "**What it looks like**" in (root / r["id"]).read_text(encoding="utf-8")
    assert api.new_research_note("Bad", "nope")["ok"] is False
    scene = api.get_workspace()["workspace"]["scenes"][0]["id"]
    before = (root / scene).read_text(encoding="utf-8")
    s = api.send_to_notebook("A passage worth keeping.", scene)
    assert s["ok"] and s["id"] == "notebook/clippings.md"
    assert "> A passage worth keeping." in (root / s["id"]).read_text(encoding="utf-8")
    assert (root / scene).read_text(encoding="utf-8") == before
    assert api.send_to_notebook("   ")["ok"] is False
    assert any(n["id"] == "notebook/clippings.md" for n in api.get_workspace()["workspace"]["research"])
