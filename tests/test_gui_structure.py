"""Api: parts, unplaced scenes, trash, scene details (Wave 1, GUI backend)."""

import json
from pathlib import Path

from tests.gui_helpers import make_book
from lorewrite.core import drafts, scenemeta
from lorewrite.gui.api import Api


def open_book(tmp_path):
    root = tmp_path / "p"
    make_book(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def ws(api):
    return api.get_workspace()["workspace"]


def test_binder_shows_real_parts_and_front_matter_is_not_counted(tmp_path):
    api, root = open_book(tmp_path)
    w = ws(api)
    kids = w["binder"][0]["children"]
    assert [(k["kind"], k["title"]) for k in kids] == [
        ("part", "Front Matter"), ("part", "The Recall"), ("part", "Ghost")]
    assert kids[0]["muted"] is True and "muted" not in kids[1]
    assert [c["title"] for c in kids[1]["children"]] == ["01  Rain", "02  Capsule"]
    # numbering is global across parts; front matter has none
    assert [s["number"] for s in w["scenes"]] == ["", "01", "02", "03"]
    assert w["status"]["projectWords"] == (2 + 10) * 3   # 3 book scenes
    assert [p["title"] for p in w["parts"]] == ["Front Matter", "The Recall", "Ghost"]
    assert w["parts"][1]["sceneIds"] == [
        "manuscript/01-the-recall/01-rain.md", "manuscript/01-the-recall/02-capsule.md"]
    assert not any(n.get("placeholder") for n in kids)
    assert w["project"]["unit"] == "scene"


def test_read_document_reports_part_kicker_and_details(tmp_path):
    api, root = open_book(tmp_path)
    r = api.read_document("manuscript/01-the-recall/02-capsule.md")
    assert r["ok"] and r["kind"] == "scene"
    assert (r["kicker"], r["parent"], r["partId"]) == (
        "SCENE 02", "The Recall", "part:manuscript/01-the-recall")
    assert r["bodyStart"] == 0 and r["details"]["status"] == ""
    assert api.read_document("manuscript/00-front-matter/01-title.md")["kicker"] == "FRONT MATTER"
    # ids still cannot escape or name non-scenes
    assert api.read_document("manuscript/01-the-recall/_part.md")["ok"] is False


def test_part_lifecycle(tmp_path):
    api, root = open_book(tmp_path)
    r = api.new_part("The Long Dark")
    assert r["id"] == "part:manuscript/03-the-long-dark"
    assert api.rename_part(r["id"], "Part III")["ok"]
    assert ws(api)["parts"][-1]["title"] == "Part III"
    assert api.delete_part(r["id"])["ok"]
    assert [p["title"] for p in ws(api)["parts"]] == ["Front Matter", "The Recall", "Ghost"]
    bad = api.delete_part("part:manuscript/02-ghost")
    assert bad["ok"] is False and "scenes" in bad["error"]
    assert api.rename_part("part:../etc", "x")["ok"] is False


def test_move_part_reports_remap_for_open_files(tmp_path):
    api, root = open_book(tmp_path)
    r = api.move_part("part:manuscript/01-the-recall", 1)
    assert r["ok"] and r["id"] == "part:manuscript/02-the-recall"
    assert r["remap"]["manuscript/01-the-recall/01-rain.md"] == "manuscript/02-the-recall/01-rain.md"
    assert r["remap"]["manuscript/02-ghost/01-signal.md"] == "manuscript/01-ghost/01-signal.md"
    assert api.read_document("manuscript/02-the-recall/01-rain.md")["ok"]
    assert api.move_part("part:manuscript/02-the-recall", 1)["ok"] is False   # last


def test_place_scene_between_parts_with_index_and_remap(tmp_path):
    api, root = open_book(tmp_path)
    r = api.place_scene("manuscript/02-ghost/01-signal.md", "part:manuscript/01-the-recall", 1)
    assert r["ok"] and r["id"] == "manuscript/01-the-recall/02-signal.md"
    assert r["remap"] == {
        "manuscript/02-ghost/01-signal.md": "manuscript/01-the-recall/02-signal.md",
        "manuscript/01-the-recall/02-capsule.md": "manuscript/01-the-recall/03-capsule.md"}
    assert api.read_document("manuscript/01-the-recall/03-capsule.md")["ok"]
    titles = [s["title"] for s in ws(api)["scenes"]]
    assert titles == ["Title Page", "Rain", "Signal", "Capsule"]
    assert api.place_scene("x.md", "part:manuscript/01-the-recall")["ok"] is False
    assert api.place_scene(r["id"], "part:manuscript/nope")["ok"] is False
    # draft sidecars follow
    drafts.add_original(root, root / r["id"], "aaaaaa", "orig")
    r2 = api.place_scene(r["id"], None)                 # to the unparted top level
    assert drafts.load_originals(root, root / r2["id"]) == {"aaaaaa": "orig"}


def test_new_scene_goes_to_the_part_of_the_open_scene(tmp_path):
    api, root = open_book(tmp_path)
    a = api.new_scene("Aftermath", None, "manuscript/02-ghost/01-signal.md")
    assert a["id"] == "manuscript/02-ghost/02-aftermath.md"
    b = api.new_scene("Elsewhere", "part:manuscript/01-the-recall")
    assert b["id"] == "manuscript/01-the-recall/03-elsewhere.md"
    c = api.new_scene("Default")                         # last real part
    assert c["id"].startswith("manuscript/02-ghost/")


def test_unplaced_scenes_leave_the_book_but_stay_readable_and_indexed(tmp_path):
    api, root = open_book(tmp_path)
    before = ws(api)["status"]["projectWords"]
    r = api.place_scene("manuscript/01-the-recall/02-capsule.md", unplaced=True)
    assert r["id"] == "manuscript/_unplaced/01-capsule.md"
    w = ws(api)
    assert w["status"]["projectWords"] == before - 12
    un = next(n for n in w["binder"] if n["id"] == "group:unplaced")
    assert [c["title"] for c in un["children"]] == ["Capsule"] and un["meta"] == "1"
    assert un["title"] == "Parked scenes" and un["kind"] == "inbox"
    assert un["description"] == ("Written but not part of the book. Not counted in word totals or export. "
                                 "Still searchable.")
    doc = api.read_document(r["id"])
    assert doc["ok"] and doc["kicker"] == "PARKED" and doc["parent"] == "Parked scenes"
    # editing it still re-indexes (backlinks) via the normal save
    text = doc["text"] + "\nMara Vale watches.\n"
    assert api.save_document(r["id"], text, doc["mtime"])["saved"]
    mara = api.get_entity("Mara Vale")
    assert any(b["sourceId"] == r["id"] for b in mara["backlinks"])


def test_delete_goes_to_trash_and_trash_roundtrip(tmp_path):
    api, root = open_book(tmp_path)
    sid = "manuscript/01-the-recall/01-rain.md"
    drafts.add_original(root, root / sid, "aaaaaa", "orig")
    assert api.delete_scene(sid)["ok"]
    assert not (root / sid).exists()
    w = ws(api)
    trash = next(n for n in w["binder"] if n["id"] == "group:trash")
    assert trash["meta"] == "1" and w["status"]["trashCount"] == 1
    items = api.list_trash()["items"]
    assert len(items) == 1 and items[0]["title"] == "Rain"
    assert items[0]["original"] == "01-the-recall/01-rain.md"
    back = api.restore_trash(items[0]["name"])
    assert back["ok"] and back["id"] == "manuscript/01-the-recall/03-rain.md"
    assert (back["where"], back["part"], back["unplaced"]) == ("part", "The Recall", False)
    assert drafts.load_originals(root, root / back["id"]) == {"aaaaaa": "orig"}
    assert api.list_trash()["items"] == []
    assert api.restore_trash("nope.md")["ok"] is False


def test_delete_forever_and_empty(tmp_path):
    api, root = open_book(tmp_path)
    api.delete_scene("manuscript/01-the-recall/01-rain.md")
    api.delete_scene("manuscript/02-ghost/01-signal.md")
    first = api.list_trash()["items"][0]["name"]
    assert api.delete_forever(first)["ok"]
    assert len(api.list_trash()["items"]) == 1
    assert api.empty_trash()["deleted"] == 1
    assert api.list_trash()["items"] == []
    assert api.delete_forever("../../etc/passwd")["ok"] is False


def test_set_scene_details_returns_a_utf16_edit_for_the_editor(tmp_path):
    api, root = open_book(tmp_path)
    sid = "manuscript/01-the-recall/01-rain.md"
    text = "# Rain\n\nPlain 😀 text.\n"
    r = api.set_scene_details(sid, text, {"pov": "Mara Vale", "status": "revising", "target": "2400"})
    assert r["ok"]
    assert r["edit"] == {"from": 0, "to": 0,
                         "insert": "---\npov: Mara Vale\nstatus: revising\ntarget: 2400\n---\n"}
    assert r["details"]["target"] == 2400 and r["bodyStart"] == len(r["edit"]["insert"])
    # editing again replaces the existing block (offsets in UTF-16 units)
    withmeta = r["edit"]["insert"] + text
    r2 = api.set_scene_details(sid, withmeta, {"status": ""})
    assert r2["edit"]["to"] == len(r["edit"]["insert"])
    assert "status" not in r2["edit"]["insert"] and "pov: Mara Vale" in r2["edit"]["insert"]
    r3 = api.set_scene_details(sid, withmeta, {"pov": "", "status": "", "target": ""})
    assert r3["edit"]["insert"] == ""                      # the block disappears
    assert api.set_scene_details(sid, text, {"mood": "x"})["ok"] is False
    assert api.set_scene_details("manuscript/../x.md", text, {})["ok"] is False


def test_details_reach_the_workspace_and_exclude_words_and_spelling(tmp_path):
    api, root = open_book(tmp_path)
    sid = "manuscript/01-the-recall/01-rain.md"
    text = ("---\npov: Mara Vale\nplace: Lower Meridian\nstatus: revising\n"
            "target: 2400\npurpose: Xqzvbnm blorptastic\n---\n# Rain\n\nrain " * 1) + "rain\n"
    (root / sid).write_text(text)
    api.rebuild_index()
    w = ws(api)
    scene = next(s for s in w["scenes"] if s["id"] == sid)
    assert scene["details"]["pov"] == "Mara Vale" and scene["details"]["target"] == 2400
    assert scene["words"] == 4                                    # "# Rain rain rain"
    assert scene["excerpt"] == "rain rain"
    doc = api.read_document(sid)
    assert doc["details"]["place"] == "Lower Meridian"
    assert doc["bodyStart"] == len(text) - len("# Rain\n\nrain rain\n")
    spell = api.spelling(sid, text)
    assert spell["ok"] and all(sp["start"] >= doc["bodyStart"] for sp in spell["spans"])
    # pov / place count as mentions of those entities; the purpose text does not
    mentions = {m["name"] for m in doc["mentions"]}
    assert {"Mara Vale", "Lower Meridian"} <= mentions
    spans = api.link_spans(sid, text)["spans"]
    assert all(sp["start"] >= doc["bodyStart"] for sp in spans)


def test_set_unit_updates_labels_only(tmp_path):
    api, root = open_book(tmp_path)
    assert api.set_unit("chapter")["ok"]
    w = ws(api)
    assert w["project"]["unit"] == "chapter"
    assert api.read_document("manuscript/01-the-recall/01-rain.md")["kicker"] == "CHAPTER 01"
    assert api.set_unit("act")["ok"] is False
    assert json.loads(json.dumps(w))        # JSON-clean (no Paths)


def test_residual_example_opens_unchanged_in_the_gui_api(tmp_path):
    """Existing flat projects behave exactly as before: one Manuscript group, numbers from
    the filenames, no parts, nothing renamed or created on open."""
    import shutil
    example = Path(__file__).resolve().parent.parent / "examples" / "residual"
    root = tmp_path / "residual"
    shutil.copytree(example, root)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    api = Api()
    assert api.open_project(str(root))["ok"]
    w = ws(api)
    assert [s["number"] for s in w["scenes"]] == ["01", "02", "03", "04"]
    assert w["parts"] == [] and w["status"]["trashCount"] == 0
    kids = w["binder"][0]["children"]
    assert [(k["id"], k["kind"]) for k in kids] == [("group:manuscript", "folder")]
    assert [c["title"].split("  ")[0] for c in kids[0]["children"]] == ["01", "02", "03", "04"]
    assert all(not s["frontMatter"] and not s["unplaced"] and s["part"] is None
               and s["details"]["status"] == "" for s in w["scenes"])
    assert w["status"]["projectWords"] == sum(s["words"] for s in w["scenes"])
    doc = api.read_document(w["scenes"][0]["id"])
    assert doc["kicker"] == "SCENE 01" and doc["parent"] == "Manuscript" and doc["bodyStart"] == 0
    new = api.new_scene("A Fifth")["id"]          # new scenes still go to the top level
    assert new == "manuscript/05-a-fifth.md"
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if ".lorewrite" not in p.parts) == sorted(
        [p for p in before if ".lorewrite" not in p.split("/")] + ["manuscript/05-a-fifth.md"])


def test_restore_reports_where_it_went(tmp_path):
    api, root = open_book(tmp_path)
    api.delete_scene("manuscript/02-ghost/01-signal.md")
    api.delete_part("manuscript/02-ghost")
    back = api.restore_trash(api.list_trash()["items"][0]["name"])
    assert (back["where"], back["unplaced"]) == ("gone", True)
    api.delete_scene(back["id"])
    again = api.restore_trash(api.list_trash()["items"][0]["name"])
    assert (again["where"], again["unplaced"]) == ("unplaced", True)
