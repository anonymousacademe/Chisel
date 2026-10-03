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


def test_rename_and_undo_carry_the_pictures_made_for_the_note(tmp_path):
    from lorewrite.core import inspiration as store

    snapshots._daily_done.clear()
    api, root = open_api(tmp_path)
    old, new = "entities/characters/mara-vale.md", "entities/characters/nia-vale.md"
    mine = store.save(api.project, b"\xff\xd8\xff\xe0" + b"j" * 20, "jpg", {"prompt": "Mara", "for": old, "pinned": True})
    other = store.save(api.project, b"\xff\xd8\xff\xe0" + b"j" * 20, "jpg", {"prompt": "Elias", "for": "entities/characters/elias-vale.md"})
    legacy = store.save(api.project, b"\xff\xd8\xff\xe0" + b"j" * 20, "jpg", {"prompt": "Old"})
    legacy.meta_path.write_text(f"---\nprompt: Old\nscene: {old}\n---\n", encoding="utf-8", newline="\n")   # old sidecar
    r = api.rename_preview("Mara Vale", "Nia Vale", True, {"Mara": "Nia"})
    done = api.rename_apply(r["plan"], [o["id"] for f in r["files"] for o in f["occurrences"]])
    assert done["ok"] and done["remap"] == {old: new}
    by_id = {i["id"]: i for i in api.list_inspiration()["images"]}
    assert by_id[mine.id]["for"] == new and by_id[mine.id]["pinned"] and by_id[mine.id]["unlinked"] is False
    assert by_id[legacy.id]["for"] == new                                    # a legacy scene: link follows too
    assert "for: " + new in legacy.meta_path.read_text(encoding="utf-8")
    assert by_id[other.id]["for"] == "entities/characters/elias-vale.md"
    assert api.list_inspiration(new)["mine"] and set(api.list_inspiration(new)["mine"]) == {mine.id, legacy.id}

    undone = api.rename_undo(done["undoId"])
    assert undone["ok"] and undone["skipped"] == []
    by_id = {i["id"]: i for i in api.list_inspiration()["images"]}
    assert by_id[mine.id]["for"] == old and by_id[legacy.id]["for"] == old and by_id[mine.id]["pinned"]
    assert by_id[other.id]["for"] == "entities/characters/elias-vale.md"


def test_a_rename_that_keeps_the_file_name_leaves_the_pictures_alone(tmp_path):
    from lorewrite.core import inspiration as store

    snapshots._daily_done.clear()
    api, root = open_api(tmp_path)
    old = "entities/characters/mara-vale.md"
    img = store.save(api.project, b"\xff\xd8\xff\xe0" + b"j" * 20, "jpg", {"prompt": "Mara", "for": old})
    before = img.meta_path.read_bytes()
    r = api.rename_preview("Mara Vale", "Mara Vale", True, {})
    if r["ok"]:                                                              # nothing to rename: a no-op plan or an error
        api.rename_apply(r["plan"], [])
    assert store.get(api.project, img.id).link == old and img.meta_path.read_bytes() == before
