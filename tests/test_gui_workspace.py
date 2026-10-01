"""workspace.py builders and the JSON fixture shared with the TS tests."""

import json
import os
from pathlib import Path

from tests.gui_helpers import make_book, make_project
from lorewrite.gui import workspace as ws

FIXTURE = Path(__file__).resolve().parents[1] / "gui/src/data/fixtures/workspace.json"
PARTS_FIXTURE = Path(__file__).resolve().parents[1] / "gui/src/data/fixtures/workspace-parts.json"


def test_fmt_words():
    assert [ws.fmt_words(n) for n in (0, 999, 1000, 2840, 42700, 120000)] == [
        "0", "999", "1.0k", "2.8k", "42.7k", "120k"]


def test_initials():
    assert ws.initials("Jane Writer") == "JW"
    assert ws.initials("Madonna") == "MA"
    assert ws.initials("") == "LW"


def test_split_excerpt_headings():
    text = "# Title\n\nFirst line of prose.\n\n## Part\n\nMore.\n"
    assert ws.split_title(text)[0] == "Title"
    assert ws.excerpt(text) == "First line of prose. More."
    assert ws.headings(text) == ["Part"]


def test_kicker_follows_the_unit_and_the_part(tmp_path):
    project = make_project(tmp_path / "p")
    scene = project.manuscript_dir / "02-the-archive.md"
    assert ws.scene_kicker(project, scene) == "SCENE 02"
    project.update_manuscript_settings(unit="chapter")
    assert ws.scene_kicker(project, scene) == "CHAPTER 02"
    assert ws.scene_kicker(project, project.unplace_scene(scene)) == "UNPLACED"


def test_pending_drafts_do_not_count(tmp_path):
    project = make_project(tmp_path / "p")
    scenes = {s["title"]: s for s in ws.scene_summaries(project)}
    # "# The Archive" (3) + "## Night shift" (3) + "Mara read the files until dawn." (6)
    assert scenes["The Archive"]["words"] == 3 + 3 + 6
    assert "AI draft" not in scenes["The Archive"]["excerpt"]


def test_workspace_shape_matches_fixture(tmp_path):
    project = make_project(tmp_path / "p")
    built = ws.build_workspace(project, project.load_entities(),
                               baseline_words=5, session_minutes=3, ai_cost=0.0123)
    built["project"]["path"] = "<root>"
    if os.environ.get("LOREWRITE_REGEN_FIXTURE"):
        FIXTURE.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == built


def test_workspace_with_parts_matches_fixture(tmp_path):
    """The same shape for a book (front matter, parts, a scene with details, one
    unplaced scene and one trashed), shared with the vitest suite."""
    project = make_book(tmp_path / "p")
    rain = project.manuscript_dir / "01-the-recall" / "01-rain.md"
    rain.write_text("---\npov: Mara Vale\nplace: Lower Meridian\nstatus: revising\ntarget: 2400\n---\n"
                    "# Rain\n\nrain rain rain\n", encoding="utf-8")
    project.unplace_scene(project.manuscript_dir / "01-the-recall" / "02-capsule.md")
    project.delete_scene(project.manuscript_dir / "02-ghost" / "01-signal.md")
    built = ws.build_workspace(project, project.load_entities(),
                               baseline_words=0, session_minutes=0, ai_cost=0)
    built["project"]["path"] = "<root>"
    if os.environ.get("LOREWRITE_REGEN_FIXTURE"):
        PARTS_FIXTURE.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    assert json.loads(PARTS_FIXTURE.read_text(encoding="utf-8")) == built


def test_binder_groups_and_placeholders(tmp_path):
    project = make_project(tmp_path / "p")
    built = ws.build_workspace(project, project.load_entities(),
                               baseline_words=0, session_minutes=0, ai_cost=0)
    top = {n["id"]: n for n in built["binder"]}
    assert {c["title"] for c in top["group:characters"]["children"]} == {"Mara Vale", "Elias Vale"}
    assert top["group:world"]["children"][0]["meta"] == "place"
    assert top["style.md"]["meta"] == "new"  # listed before it exists; opening creates the stub
    assert top["ph:research"]["placeholder"]            # Wave 3
    assert not top["group:trash"].get("placeholder") and top["group:trash"]["kind"] == "trash"
    assert top["group:unplaced"]["kind"] == "inbox" and top["group:unplaced"]["children"] == []
    assert not any(c.get("placeholder") for c in top["project"]["children"])  # Parts are real now
    manuscript = next(c for c in top["project"]["children"] if c["id"] == "group:manuscript")
    assert [c["title"] for c in manuscript["children"]] == ["01  Arrival", "02  The Archive"]
