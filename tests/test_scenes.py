"""Scene organization: retitle, rename, move, delete — core + palette."""

from pathlib import Path

from lorewrite.core.project import Project, retitle_text
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.commands import ActionProvider, SceneProvider


def _three_scene_project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="Scenes")
    (proj.manuscript_dir / "02-second.md").write_text("# Second\n\nTwo.\n")
    (proj.manuscript_dir / "03-third.md").write_text("# Third\n\nThree.\n")
    return proj


# -- core --------------------------------------------------------------------


def test_retitle_text_replaces_first_heading():
    assert retitle_text("# Old\n\nBody.\n", "New") == "# New\n\nBody.\n"


def test_retitle_text_prepends_when_no_heading():
    assert retitle_text("Just text.\n", "New") == "# New\n\nJust text.\n"


def test_rename_scene_on_disk(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    path = proj.manuscript_dir / "02-second.md"
    proj.rename_scene(path, "Second, Revised")
    assert proj.scene_title(path) == "Second, Revised"
    assert "Two." in path.read_text()


def test_move_scene_swaps_and_returns_new_path(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    path = proj.manuscript_dir / "02-second.md"
    new_path = proj.move_scene(path, +1)
    assert new_path is not None
    assert new_path.name == "03-second.md"
    assert (proj.manuscript_dir / "02-third.md").is_file()
    assert [s.name for s in proj.list_scenes()] == [
        "01-opening.md", "02-third.md", "03-second.md",
    ]


def test_move_scene_at_edge_returns_none(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    first = proj.manuscript_dir / "01-opening.md"
    assert proj.move_scene(first, -1) is None
    assert first.is_file()


def test_delete_scene(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    path = proj.manuscript_dir / "02-second.md"
    proj.delete_scene(path)
    assert not path.exists()
    assert len(proj.list_scenes()) == 2


# -- palette ------------------------------------------------------------------


async def test_palette_discover_shows_actions(tmp_path: Path):
    """Regression: ctrl+p opened to a blank search bar."""
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        action_hits = [
            str(hit.display)
            async for hit in ActionProvider(app.screen).discover()
        ]
        scene_hits = [
            str(hit.display)
            async for hit in SceneProvider(app.screen).discover()
        ]
    assert any("New scene" in h for h in action_hits)
    assert any("Rename current scene" in h for h in action_hits)
    assert any("Delete current scene" in h for h in action_hits)
    assert any("Second" in h for h in scene_hits)
    # categorized: every hit carries a category prefix
    assert all(" · " in h for h in action_hits + scene_hits)


async def test_palette_ui_populates_on_open(tmp_path: Path):
    """End-to-end: pressing ctrl+p shows options without typing."""
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause(1.0)
        from textual.widgets import OptionList

        prompts = [
            str(option.prompt)
            for option_list in app.screen.query(OptionList)
            for option in option_list.options
        ]
    assert any("New scene" in p for p in prompts), prompts
    assert any("Opening" in p for p in prompts), prompts


async def test_palette_search_empty_query_matches_all(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hits = [h async for h in ActionProvider(app.screen).search("")]
        scenes = [h async for h in SceneProvider(app.screen).search("  ")]
    assert len(hits) == len(ActionProvider.ACTIONS)
    assert len(scenes) == 3


async def test_palette_search_still_filters(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hits = [h async for h in ActionProvider(app.screen).search("rename")]
    assert len(hits) >= 1
    assert any("Rename current scene" in str(h.match_display) for h in hits)


# -- app flows ------------------------------------------------------------------


async def test_rename_scene_flow(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-second.md")
        app.rename_scene_prompt()
        await pilot.pause()
        from textual.widgets import Input

        app.screen.query_one(Input).value = "Second, Revised"
        await pilot.press("enter")
        await pilot.pause()
        assert proj.scene_title(proj.manuscript_dir / "02-second.md") == (
            "Second, Revised"
        )
        assert "# Second, Revised" in app.editor.text


async def test_delete_scene_flow(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-second.md")
        app.delete_scene_confirm()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert not (proj.manuscript_dir / "02-second.md").exists()
        # fell back to another scene in the editor
        assert app.current_path is not None
        assert "Opening" in app.editor.text


async def test_move_scene_flow(tmp_path: Path):
    proj = _three_scene_project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-second.md")
        app.move_scene_down()
        await pilot.pause()
        assert app.current_path is not None
        assert app.current_path.name == "03-second.md"
        assert "Second" in app.editor.text
