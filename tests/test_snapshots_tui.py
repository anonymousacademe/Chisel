"""Snapshots in the terminal app (Wave 2.1)."""

from pathlib import Path

from textual.widgets import Input, ListView, Static

from chisel.core import drafts, snapshots
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.commands import ActionProvider
from chisel.tui.snapshotscreens import CompareScreen, LabelPrompt, SnapshotsScreen, unified


def _mk(path: Path, title: str, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n")
    return path


def _project(tmp_path: Path) -> tuple[Project, Path]:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").unlink()
    scene = _mk(p.manuscript_dir / "01-rain.md", "Rain", "the rain fell on the spur")
    _mk(p.manuscript_dir / "02-wind.md", "Wind", "the wind rose")
    return p, scene


def test_palette_lists_the_snapshot_actions():
    names = {m: t for t, m, _ in ActionProvider.ACTIONS}
    assert {"open_snapshots", "snapshot_scene_prompt", "snapshot_all_prompt"} <= set(names)
    assert ActionProvider.CATEGORY["open_snapshots"] == "Scene"


def test_unified_marks_removed_and_added_without_brackets():
    segs = snapshots.diff_words("the rain fell\n", "the rain poured\n")
    text = unified(segs)
    assert "fell" in text.plain and "poured" in text.plain
    styles = {str(s.style) for s in text.spans}
    assert "red strike" in styles and "green underline" in styles
    assert "[" not in text.plain


async def test_snapshot_scene_then_list_compare_restore(tmp_path: Path):
    p, scene = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.snapshot_scene_prompt()
        await pilot.pause()
        assert isinstance(app.screen, LabelPrompt)
        app.screen.query_one(Input).value = "first take"
        await pilot.press("enter")
        await pilot.pause()
        snaps = snapshots.list_snapshots(p, scene)
        assert [s.label for s in snaps] == ["first take"]
        assert "Snapshot just now" in app._status_text

        # edit the buffer, then compare
        app.editor.load_text("# Rain\n\nthe rain poured on the spur\n")
        await pilot.pause()
        app.open_snapshots()
        await pilot.pause()
        assert isinstance(app.screen, SnapshotsScreen)
        await pilot.press("enter")          # compare
        await pilot.pause()
        assert isinstance(app.screen, CompareScreen)
        header = app.screen.query_one("#compare-header").render().plain
        assert "first take" in header and snaps[0].name not in header
        assert snaps[0].when.strftime("%Y-%m-%d %H:%M") in header
        plain = app.screen.query_one("#compare-text", Static).render().plain
        assert "fell" in plain and "poured" in plain
        await pilot.press("r")              # restore from the compare view
        await pilot.pause()
        await pilot.press("y")              # confirm
        await pilot.pause()
        assert "the rain fell on the spur" in scene.read_text()
        assert app.editor.text == scene.read_text()
        labels = [s.label for s in snapshots.list_snapshots(p, scene)]
        assert "before-restore" in labels and "first take" in labels


async def test_delete_snapshot_asks_first(tmp_path: Path):
    p, scene = _project(tmp_path)
    snapshots.create(p, scene, "keep")
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.open_snapshots()
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("n")              # decline: back to the list
        await pilot.pause()
        assert len(snapshots.list_snapshots(p, scene)) == 1
        assert isinstance(app.screen, SnapshotsScreen)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert snapshots.list_snapshots(p, scene) == []


async def test_snapshot_all_scenes(tmp_path: Path):
    p, scene = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.snapshot_all_prompt()
        await pilot.pause()
        app.screen.query_one(Input).value = "milestone"
        await pilot.press("enter")
        await pilot.pause()
        for s in p.all_scene_files():
            assert [x.label for x in snapshots.list_snapshots(p, s)] == ["milestone"]


async def test_escape_cancels_the_label_prompt(tmp_path: Path):
    p, scene = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.snapshot_scene_prompt()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert snapshots.list_snapshots(p, scene) == []


async def test_first_save_of_the_day_takes_an_auto_snapshot(tmp_path: Path):
    snapshots._daily_done.clear()
    p, scene = _project(tmp_path)
    before = scene.read_text()
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.editor.load_text(before + "one more line\n")
        await pilot.pause()
        app.save_current()
        await pilot.pause()
        snaps = snapshots.list_snapshots(p, scene)
        assert [s.label for s in snaps] == ["auto"]
        assert snaps[0].path.read_text() == before


async def test_auto_snapshot_setting_off(tmp_path: Path):
    from chisel.core import settings as user_settings
    snapshots._daily_done.clear()
    user_settings.set("auto_snapshot", False)
    p, scene = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.editor.load_text("# Rain\n\nchanged\n")
        await pilot.pause()
        app.save_current()
        await pilot.pause()
        assert snapshots.list_snapshots(p, scene) == []


async def test_accept_all_drafts_snapshots_first(tmp_path: Path):
    p, scene = _project(tmp_path)
    text = '# Rain\n\nthe rain <!--ai-->poured<!--/ai--> down\n'
    scene.write_text(text)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.accept_all_drafts()
        await pilot.pause()
        snaps = snapshots.list_snapshots(p, scene)
        assert [s.label for s in snaps] == ["before-accept-all"]
        assert snaps[0].path.read_text() == text
        assert "<!--ai" not in app.editor.text


async def test_start_new_draft_confirms_snapshots_and_counts_up(tmp_path: Path):
    from textual.widgets import Label
    p, scene = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        assert "Draft 1" in app._status_text
        app.start_new_draft()
        await pilot.pause()
        await pilot.press("n")              # decline: nothing happens
        await pilot.pause()
        assert p.draft == 1 and snapshots.list_snapshots(p, scene) == []
        app.start_new_draft()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert p.draft == 2 and "Draft 2" in app._status_text
        for s in p.all_scene_files():
            assert [x.label for x in snapshots.list_snapshots(p, s)] == ["end-of-draft-1"]
        assert Project.open(p.root).draft == 2


def test_palette_has_start_new_draft():
    assert "start_new_draft" in {m for _, m, _ in ActionProvider.ACTIONS}


def test_word_deltas_use_one_form():
    from chisel.core.stats import signed
    from chisel.tui.snapshotscreens import delta_text
    assert [signed(n) for n in (0, 12, -5, 1240)] == ["\u00b10", "+12", "\u22125", "+1,240"]
    assert delta_text(0) == "\u00b10" and delta_text(-5) == "\u22125"
