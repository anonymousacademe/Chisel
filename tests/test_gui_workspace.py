"""workspace.py builders and the JSON fixture shared with the TS tests."""

import json
import os
from pathlib import Path

from tests.gui_helpers import make_book, make_project
from chisel.core import collections as coll
from chisel.gui import workspace as ws

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
    assert ws.scene_kicker(project, project.unplace_scene(scene)) == "PARKED"


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
    if os.environ.get("CHISEL_REGEN_FIXTURE"):
        FIXTURE.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == built


def test_workspace_with_parts_matches_fixture(tmp_path):
    """The same shape for a book (front matter, parts, a scene with details, one
    unplaced scene and one trashed), shared with the vitest suite."""
    project = make_book(tmp_path / "p")
    rain = project.manuscript_dir / "01-the-recall" / "01-rain.md"
    rain.write_text("---\npov: Mara Vale\nplace: Lower Meridian\nstatus: revising\ntarget: 2400\n"
                    "collections: [Needs continuity pass]\n---\n"
                    "# Rain\n\nrain rain rain\n", encoding="utf-8")
    (project.root / "notebook" / "tides").mkdir(parents=True)
    (project.root / "notebook" / "tides" / "almanac.md").write_text("# Tide almanac\n\nHigh water at dusk.\n")
    (project.root / "notebook" / "trams.md").write_text("Trams stop at midnight.\n")
    coll.create(project, "Needs continuity pass", "amber")
    coll.create(project, "Mara's arc", "violet")
    project.unplace_scene(project.manuscript_dir / "01-the-recall" / "02-capsule.md")
    project.delete_scene(project.manuscript_dir / "02-ghost" / "01-signal.md")
    built = ws.build_workspace(project, project.load_entities(),
                               baseline_words=0, session_minutes=0, ai_cost=0)
    built["project"]["path"] = "<root>"
    if os.environ.get("CHISEL_REGEN_FIXTURE"):
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
    assert top["group:research"]["kind"] == "research" and top["group:research"]["children"] == []   # real since Wave 3
    assert not any(n.get("placeholder") for n in built["binder"])
    assert not top["group:trash"].get("placeholder") and top["group:trash"]["kind"] == "trash"
    assert "group:unplaced" not in top        # Parked scenes is listed only while it holds scenes
    assert not any(c.get("placeholder") for c in top["project"]["children"])  # Parts are real now
    manuscript = next(c for c in top["project"]["children"] if c["id"] == "group:manuscript")
    assert [c["title"] for c in manuscript["children"]] == ["01  Arrival", "02  The Archive"]


def test_parked_scenes_group_hidden_when_empty_and_shown_with_a_count(tmp_path):
    project = make_book(tmp_path / "p")

    def ids():
        built = ws.build_workspace(project, project.load_entities(),
                                   baseline_words=0, session_minutes=0, ai_cost=0)
        return built, {n["id"]: n for n in built["binder"]}

    built, top = ids()
    assert "group:unplaced" not in top
    first = project.manuscript_dir / "01-the-recall" / "01-rain.md"
    second = project.manuscript_dir / "01-the-recall" / "02-capsule.md"
    parked = project.unplace_scene(first)
    built, top = ids()
    node = top["group:unplaced"]
    assert (node["title"], node["kind"], node["meta"]) == ("Parked scenes", "inbox", "1")
    assert node["description"].startswith("Written but not part of the book.")
    assert "Not counted in word totals or export" in node["description"] and "searchable" in node["description"]
    project.unplace_scene(second)
    assert ids()[1]["group:unplaced"]["meta"] == "2"
    # the folder and the internal names do not change
    assert parked.parent.name == "_unplaced" and node["id"] == "group:unplaced"
    # putting everything back hides the group again
    for p in sorted(project.unplaced_dir.glob("*.md")):
        project.place_scene(p, project.list_parts()[-1])
    assert "group:unplaced" not in ids()[1]


def test_dead_placeholder_helper_is_gone():
    from chisel.gui import workspace
    assert not hasattr(workspace, "_placeholder")
