"""core/inspiration: storage, pins, scene links, Trash."""

import sys

import pytest

from chisel.core import inspiration as insp
from chisel.core.project import Project

from tests.gui_helpers import make_book

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 40
SCENE = "manuscript/01-the-recall/01-rain.md"


@pytest.fixture
def project(tmp_path):
    return make_book(tmp_path / "book")


def test_save_round_trip_and_sidecar_is_plain_text(project):
    img = insp.save(project, JPEG, "jpeg", {
        "prompt": "A dark subway platform at night: flickering lights # not a comment",
        "model": "m/img", "scene": SCENE, "cost": 0.0336, "pinned": True,
        "notes": "Use for the tunnel chase."})
    assert img.ext == "jpg" and img.path.read_bytes() == JPEG
    assert img.path.parent == project.root / "inspiration"
    assert img.meta_path.name == img.path.stem + ".md"
    assert img.id.endswith("-a-dark-subway-platform-at-night")
    got = insp.get(project, img.id)
    assert got.prompt == "A dark subway platform at night: flickering lights # not a comment"
    assert (got.model, got.scene, got.cost, got.pinned) == ("m/img", SCENE, 0.0336, True)
    assert got.notes == "Use for the tunnel chase."
    text = img.meta_path.read_text()
    assert text.startswith("---\nprompt:") and "pinned: true" in text and text.rstrip().endswith("chase.")


def test_unknown_types_and_empty_input_are_refused(project):
    with pytest.raises(ValueError):
        insp.save(project, JPEG, "gif", {"prompt": "x"})
    with pytest.raises(ValueError):
        insp.save(project, b"", "png", {"prompt": "x"})
    with pytest.raises(ValueError):
        insp.save(project, PNG, "png", {"prompt": "  "})
    assert insp.list_images(project) == []


def test_same_prompt_same_second_gets_distinct_files(project):
    meta = {"prompt": "same", "created": "2026-10-01T17:53:00"}
    a = insp.save(project, JPEG, "jpg", meta)
    b = insp.save(project, PNG, "png", meta)
    assert a.id != b.id and a.path.exists() and b.path.exists()
    assert {i.id for i in insp.list_images(project)} == {a.id, b.id}


def test_list_filters_by_scene_newest_first(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "one", "scene": SCENE, "created": "2026-10-01T10:00:00"})
    b = insp.save(project, PNG, "png", {"prompt": "two", "created": "2026-10-02T10:00:00"})
    c = insp.save(project, JPEG, "jpg", {"prompt": "three", "scene": SCENE, "created": "2026-10-03T10:00:00"})
    assert [i.id for i in insp.list_images(project)] == [c.id, b.id, a.id]
    assert [i.id for i in insp.list_images(project, SCENE)] == [c.id, a.id]
    assert insp.list_images(project, "manuscript/other.md") == []


def test_pin_per_scene(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "one", "scene": SCENE})
    b = insp.save(project, PNG, "png", {"prompt": "two"})
    with pytest.raises(ValueError):
        insp.update(project, b.id, pinned=True)             # no scene to pin to
    assert insp.update(project, a.id, pinned=True).pinned
    assert insp.update(project, b.id, pinned=True, scene=SCENE).scene == SCENE
    assert {i.id for i in insp.pinned_for(project, SCENE)} == {a.id, b.id}
    assert insp.pinned_for(project, "manuscript/elsewhere.md") == []
    assert not insp.update(project, a.id, pinned=False).pinned
    assert [i.id for i in insp.pinned_for(project, SCENE)] == [b.id]
    assert insp.update(project, b.id, scene="").pinned is False       # detaching unpins


def test_title_and_notes_edit_keeps_everything_else(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "p", "model": "m", "cost": 0.03, "scene": SCENE})
    b = insp.update(project, a.id, title="Platform 9", notes="line one\nline two")
    assert (b.title, b.notes, b.prompt, b.model, b.cost) == ("Platform 9", "line one\nline two", "p", "m", 0.03)
    assert b.label == "Platform 9" and insp.update(project, a.id, title="").label == "p"


def test_ids_cannot_leave_the_folder(project, tmp_path):
    (tmp_path / "secret.md").write_text("---\nprompt: x\n---\n")
    for bad in ("../secret", "..", "a/b", "/etc/passwd", ".hidden", "", "a\\b", "x..y/../z"):
        for fn in (insp.get, insp.read_file):
            with pytest.raises((ValueError, FileNotFoundError)):
                fn(project, bad)
        with pytest.raises((ValueError, FileNotFoundError)):
            insp.update(project, bad, notes="x")
        with pytest.raises((ValueError, FileNotFoundError)):
            project.trash_inspiration(bad)


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs a privilege on Windows")
def test_read_file_refuses_a_symlink_out_of_the_folder(project, tmp_path):
    img = insp.save(project, JPEG, "jpg", {"prompt": "p"})
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"\xff\xd8\xff secret")
    img.path.unlink()
    img.path.symlink_to(outside)
    with pytest.raises(ValueError):
        insp.read_file(project, img.id)


