"""The terminal app's own footer bindings use the project's unit word (scene in story and script, section in research)."""

import pytest

from chisel.core.project import Project
from chisel.tui.app import ChiselApp


def descriptions(app) -> dict[str, str]:
    return {b.action: b.description for items in app._bindings.key_to_bindings.values() for b in items}


@pytest.mark.parametrize("mode, word", [("story", "scene"), ("script", "scene"), ("research", "section")])
async def test_footer_bindings_follow_the_unit(tmp_path, mode, word):
    project = Project.create(tmp_path / "p", "P", mode)
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        d = descriptions(app)
        assert d["new_scene"] == f"New {word}"
        assert d["previous_scene"] == f"Prev {word}"
        assert d["next_scene"] == f"Next {word}"


async def test_toggling_the_unit_updates_the_footer(tmp_path):
    project = Project.create(tmp_path / "p", "P", "research")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert descriptions(app)["new_scene"] == "New section"
        app.toggle_unit()                       # section -> chapter
        await pilot.pause()
        assert descriptions(app)["new_scene"] == "New chapter"
