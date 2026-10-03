"""Comments in the terminal app (Wave 3.2)."""

from pathlib import Path

from textual.widgets.text_area import Selection

from chisel.core import comments as cm
from chisel.core.project import Project
from chisel.tui.app import ConfirmScreen, ChiselApp, NamePrompt
from chisel.tui.commands import ActionProvider
from chisel.tui.commentscreens import CommentsScreen

BODY = "the rain fell on the spur and the market held its breath"


def _project(tmp_path: Path) -> tuple[Project, Path]:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").unlink()
    scene = p.manuscript_dir / "01-rain.md"
    scene.write_text(f"# Rain\n\n{BODY}.\n")
    return p, scene


def test_palette_lists_the_comment_actions():
    methods = {m for _, m, _ in ActionProvider.ACTIONS}
    assert {"add_comment_prompt", "open_comments"} <= methods
    assert ActionProvider.CATEGORY["add_comment_prompt"] == "Scene"


async def test_add_underline_list_resolve_edit_delete(tmp_path: Path):
    p, scene = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()

        app.add_comment_prompt()                 # nothing selected: refused, no prompt
        await pilot.pause()
        assert not isinstance(app.screen, NamePrompt)

        app.editor.selection = Selection((2, 4), (2, 13))      # "rain fell"
        app.add_comment_prompt()
        await pilot.pause()
        assert isinstance(app.screen, NamePrompt)
        app.screen.query_one("Input").value = "too soft?"
        await pilot.press("enter")
        await pilot.pause()
        (c,) = cm.load(p.root, scene)
        assert c.quote == "rain fell" and c.body == "too soft?"
        assert scene.read_text() == f"# Rain\n\n{BODY}.\n"           # prose untouched
        assert app.editor._comments == {2: [(4, 13)]}                # faint underline

        # typing before it moves the underline with the text
        app.editor.move_cursor((2, 0))
        app.editor.insert("Then ")
        await pilot.pause()
        assert app.editor._comments == {2: [(9, 18)]}

        app.open_comments()
        await pilot.pause()
        assert isinstance(app.screen, CommentsScreen)
        await pilot.press("r")                    # resolve: underline goes
        await pilot.pause()
        assert cm.load(p.root, scene)[0].resolved is True
        assert isinstance(app.screen, CommentsScreen)
        await pilot.press("r")                    # reopen
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, NamePrompt)
        assert app.screen.query_one("Input").value == "too soft?"
        app.screen.query_one("Input").value = "too soft"
        await pilot.press("enter")
        await pilot.pause()
        assert cm.load(p.root, scene)[0].body == "too soft"
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        assert cm.load(p.root, scene) == []
        await pilot.press("escape")
        await pilot.pause()
        assert app.editor._comments == {}


async def test_jump_selects_the_passage_and_saving_refreshes_anchors(tmp_path: Path):
    p, scene = _project(tmp_path)
    c = cm.add(p.root, scene, scene.read_text(), *(lambda t: (t.index("market"), t.index("market") + 6))(scene.read_text()), "x")
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.open_comments()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.editor.selected_text == "market"
        app.editor.move_cursor((2, 0))
        app.editor.insert("Meanwhile ")
        app.save_current()
        (stored,) = cm.load(p.root, scene)
        assert stored.id == c.id and stored.prefix.startswith("while the rain")      # anchor refreshed on save
