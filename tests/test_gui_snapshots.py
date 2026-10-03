"""Api: snapshots, the draft counter and the safety nets (Wave 2.1 / 2.2)."""

from pathlib import Path

from tests.gui_helpers import make_book, make_project
from chisel.core import drafts, snapshots
from chisel.gui.api import Api

RAIN = "manuscript/01-the-recall/01-rain.md"


def open_book(tmp_path):
    root = tmp_path / "p"
    make_book(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def test_manual_snapshot_list_compare_restore_delete(tmp_path):
    api, root = open_book(tmp_path)
    r = api.create_snapshot(RAIN, "before the rewrite")
    assert r["ok"] and r["snapshotAt"]
    edited = "# Rain\n\nrain " * 3 + "\nfresh words here\n"
    listed = api.list_snapshots(RAIN, edited)
    row = listed["items"][0]
    assert row["label"] == "before the rewrite" and row["words"] == 12
    assert row["delta"] == listed["words"] - 12
    assert listed["snapshotAt"] == r["snapshotAt"]

    diff = api.compare_snapshot(RAIN, row["id"], edited)
    assert diff["ok"] and diff["added"] > 0
    assert "".join(s["new"] for s in diff["segments"]) == edited
    old = (root / RAIN).read_text(encoding="utf-8")
    assert "".join(s["old"] for s in diff["segments"]) == old

    (root / RAIN).write_text(edited, encoding="utf-8")
    res = api.restore_snapshot(RAIN, row["id"], edited)
    assert res["ok"]
    assert (root / RAIN).read_text(encoding="utf-8") == old
    labels = [i["label"] for i in api.list_snapshots(RAIN)["items"]]
    assert labels.count("before-restore") == 1

    assert api.delete_snapshot(RAIN, row["id"])["ok"]
    assert [i["label"] for i in api.list_snapshots(RAIN)["items"]] == ["before-restore"]


def test_restore_reindexes_the_scene(tmp_path):
    api, root = open_book(tmp_path)
    (root / RAIN).write_text("# Rain\n\nMara walked.\n", encoding="utf-8")
    sid = api.create_snapshot(RAIN)["id"]
    (root / RAIN).write_text("# Rain\n\nnothing\n", encoding="utf-8")
    api.restore_snapshot(RAIN, sid)
    mara = next(e for e in api.entities if e.name == "Mara Vale")
    assert any("01-rain" in str(b) for b in api.index.backlinks(mara))


def test_bad_ids_and_non_scenes_are_errors_not_exceptions(tmp_path):
    api, root = open_book(tmp_path)
    assert api.compare_snapshot(RAIN, "../../project")["ok"] is False
    assert api.restore_snapshot(RAIN, "20260101-000000")["ok"] is False
    assert api.create_snapshot("entities/characters/mara-vale.md")["ok"] is False
    assert api.list_snapshots("manuscript/nope.md")["ok"] is False


def test_snapshot_all_and_new_draft(tmp_path):
    api, root = open_book(tmp_path)
    assert api.get_workspace()["workspace"]["project"]["draft"] == 1
    assert api.snapshot_all("checkpoint") == {"ok": True, "count": 4}
    r = api.start_new_draft()
    assert r["ok"] and (r["draft"], r["previous"]) == (2, 1)
    assert api.get_workspace()["workspace"]["project"]["draft"] == 2
    labels = {i["label"] for i in api.list_snapshots(RAIN)["items"]}
    assert labels == {"checkpoint", "end-of-draft-1"}


def test_read_document_reports_the_latest_snapshot(tmp_path):
    api, root = open_book(tmp_path)
    assert api.read_document(RAIN)["snapshotAt"] is None
    at = api.create_snapshot(RAIN)["snapshotAt"]
    assert api.read_document(RAIN)["snapshotAt"] == at


def test_first_edit_of_the_day_snapshots_the_old_text_when_enabled(tmp_path):
    snapshots._daily_done.clear()
    api, root = open_book(tmp_path)
    before = (root / RAIN).read_text(encoding="utf-8")
    doc = api.read_document(RAIN)
    saved = api.save_document(RAIN, before + "one more line\n", doc["mtime"])
    assert saved["saved"] and saved["snapshotAt"]
    snaps = api.list_snapshots(RAIN)["items"]
    assert [s["label"] for s in snaps] == ["auto"]
    sid = snaps[0]["id"]
    assert snapshots.read_text(api.project, root / RAIN, sid) == before
    api.save_document(RAIN, before + "two lines\n", saved["mtime"])   # not again today
    assert len(api.list_snapshots(RAIN)["items"]) == 1


def test_auto_snapshot_can_be_turned_off(tmp_path):
    snapshots._daily_done.clear()
    api, root = open_book(tmp_path)
    assert api.get_settings()["autoSnapshot"] is True
    assert api.set_settings(auto_snapshot=False)["ok"]
    assert api.get_settings()["autoSnapshot"] is False
    doc = api.read_document(RAIN)
    api.save_document(RAIN, doc["text"] + "x\n", doc["mtime"])
    assert api.list_snapshots(RAIN)["items"] == []


def test_accept_all_and_reject_all_snapshot_first_but_single_does_not(tmp_path):
    api, root = open_book(tmp_path)
    path = root / "manuscript/01-the-recall/02-capsule.md"
    drafts.add_original(root, path, "k3f9q2", "the first words")
    text = ('# Capsule\n\n<!--ai id="k3f9q2"-->new words<!--/ai--> and '
            '<!--ai-->an insertion<!--/ai-->\n')
    path.write_text(text, encoding="utf-8")
    cap = "manuscript/01-the-recall/02-capsule.md"
    assert api.resolve_drafts(cap, text, True, 0)["ok"]          # one draft: no snapshot
    assert api.list_snapshots(cap)["items"] == []
    drafts.add_original(root, path, "k3f9q2", "the first words")
    r = api.resolve_drafts(cap, text, False)                       # all: snapshot of the buffer
    assert r["found"] == 2
    items = api.list_snapshots(cap)["items"]
    assert [i["label"] for i in items] == ["before-reject-all"]
    kept = snapshots.read_text(api.project, path, items[0]["id"])
    assert kept == text
    # nothing pending: nothing to snapshot
    api.resolve_drafts(cap, "# Capsule\n\nplain\n", True)
    assert len(api.list_snapshots(cap)["items"]) == 1
    api.resolve_drafts(cap, text, True)
    assert [i["label"] for i in api.list_snapshots(cap)["items"]][0] == "before-accept-all"


def test_moving_a_scene_keeps_its_snapshots_in_the_api(tmp_path):
    api, root = open_book(tmp_path)
    api.create_snapshot(RAIN, "mine")
    moved = api.place_scene(RAIN, "part:manuscript/02-ghost", 0)
    assert moved["ok"]
    new_id = moved["id"]
    assert [i["label"] for i in api.list_snapshots(new_id)["items"]] == ["mine"]


def test_example_project_opens_unchanged_and_creates_nothing(tmp_path):
    """Migration rule: an existing project (examples/residual) opens, reads and
    reports 'draft 1' without writing a single file."""
    import shutil
    root = tmp_path / "residual"
    shutil.copytree(Path(__file__).resolve().parents[1] / "examples" / "residual", root)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    api = Api()
    assert api.open_project(str(root))["ok"]
    w = api.get_workspace()["workspace"]
    assert w["project"]["draft"] == 1
    first = w["scenes"][0]["id"]
    assert api.read_document(first)["snapshotAt"] is None
    assert api.list_snapshots(first)["items"] == []
    after = {p: p.read_bytes() for p in root.rglob("*")
             if p.is_file() and ".chisel" not in p.parts}
    before = {p: b for p, b in before.items() if ".chisel" not in p.parts}
    assert after == before
    assert not (root / ".snapshots").exists()
