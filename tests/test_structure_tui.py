"""Parts, Unplaced, Trash and scene details in the terminal app (Wave 1)."""

from pathlib import Path

from textual.widgets import Button, Input, ListView

from chisel.core import scenemeta
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.commands import ActionProvider, SceneProvider
from chisel.tui.structurescreens import ChoiceScreen, DetailsScreen, TrashScreen


def _mk(path: Path, title: str, body: str = "Prose here.") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n")
    return path


def _book(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").unlink()
    m = p.manuscript_dir
    _mk(m / "00-front-matter" / "01-title.md", "Title Page", "front " * 7)
    _mk(m / "01-the-recall" / "01-a.md", "Alpha", "alpha " * 10)
    _mk(m / "01-the-recall" / "02-b.md", "Beta", "beta " * 10)
    _mk(m / "02-ghost-frequency" / "01-c.md", "Gamma", "gamma " * 10)
    return p


def _labels(app) -> list[str]:
    lv = app.query_one("#scenes", ListView)
    return [str(item.children[0].render()) for item in lv.children]


async def test_sidebar_groups_scenes_under_part_headers(tmp_path: Path):
    app = ChiselApp(_book(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert _labels(app) == [
            "FRONT MATTER", "Title Page", "THE RECALL", "Alpha", "Beta",
            "GHOST FREQUENCY", "Gamma"]
        # picking a header opens nothing
        lv = app.query_one("#scenes", ListView)
        before = app.current_path
        lv.index = 0
        lv.action_select_cursor()
        await pilot.pause()
        assert app.current_path == before
        # front matter is not counted as the book
        assert app._project_words == 36   # 3 book scenes x 12 words; front matter excluded
        # filter keeps matching scenes and the header above them
        app.query_one("#filter", Input).value = "gamma"
        await pilot.pause()
        assert _labels(app) == ["GHOST FREQUENCY", "Gamma"]


async def test_flat_projects_look_exactly_as_before(tmp_path: Path):
    p = Project.create(tmp_path / "flat", "Flat")
    (p.manuscript_dir / "02-second.md").write_text("# Second\n\nTwo.\n")
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert _labels(app) == ["Opening", "Second"]


async def test_new_scene_lands_in_the_open_scenes_part(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(p.manuscript_dir / "02-ghost-frequency" / "01-c.md")
        app.create_scene_prompt()
        await pilot.pause()
        app.screen.query_one(Input).value = "Delta"
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_path == p.manuscript_dir / "02-ghost-frequency" / "02-delta.md"


async def test_new_part_and_move_scene_to_it_and_unplace(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.new_part_prompt()
        await pilot.pause()
        app.screen.query_one(Input).value = "The Long Dark"
        await pilot.press("enter")
        await pilot.pause()
        assert (p.manuscript_dir / "03-the-long-dark").is_dir()
        app.open_file(p.manuscript_dir / "01-the-recall" / "02-b.md")
        app.move_scene_to_part_prompt()
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        # options: front matter, recall, ghost, long dark, top level
        lv = app.screen.query_one(ListView)
        lv.index = 3
        lv.action_select_cursor()
        await pilot.pause()
        moved = p.manuscript_dir / "03-the-long-dark" / "01-b.md"
        assert moved.is_file() and app.current_path == moved
        app.unplace_scene_action()
        await pilot.pause()
        assert app.current_path.parent == p.unplaced_dir
        assert _labels(app)[-2:] == ["UNPLACED SCENES", "Beta"]


async def test_delete_goes_to_trash_and_restores(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        target = p.manuscript_dir / "01-the-recall" / "02-b.md"
        app.open_file(target)
        app.delete_scene_confirm()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert not target.exists()
        assert len(p.list_trash()) == 1
        app.open_trash()
        await pilot.pause()
        assert isinstance(app.screen, TrashScreen)
        await pilot.press("r")
        await pilot.pause()
        assert (p.manuscript_dir / "01-the-recall" / "02-b.md").is_file()
        assert p.list_trash() == []
        await pilot.press("escape")  # the reopened (now empty) trash
        await pilot.pause()


async def test_trash_delete_forever_asks_first(tmp_path: Path):
    p = _book(tmp_path)
    p.delete_scene(p.manuscript_dir / "01-the-recall" / "01-a.md")
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_trash()
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("n")     # decline
        await pilot.pause()
        assert len(p.list_trash()) == 1
        assert isinstance(app.screen, TrashScreen)
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert p.list_trash() == []


async def test_edit_details_writes_frontmatter_and_fades_it(tmp_path: Path):
    p = _book(tmp_path)
    p.create_entity("Mara Vale", "character")
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        scene = p.manuscript_dir / "01-the-recall" / "01-a.md"
        original = scene.read_text()
        app.open_file(scene)
        app.edit_details()
        await pilot.pause()
        assert isinstance(app.screen, DetailsScreen)
        app.screen.query_one("#detail-pov", Input).value = "Mara Vale"
        app.screen.query_one("#detail-status", Input).value = "revising"
        app.screen.query_one("#detail-target", Input).value = "2,400"
        app.screen.action_save()
        await pilot.pause()
        text = scene.read_text()
        assert text.startswith("---\npov: Mara Vale\nstatus: revising\ntarget: 2400\n---\n# Alpha")
        assert scenemeta.details(app.editor.text)["target"] == 2400
        # the block is faded (marker spans on rows 0..4), not scanned for names
        assert 0 in app.editor._spans and app.editor._spans[0][0][2] == "marker"
        # word count ignores it
        assert app._project_words == 36
        # clearing everything removes the block again
        app.edit_details()
        await pilot.pause()
        for key in ("pov", "place", "purpose", "status", "target"):
            app.screen.query_one(f"#detail-{key}", Input).value = ""
        app.screen.action_save()
        await pilot.pause()
        assert scene.read_text() == original


async def test_details_rejects_a_non_numeric_target(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(p.manuscript_dir / "01-the-recall" / "01-a.md")
        app.edit_details()
        await pilot.pause()
        app.screen.query_one("#detail-target", Input).value = "lots"
        app.screen.action_save()
        await pilot.pause()
        assert isinstance(app.screen, DetailsScreen)     # still open
        app.screen.action_cancel()


async def test_move_part_keeps_the_open_scene_open(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(p.manuscript_dir / "01-the-recall" / "01-a.md")
        app.move_part_down()
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        assert app.screen.query_one("#choice-list", ListView).index == 1   # the open scene's part
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_path == p.manuscript_dir / "02-the-recall" / "01-a.md"
        assert app.current_path.is_file()
        assert [p.part_title(x) for x in p.list_parts()] == [
            "Front Matter", "Ghost Frequency", "The Recall"]


async def test_delete_empty_part_asks_which_part_with_a_part_scene_open(tmp_path: Path):
    p = _book(tmp_path)
    empty = p.new_part("Epilogue")
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(p.manuscript_dir / "01-the-recall" / "01-a.md")
        app.delete_part_confirm()
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        lv = app.screen.query_one("#choice-list", ListView)
        assert lv.index == 1                      # defaults to the open scene's part
        lv.index = len(p.list_parts()) - 1        # but any part can be picked
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")                # confirm the delete
        await pilot.pause()
        assert not empty.exists()
        assert (p.manuscript_dir / "01-the-recall" / "01-a.md").is_file()


async def test_chapter_unit_changes_palette_words_only(tmp_path: Path):
    p = _book(tmp_path)
    p.update_manuscript_settings(unit="chapter")
    app = ChiselApp(Project.open(p.root))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        scene_hits = [str(h.display) async for h in SceneProvider(app.screen).discover()]
        action_hits = [str(h.display) async for h in ActionProvider(app.screen).discover()]
    assert any(h.startswith("Chapter · Alpha") for h in scene_hits)
    assert any("New chapter" in h for h in action_hits)
    assert any(h.startswith("Chapter · Edit details") for h in action_hits)


async def test_unit_switch_label_names_the_switch(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hits = [str(h.display) async for h in ActionProvider(app.screen).discover()]
        assert "Action · Call them chapters" in hits
        app.toggle_unit()
        await pilot.pause()
        hits = [str(h.display) async for h in ActionProvider(app.screen).discover()]
        assert "Action · Call them scenes" in hits
        assert not any("Toggle" in h and "label" in h or "chapter/chapter" in h for h in hits)


async def test_details_form_sets_and_clears_story_time(tmp_path: Path):
    p = _book(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        scene = p.manuscript_dir / "01-the-recall" / "01-a.md"
        original = scene.read_text()
        app.open_file(scene)
        app.edit_details()
        await pilot.pause()
        app.screen.query_one("#detail-when", Input).value = "2187-03-14"
        app.screen.action_save()
        await pilot.pause()
        assert scenemeta.details(scene.read_text())["when"] == "2187-03-14"
        app.edit_details()
        await pilot.pause()
        assert app.screen.query_one("#detail-when", Input).value == "2187-03-14"
        app.screen.query_one("#detail-when", Input).value = ""
        app.screen.action_save()
        await pilot.pause()
        assert scene.read_text() == original
