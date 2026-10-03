"""Spell check in the TUI: underline, toggle, f6 modal, dictionary actions."""

from pathlib import Path

import pytest
from textual.widgets.text_area import Selection

from chisel.core import settings as user_settings
from chisel.core import spelling
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.spellscreen import SpellScreen

SCENE = "# Docks\n\nHe would recieve Zorblax at the dock.\n\nA second pragraph.\n"


@pytest.fixture
def project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="Spell Novel")
    (proj.manuscript_dir / "01-opening.md").unlink()
    (proj.manuscript_dir / "01-docks.md").write_text(SCENE, encoding="utf-8")
    return proj


def underlined(app: ChiselApp, row: int) -> str:
    strip = app.editor.render_line(row)
    return "".join(seg.text for seg in strip
                   if seg.style and seg.style.underline
                   and seg.style.color and seg.style.color.name == "red").strip()


async def wait_until(pilot, check, tries: int = 50) -> bool:
    """The re-check runs in a worker; slow CI runners need more than one pause."""
    for _ in range(tries):
        if check():
            return True
        await pilot.pause(0.1)
    return check()


async def test_misspelling_is_underlined_and_toggle_removes_it(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.refresh_spelling()
        await pilot.pause()
        assert "recieve" in underlined(app, 2)
        app.toggle_spellcheck()
        await pilot.pause()
        assert underlined(app, 2) == ""
        assert user_settings.get("spellcheck") is False
        app.toggle_spellcheck()
        await pilot.pause()
        assert "recieve" in underlined(app, 2)


async def test_debounced_check_runs_on_open_and_after_edit(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.9)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "recieve" in underlined(app, 2)
        app.editor.move_cursor((4, 0))
        await pilot.press("x", "q", "z", "v", "k")
        await pilot.pause(1.0)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "xqzvk" in underlined(app, 4)


async def test_only_scenes_are_checked(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_project_dictionary()
        await pilot.pause()
        assert app.current_path == project.root / "dictionary.txt"
        app.editor.load_text("recieve\n")
        app.refresh_spelling()
        await pilot.pause()
        assert underlined(app, 0) == ""


async def test_f6_replace(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.editor.move_cursor((0, 0))
        await pilot.press("f6")
        await pilot.pause()
        assert isinstance(app.screen, SpellScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert "He would receive Zorblax" in app.editor.text


async def test_f6_add_project_personal_and_ignore(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.editor.move_cursor((0, 0))
        await pilot.press("f6")  # recieve
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert spelling.load_dictionary(spelling.project_dictionary_path(project)) \
            == ["recieve"]
        assert await wait_until(pilot, lambda: "recieve" not in underlined(app, 2))
        await pilot.press("f6")  # cursor after "recieve" -> Zorblax
        await pilot.pause()
        assert isinstance(app.screen, SpellScreen)
        await pilot.press("p")
        await pilot.pause()
        assert spelling.load_dictionary(spelling.personal_dictionary_path()) \
            == ["Zorblax"]
        await pilot.press("f6")  # next: pragraph
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert await wait_until(pilot, lambda: underlined(app, 4) == "")
        assert "pragraph" not in spelling.load_dictionary(
            spelling.project_dictionary_path(project))
        await pilot.press("f6")
        await pilot.pause()
        assert not isinstance(app.screen, SpellScreen)  # nothing left


async def test_f6_esc_cancels_and_wraps(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.editor.move_cursor((4, 20))  # past the last misspelling
        await pilot.press("f6")
        await pilot.pause()
        assert isinstance(app.screen, SpellScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert "recieve" in app.editor.text
        assert app.editor.cursor_location[0] == 2  # wrapped to the first


async def test_add_selection_as_phrase(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.editor.load_text("The maglev spur ran.\n")
        app.editor.select_all()
        app.add_selection_to_dictionary()
        await pilot.pause()
        assert spelling.load_dictionary(spelling.project_dictionary_path(project)) \
            == ["The maglev spur ran."]
        app.editor.load_text("A maglev spur ran. A maglev.\n")
        await pilot.pause()  # let the Changed message land first
        app.editor.selection = Selection((0, 2), (0, 13))
        app.add_selection_to_dictionary()
        app.refresh_spelling()
        await pilot.pause()
        assert underlined(app, 0) == "maglev"  # only the lone one


async def test_settings_checkbox_persists(project):
    from chisel.tui.settingscreen import SettingsScreen
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_settings()
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        from textual.widgets import Checkbox
        box = app.screen.query_one("#spellcheck", Checkbox)
        assert box.value is True
        box.value = False
        app.screen._save()
        assert user_settings.get("spellcheck") is False


async def test_teardown_with_pending_spell_check(project):
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.editor.move_cursor((4, 0))
        await pilot.press("x")  # spell timer pending at exit


async def test_large_scene_applies_quickly(project):
    """The check runs off the UI thread; applying thousands of spans is cheap."""
    import time
    para = "The quick brown fox recieve the lazy dog near Kessler's noodle-stall.\n\n"
    text = "# Big\n\n" + para * 4000  # ~50k words, 4000 misspellings
    (project.manuscript_dir / "01-docks.md").write_text(text, encoding="utf-8")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        found = spelling.check(app.editor.text, app._accepted())
        t0 = time.process_time()  # CPU time: wall time flakes on a busy machine
        app.editor.set_misspellings(found)
        assert time.process_time() - t0 < 1.0
        assert len(app.editor._spelling) == 4000
