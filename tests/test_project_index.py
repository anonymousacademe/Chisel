from pathlib import Path

import pytest

from lorewrite.core.index import Index
from lorewrite.core.project import Project


@pytest.fixture
def project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="Test Novel")
    proj.create_entity("Elara Vance")
    entity, _ = proj.create_entity("Thornwick", "place")
    # give Elara an alias
    elara_path = proj.entities_dir / "characters" / "elara-vance.md"
    elara_path.write_text(
        "---\nname: Elara Vance\ntype: character\naliases: [the captain]\n---\n\nGreen eyes.\n",
        encoding="utf-8",
    )
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text(
        "# The Tavern\n\n[[Elara Vance]] entered. The captain ordered ale.\n"
        "[[Thornwick]] was far away. [[Nobody]] does not exist.\n",
        encoding="utf-8",
    )
    return proj


def test_create_and_open(tmp_path: Path):
    proj = Project.create(tmp_path / "n", title="My Book")
    assert (proj.root / "project.toml").is_file()
    assert (proj.root / "manuscript" / "01-opening.md").is_file()
    reopened = Project.open(proj.root)
    assert reopened.title == "My Book"


def test_open_non_project_fails(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        Project.open(tmp_path)


def test_scene_title_and_order(project: Project):
    scenes = project.list_scenes()
    assert [s.name for s in scenes] == ["01-opening.md", "02-tavern.md"]
    assert project.scene_title(scenes[1]) == "The Tavern"


def test_next_scene_path(project: Project):
    path = project.next_scene_path("The Road North")
    assert path.name == "03-the-road-north.md"


def test_create_entity_lands_in_type_subdir(project: Project):
    _, path = project.create_entity("The Ashen Guild", "faction")
    assert path.parent.name == "factions"
    assert path.name == "the-ashen-guild.md"


def test_index_backlinks(project: Project):
    index = Index(project.index_path)
    index.rebuild(project)
    entities = project.load_entities()
    elara = next(e for e in entities if e.name == "Elara Vance")
    backlinks = index.backlinks(elara)
    # [[Elara Vance]] and the plain alias "The captain" share one line: one entry
    assert len(backlinks) == 1
    assert backlinks[0].source.endswith("02-tavern.md")
    assert backlinks[0].row == 2
    assert "Elara Vance" in backlinks[0].line
    index.close()


def test_plain_mentions_count_as_backlinks_in_scenes(project: Project):
    (project.manuscript_dir / "03-road.md").write_text(
        "# The Road\n\nElara rode on. the captain was tired.\n", encoding="utf-8")
    elara_path = project.entities_dir / "characters" / "elara-vance.md"
    elara_path.write_text(
        "---\nname: Elara Vance\ntype: character\naliases: [the captain, Elara]\n"
        "---\n\nElara has green eyes.\n", encoding="utf-8")
    index = Index(project.index_path)
    index.rebuild(project)
    elara = next(e for e in project.load_entities() if e.name == "Elara Vance")
    sources = [(b.source, b.row) for b in index.backlinks(elara)]
    assert ("manuscript/03-road.md", 2) in sources
    # an entity's own note mentioning its name is not a backlink
    assert not any(s.startswith("entities/") for s, _ in sources)
    index.close()


def test_index_rows_match_offset_to_rowcol(tmp_path):
    from lorewrite.core.index import Index
    from lorewrite.core.links import find_all_links, offset_to_rowcol

    text = "# T\n\nMara walked.\nThen [[Elias]] and Mara.\n\n\nLast Mara line"
    idx = Index(tmp_path / "i.sqlite")
    idx.update_file("manuscript/01-a.md", text, ["Mara"])
    rows = sorted(r[0] for r in idx._conn.execute("SELECT row FROM links"))
    expected = sorted(offset_to_rowcol(text, l.start)[0] for l in find_all_links(text, ["Mara"]))
    assert rows == expected == [2, 3, 3, 6]
