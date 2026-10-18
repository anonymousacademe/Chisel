"""P8a Python half: research binder groups and the zotero_collections bridge method."""

from chisel.core import entities as ent
from chisel.core.project import Project
from chisel.core.zotero import Status, ZoteroError
from chisel.gui import research_sources_api as mod
from chisel.gui.api import Api
from tests.gui_helpers import make_project


def research_api(tmp_path):
    project = Project.create(tmp_path / "paper", "Paper", "research")
    api = Api()
    api._load(project)
    return api, project


def workspace(api):
    ws = api.get_workspace()
    return ws.get("workspace", ws)


def group(ws, gid):
    return next(n for n in ws["binder"] if n["id"] == gid)


def test_research_binder_lists_sources_and_concepts(tmp_path):
    api, project = research_api(tmp_path)
    s1, p1 = project.create_entity("smith2024", "source")
    s1.extra["year"] = 2024
    p1.write_text(s1.to_markdown(), encoding="utf-8", newline="\n")
    project.create_entity("smith2020", "source")
    project.create_entity("Kalman filter", "method")
    project.create_entity("Streamflow", "concept")
    project.create_entity("Mara", "character")
    api._entities_changed()
    ws = workspace(api)
    src = group(ws, "group:characters")
    assert src["title"] == "Sources" and src["kind"] == "characters"
    by = {c["title"]: c for c in src["children"]}
    assert set(by) == {"smith2024", "smith2020"}
    assert by["smith2024"]["meta"] == "2024" and "meta" not in by["smith2020"]
    assert by["smith2024"]["kind"] == "entity"
    world = group(ws, "group:world")
    assert world["title"] == "Concepts and methods"
    assert {c["title"] for c in world["children"]} == {"Kalman filter", "Streamflow"}


def test_source_note_opens_as_entity(tmp_path):
    api, project = research_api(tmp_path)
    _, path = project.create_entity("smith2024", "source")
    rid = path.relative_to(project.root).as_posix()
    assert "sources" in rid
    r = api.read_document(rid)
    assert r["ok"] and r["kind"] == "entity"


def test_story_binder_unchanged(tmp_path):
    api = Api()
    api._load(make_project(tmp_path / "n"))
    ws = workspace(api)
    assert {c["title"] for c in group(ws, "group:characters")["children"]} == {"Mara Vale", "Elias Vale"}
    assert [c["title"] for c in group(ws, "group:world")["children"]] == ["Lower Meridian"]


class Backend:
    def __init__(self, name, ok=True, rows=None, err=None):
        self.name, self._ok, self._rows, self._err = name, ok, rows, err

    def probe(self):
        return Status(self._ok, "" if self._ok else "down")

    def collections(self):
        if self._err:
            raise ZoteroError(self._err)
        return self._rows


def test_collections_first_answering_backend(tmp_path, monkeypatch):
    api, _ = research_api(tmp_path)
    rows = [{"key": "A", "path": "A", "items": 3}]
    monkeypatch.setattr(mod.zotero, "open_sources",
                        lambda s: [Backend("web", ok=False), Backend("local", rows=rows), Backend("file")])
    assert api.zotero_collections() == {"ok": True, "collections": rows}


def test_collections_error_and_non_research(tmp_path, monkeypatch):
    api, _ = research_api(tmp_path)
    monkeypatch.setattr(mod.zotero, "open_sources", lambda s: [Backend("local", err="boom")])
    r = api.zotero_collections()
    assert not r["ok"] and "boom" in r["error"]
    story = Api()
    story._load(make_project(tmp_path / "n"))
    assert not story.zotero_collections()["ok"]
