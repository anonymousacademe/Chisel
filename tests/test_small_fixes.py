"""Follow-up fixes: help from the editor, launch hint width, version."""

import tomllib
from pathlib import Path

import chisel
from chisel.core.project import Project
from chisel.tui.app import HelpScreen, ChiselApp
from chisel.tui.launch import LaunchScreen


async def test_f1_opens_help_while_editor_is_focused(tmp_path: Path):
    proj = Project.create(tmp_path / "n", title="N")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.focused is app.editor
        before = app.editor.text
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("f1")               # f1 closes it again
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert app.editor.text == before
        # ? still types a character in the editor (it is prose)
        await pilot.press("question_mark")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert "?" in app.editor.text


async def test_help_text_and_footer_mention_f1(tmp_path: Path):
    from chisel.tui.app import HELP_TEXT
    from chisel.tui.tour import PAGES

    assert "f1" in HELP_TEXT and any("f1" in p for p in PAGES)
    proj = Project.create(tmp_path / "n", title="N")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        keys = {b.key: b for b in app.BINDINGS}
        assert keys["f1"].show


async def test_launch_hint_fits_at_80_and_100_columns(tmp_path: Path):
    for width in (80, 100):
        app = ChiselApp(None)
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause(0.5)
            assert isinstance(app.screen, LaunchScreen)
            hint = app.screen.query_one("#launch-hint")
            text = str(hint.render())
            assert "q: quit" in text
            # every line of the hint is fully inside its box, none clipped
            assert all(len(line) <= hint.size.width for line in text.splitlines())
            assert hint.size.height >= len(text.splitlines())


def test_pyproject_version_matches_package():
    root = Path(chisel.__file__).resolve().parents[2]
    data = tomllib.loads((root / "pyproject.toml").read_text())
    # the version has one source: __version__ (pyproject reads it as an attribute)
    assert "version" in data["project"]["dynamic"]
    assert data["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "chisel.__version__"}


async def test_help_lines_render_on_separate_rows(tmp_path: Path):
    from chisel.tui.app import HELP_TEXT

    proj = Project.create(tmp_path / "n", title="N")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause(0.5)
        help_widget = app.screen.query_one("#help")
        rows = [strip.text.strip() for strip in help_widget.render_lines(
            help_widget.region.reset_offset)]

        def row_of(fragment: str) -> int:
            hits = [i for i, r in enumerate(rows) if fragment in r]
            assert hits, (fragment, rows)
            return hits[0]

        # consecutive keybinding lines sit on different rows, in order
        assert row_of("new scene") < row_of("previous / next scene") \
            < row_of("command palette")
        assert row_of("new scene") != row_of("command palette")
        # no help line is merged with another
        assert not any("new scene" in r and "command palette" in r for r in rows)
        # headings are still their own, distinct rows
        assert row_of("Keybindings") < row_of("Also in the palette") < row_of("Links")
        for heading in ("Keybindings", "Also in the palette", "Links"):
            assert rows[row_of(heading)].strip("│ ").startswith(heading)
        # every non-empty help line is present somewhere
        for line in HELP_TEXT.splitlines():
            text = line.strip().removeprefix("# ")
            if text and len(text) < 50:
                assert text in " ".join(rows), text
