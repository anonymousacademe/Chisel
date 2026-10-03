"""Rename everywhere in the terminal app: form, ticked preview, apply, undo."""

from pathlib import Path

from textual.widgets import Input, ListView

from chisel.core import entities as ent
from chisel.core import snapshots
from chisel.core.project import Project
from chisel.tui.commands import ActionProvider
from chisel.tui.renamescreens import RenameFormScreen, RenamePreviewScreen


def _project(tmp_path: Path):
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").unlink()
    a = p.manuscript_dir / "01-a.md"
    a.write_text("# A\n\nMara ran. Will you stay? Mara hid.\n", encoding="utf-8")
    b = p.manuscript_dir / "02-b.md"
    b.write_text("# B\n\nNothing here.\n", encoding="utf-8")
    e, _ = p.create_entity("Mara", "character")
    return p, a, b


def test_palette_entries_are_entity_actions():
    methods = {m for _, m, _ in ActionProvider.ACTIONS}
    assert {"rename_entity_prompt", "rename_undo_action"} <= methods
    assert ActionProvider.CATEGORY["rename_entity_prompt"] == "Entity"


async def test_rename_flow_untick_apply_undo(tmp_path: Path):
    from chisel.tui.app import ChiselApp

    snapshots._daily_done.clear()
    p, a, b = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(p.entities_dir / "characters" / "mara.md")  # the open note is the target
        await pilot.pause()
        app.rename_entity_prompt()
        await pilot.pause()
        assert isinstance(app.screen, RenameFormScreen)
        app.screen.query_one("#rename-name", Input).value = "Nia"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RenamePreviewScreen)
        assert a.read_text(encoding="utf-8").startswith("# A\n\nMara ran")  # nothing yet
        lv = app.screen.query_one("#rp-list", ListView)
        assert len(lv.children) == 2
        await pilot.press("down")
        await pilot.press("space")        # untick the second one
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert a.read_text(encoding="utf-8") == "# A\n\nNia ran. Will you stay? Mara hid.\n"
        assert (p.entities_dir / "characters" / "nia.md").exists()
        assert app.current_path == p.entities_dir / "characters" / "nia.md"  # followed the note
        assert [s.label for s in snapshots.list_snapshots(p, a)] == ["before-rename"]

        app.rename_undo_action()
        await pilot.pause()
        assert a.read_text(encoding="utf-8") == "# A\n\nMara ran. Will you stay? Mara hid.\n"
        assert (p.entities_dir / "characters" / "mara.md").exists()
        assert app.current_path == p.entities_dir / "characters" / "mara.md"
        assert ent.load_entity(app.current_path).name == "Mara"


async def test_cancel_changes_nothing(tmp_path: Path):
    from chisel.tui.app import ChiselApp

    p, a, b = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(p.entities_dir / "characters" / "mara.md")
        await pilot.pause()
        app.rename_entity_prompt()
        await pilot.pause()
        app.screen.query_one("#rename-name", Input).value = "Nia"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert (p.entities_dir / "characters" / "mara.md").exists()
        assert not (p.entities_dir / "characters" / "nia.md").exists()
        assert a.read_text(encoding="utf-8").count("Mara") == 2
