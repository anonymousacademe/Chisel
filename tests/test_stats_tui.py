"""Writing stats in the terminal app (Wave 4.1)."""

from pathlib import Path

from textual.widgets import Input

from lorewrite.core import stats as writing_stats
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.commands import ActionProvider
from lorewrite.tui.statsscreens import StatsScreen


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").write_text("# Opening\n\nalpha beta gamma\n")
    return p


async def test_saving_counts_words_in_state_dir(tmp_path: Path):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.editor.insert("one two three four\n", app.editor.document.end)
        await pilot.pause()
        app.save_current()
        await pilot.pause()
        assert app.stats.summary()["today"]["words"] == 4
        assert app._stats_brief["todayWords"] == 4
        assert "+4 / 500 today" in app._status_text
    files = list((tmp_path / "state" / "stats").glob("*.json"))
    assert [f.name for f in files] == [writing_stats.project_id(p.root) + ".json"]


async def test_opening_scene_counts_nothing_and_stats_screen(tmp_path: Path):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.stats.summary()["today"]["words"] == 0
        app.open_stats()
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen)
        assert "Streak" in app.screen._text and "Last 30 days" in app.screen._text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, StatsScreen)


async def test_accepting_a_draft_is_ai_words(tmp_path: Path):
    p = _project(tmp_path)
    path = p.manuscript_dir / "01-opening.md"
    path.write_text("# Opening\n\nalpha beta gamma\n<!--ai-->six new words from the model ok<!--/ai-->\n")
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        text = app.editor.text
        offset = text.index("six")
        app.editor.move_cursor(app.editor.document.get_location_from_index(offset))
        app.action_accept_draft()
        await pilot.pause()
        app.save_current()
        s = app.stats.summary()
        assert s["today"]["aiWords"] == 7 and s["today"]["words"] == 0


async def test_daily_target_is_saved_from_settings(tmp_path: Path):
    from lorewrite.tui.settingscreen import SettingsScreen
    app = LorewriteApp(_project(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SettingsScreen(app.project))
        await pilot.pause()
        field = app.screen.query_one("#daily-target", Input)
        assert field.value == "500"
        field.value = "1200"
        app.screen._save()
    assert writing_stats.get_target() == 1200


def test_palette_lists_session_stats():
    assert any(a[0] == "Session stats" for a in ActionProvider.ACTIONS)


async def test_focus_sprint_counts_down_ends_and_is_recorded(tmp_path: Path):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        now = [app.stats._clock()]
        app.stats._clock = lambda: now[0]
        app._start_sprint(25, writer=True)
        await pilot.pause()
        assert app._writer_mode and app.stats.sprint is not None
        assert "SPRINT 25:00" in app._status_text
        app.editor.insert("four fresh words here\n", app.editor.document.end)
        await pilot.pause()
        app.save_current()
        now[0] += 600
        app._sprint_tick()
        assert "SPRINT 15:00 (+4)" in app._status_text
        now[0] += 900
        app._sprint_tick()                     # time is up
        await pilot.pause()
        assert app.stats.sprint is None and not app._writer_mode
        rec = app.stats.summary()["sprints"][0]
        assert rec["words"] == 4 and rec["completed"] and rec["minutes"] == 25
        assert "SPRINT" not in app._status_text


async def test_focus_sprint_can_be_stopped_early(tmp_path: Path):
    app = LorewriteApp(_project(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._start_sprint(15, writer=False)
        assert not app._writer_mode
        app.focus_sprint()                    # running: offers to stop
        await pilot.pause()
        from lorewrite.tui.structurescreens import ChoiceScreen
        assert isinstance(app.screen, ChoiceScreen)
        app.screen.dismiss("stop")
        await pilot.pause()
        assert app.stats.sprint is None
        assert app.stats.summary()["sprints"][0]["completed"] is False


def test_palette_lists_focus_sprint():
    assert any(a[0] == "Focus sprint" for a in ActionProvider.ACTIONS)
