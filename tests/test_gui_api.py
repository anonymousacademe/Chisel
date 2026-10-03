"""Api: project lifecycle, document reads, id safety, thread-safety."""

import threading

from tests.gui_helpers import make_project
from chisel.core.project import Project
from chisel.gui.api import Api


def open_api(tmp_path):
    root = tmp_path / "p"
    make_project(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def test_no_project_open():
    api = Api()
    assert api.get_workspace() == {"workspace": None, "ok": True}
    assert api.read_document("manuscript/01-a.md")["ok"] is False


def test_open_missing_project_errors(tmp_path):
    r = Api().open_project(str(tmp_path / "nope"))
    assert r["ok"] is False and "not a Chisel project" in r["error"]


def test_open_and_workspace(tmp_path):
    api, root = open_api(tmp_path)
    w = api.get_workspace()["workspace"]
    assert w["project"]["title"] == "Test Novel"
    assert w["project"]["initials"] == "JW"
    assert [s["title"] for s in w["scenes"]] == ["Arrival", "The Archive"]
    assert w["status"]["sessionWords"] == 0
    assert api.recent_projects()["recents"][0]["path"] == str(root.resolve())


def test_new_project(tmp_path):
    api = Api()
    r = api.new_project("Fresh", str(tmp_path / "fresh"))
    assert r["ok"] and Project.is_project(tmp_path / "fresh")
    assert api.new_project("Again", str(tmp_path / "fresh"))["ok"] is False
    assert api.new_project("  ", str(tmp_path / "x"))["ok"] is False


def test_read_document(tmp_path):
    api, _ = open_api(tmp_path)
    scene = api.read_document("manuscript/01-arrival.md")
    assert scene["kind"] == "scene" and scene["kicker"] == "SCENE 01"
    assert scene["title"] == "Arrival" and scene["text"].startswith("# Arrival")
    assert [m["name"] for m in scene["mentions"]] == ["Mara Vale", "Lower Meridian", "Elias Vale"]
    assert scene["mtime"].isdigit()
    note = api.read_document("entities/characters/mara-vale.md")
    assert note["kind"] == "entity" and note["title"] == "Mara Vale"
    assert note["kicker"] == "CHARACTER"


def test_document_ids_cannot_escape(tmp_path):
    api, root = open_api(tmp_path)
    (tmp_path / "secret.md").write_text("x")
    for bad in ("../secret.md", "project.toml", "manuscript/../../secret.md",
                "/etc/passwd", "manuscript/nope.md", ".chisel/index.sqlite"):
        assert api.read_document(bad)["ok"] is False, bad


def test_concurrent_reads_share_the_index(tmp_path):
    api, _ = open_api(tmp_path)
    errors = []

    def work():
        for _ in range(20):
            r = api.get_workspace()
            if not r["ok"]:
                errors.append(r)
            r = api.read_document("manuscript/01-arrival.md")
            if not r["ok"]:
                errors.append(r)

    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors


# -- phase 2: save / conflict / scenes / spans -----------------------------------

def test_save_document_writes_and_reindexes(tmp_path):
    api, root = open_api(tmp_path)
    doc = api.read_document("manuscript/01-arrival.md")
    new = doc["text"] + "\nMara met [[Elias Vale]] again.\n"
    r = api.save_document(doc["id"], new, doc["mtime"])
    assert r["saved"] is True and r["mtime"] != doc["mtime"]
    assert (root / "manuscript/01-arrival.md").read_text() == new
    assert not list((root / "manuscript").glob("*.tmp"))
    assert any("again" in b.line for b in api.index.backlinks(api.entities[1]))
    # the next save carries the fresh mtime and succeeds
    assert api.save_document(doc["id"], new + "x", r["mtime"])["saved"] is True


def test_save_detects_external_change_and_keep_mine_overwrites(tmp_path):
    api, root = open_api(tmp_path)
    doc = api.read_document("manuscript/01-arrival.md")
    path = root / "manuscript/01-arrival.md"
    path.write_text("# Arrival\n\nChanged by the TUI.\n")  # someone else wrote
    r = api.save_document(doc["id"], "# Arrival\n\nMine.\n", doc["mtime"])
    assert r["saved"] is False and r["conflict"] is True
    assert "TUI" in path.read_text()  # untouched
    # same content as disk is not a conflict
    same = api.save_document(doc["id"], "# Arrival\n\nChanged by the TUI.\n", doc["mtime"])
    assert same["saved"] is True
    # keep mine
    forced = api.save_document(doc["id"], "# Arrival\n\nMine.\n", "stale", force=True)
    assert forced["saved"] is True and "Mine." in path.read_text()


def test_crlf_file_from_another_editor_is_read_as_lf_saved_as_lf_and_never_a_conflict(tmp_path):
    api, root = open_api(tmp_path)
    path = root / "manuscript/01-arrival.md"
    doc = api.read_document("manuscript/01-arrival.md")
    path.write_bytes(b"# Arrival\r\n\r\nWritten elsewhere.\r\n")   # another editor, CRLF
    # the same words with LF are not a change, even though the mtime moved
    r = api.save_document(doc["id"], "# Arrival\n\nWritten elsewhere.\n", doc["mtime"])
    assert r["saved"] is True and "conflict" not in r
    assert api.read_document("manuscript/01-arrival.md")["text"] == "# Arrival\n\nWritten elsewhere.\n"
    # our own save keeps LF on every platform
    fresh = api.read_document("manuscript/01-arrival.md")
    assert api.save_document(fresh["id"], fresh["text"] + "More.\n", fresh["mtime"])["saved"]
    assert b"\r" not in path.read_bytes()


def test_save_never_recreates_a_deleted_scene(tmp_path):
    api, root = open_api(tmp_path)
    doc = api.read_document("manuscript/02-the-archive.md")
    assert api.delete_scene(doc["id"])["ok"]
    assert not (root / "manuscript/02-the-archive.md").exists()
    r = api.save_document(doc["id"], doc["text"], doc["mtime"])
    assert r["ok"] is False
    assert not (root / "manuscript/02-the-archive.md").exists()


def test_save_entity_note_reloads_aliases(tmp_path):
    api, root = open_api(tmp_path)
    note = api.read_document("entities/characters/mara-vale.md")
    text = note["text"].replace("aliases:\n- Mara", "aliases:\n- Mara\n- Archivist")
    assert api.save_document(note["id"], text, note["mtime"])["saved"]
    assert "Archivist" in [a for e in api.entities for a in e.aliases]


def test_link_spans_uses_the_editor_buffer(tmp_path):
    api, _ = open_api(tmp_path)
    r = api.link_spans("manuscript/01-arrival.md", "Mara and Lower Meridian")
    assert [(s["kind"], s["target"]) for s in r["spans"]] == [
        ("mention", "Mara"), ("mention", "Lower Meridian")]
    assert api.link_spans("nope.md", "x")["ok"] is False


def test_scene_management(tmp_path):
    api, root = open_api(tmp_path)
    new = api.new_scene("Third Act")
    assert new["id"] == "manuscript/03-third-act.md"
    assert (root / new["id"]).read_text() == "# Third Act\n\n"
    assert api.new_scene("  ")["ok"] is False
    assert api.rename_scene(new["id"], "Final Act")["ok"]
    assert (root / new["id"]).read_text().startswith("# Final Act")
    moved = api.move_scene(new["id"], -1)
    assert moved["id"] == "manuscript/02-third-act.md"  # renames keep the filename
    top = api.move_scene("manuscript/01-arrival.md", -1)
    assert top["ok"] is False and "edge" in top["error"]
    titles = [s["title"] for s in api.get_workspace()["workspace"]["scenes"]]
    assert titles == ["Arrival", "Final Act", "The Archive"]
    assert api.delete_scene(moved["id"])["ok"]
    assert not (root / moved["id"]).exists()
    assert api.rename_scene("entities/characters/mara-vale.md", "x")["ok"] is False


def test_concurrent_saves_do_not_corrupt(tmp_path):
    api, root = open_api(tmp_path)
    doc = api.read_document("manuscript/01-arrival.md")
    results = []

    def work(i):
        results.append(api.save_document(doc["id"], f"# Arrival\n\nwriter {i}\n", None, force=True))

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r["ok"] and r["saved"] for r in results)
    text = (root / "manuscript/01-arrival.md").read_text()
    assert text.startswith("# Arrival\n\nwriter ") and text.count("writer") == 1


