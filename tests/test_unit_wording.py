"""Research projects say "section" where story and script projects say "scene" (wording only)."""

import pytest

from chisel.core.project import Project
from chisel.core.export import summarize, summary_line
from chisel.core.export.manuscript import ExportOptions
from chisel.gui.api import Api
from chisel.gui import workspace as ws

from tests.gui_helpers import make_project


def _write_meta(root, text):
    path = root / "project.toml"
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")


def test_unit_validation_per_mode(tmp_path):
    story = Project.create(tmp_path / "s", "S")
    script = Project.create(tmp_path / "x", "X", "script")
    paper = Project.create(tmp_path / "r", "R", "research")
    assert (story.unit, script.unit, paper.unit) == ("scene", "scene", "section")
    for p in (story, script):
        p.update_manuscript_settings(unit="chapter")
        assert p.unit == "chapter"
        with pytest.raises(ValueError):
            p.update_manuscript_settings(unit="section")
    paper.update_manuscript_settings(unit="chapter")
    assert paper.unit == "chapter"
    paper.update_manuscript_settings(unit="section")
    assert paper.unit == "section"
    with pytest.raises(ValueError):
        paper.update_manuscript_settings(unit="scene")


def test_research_create_writes_section_unit(tmp_path):
    root = tmp_path / "r"
    Project.create(root, "R", "research")
    assert 'unit = "section"' in (root / "project.toml").read_text(encoding="utf-8")
    assert Project.open(root).unit == "section"


def test_existing_research_projects_read_as_section(tmp_path):
    root = tmp_path / "old"
    Project.create(root, "Old", "research")
    text = (root / "project.toml").read_text(encoding="utf-8").replace('unit = "section"', 'unit = "scene"')
    (root / "project.toml").write_text(text, encoding="utf-8", newline="\n")
    assert Project.open(root).unit == "section"
    bare = tmp_path / "bare"
    Project.create(bare, "Bare", "research")
    (bare / "project.toml").write_text('title = "Bare"\n[project]\nmode = "research"\n', encoding="utf-8", newline="\n")
    assert Project.open(bare).unit == "section"
    # a story project with a section value falls back to scene
    story = tmp_path / "st"
    Project.create(story, "St")
    _write_meta(story, '\n[manuscript]\nunit = "section"\n')
    assert Project.open(story).unit == "scene"


def test_story_and_script_workspace_wording_unchanged(tmp_path):
    api = Api()
    assert api.new_project("Tale", str(tmp_path / "tale"))["ok"]
    story = api.get_workspace()["workspace"]
    assert story["project"]["unit"] == "scene"
    assert story["project"]["labels"]["parked"] == "Parked scenes"
    assert api.new_project("Play", str(tmp_path / "play"), "script")["ok"]
    script = api.get_workspace()["workspace"]
    assert script["project"]["unit"] == "scene"
    assert script["project"]["labels"]["parked"] == "Parked scenes"


def test_research_workspace_says_section(tmp_path):
    api = Api()
    assert api.new_project("Paper", str(tmp_path / "paper"), "research")["ok"]
    w = api.get_workspace()["workspace"]
    assert w["project"]["unit"] == "section"
    assert w["project"]["labels"]["parked"] == "Parked sections"
    doc_id = w["scenes"][0]["id"]
    project = api.project
    assert ws.scene_kicker(project, project.root / doc_id).startswith("SECTION")


# Every Python string that reaches the author and names the unit: (what, expected substring for a research project).
def _errors(api, doc_id):
    return {
        "new_scene without a title": api.new_scene("  ", None, None)["error"],
        "rename_scene without a title": api.rename_scene(doc_id, "")["error"],
        "register_draft on a note": api.register_draft("notes/none.md", "abc123", "x")["error"],
    }


def test_research_error_text_table(tmp_path):
    api = Api()
    assert api.new_project("Paper", str(tmp_path / "paper"), "research")["ok"]
    w = api.get_workspace()["workspace"]
    errors = _errors(api, w["scenes"][0]["id"])
    assert errors["new_scene without a title"] == "a section needs a title"
    assert errors["rename_scene without a title"] == "a section needs a title"
    assert "scene" not in errors["register_draft on a note"]
    project = api.project
    with pytest.raises(ValueError, match="not a manuscript section"):
        project.place_scene(project.root / "notebook" / "x.md")
    r = api.set_unit("scene")
    assert r["ok"] is False and "section" in r["error"]
    assert api.set_unit("chapter")["ok"]


def test_story_error_text_unchanged(tmp_path):
    api = Api()
    root = tmp_path / "p"
    make_project(root)
    assert api.open_project(str(root))["ok"]
    assert api.new_scene("  ", None, None)["error"] == "a scene needs a title"
    assert api.set_unit("section")["ok"] is False


def test_export_wording(tmp_path):
    paper = Project.create(tmp_path / "paper", "P", "research")
    s = summarize(paper, ExportOptions())
    assert "section" in summary_line(s, paper.unit)
    story = make_project(tmp_path / "story2")
    assert "scene" in summary_line(summarize(story, ExportOptions()), story.unit)
    assert ws.LABELS["research"]["parked"] == "Parked sections"
