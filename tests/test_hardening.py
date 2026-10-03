"""Regression tests for a batch of verified bugs (titles, renames, slugs, mentions...)."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from chisel.core import comments, drafts, fsutil, rename, snapshots
from chisel.core import entities as ent
from chisel.core import links
from chisel.core.index import Index
from chisel.core.project import Project
from chisel.gui import devserver
from chisel.gui.api import Api
from tests.gui_helpers import make_project


@pytest.fixture(autouse=True)
def _clear_daily():
    snapshots._daily_done.clear()
    yield
    snapshots._daily_done.clear()


def blank(tmp_path, title="Book") -> Project:
    project = Project.create(tmp_path / "book", title)
    (project.root / "manuscript" / "01-opening.md").unlink()
    return project


# -- 1. project.toml titles -------------------------------------------------------


@pytest.mark.parametrize("title", ['The "Quoted" Book', "back\\slash", "two\nlines",
                                   "tab\there", "del\x7fchar", "Zoe 王"])
def test_title_round_trips(tmp_path, title):
    Project.create(tmp_path / "p", title)
    assert Project.open(tmp_path / "p").title == title


def test_export_ok_when_remembering_options_fails(tmp_path, monkeypatch):
    from chisel.core import export
    project = blank(tmp_path)
    (project.manuscript_dir / "01-a.md").write_text("# A\n\nText.\n", encoding="utf-8")

    def boom(*a, **k):
        raise ValueError("bad toml")
    monkeypatch.setattr(export, "save_options", boom)
    opts = export.ExportOptions.from_dict({"format": "md"})
    result = export.run_export(project, opts)
    assert result.path.is_file()


# -- 2. staged renames roll back -----------------------------------------------------


def three_scenes(project):
    paths = []
    for i, name in enumerate("abc", 1):
        p = project.manuscript_dir / f"0{i}-{name}.md"
        p.write_text(f"# {name}\n", encoding="utf-8")
        paths.append(p)
    return paths


def fail_on_second(monkeypatch):
    real, calls = fsutil.rename, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 2:
            raise PermissionError("locked")
        return real(src, dst)
    monkeypatch.setattr(fsutil, "rename", flaky)


def test_apply_renames_rolls_back_on_failure(tmp_path, monkeypatch):
    project = blank(tmp_path)
    a, b, c = three_scenes(project)
    side = drafts.sidecar_path(project.root, a)
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text("{}", encoding="utf-8")
    fail_on_second(monkeypatch)
    with pytest.raises(PermissionError):
        project._apply_renames([(a, project.manuscript_dir / "09-a.md"),
                                (b, project.manuscript_dir / "08-b.md")])
    monkeypatch.undo()
    assert sorted(p.name for p in project.manuscript_dir.iterdir()) == \
        ["01-a.md", "02-b.md", "03-c.md"]
    assert side.is_file()
    assert project.last_renames == {}


def test_move_part_rolls_back_on_failure(tmp_path, monkeypatch):
    project = blank(tmp_path)
    p1, p2 = project.new_part("One"), project.new_part("Two")
    (p1 / "01-x.md").write_text("# x\n", encoding="utf-8")
    fail_on_second(monkeypatch)
    with pytest.raises(PermissionError):
        project.move_part(p1, 1)
    monkeypatch.undo()
    assert p1.is_dir() and p2.is_dir() and (p1 / "01-x.md").is_file()
    assert not [p for p in project.manuscript_dir.iterdir() if p.name.startswith(".")]


def test_open_recovers_orphaned_stage_files(tmp_path):
    project = blank(tmp_path)
    a = project.manuscript_dir / "01-a.md"
    a.write_text("# a\n", encoding="utf-8")
    side = drafts.sidecar_path(project.root, a)
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text("{}", encoding="utf-8")
    a.rename(a.with_name(".mv0-01-a.md"))
    side.rename(side.with_name(f".mv0-{side.name}"))
    Project.open(project.root)
    assert a.read_text(encoding="utf-8") == "# a\n" and side.is_file()


def test_open_leaves_stage_file_when_name_taken(tmp_path):
    project = blank(tmp_path)
    (project.manuscript_dir / "01-a.md").write_text("new", encoding="utf-8")
    stray = project.manuscript_dir / ".mv0-01-a.md"
    stray.write_text("old", encoding="utf-8")
    Project.open(project.root)
    assert stray.is_file()
    assert (project.manuscript_dir / "01-a.md").read_text(encoding="utf-8") == "new"


# -- 3. slugs and entity creation ------------------------------------------------------


def test_slugify_keeps_unicode_and_is_windows_safe():
    assert ent.slugify("王小明") == "王小明"
    assert ent.slugify("Елена Ivanova") == "елена-ivanova"
    assert ent.slugify("Élan") == "elan"
    assert ent.slugify("Elara Vance") == "elara-vance"
    assert ent.slugify('a<b>:"c"?*') == "abc"
    assert ent.slugify("CON") == "con-note"
    assert ent.slugify("???") == "untitled"


def test_non_latin_entities_get_distinct_notes(tmp_path):
    project = blank(tmp_path)
    _, p1 = project.create_entity("王小明")
    _, p2 = project.create_entity("李华")
    assert p1 != p2 and p1.stem != "untitled"
    assert ent.load_entity(p1).name == "王小明"
    assert "王" in p1.read_text(encoding="utf-8")  # readable YAML


def test_create_entity_disambiguates_slug_collisions(tmp_path):
    project = blank(tmp_path)
    e1, p1 = project.create_entity("Wren")
    e2, p2 = project.create_entity("wren")
    assert p1 != p2 and e2.name == "wren"
    assert e1.name == "Wren"
    e3, p3 = project.create_entity("Élan")
    e4, p4 = project.create_entity("Elan")
    assert p3 != p4 and e4.name == "Elan"
    # the same name again returns the existing one
    again, pa = project.create_entity("Wren")
    assert (again.name, pa) == ("Wren", p1)
    again, pa = project.create_entity("Elan")
    assert pa == p4


def test_create_entity_returns_owner_of_alias(tmp_path):
    project = blank(tmp_path)
    vesper, _ = project.create_entity("Vesper Quill")
    ent.add_alias(vesper, "Wren")
    got, path = project.create_entity("Wren")
    assert got.name == "Vesper Quill" and path == vesper.path
    assert len(project.list_entity_files()) == 1


# -- 4. mentions: quotes and normalization ------------------------------------------------


def test_mentions_treat_curly_and_straight_quotes_alike():
    text = "She met O’Brien and O'Brien."
    found = links.find_mentions(text, ["O'Brien"])
    assert [(l.start, l.end) for l in found] == [(8, 15), (20, 27)]
    assert text[8:15] == "O’Brien"
    assert [(l.start, l.end) for l in links.find_mentions("O'Hara", ["O’Hara"])] == [(0, 6)]


def test_mentions_match_nfc_and_nfd_with_original_offsets():
    nfd = "x Élan sat. Élan stood."
    found = links.find_mentions(nfd, ["Élan"])
    assert [nfd[l.start:l.end] for l in found] == ["Élan", "Élan"]
    assert found[0].start == 2 and found[0].end == 7
    nfc = "Élan here"
    assert len(links.find_mentions(nfc, ["Élan"])) == 1


def test_mention_not_found_inside_longer_accented_word():
    assert links.find_mentions("Zoë ran", ["Zoe"]) == []
    assert links.find_mentions("Zoë ran", ["Zoe"]) == []


def test_resolve_ignores_quote_style_and_normalization():
    e = ent.Entity(name="O'Brien", aliases=["Élan"])
    assert ent.resolve("O’Brien", [e]) is e
    assert ent.resolve("Élan", [e]) is e


def test_index_backlinks_follow_curly_quotes(tmp_path):
    e = ent.Entity(name="O'Brien")
    idx = Index(tmp_path / "i.sqlite")
    idx.update_file("manuscript/01-a.md", "Then O’Brien left.\n", e.names)
    assert len(idx.backlinks(e)) == 1
    idx.close()


# -- 5. index rows with odd line separators ----------------------------------------------


def test_backlink_row_ignores_unicode_line_separators(tmp_path):
    e = ent.Entity(name="Mara")
    idx = Index(tmp_path / "i.sqlite")
    text = "one two\x0bthree\x0cfour\x85five\nMara arrives.\n"
    idx.update_file("manuscript/01-a.md", text, e.names)
    (b,) = idx.backlinks(e)
    assert b.row == 1 and b.line == "Mara arrives."
    idx.close()


# -- 6. length caps -----------------------------------------------------------------------


def test_slug_is_capped():
    assert len(ent.slugify("word " * 100)) <= ent.MAX_SLUG


def test_scene_path_and_trash_names_are_capped(tmp_path):
    project = blank(tmp_path)
    long_title = "very long title " * 40
    path = project.next_scene_path(long_title)
    assert len(path.name) < 80
    path.write_text("# x\n", encoding="utf-8")
    project.delete_scene(path)
    (item,) = project.list_trash()
    assert len(item.name) <= 15 + 1 + 120 + 40
    assert project.restore_scene(item.name).is_file()
    # an old project with an overlong file name still trashes and restores
    old = project.manuscript_dir / ("02-" + "z" * 200 + ".md")
    old.write_text("# old\n", encoding="utf-8")
    dest = project.delete_scene(old)
    assert len(dest.name) < 200 and dest.is_file()
    assert project.list_trash()


# -- 7. undo keeps its journal when it could not finish ------------------------------------


def test_undo_keeps_journal_when_files_skipped(tmp_path):
    project = blank(tmp_path)
    project.create_entity("Mara")
    a = project.manuscript_dir / "01-a.md"
    a.write_text("Mara one.\n", encoding="utf-8")
    e = ent.resolve("Mara", project.load_entities())
    plan = rename.plan_rename(project, e, "Nia")
    result = rename.apply_rename(project, plan, plan.default_ids())
    a.write_text("Nia one. More words.\n", encoding="utf-8")
    undone = rename.undo_rename(project, result.undo_id)
    assert "manuscript/01-a.md" in undone.skipped
    assert rename.latest_undo(project) is not None  # journal survives
    a.write_text("Nia one.\n", encoding="utf-8")  # back to the post-rename text
    again = rename.undo_rename(project, result.undo_id)
    assert a.read_text(encoding="utf-8") == "Mara one.\n" and again.skipped == []
    assert rename.latest_undo(project) is None


# -- A. aliases may not steal another note's name ---------------------------------------------


def test_add_alias_refuses_names_of_other_notes(tmp_path):
    api = Api()
    root = tmp_path / "p"
    make_project(root)
    assert api.open_project(str(root))["ok"]
    api.add_alias("Mara Vale", "Zed")
    r = api.add_alias("Mara Vale", "Elias")  # an alias of Elias Vale
    assert r["ok"] is False and "already a name or alias of another note" in r["error"]
    r = api.add_alias("Mara Vale", "lower meridian")
    assert r["ok"] is False
    assert ent.resolve("Elias", api.entities).name == "Elias Vale"
    r = api.apply_aliases([{"entity": "Mara Vale", "surface": "Elias"},
                           {"entity": "Mara Vale", "surface": "Em"}])
    assert r["added"] == 1
    mara = ent.resolve("Mara Vale", api.entities)
    assert "Elias" not in mara.aliases and "Em" in mara.aliases


def test_core_add_alias_checks_other_entities(tmp_path):
    project = blank(tmp_path)
    a, _ = project.create_entity("Alpha")
    project.create_entity("Beta")
    with pytest.raises(ValueError):
        ent.add_alias(a, "beta", project.load_entities())


# -- B. a stray non-UTF-8 file does not stop a project from opening ----------------------------


def test_non_utf8_files_do_not_break_open_workspace_or_rebuild(tmp_path):
    root = tmp_path / "p"
    make_project(root)
    bad_scene = root / "manuscript" / "03-bad.md"
    bad_scene.write_bytes(b"# Bad\n\nMara \xff here.\n")
    bad_note = root / "entities" / "characters" / "bad.md"
    bad_note.write_bytes(b"---\nname: Bad\ntype: character\naliases: []\n---\n\n\xff\n")
    before = (bad_scene.read_bytes(), bad_note.read_bytes())
    api = Api()
    assert api.open_project(str(root))["ok"]
    assert api.get_workspace()["ok"]
    assert api.rebuild_index()["ok"]
    assert (bad_scene.read_bytes(), bad_note.read_bytes()) == before  # never rewritten


# -- C. devserver argument handling ---------------------------------------------------------------


def test_devserver_bad_bodies(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    server = devserver.serve(Api(), dist=tmp_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/api/"

    def post(name, body):
        req = urllib.request.Request(base + name, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    try:
        for body in (b'{"args": 5}', b'{"args": null}', b"[1, 2]", b'{"args": {"a": 1}}'):
            status, data = post("ping", body)
            assert status == 200 and data["ok"] is False
        status, data = post("ping", b'{"args": [1, 2, 3]}')  # wrong arity
        assert status == 200 and data["ok"] is False
        status, data = post("ping", b"{not json")
        assert status == 400 and data["ok"] is False
        status, data = post("ping", b'{"args": []}')
        assert status == 200 and data["pong"] is True
    finally:
        server.shutdown()


# -- D. never overwrite a non-UTF-8 file with lossy text ---------------------------------------

LATIN1 = b"# Caf\xe9\n\nMara walked to the caf\xe9.\n"


def _api(tmp_path):
    root = tmp_path / "p"
    make_project(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def _bad(path, data=LATIN1):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _refused(result, path):
    assert result["ok"] is False
    assert path.name in result["error"] and "not valid UTF-8" in result["error"]
    assert "convert it to UTF-8" in result["error"]


@pytest.mark.parametrize("auto", [True, False])
def test_save_scene_refuses_non_utf8(tmp_path, monkeypatch, auto):
    monkeypatch.setattr(snapshots, "auto_enabled", lambda: auto)
    api, root = _api(tmp_path)
    scene = root / "manuscript" / "01-arrival.md"
    data = _bad(scene)
    doc = api.read_document("manuscript/01-arrival.md")
    assert doc["ok"]  # reading stays lenient
    for base in (doc["mtime"], None):
        for force in (False, True):
            r = api.save_document("manuscript/01-arrival.md", doc["text"] + "more", base, force)
            _refused(r, scene)
    assert scene.read_bytes() == data
    assert not list(root.rglob("*.tmp"))
    assert not (root / ".snapshots").exists() or not list((root / ".snapshots").rglob("*.md"))


@pytest.mark.parametrize("rel", ["entities/characters/mara-vale.md", "style.md", "dictionary.txt",
                                 "notebook/notes.md"])
def test_save_other_kinds_refuse_non_utf8(tmp_path, rel):
    api, root = _api(tmp_path)
    path = root / rel
    data = _bad(path, b"---\nname: Mara Vale\ntype: character\naliases: []\n---\n\ncaf\xe9\n"
                if rel.startswith("entities") else b"# Notes\n\ncaf\xe9\n")
    doc = api.read_document(rel)
    assert doc["ok"], doc
    r = api.save_document(rel, doc["text"] + "x", doc["mtime"])
    _refused(r, path)
    assert path.read_bytes() == data


def test_rename_scene_refuses_non_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "auto_enabled", lambda: True)
    api, root = _api(tmp_path)
    scene = root / "manuscript" / "01-arrival.md"
    data = _bad(scene)
    _refused(api.rename_scene("manuscript/01-arrival.md", "New title"), scene)
    assert scene.read_bytes() == data
    with pytest.raises(fsutil.NotUtf8Error):
        api.project.rename_scene(scene, "x")
    assert scene.read_bytes() == data


def test_entity_saves_refuse_non_utf8(tmp_path):
    api, root = _api(tmp_path)
    note = root / "entities" / "characters" / "mara-vale.md"
    data = _bad(note, b"---\nname: Mara Vale\ntype: character\naliases: [Mara]\n---\n\ncaf\xe9\n")
    entity = ent.load_entity(note)  # lenient load still works
    assert entity.name == "Mara Vale"
    with pytest.raises(fsutil.NotUtf8Error):
        ent.save_entity(entity, note)
    with pytest.raises(fsutil.NotUtf8Error):
        ent.add_alias(entity, "Em")
    api.reload_entities()
    _refused(api.add_alias("Mara Vale", "Em"), note)
    _refused(api.apply_aliases([{"entity": "Mara Vale", "surface": "Emm"}]), note)
    assert note.read_bytes() == data


def test_notebook_and_style_core_writes_refuse_non_utf8(tmp_path):
    from chisel.core import research, spelling, style
    project = blank(tmp_path)
    folder = research.research_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    paths = [folder / research.CLIPPINGS, folder / research.ASSISTANT_NOTES,
             style.style_path(project), spelling.project_dictionary_path(project)]
    datas = {p: _bad(p) for p in paths}
    with pytest.raises(fsutil.NotUtf8Error):
        research.append_clipping(project, "a passage")
    with pytest.raises(fsutil.NotUtf8Error):
        research.append_assistant_note(project, "q", "a")
    with pytest.raises(fsutil.NotUtf8Error):
        style.save_style(project, "new")
    with pytest.raises(fsutil.NotUtf8Error):
        spelling.add_to_dictionary(spelling.project_dictionary_path(project), "zorp")
    with pytest.raises(fsutil.NotUtf8Error):
        spelling.remove_from_dictionary(spelling.project_dictionary_path(project), "zorp")
    assert {p: p.read_bytes() for p in datas} == datas
    assert not list(project.root.rglob("*.bak"))


def test_snapshots_never_crash_or_copy_lossy(tmp_path):
    api, root = _api(tmp_path)
    scene = root / "manuscript" / "01-arrival.md"
    data = _bad(scene)
    project = api.project
    assert snapshots.ensure_daily(project, scene, "other text") is None
    with pytest.raises(fsutil.NotUtf8Error):
        snapshots.create(project, scene, "x")
    assert snapshots.snapshot_all(project) == 1  # the other scene only
    assert snapshots.list_snapshots(project, scene) == []
    assert scene.read_bytes() == data


def test_rename_everywhere_skips_non_utf8_files(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "auto_enabled", lambda: True)
    api, root = _api(tmp_path)
    other = root / "manuscript" / "02-the-archive.md"
    data = _bad(other, b"# Archive\n\nMara read caf\xe9 files.\n")
    good = root / "manuscript" / "01-arrival.md"
    r = api.rename_preview("Mara Vale", "Nia Vale", True, {"Mara": "Nia"})
    assert r["ok"]
    assert {f["file"] for f in r["files"]} == {"manuscript/01-arrival.md"}  # skipped, not crashed
    done = api.rename_apply(r["plan"], [o["id"] for f in r["files"] for o in f["occurrences"]])
    assert done["ok"]
    assert other.read_bytes() == data
    assert "Nia stepped off" in good.read_text(encoding="utf-8")


def test_rename_apply_refuses_file_that_went_bad_after_preview(tmp_path):
    api, root = _api(tmp_path)
    scene = root / "manuscript" / "01-arrival.md"
    r = api.rename_preview("Mara Vale", "Nia Vale", True, {"Mara": "Nia"})
    assert r["ok"]
    data = _bad(scene, b"# Arrival\n\nMara at the caf\xe9.\n")
    done = api.rename_apply(r["plan"], [o["id"] for f in r["files"] for o in f["occurrences"]])
    assert done["ok"] is False
    assert scene.read_bytes() == data
    assert (root / "entities/characters/mara-vale.md").exists()  # nothing was renamed


def test_rename_preview_refuses_non_utf8_note(tmp_path):
    api, root = _api(tmp_path)
    note = root / "entities" / "characters" / "mara-vale.md"
    data = _bad(note, b"---\nname: Mara Vale\ntype: character\naliases: []\n---\n\ncaf\xe9\n")
    _refused(api.rename_preview("Mara Vale", "Nia Vale"), note)
    assert note.read_bytes() == data


def test_valid_utf8_still_saves_bom_and_crlf(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "auto_enabled", lambda: True)
    api, root = _api(tmp_path)
    scene = root / "manuscript" / "01-arrival.md"
    scene.write_bytes("﻿# Café\r\n\r\nMara.\r\n".encode("utf-8"))
    doc = api.read_document("manuscript/01-arrival.md")
    r = api.save_document("manuscript/01-arrival.md", "# Café\n\nMara, again.\n", doc["mtime"])
    assert r["ok"] and r["saved"]
    assert scene.read_bytes() == "# Café\n\nMara, again.\n".encode("utf-8")
    assert api.rename_scene("manuscript/01-arrival.md", "Fresh")["ok"]
    assert fsutil.is_valid_utf8(scene) and fsutil.is_valid_utf8(root / "missing.md")


def test_notebook_slug_is_capped(tmp_path):
    from chisel.core import research
    project = blank(tmp_path)
    path = research.new_note(project, "word " * 400)
    assert len(path.stem) <= ent.MAX_SLUG + 4 and path.is_file()


def test_devserver_bad_content_length(tmp_path):
    import http.client
    (tmp_path / "index.html").write_text("<html></html>")
    server = devserver.serve(Api(), dist=tmp_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for value in ("abc", "-5"):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
            conn.putrequest("POST", "/api/ping")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", value)
            conn.endheaders()
            resp = conn.getresponse()
            assert resp.status == 400
            resp.read()
            conn.close()
    finally:
        server.shutdown()
        server.server_close()