# -- phase 3: entities & notes ---------------------------------------------------

def test_get_entity_by_name_or_alias_with_backlinks(tmp_path):
    api, _ = open_api(tmp_path)
    by_alias = api.get_entity("Mara")
    assert by_alias["found"] and by_alias["name"] == "Mara Vale"
    assert by_alias["type"] == "character" and by_alias["aliases"] == ["Mara"]
    assert by_alias["id"] == "entities/characters/mara-vale.md"
    sources = {(b["sourceKind"], b["sourceTitle"]) for b in by_alias["backlinks"]}
    assert ("scene", "Arrival") in sources and ("scene", "The Archive") in sources
    missing = api.get_entity("Nobody")
    assert missing["ok"] and missing["found"] is False


def test_backlinks_skip_pending_draft_mentions(tmp_path):
    api, root = open_api(tmp_path)
    scene = root / "manuscript/01-arrival.md"
    scene.write_text("# Arrival\n\nNothing. <!--ai-->Mara Vale appears only in a draft.<!--/ai-->\n")
    assert api.rebuild_index()["ok"]
    titles = {b["sourceTitle"] for b in api.get_entity("Mara Vale")["backlinks"]}
    assert "Arrival" not in titles and "The Archive" in titles


def test_scene_context_counts(tmp_path):
    api, _ = open_api(tmp_path)
    r = api.scene_context("manuscript/01-arrival.md")
    counts = {m["name"]: m["count"] for m in r["mentions"]}
    assert counts == {"Mara Vale": 1, "Lower Meridian": 1, "Elias Vale": 1}
    assert all(m["backlinks"] >= 1 for m in r["mentions"])
    # the editor buffer wins over the file
    r2 = api.scene_context("manuscript/01-arrival.md", "Mara, Mara and Mara.")
    assert r2["mentions"] == [{"name": "Mara Vale", "type": "character", "count": 3, "backlinks": 2}]
    assert api.scene_context("entities/characters/mara-vale.md")["mentions"] == []


