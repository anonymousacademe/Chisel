"""Collections in the terminal app (Wave 3.1)."""

from pathlib import Path

from textual.widgets import Input, ListView

from lorewrite.core import collections as coll
from lorewrite.core import scenemeta
from lorewrite.core.project import Project
from lorewrite.tui.app import ConfirmScreen, LorewriteApp, NamePrompt
from lorewrite.tui.collectionscreens import CollectionsScreen
from lorewrite.tui.commands import ActionProvider


def _project(tmp_path: Path) -> tuple[Project, Path, Path]:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").unlink()
    a = p.manuscript_dir / "01-rain.md"
    a.write_text("# Rain\n\nthe rain fell\n")
    b = p.manuscript_dir / "02-wind.md"
    b.write_text("# Wind\n\nthe wind rose\n")
    return p, a, b


def test_palette_lists_collections_under_scene():
    assert "open_collections" in {m for _, m, _ in ActionProvider.ACTIONS}
    assert ActionProvider.CATEGORY["open_collections"] == "Scene"


async def test_new_tick_rename_delete(tmp_path: Path):
    p, a, b = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(a)
        await pilot.pause()
        app.open_collections()
        await pilot.pause()
        assert isinstance(app.screen, CollectionsScreen)
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, NamePrompt)
        app.screen.query_one(Input).value = "Mara's arc"
        await pilot.press("enter")
        await pilot.pause()
        assert [c.name for c in coll.list_collections(p)] == ["Mara's arc"]
        assert isinstance(app.screen, CollectionsScreen)

        await pilot.press("space")                      # tick for the open scene
        await pilot.pause()
        assert scenemeta.details(a.read_text())["collections"] == ["Mara's arc"]
        assert "collections: [Mara's arc]" in app.editor.text
        await pilot.press("c")                           # recolour: violet -> amber
        await pilot.pause()
        assert coll.list_collections(p)[0].color == "amber"

        await pilot.press("r")
        await pilot.pause()
        app.screen.query_one(Input).value = "Arc"
        await pilot.press("enter")
        await pilot.pause()
        assert scenemeta.details(a.read_text())["collections"] == ["Arc"]
        assert "collections: [Arc]" in app.editor.text    # the open buffer followed the rename

        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        assert coll.list_collections(p) == []
        assert a.read_text().startswith("# Rain")
        assert app.editor.text.startswith("# Rain")


async def test_sidebar_hash_filter_lists_members_only(tmp_path: Path):
    p, a, b = _project(tmp_path)
    coll.create(p, "Needs continuity pass", "amber")
    coll.toggle(p, b, "Needs continuity pass")
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app.sidebar
        sidebar.query_one("#filter", Input).value = "#continuity"
        await pilot.pause()
        assert sidebar._scene_paths == [b]
        assert sidebar._entity_paths == []
        sidebar.query_one("#filter", Input).value = "#nothing"
        await pilot.pause()
        assert sidebar._scene_paths == []
        sidebar.query_one("#filter", Input).value = ""
        await pilot.pause()
        assert sidebar._scene_paths == [a, b]
