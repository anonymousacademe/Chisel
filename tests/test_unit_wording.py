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


def test_tui_notice_text_story_and_script_pinned(tmp_path):
    """Table: the exact story / script strings (byte for byte) next to the research ones."""
    import inspect
    from chisel.tui import structuremixin, snapshotsmixin, commentsmixin, spellmixin, inspirationmixin, app as appmod
    srcs = {m.__name__.rsplit('.', 1)[-1]: inspect.getsource(m) for m in (structuremixin, snapshotsmixin, commentsmixin,
                                                       spellmixin, inspirationmixin, appmod)}
    table = [   # (module, rendered text for a story/script project)
        ("structuremixin", 'f"Open a {self._unit_word} first"', "Open a scene first", "Open a section first"),
        ("structuremixin", "f\"'{title}' still has {self._unit_word}s - move them out first\"",
         "'X' still has scenes - move them out first", "'X' still has sections - move them out first"),
        ("structuremixin", 'f"Moved to Unplaced {self._unit_word}s (not counted in the book)"',
         "Moved to Unplaced scenes (not counted in the book)", "Moved to Unplaced sections (not counted in the book)"),
        ("spellmixin", 'f"Spell check applies to {self._unit_word}s"', "Spell check applies to scenes",
         "Spell check applies to sections"),
        ("snapshotsmixin", 'f"Snapshot taken of {n} {self._unit_word}(s)"', "Snapshot taken of 2 scene(s)",
         "Snapshot taken of 2 section(s)"),
        ("commentsmixin", 'f"Comment added (it is kept beside the {self._unit_word}, not in the text)"',
         "Comment added (it is kept beside the scene, not in the text)",
         "Comment added (it is kept beside the section, not in the text)"),
    ]
    for kind in ("story", "script", "research"):
        u = _app_for(tmp_path, kind)._unit_word
        for mod, template, story_text, research_text in table:
            assert template in srcs[mod]
            title, n = "X", 2
            got = eval(template, {"self": type("S", (), {"_unit_word": u})(), "title": title, "n": n})
            assert got == (research_text if kind == "research" else story_text)


def test_tui_palette_titles_story_script_pinned(tmp_path):
    """Story and script palettes show the ACTIONS table verbatim (no unit rewriting)."""
    from chisel.tui.commands import ActionProvider
    for kind in ("story", "script"):
        app = _app_for(tmp_path, kind)
        rows = list(ActionProvider._entries(_Stub(app)))
        raw = {m: (t, h) for t, m, h in ActionProvider.ACTIONS}
        by_title = {title: (display, help_text) for display, title, _f, help_text in rows}
        for method, (title, help_text) in raw.items():
            if method == "toggle_unit" or title not in by_title:
                continue   # toggle names its switch; some rows are mode-gated
            assert by_title[title][1] == help_text
    paper = _app_for(tmp_path, "research")
    shown = {t for _d, t, _f, _h in ActionProvider._entries(_Stub(paper))}
    assert "Snapshot section" in shown or any("section" in t for t in shown)


class _Stub:
    def __init__(self, app):
        from chisel.tui.commands import ActionProvider
        self.app = app
        self.ACTIONS = ActionProvider.ACTIONS
        self.CATEGORY = ActionProvider.CATEGORY


def test_export_summary_text_story_script_pinned(tmp_path):
    story = make_project(tmp_path / "st")
    line = summary_line(summarize(story, ExportOptions()), story.unit)
    assert line == summary_line(summarize(story, ExportOptions()), "scene")
    assert "section" not in line
