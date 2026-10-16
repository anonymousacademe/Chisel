"""The Trash kind "object": figures, tables and equations ride to .trash/ with their image or CSV."""

import pytest

from chisel.core.objects import create_figure, list_objects
from chisel.core.project import Project

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def proj(tmp_path):
    return Project.create(tmp_path / "paper", "Paper", "research")


def test_figure_trash_and_restore_together(proj):
    create_figure(proj, PNG, "flow", "The flow")
    dest = proj.trash_object("figures/fig-flow.md")
    assert not (proj.root / "figures" / "fig-flow.md").exists()
    assert not (proj.root / "figures" / "fig-flow.png").exists()
    assert dest.parent == proj.trash_dir and dest.with_name(dest.name + ".png").is_file()
    [item] = proj.list_trash()
    assert item.kind == "object" and item.original == "figures/fig-flow.md" and item.title == "The flow"
    final = proj.restore_scene(item.name)
    assert final == proj.root / "figures" / "fig-flow.md"
    assert (proj.root / "figures" / "fig-flow.png").read_bytes() == PNG
    assert [o.label for o in list_objects(proj)] == ["flow"] and not proj.trash_dir.exists()


def test_restore_takes_a_free_name_when_the_label_was_reused(proj):
    create_figure(proj, PNG, "flow", "old")
    proj.trash_object("figures/fig-flow.md")
    create_figure(proj, PNG, "flow", "new")
    [item] = proj.list_trash()
    final = proj.restore_scene(item.name)
    assert final.name == "fig-flow-2.md"
    assert (proj.root / "figures" / "fig-flow-2.png").is_file()
    assert (proj.root / "figures" / "fig-flow.png").is_file()


def test_table_with_csv_and_equation(proj):
    (proj.root / "tables").mkdir()
    (proj.root / "equations").mkdir()
    (proj.root / "tables" / "tbl-r.md").write_text("| a |\n| --- |\n| 1 |\n", encoding="utf-8", newline="\n")
    (proj.root / "tables" / "tbl-r.csv").write_text("a\n1\n", encoding="utf-8", newline="\n")
    (proj.root / "equations" / "eq-m.md").write_text("E=mc^2\n", encoding="utf-8", newline="\n")
    proj.trash_object("tables/tbl-r.md")
    proj.trash_object("equations/eq-m.md")
    kinds = {i.original: (i.kind, i.title) for i in proj.list_trash()}
    assert kinds == {"tables/tbl-r.md": ("object", "tbl-r"), "equations/eq-m.md": ("object", "eq-m")}
    for item in proj.list_trash():
        proj.restore_scene(item.name)
    assert (proj.root / "tables" / "tbl-r.csv").read_text(encoding="utf-8") == "a\n1\n"
    assert (proj.root / "equations" / "eq-m.md").is_file()


def test_delete_forever_and_empty_remove_companions(proj):
    create_figure(proj, PNG, "a", "")
    create_figure(proj, PNG, "b", "")
    proj.trash_object("figures/fig-a.md")
    proj.trash_object("figures/fig-b.md")
    first = proj.list_trash()[0]
    proj.delete_forever(first.name)
    assert len(list(proj.trash_dir.iterdir())) == 2   # the other item's md + png
    assert proj.empty_trash() == 1
    assert not proj.trash_dir.exists()


def test_only_object_files_can_be_trashed(proj):
    create_figure(proj, PNG, "a", "")
    for bad in ("project.toml", "figures/fig-a.png", "figures/missing.md", "../x.md", "manuscript/01.md",
                "figures/../project.toml"):
        with pytest.raises(FileNotFoundError):
            proj.trash_object(bad)


def test_scenes_and_notes_still_list_as_before(proj):
    scene = proj.manuscript_dir / "01-a.md"
    scene.write_text("hi\n", encoding="utf-8", newline="\n")
    proj.delete_scene(scene)
    [item] = proj.list_trash()
    assert item.kind == "scene"
