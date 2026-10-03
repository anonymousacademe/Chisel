"""UX upgrade tests: tour, writer mode, scene nav, filter, status, settings."""

from pathlib import Path

from textual.widgets import Input, ListView

from chisel import __version__
from chisel.core import settings as user_settings
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.tour import TourScreen


def _project(tmp_path: Path, title: str = "UX") -> Project:
    proj = Project.create(tmp_path / "novel", title=title)
    (proj.manuscript_dir / "02-second.md").write_text("# Second\n\nTwo.\n")
    (proj.manuscript_dir / "03-third.md").write_text("# Third\n\nThree.\n")
    return proj


# -- settings store -------------------------------------------------------------


def test_settings_roundtrip(tmp_path: Path):
    assert user_settings.get("tour_seen", False, tmp_path) is False
    user_settings.set("tour_seen", True, tmp_path)
    assert user_settings.get("tour_seen", False, tmp_path) is True


# -- first-run tour ----------------------------------------------------------------


async def test_tour_shows_on_first_run_only(tmp_path: Path):
    proj = _project(tmp_path)
    user_settings.set("tour_seen", False)  # conftest pre-set it True

    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TourScreen)
        await pilot.press("escape")
        await pilot.pause()

    # second launch: tour already seen
    app2 = ChiselApp(proj)
    async with app2.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert not isinstance(app2.screen, TourScreen)


async def test_tour_pages_advance(tmp_path: Path):
    proj = _project(tmp_path)
    user_settings.set("tour_seen", False)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TourScreen)
        assert screen._page == 0
        await pilot.press("space")
        await pilot.pause()
        assert screen._page == 1


# -- writer mode ---------------------------------------------------------------------


async def test_writer_mode_toggles(tmp_path: Path):
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "writer-mode" not in app.screen.classes
        app.writer_mode()
        await pilot.pause()
        assert "writer-mode" in app.screen.classes
        assert app.editor.styles.padding.right == 4
        app.writer_mode()
        await pilot.pause()
        assert "writer-mode" not in app.screen.classes
        assert app.editor.styles.padding.right == 0


# -- scene navigation ------------------------------------------------------------------


async def test_scene_navigation(tmp_path: Path):
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.current_path is not None
        assert app.current_path.name == "01-opening.md"
        app.next_scene()
        await pilot.pause()
        assert app.current_path.name == "02-second.md"
        app.next_scene()
        await pilot.pause()
        assert app.current_path.name == "03-third.md"
        app.next_scene()  # at the edge: stays
        await pilot.pause()
        assert app.current_path.name == "03-third.md"
        app.previous_scene()
        await pilot.pause()
        assert app.current_path.name == "02-second.md"


# -- sidebar filter ---------------------------------------------------------------------


async def test_sidebar_filter(tmp_path: Path):
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        scenes = app.query_one("#scenes", ListView)
        assert len(scenes.children) == 3
        filt = app.query_one("#filter", Input)
        filt.value = "third"
        await pilot.pause()
        assert len(scenes.children) == 1
        assert "Third" in str(scenes.children[0].children[0].render())
        filt.value = ""
        await pilot.pause()
        assert len(scenes.children) == 3


# -- status bar --------------------------------------------------------------------------


async def test_status_shows_save_time_and_project_words(tmp_path: Path):
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.save_current()
        await pilot.pause()
        status = app._status_text
        assert "saved" in status and ":" in status  # saved HH:MM
        assert "project)" in status
        # project words = sample scene + "Second Two." + "Third Three."
        assert app._project_words > 10


# -- editor settings from project.toml -----------------------------------------------------


def test_editor_settings_parsing(tmp_path: Path):
    proj = _project(tmp_path)
    (proj.root / "project.toml").write_text(
        'title = "UX"\n\n[editor]\npadding = 3\nline_numbers = false\n'
    )
    proj = Project.open(proj.root)
    prefs = proj.editor_settings()
    assert prefs == {"padding": 3, "line_numbers": False}


async def test_editor_settings_applied(tmp_path: Path):
    proj = _project(tmp_path)
    (proj.root / "project.toml").write_text(
        'title = "UX"\n\n[editor]\npadding = 3\nline_numbers = false\n'
    )
    proj = Project.open(proj.root)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.editor.show_line_numbers is False
        assert app.editor.styles.padding.right == 3


# -- version visibility --------------------------------------------------------------------


async def test_version_in_title(tmp_path: Path):
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert __version__ in app.title
