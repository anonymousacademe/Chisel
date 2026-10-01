"""Research notes: plain Markdown in research/, keyword retrieval (Wave 3.3)."""

import pytest

from lorewrite.core import research as rs
from tests.gui_helpers import make_project


def project_with_notes(tmp_path):
    project = make_project(tmp_path / "p")
    base = project.root / "research"
    (base / "tides").mkdir(parents=True)
    (base / "tides" / "almanac.md").write_text(
        "# Tide almanac\n\nThe spur floods at dusk when the spring tide meets the storm drains.\n\n"
        "Low water is about six hours later.\n", encoding="utf-8")
    (base / "noodles.md").write_text(
        "# Noodle stalls\n\nStalls sell soy noodles; the broth is salted with copper-tasting water.\n",
        encoding="utf-8")
    (base / "plain-name.md").write_text("Just a body with no heading about trams and timetables.\n",
                                        encoding="utf-8")
    (base / ".hidden.md").write_text("# nope\n", encoding="utf-8")
    return project


def test_listing_titles_and_hidden_files(tmp_path):
    project = project_with_notes(tmp_path)
    notes = rs.list_notes(project)
    assert [(n.rel, n.title) for n in notes] == [
        ("noodles.md", "Noodle stalls"), ("plain-name.md", "Plain Name"),
        ("tides/almanac.md", "Tide almanac")]
    assert rs.is_research_path(project, project.root / "research" / "tides" / "almanac.md")
    assert not rs.is_research_path(project, project.root / "research" / ".hidden.md")
    assert not rs.is_research_path(project, project.root / "manuscript" / "01-arrival.md")
    assert rs.list_notes(make_project(tmp_path / "empty")) == []


def test_new_notes_get_unique_names(tmp_path):
    project = make_project(tmp_path / "p")
    a = rs.new_note(project, "Tide  tables")
    b = rs.new_note(project, "Tide tables")
    assert a.name == "tide-tables.md" and b.name == "tide-tables-2.md"
    assert a.read_text() == "# Tide  tables\n\n".replace("  ", " ")
    with pytest.raises(ValueError):
        rs.new_note(project, "  ")


def test_note_from_url_has_the_link_and_a_title_and_fetches_nothing(tmp_path):
    project = make_project(tmp_path / "p")
    path = rs.note_from_url(project, "https://www.example.com/articles/tide-tables-explained.html")
    assert path.read_text() == ("# example.com - tide tables explained\n\n"
                                "https://www.example.com/articles/tide-tables-explained.html\n")
    assert rs.note_from_url(project, "http://a.org", "My title").read_text().startswith("# My title")
    for bad in ("tide tables", "ftp://x.org/a", "javascript:alert(1)", "", "https://a.org some words"):
        with pytest.raises(ValueError):
            rs.note_from_url(project, bad)
    assert rs.looks_like_url(" https://a.org/x ") and not rs.looks_like_url("a.org")


def test_search_ranks_by_term_rarity_and_titles_and_returns_the_passage(tmp_path):
    project = project_with_notes(tmp_path)
    hits = rs.search(project, "When does the spur flood at dusk?")
    assert [h.note.rel for h in hits][0] == "tides/almanac.md"
    assert "floods at dusk" in hits[0].excerpt and "Low water" not in hits[0].excerpt
    assert hits[0].score > 0
    # title words count extra
    assert rs.search(project, "noodle")[0].note.rel == "noodles.md"
    # nothing matches: nothing returned (no zero-score padding); stop words alone match nothing
    assert rs.search(project, "zeppelin") == []
    assert rs.search(project, "the and of") == []
    assert len(rs.search(project, "the spur copper trams", limit=2)) == 2


def test_delete_note_only_inside_research(tmp_path):
    project = project_with_notes(tmp_path)
    note = project.root / "research" / "noodles.md"
    rs.delete_note(project, note)
    assert not note.exists()
    with pytest.raises(FileNotFoundError):
        rs.delete_note(project, project.list_scenes()[0])
    assert project.list_scenes()[0].exists()


def test_deleting_a_note_moves_it_to_the_trash_and_it_can_come_back(tmp_path):
    project = project_with_notes(tmp_path)
    note = project.root / "research" / "tides" / "almanac.md"
    text = note.read_text(encoding="utf-8")
    moved = rs.delete_note(project, note)
    assert not note.exists() and moved.parent == project.trash_dir and moved.is_file()
    assert moved.name.endswith("-research__tides__almanac.md")
    (item,) = project.list_trash()
    assert (item.kind, item.title, item.original) == ("research", "Tide almanac", "research/tides/almanac.md")
    assert [n.rel for n in rs.list_notes(project)] == ["noodles.md", "plain-name.md"]
    back = project.restore_scene(item.name)
    assert back == note and note.read_text(encoding="utf-8") == text
    assert project.list_trash() == [] and not project.trash_dir.exists()


def test_restore_falls_back_to_research_when_its_folder_is_gone_or_the_name_is_taken(tmp_path):
    project = project_with_notes(tmp_path)
    note = project.root / "research" / "tides" / "almanac.md"
    rs.delete_note(project, note)
    note.parent.rmdir()                                    # the folder is gone
    (item,) = project.list_trash()
    assert project.restore_scene(item.name) == project.root / "research" / "almanac.md"
    again = project.root / "research" / "noodles.md"
    rs.delete_note(project, again)
    again.write_text("# A newer noodles note\n", encoding="utf-8")   # the name was reused
    (item,) = project.list_trash()
    assert project.restore_scene(item.name) == project.root / "research" / "noodles-2.md"
    assert again.read_text(encoding="utf-8") == "# A newer noodles note\n"


def test_trash_lists_scenes_and_research_together_and_empties_both(tmp_path):
    project = project_with_notes(tmp_path)
    scene = project.list_scenes()[0]
    project.delete_scene(scene)
    rs.delete_note(project, project.root / "research" / "noodles.md")
    kinds = sorted(i.kind for i in project.list_trash())
    assert kinds == ["research", "scene"]
    research_item = next(i for i in project.list_trash() if i.kind == "research")
    project.delete_forever(research_item.name)
    assert [i.kind for i in project.list_trash()] == ["scene"]
    assert not (project.root / "research" / "noodles.md").exists()
    rs.delete_note(project, project.root / "research" / "plain-name.md")
    assert project.empty_trash() == 2 and project.list_trash() == []
