"""Project mode (project.toml [project] mode): story (default), research or script."""

import pytest

from chisel.core.project import MODES, Project


def test_new_project_defaults_to_story(tmp_path):
    p = Project.create(tmp_path / "a", "A")
    assert p.mode == "story"
    assert Project.open(tmp_path / "a").mode == "story"


def test_create_with_research_mode_round_trips(tmp_path):
    p = Project.create(tmp_path / "a", "A", "research")
    assert p.mode == "research"
    assert Project.open(tmp_path / "a").mode == "research"


def test_unknown_mode_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(ValueError):
        Project.create(tmp_path / "a", "A", "poetry")
    assert not (tmp_path / "a").exists()


def test_script_mode_is_a_story_variant_with_a_fountain_sample(tmp_path):
    p = Project.create(tmp_path / "a", "A", "script")
    assert p.mode == "script" and Project.open(tmp_path / "a").mode == "script"
    # the story folders (characters, places...) exist; the research ones do not
    assert (tmp_path / "a" / "entities" / "characters").is_dir()
    assert not (tmp_path / "a" / "entities" / "sources").exists()
    sample = (tmp_path / "a" / "manuscript" / "01-opening.md").read_text(encoding="utf-8")
    assert "INT. KITCHEN - DAY" in sample and "CUT TO:" in sample


def test_old_projects_without_a_mode_are_story(tmp_path):
    root = tmp_path / "old"
    root.mkdir()
    (root / "project.toml").write_text('title = "Old"\nauthor = ""\n', encoding="utf-8", newline="\n")
    assert Project.open(root).mode == "story"


@pytest.mark.parametrize("raw", ['"fiction"', '"nonsense"', "3", '""'])
def test_unknown_or_old_values_read_as_story(tmp_path, raw):
    root = tmp_path / "x"
    root.mkdir()
    (root / "project.toml").write_text(f'title = "X"\n\n[project]\nmode = {raw}\n', encoding="utf-8", newline="\n")
    assert Project.open(root).mode == "story"


def test_editing_author_details_keeps_the_mode(tmp_path):
    p = Project.create(tmp_path / "a", "A", "research")
    p.update_author_info(author="Jane")
    assert Project.open(tmp_path / "a").mode == "research"


def test_modes_listed():
    assert MODES[0] == "story"
