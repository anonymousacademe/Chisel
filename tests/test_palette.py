"""The command palette must show its results inside the window."""

from pathlib import Path

from textual.command import CommandList, CommandPalette

from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp


def _visible_rows(app, palette) -> tuple:
    results = palette.query_one(CommandList)
    screen_region = app.screen.region
    return results, screen_region


async def test_palette_results_are_on_screen_for_menu_and_query(tmp_path: Path):
    proj = Project.create(tmp_path / "novel", title="Palette")
    proj.create_entity("Borin")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause(0.5)
        assert isinstance(app.screen, CommandPalette)
        for query in ("", "scene"):
            if query:
                await pilot.press(*query)
            await pilot.pause(1.0)
            results = app.screen.query_one(CommandList)
            region = results.region
            screen = app.screen.region
            assert results.display
            assert region.height >= 1, region
            assert screen.contains_region(region), (region, screen)
            assert results.option_count >= 1
            # at least one option row is actually laid out inside the region
            assert results.virtual_size.height >= 1
            assert region.y + 1 <= screen.bottom


async def test_palette_input_row_is_not_stretched(tmp_path: Path):
    proj = Project.create(tmp_path / "novel", title="Palette")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause(0.5)
        from textual.containers import Horizontal

        rows = list(app.screen.query(Horizontal))
        assert rows, "palette layout changed; adjust this test"
        assert all(r.region.height <= 5 for r in rows), [r.region for r in rows]
