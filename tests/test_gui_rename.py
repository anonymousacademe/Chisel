"""Api: rename a note everywhere (preview, apply, undo)."""

from lorewrite.core import snapshots
from tests.test_gui_api import open_api

A = "manuscript/01-arrival.md"
B = "manuscript/02-the-archive.md"


def test_rename_through_the_bridge(tmp_path):
    snapshots._daily_done.clear()
    api, root = open_api(tmp_path)
    before_a = (root / A).read_text(encoding="utf-8")
    r = api.rename_preview("Mara Vale", "Nia Vale", True, {"Mara": "Nia"})
    assert r["ok"] and r["newName"] == "Nia Vale"
    scenes = {f["file"]: f for f in r["files"]}
    assert set(scenes) == {A, B}
    assert (root / A).read_text(encoding="utf-8") == before_a  # preview writes nothing
    assert (root / "entities/characters/mara-vale.md").exists()

    # the occurrence in the pending AI draft is not here (the draft says nothing of Mara);
    # untick the first one of A
    first = scenes[A]["occurrences"][0]
    assert first["before"] == "Mara" and first["after"] == "Nia" and first["defaultOn"]
    accepted = [o["id"] for f in r["files"] for o in f["occurrences"] if o["id"] != first["id"]]
    done = api.rename_apply(r["plan"], accepted)
    assert done["ok"] and done["remap"] == {
        "entities/characters/mara-vale.md": "entities/characters/nia-vale.md"}
    assert "Mara stepped off" in (root / A).read_text(encoding="utf-8")  # unticked stays
    assert "Nia read the files" in (root / B).read_text(encoding="utf-8")
    assert api.get_entity("Nia Vale")["found"] and api.get_entity("Mara Vale")["found"]  # old name = alias
    assert api.rename_apply(r["plan"], accepted)["ok"] is False          # a plan applies once

    undone = api.rename_undo(done["undoId"])
    assert undone["ok"] and undone["skipped"] == []
    assert (root / A).read_text(encoding="utf-8") == before_a
    assert "Mara read the files" in (root / B).read_text(encoding="utf-8")
    assert (root / "entities/characters/mara-vale.md").exists()
    assert api.rename_undo(done["undoId"])["ok"] is False


def test_rename_errors_do_not_raise(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.rename_preview("Nobody", "X")["ok"] is False
    assert "another note" in api.rename_preview("Mara Vale", "elias vale")["error"]
    assert api.rename_apply("nope", [])["ok"] is False