def test_create_entity_then_scenes_recognize_it(tmp_path):
    api, root = open_api(tmp_path)
    (root / "manuscript/02-the-archive.md").write_text("# The Archive\n\nThe Hollow Market was closed.\n")
    r = api.create_entity("Hollow Market", "place")
    assert r["ok"] and r["existed"] is False
    assert (root / r["id"]).is_file() and r["id"].startswith("entities/places/")
    spans = api.link_spans("manuscript/02-the-archive.md", "The Hollow Market was closed.")["spans"]
    assert [(s["kind"], s["target"]) for s in spans] == [("mention", "Hollow Market")]
    assert any(b["sourceTitle"] == "The Archive" for b in api.get_entity("Hollow Market")["backlinks"])
    again = api.create_entity("hollow market", "place")  # resolves, never duplicates
    assert again["existed"] is True and again["id"] == r["id"]
    assert len(list((root / "entities/places").glob("*.md"))) == 2


def test_create_entity_validates(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.create_entity("  ", "place")["ok"] is False
    assert api.create_entity("A/B", "place")["ok"] is False
    assert api.create_entity("X", "monster")["ok"] is False


def test_add_alias(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.add_alias("Mara Vale", "the archivist")["ok"]
    assert "the archivist" in api.get_entity("Mara Vale")["aliases"]
    spans = api.link_spans("manuscript/01-arrival.md", "Then the archivist left.")["spans"]
    assert [s["kind"] for s in spans] == ["mention"]
    assert api.add_alias("Nobody", "x")["ok"] is False
    assert api.add_alias("Mara Vale", " ")["ok"] is False


def test_new_project_without_folder_goes_to_default_location(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() on Windows
    api = Api()
    assert api.suggest_project_path("The Salt Road")["path"] == str(
        tmp_path / "novels" / "the-salt-road")
    assert api.suggest_project_path("   ")["path"] == ""
    assert api.new_project("The Salt Road", "")["ok"] is True
    assert (tmp_path / "novels" / "the-salt-road" / "project.toml").is_file()
    # a second project with the same title must not overwrite the first
    assert api.new_project("The Salt Road", "")["ok"] is False


def test_default_project_path_helper(tmp_path):
    from chisel.core.project import default_project_path

    assert default_project_path("Neon Requiem", tmp_path) == tmp_path / "neon-requiem"
    assert default_project_path("  ") is None
