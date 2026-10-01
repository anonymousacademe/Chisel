"""Export in the terminal app (M7): palette entries and the form."""

import asyncio
from pathlib import Path

from textual.widgets import Checkbox, Select

from lorewrite.core import export as exporting
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.commands import ActionProvider
from lorewrite.tui.exportscreen import ExportScreen
from tests.export_helpers import make_structured


async def wait_for(pred, tries=100):
    for _ in range(tries):
        if pred():
            return True
        await asyncio.sleep(0.1)
    return False


def test_palette_has_the_export_actions(tmp_path: Path):
    titles = {t for t, m, _ in ActionProvider.ACTIONS}
    assert {"Export manuscript", "Open exports folder"} <= titles


async def test_export_form_writes_a_markdown_file(tmp_path: Path):
    project = make_structured(tmp_path / "p")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.export_manuscript()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ExportScreen)
        assert "4 scenes" in str(screen.query_one("#export-summary").render())
        screen.query_one("#export-format", Select).value = "md"
        screen.query_one("#export-drafts", Checkbox).value = True
        await pilot.pause()
        assert screen.query_one("#export-layout", Select).disabled  # PDF-only fields
        screen.action_export()
        assert await wait_for(lambda: any((tmp_path / "p" / "exports").glob("*.md")))
        await pilot.pause()
    out = next((tmp_path / "p" / "exports").glob("*.md")).read_text()
    assert "A grand rewritten sentence." in out  # include drafts was ticked
    assert exporting.load_options(type(project).open(tmp_path / "p")).include_drafts is True


async def test_form_cancel_and_unavailable_format(tmp_path: Path, monkeypatch):
    from lorewrite.core.export import pandoc
    monkeypatch.setattr(pandoc, "find", lambda: None)
    project = make_structured(tmp_path / "p")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.export_manuscript()
        await pilot.pause()
        screen = app.screen
        screen.query_one("#export-format", Select).value = "docx"
        screen.action_export()
        await pilot.pause()
        assert app.screen is screen  # refused: "install pandoc"
        screen.action_cancel()
        await pilot.pause()
        assert not isinstance(app.screen, ExportScreen)
    assert not (tmp_path / "p" / "exports").exists()


async def test_open_exports_folder_opens_only_on_request(tmp_path: Path, monkeypatch):
    seen = []
    monkeypatch.setattr(exporting, "open_in_desktop", seen.append)
    project = make_structured(tmp_path / "p")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert seen == []
        app.open_exports_folder()
        await pilot.pause()
    assert seen == [tmp_path / "p" / "exports"]
