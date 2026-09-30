"""workspace.py builders and the JSON fixture shared with the TS tests."""

import json
import os
from pathlib import Path

from tests.gui_helpers import make_project
from lorewrite.gui import workspace as ws

FIXTURE = Path(__file__).resolve().parents[1] / "gui/src/data/fixtures/workspace.json"


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
    assert ws.scene_kicker(Path("07-x.md")) == "SCENE 07"


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


def test_binder_groups_and_placeholders(tmp_path):
    project = make_project(tmp_path / "p")
    built = ws.build_workspace(project, project.load_entities(),
                               baseline_words=0, session_minutes=0, ai_cost=0)
    top = {n["id"]: n for n in built["binder"]}
    assert {c["title"] for c in top["group:characters"]["children"]} == {"Mara Vale", "Elias Vale"}
    assert top["group:world"]["children"][0]["meta"] == "place"
    assert top["style.md"]["meta"] == "new"  # listed before it exists; opening creates the stub
    assert top["ph:research"]["placeholder"] and top["ph:trash"]["placeholder"]
    manuscript = next(c for c in top["project"]["children"] if c["id"] == "group:manuscript")
    assert [c["title"] for c in manuscript["children"]] == ["01  Arrival", "02  The Archive"]
