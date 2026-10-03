"""Launch screen flow tests."""

import time
from pathlib import Path

from textual.widgets import Input, ListView

import chisel.tui.launch as launch_mod
from chisel.core.project import Project
from chisel.core.recents import Recent
from chisel.tui.app import ChiselApp
from chisel.tui.launch import LaunchScreen, NewProjectPrompt


def fake_recents(*recents: Recent):
    return lambda: list(recents)


async def test_launch_screen_lists_recents(tmp_path: Path, monkeypatch):
    proj = Project.create(tmp_path / "novel", title="Launch Novel")
    recent = Recent(proj.root, proj.title, time.time())
    monkeypatch.setattr(launch_mod, "load_recents", fake_recents(recent))

    app = ChiselApp()  # no project -> launch screen
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LaunchScreen)
        lv = app.screen.query_one("#recents", ListView)
        assert len(lv.children) == 1

        await pilot.press("enter")  # resume the highlighted recent project
        await pilot.pause()
        assert app.project is not None
        assert app.project.title == "Launch Novel"
        assert "Welcome to chisel" in app.editor.text


async def test_launch_screen_skips_stale_recents(tmp_path: Path, monkeypatch):
    gone = Recent(tmp_path / "deleted-novel", "Gone", time.time())
    monkeypatch.setattr(launch_mod, "load_recents", fake_recents(gone))

    app = ChiselApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LaunchScreen)
        lv = app.screen.query_one("#recents", ListView)
        # stale entry filtered; only the "(none yet…)" placeholder remains
        assert len(lv.children) == 1
        assert "none yet" in str(lv.children[0].children[0].render())


async def test_launch_new_project(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(launch_mod, "load_recents", fake_recents())

    app = ChiselApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LaunchScreen)
        screen.action_new_project()
        await pilot.pause()

        prompt = app.screen
        assert isinstance(prompt, NewProjectPrompt)
        title_input = prompt.query_one("#title-input", Input)
        path_input = prompt.query_one("#path-input", Input)
        title_input.value = "The Salt Road"
        await pilot.pause()
        # path prefilled from the title slug
        assert path_input.value.endswith("the-salt-road")
        # redirect into tmp for the test
        path_input.value = str(tmp_path / "the-salt-road")
        prompt._submit()
        await pilot.pause()

        assert app.project is not None
        assert app.project.title == "The Salt Road"
        assert (tmp_path / "the-salt-road" / "project.toml").is_file()
        assert "Welcome to chisel" in app.editor.text


async def test_entity_labels_show_type_with_brackets(tmp_path: Path):
    """Regression: Rich markup ate '[character]' in sidebar labels."""
    proj = Project.create(tmp_path / "novel", title="T")
    proj.create_entity("Rick")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        lv = app.query_one("#entities", ListView)
        labels = [str(item.children[0].render()) for item in lv.children]
        assert any("Rick [character]" in label for label in labels), labels