def test_read_file_returns_mime(project):
    a = insp.save(project, PNG, "png", {"prompt": "p"})
    assert insp.read_file(project, a.id) == (PNG, "image/png")


def test_sniff_ext():
    assert insp.sniff_ext(JPEG) == "jpg" and insp.sniff_ext(PNG) == "png"
    assert insp.sniff_ext(b"RIFF\0\0\0\0WEBPVP8 ") == "webp" and insp.sniff_ext(b"GIF89a") is None


def test_damaged_sidecar_and_orphans_do_not_break_listing(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "good"})
    (project.root / "inspiration" / "20260101-000000-bad.md").write_text("---\n: : [\n---\n")
    (project.root / "inspiration" / "20260101-000000-orphan.jpg").write_bytes(JPEG)
    (project.root / "inspiration" / "20260101-000000-nopic.md").write_text("---\nprompt: x\n---\n")
    assert [i.id for i in insp.list_images(project)] == [a.id]


# -- scene renames and moves -----------------------------------------------------


def test_scene_move_and_swap_keep_the_link(project):
    one = project.root / SCENE
    two = project.root / "manuscript/01-the-recall/02-capsule.md"
    a = insp.save(project, JPEG, "jpg", {"prompt": "a", "scene": SCENE, "pinned": True})
    b = insp.save(project, JPEG, "jpg", {"prompt": "b", "scene": "manuscript/01-the-recall/02-capsule.md"})
    project.move_scene(one, +1)                                   # swap: both ids change
    assert insp.get(project, a.id).scene == "manuscript/01-the-recall/02-rain.md"
    assert insp.get(project, b.id).scene == "manuscript/01-the-recall/01-capsule.md"
    assert insp.get(project, a.id).pinned and (project.root / insp.get(project, a.id).scene).is_file()
    assert two.exists() is False


def test_part_move_and_scene_to_other_part_keep_the_link(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "a", "scene": SCENE})
    p1, p2 = [p for p in project.list_parts() if "front" not in p.name]
    project.move_part(p1, +1)
    new = insp.get(project, a.id).scene
    assert new.startswith("manuscript/02-the-recall/") and (project.root / new).is_file()
    project.move_scene_to_part(project.root / new, project.list_parts()[-1])
    new2 = insp.get(project, a.id).scene
    assert (project.root / new2).is_file() and new2 != new


# -- Trash ------------------------------------------------------------------------


def test_trash_and_restore(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "A tunnel", "scene": SCENE, "pinned": True, "notes": "n"})
    item_path = project.trash_inspiration(a.id)
    assert not a.path.exists() and not a.meta_path.exists()
    assert item_path.parent == project.trash_dir and (project.trash_dir / (item_path.name + ".jpg")).is_file()
    items = project.list_trash()
    assert [(i.kind, i.title) for i in items] == [("inspiration", "A tunnel")]
    assert items[0].original == f"inspiration/{a.id}.md"
    final = project.restore_scene(items[0].name)
    back = insp.get(project, final.stem)
    assert back.id == a.id and back.path.read_bytes() == JPEG
    assert (back.scene, back.pinned, back.notes) == (SCENE, True, "n")
    assert not project.trash_dir.exists()


def test_restore_takes_a_free_name_and_delete_forever_removes_the_picture(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "x", "created": "2026-10-01T10:00:00"})
    project.trash_inspiration(a.id)
    b = insp.save(project, PNG, "png", {"prompt": "x", "created": "2026-10-01T10:00:00"})
    assert b.id == a.id                              # the name was free again
    name = project.list_trash()[0].name
    restored = project.restore_scene(name)
    assert restored.stem == a.id + "-2" and len(insp.list_images(project)) == 2
    project.trash_inspiration(b.id)
    name = project.list_trash()[0].name
    project.delete_forever(name)
    assert not project.trash_dir.exists()
    assert [i.id for i in insp.list_images(project)] == [a.id + "-2"]


def test_trash_lists_scenes_research_and_images_together(project):
    a = insp.save(project, JPEG, "jpg", {"prompt": "x"})
    project.trash_inspiration(a.id)
    project.delete_scene(project.root / SCENE)
    assert sorted(i.kind for i in project.list_trash()) == ["inspiration", "scene"]
    assert project.empty_trash() == 2 and not project.trash_dir.exists()


def test_a_project_without_the_folder_is_unchanged(tmp_path):
    p = Project.create(tmp_path / "plain", "Plain")
    assert insp.list_images(p) == [] and not (p.root / "inspiration").exists()


def test_the_folder_is_not_git_ignored(tmp_path):
    p = Project.create(tmp_path / "ignored", "Ignored")
    insp.save(p, JPEG, "jpg", {"prompt": "x"})
    ignore = (p.root / ".gitignore").read_text()
    assert "inspiration" not in ignore and ".chisel/" in ignore
