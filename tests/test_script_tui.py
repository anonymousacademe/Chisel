"""Script mode in the terminal app: the export form, the import command, the palette and spell checking."""

import asyncio
from pathlib import Path

from textual.widgets import Checkbox, Select

from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.commands import ActionProvider
from chisel.tui.dialogs import NamePrompt
from chisel.tui.exportscreen import ExportScreen
from tests.test_script_export import make_script


async def wait_for(pred, tries=100):
    for _ in range(tries):
        if pred():
            return True
        await asyncio.sleep(0.1)
    return False


def entries(app):
    return [title for _cat, title, _fn, _help in ActionProvider(app.screen)._entries()]


async def test_palette_offers_import_only_to_scripts(tmp_path: Path):
    script = ChiselApp(make_script(tmp_path / "s"))
    async with script.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "Import Fountain file" in entries(script)
    story = ChiselApp(Project.create(tmp_path / "n", "Novel"))
    async with story.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "Import Fountain file" not in entries(story)


async def test_export_form_for_a_script_has_no_chapter_options(tmp_path: Path):
    app = ChiselApp(make_script(tmp_path / "s"))
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.export_manuscript()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ExportScreen)
        assert not screen.query("#export-numbering") and not screen.query("#export-toc")
        assert not screen.query("#export-continuous")
        values = {value for _label, value in screen.query_one("#export-format", Select)._options if value != Select.BLANK}
        assert values == {"pdf", "fountain"}
        screen.query_one("#export-format", Select).value = "fountain"
        screen.query_one("#export-front", Checkbox).value = True
        await pilot.pause()
        screen.action_export()
        assert await wait_for(lambda: any((tmp_path / "s" / "exports").glob("*.fountain")))
        await pilot.pause()
    out = next((tmp_path / "s" / "exports").glob("*.fountain")).read_text(encoding="utf-8")
    assert out.startswith("Title: The Toast") and "INT. KITCHEN - DAY" in out


async def test_import_command_adds_the_scenes(tmp_path: Path):
    src = tmp_path / "in.fountain"
    src.write_text("INT. OFFICE - NIGHT\n\nPhone rings.\n\nEXT. STREET - DAY\n\nRain.\n", encoding="utf-8")
    project = make_script(tmp_path / "s")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.import_fountain_prompt()
        await pilot.pause()
        prompt = app.screen
        assert isinstance(prompt, NamePrompt)
        prompt.query_one("Input").value = f'"{src}"'            # a path pasted with quotes
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, NamePrompt)
    titles = [project.scene_title(p) for p in Project.open(tmp_path / "s").list_scenes()]
    assert titles[-2:] == ["INT. OFFICE - NIGHT", "EXT. STREET - DAY"]


async def test_import_command_reports_a_bad_file_and_refuses_stories(tmp_path: Path):
    app = ChiselApp(make_script(tmp_path / "s"))
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.import_fountain_prompt()
        await pilot.pause()
        app.screen.query_one("Input").value = str(tmp_path / "missing.fountain")
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, NamePrompt)           # the prompt closed; the error was a notification
    story = ChiselApp(Project.create(tmp_path / "n", "Novel"))
    async with story.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        story.import_fountain_prompt()
        await pilot.pause()
        assert not isinstance(story.screen, NamePrompt)         # refused without asking for a file


async def test_spell_check_skips_non_prose_in_a_script(tmp_path: Path):
    app = ChiselApp(make_script(tmp_path / "s"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        text = "# T\n\nINT. KITCHN - DAY\n\nKeith recieve it.\n\nZORBLAX\nHello.\n\nSMASH TOO:\n"
        words = [text[m.start:m.end] for m in __import__("chisel.core.spelling", fromlist=["x"]).check(
            app._spell_text(text), app._accepted())]
        assert words == ["recieve"]


async def test_ctrl_g_in_a_script_asks_for_fountain_and_starts_a_block(tmp_path: Path, monkeypatch):
    import chisel.tui.app as app_mod
    from chisel.ai.writing import SCRIPT_SYSTEM_PROMPT
    from chisel.core import drafts
    from chisel.tui.promptscreen import PromptScreen

    calls = []

    def fake(mode, instruction, context, model, client=None, selection=None, **kw):
        calls.append(kw)
        return "BOB\nHello there."

    monkeypatch.setattr(app_mod, "generate", fake)
    project = make_script(tmp_path / "s")
    scene = project.list_scenes()[0]
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.editor.move_cursor((app.editor.document.line_count - 1, 0))
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        await pilot.press(*"bob arrives")
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
        assert len(calls) == 1 and calls[0]["script"] is True
        (pending,) = drafts.find_pending(app.editor.text)
        body = app.editor.text[pending.body_start:pending.body_end]
        assert body.rstrip("\n").endswith("BOB\nHello there.")
        assert SCRIPT_SYSTEM_PROMPT.startswith("You are a ghostwriter helping a screenwriter")
