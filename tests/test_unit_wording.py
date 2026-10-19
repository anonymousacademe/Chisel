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
    # the starter outline begins with a front-matter part: look at the first section of the article itself
    doc_id = next(sc["id"] for sc in w["scenes"] if not sc["frontMatter"])
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


# -- the terminal app: guards with no project open, and story/script text pinned ----------

GUARDS = ["action_find_aliases", "action_generate", "action_check_continuity", "action_check_voice",
          "restore_waived", "action_update_bible", "edit_details", "delete_scene_confirm",
          "snapshot_scene_prompt", "add_comment_prompt"]


@pytest.mark.parametrize("name", GUARDS)
def test_tui_guards_without_a_project_notify_not_raise(name):
    from chisel.tui.app import ChiselApp
    app = ChiselApp(None)
    seen = []
    app.notify = lambda msg, **kw: seen.append(msg)   # type: ignore[method-assign]
    fn = getattr(app, name, None)
    if fn is None:
        pytest.skip(f"{name} is not a method here")
    fn()
    assert seen and "first" in seen[0] or name == "restore_waived" and seen


def _app_for(tmp_path, mode, unit=None):
    from chisel.tui.app import ChiselApp
    p = Project.create(tmp_path / mode, "T", mode)
    if unit:
        p.update_manuscript_settings(unit=unit)
    app = ChiselApp(p)
    app.notify = lambda msg, **kw: None   # type: ignore[method-assign]
    return app


def test_tui_unit_word_property(tmp_path):
    from chisel.tui.app import ChiselApp
    assert ChiselApp(None)._unit_word == "scene"
    assert _app_for(tmp_path, "story")._unit_word == "scene"
    assert _app_for(tmp_path, "script")._unit_word == "scene"
    assert _app_for(tmp_path, "research")._unit_word == "section"


EXPECT = {  # unit word -> exact text; story and script are the pre-change strings
    "scene": {
        "open_first": "Open a scene first",
        "status": "no file open — ctrl+p to open a scene",
        "comments_empty": "No comments on this scene. Select text and use 'Add comment on selection'.",
        "snap_empty": "No snapshots of this scene yet.",
        "snap_hint": "enter/c compare · r restore · d delete · n new snapshot · a snapshot all scenes · esc close",
        "details_header": "Scene details",
        "unit": "scene",
    },
    "section": {
        "open_first": "Open a section first",
        "status": "no file open — ctrl+p to open a section",
        "comments_empty": "No comments on this section. Select text and use 'Add comment on selection'.",
        "snap_empty": "No snapshots of this section yet.",
        "snap_hint": "enter/c compare · r restore · d delete · n new snapshot · a snapshot all sections · esc close",
        "details_header": "Section details",
        "unit": "section",
    },
}


def _label_text(screen, selector):
    from textual.widgets import Label
    return str(screen.query_one(selector, Label).render())


@pytest.mark.parametrize("kind", ["story", "script", "research"])
async def test_tui_notices_run_the_real_code(tmp_path, kind):
    """Drive the real notify / status / screen code; story and script text is exact, research says section."""
    from chisel.tui.app import ChiselApp
    from chisel.tui.commentscreens import CommentsScreen
    from chisel.tui.snapshotscreens import SnapshotsScreen
    from chisel.tui.structurescreens import DetailsScreen
    project = Project.create(tmp_path / kind, "T", kind)
    want = EXPECT["section" if kind == "research" else "scene"]
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        seen: list[str] = []
        app.notify = lambda msg, **kw: seen.append(msg)   # type: ignore[method-assign]
        app.current_path = None
        app.update_status()
        assert app._status_text == want["status"]
        for name in ("delete_scene_confirm", "snapshot_scene_prompt", "add_comment_prompt", "open_comments",
                     "open_snapshots", "edit_details", "restore_waived", "action_update_bible"):
            seen.clear()
            getattr(app, name)()
            assert seen == [want["open_first"]], (name, seen)
        app.push_screen(CommentsScreen([], {}, "T", None))
        await pilot.pause()
        assert _label_text(app.screen, "#cm-empty") == want["comments_empty"]
        app.pop_screen()
        app.push_screen(SnapshotsScreen("T", [], 0))
        await pilot.pause()
        assert _label_text(app.screen, "#snap-empty") == want["snap_empty"]
        assert _label_text(app.screen, "#snap-hint") == want["snap_hint"]
        descs = {b.action: b.description for items in app.screen._bindings.key_to_bindings.values() for b in items}
        assert descs["plain('all')"] == ("All sections" if kind == "research" else "All scenes")
        app.pop_screen()
        app.push_screen(DetailsScreen("", [], []))
        await pilot.pause()
        assert _label_text(app.screen, "#details-header") == want["details_header"]
        app.pop_screen()
        # the export notice for an empty book
        for f in list(project.list_scenes()):
            f.unlink()
        seen.clear()
        app.export_manuscript()
        assert seen == [f"There is nothing to export yet: the book has no {want['unit']}s"]


def test_tui_palette_titles_story_script_pinned(tmp_path):
    """Story and script palettes show every ACTIONS row verbatim (a missing row fails); research says section."""
    from chisel.tui.commands import ActionProvider
    raw = {m: (t, h) for t, m, h in ActionProvider.ACTIONS}
    gated = {"import_fountain_prompt", "check_voice"}   # script-only rows
    for kind in ("story", "script"):
        app = _app_for(tmp_path, kind)
        rows = {title: (cat_display, help_text) for cat_display, title, _f, help_text
                in ActionProvider._entries(_Stub(app))}
        for method, (title, help_text) in raw.items():
            if method == "toggle_unit" or method.startswith("sync_"):
                continue   # the toggle names its switch; sync rows depend on git state
            if method in gated and kind != "script":
                assert title not in rows
                continue
            assert title in rows, f"{kind}: palette lost {title!r}"
            assert rows[title][1] == help_text, (kind, title)
            cat = ActionProvider.CATEGORY.get(method, "Action")
            assert rows[title][0] == f"{cat} · {title}"
    paper = _app_for(tmp_path, "research")
    shown = {t: h for _d, t, _f, h in ActionProvider._entries(_Stub(paper))}
    assert "Snapshot section" in shown and "Rename current section" in shown
    assert "Next section" in shown and "New section" in shown
    assert shown["Rename current section"] == "Rename the section open in the editor"
    assert not [t for t in shown if "scene" in t.lower()], [t for t in shown if "scene" in t.lower()]
    assert not [t for t, h in shown.items() if "scene" in h.lower() and "chapters" not in h.lower()]


class _Stub:
    def __init__(self, app):
        from chisel.tui.commands import ActionProvider
        self.app = app
        self.ACTIONS = ActionProvider.ACTIONS
        self.CATEGORY = ActionProvider.CATEGORY


def test_export_summary_text_pinned(tmp_path):
    from chisel.core.project import Project as P
    story = make_project(tmp_path / "st")
    assert summary_line(summarize(story, ExportOptions()), story.unit) == "2 scenes, 36 words; 1 scene has unaccepted AI drafts"
    script = P.create(tmp_path / "sc", "S", "script")
    assert summary_line(summarize(script, ExportOptions()), script.unit) == "1 scene, 50 words"
    paper = P.create(tmp_path / "paper", "P", "research")
    assert summary_line(summarize(paper, ExportOptions()), paper.unit) == "11 sections, 0 words, 2 parts"   # the starter outline (the opening note is parked)
