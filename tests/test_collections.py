"""Collections: definitions in project.toml, membership in scene frontmatter (Wave 3.1)."""

import pytest

from lorewrite.core import collections as coll
from lorewrite.core import scenemeta
from lorewrite.core.project import Project
from tests.gui_helpers import make_project


def scene(project, n):
    return project.list_scenes()[n]


def test_create_list_and_toml_roundtrip(tmp_path):
    project = make_project(tmp_path / "p")
    coll.create(project, "Needs continuity pass", "amber")
    coll.create(project, "Mara's arc", "violet")
    got = coll.list_collections(Project.open(project.root))  # re-read from disk
    assert [(c.name, c.color, c.declared) for c in got] == [
        ("Needs continuity pass", "amber", True), ("Mara's arc", "violet", True)]
    text = (project.root / "project.toml").read_text()
    assert "[collections]" in text and 'title = "Test Novel"' in text


def test_validation(tmp_path):
    project = make_project(tmp_path / "p")
    coll.create(project, "A")
    with pytest.raises(ValueError):
        coll.create(project, "a")        # case-insensitive duplicate
    with pytest.raises(ValueError):
        coll.create(project, "  ")
    with pytest.raises(ValueError):
        coll.create(project, "B", "chartreuse")
    with pytest.raises(LookupError):
        coll.recolor(project, "nope", "red")


def test_membership_is_scene_frontmatter(tmp_path):
    project = make_project(tmp_path / "p")
    coll.create(project, "Arc")
    s = scene(project, 0)
    assert coll.toggle(project, s, "arc") is True       # case-insensitive lookup, canonical name stored
    assert scenemeta.details(s.read_text())["collections"] == ["Arc"]
    assert s.read_text().startswith("---\ncollections: [Arc]\n---\n# Arrival")
    assert coll.toggle(project, s, "Arc", True) is True  # idempotent
    assert coll.toggle(project, s, "Arc") is False       # flips off; empty block disappears
    assert s.read_text().startswith("# Arrival")
    coll.toggle(project, s, "Arc")
    assert [c.scenes for c in coll.list_collections(project)] == [(s,)]


def test_rename_rewrites_members_and_recolor_keeps_them(tmp_path):
    project = make_project(tmp_path / "p")
    coll.create(project, "Arc", "green")
    for i in (0, 1):
        coll.toggle(project, scene(project, i), "Arc")
    changed = coll.rename(project, "Arc", "Mara's arc")
    assert len(changed) == 2
    (c,) = coll.list_collections(project)
    assert (c.name, c.color, len(c.scenes)) == ("Mara's arc", "green", 2)
    assert "Arc" not in scene(project, 0).read_text().replace("Mara's arc", "")
    coll.recolor(project, "mara's arc", "red")
    assert coll.list_collections(project)[0].color == "red"
    coll.create(project, "Other")
    with pytest.raises(ValueError):
        coll.rename(project, "Other", "mara's ARC")


def test_delete_removes_membership_but_not_scenes(tmp_path):
    project = make_project(tmp_path / "p")
    coll.create(project, "Arc")
    coll.create(project, "Keep")
    s = scene(project, 0)
    coll.toggle(project, s, "Arc")
    coll.toggle(project, s, "Keep")
    before = s.read_text().split("---\n", 2)[2]
    coll.delete(project, "Arc")
    assert [c.name for c in coll.list_collections(project)] == ["Keep"]
    assert scenemeta.details(s.read_text())["collections"] == ["Keep"]
    assert s.read_text().split("---\n", 2)[2] == before


def test_undeclared_names_in_frontmatter_still_show(tmp_path):
    project = make_project(tmp_path / "p")
    s = scene(project, 0)
    s.write_text("---\ncollections: [Hand written]\n---\n" + s.read_text(), encoding="utf-8")
    (c,) = coll.list_collections(project)
    assert (c.name, c.declared, c.color, c.scenes) == ("Hand written", False, "gray", (s,))
    coll.recolor(project, "Hand written", "amber")      # declares it
    assert coll.list_collections(project)[0].declared is True


def test_trash_and_unplaced_scenes_are_counted_per_rules(tmp_path):
    project = make_project(tmp_path / "p")
    coll.create(project, "Arc")
    s = scene(project, 1)
    coll.toggle(project, s, "Arc")
    moved = project.place_scene(s, unplaced=True)
    assert coll.list_collections(project)[0].scenes == (moved,)   # unplaced scenes keep membership
    project.delete_scene(moved)
    assert coll.list_collections(project)[0].scenes == ()
