"""Headless smoke tests for the TUI using Textual Pilot."""

from pathlib import Path

import pytest
from textual.widgets import ListView, Markdown

from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp


@pytest.fixture
def project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="Smoke Novel")
    proj.create_entity("Elara Vance")
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text("# The Tavern\n\n[[Elara Vance]] entered.\n", encoding="utf-8")
    return proj


async def test_app_mounts_and_lists_project(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        scenes = app.query_one("#scenes", ListView)
        assert len(scenes.children) == 2
        entities = app.query_one("#entities", ListView)
        assert len(entities.children) == 1
        # first scene opened in editor
        assert "[[New Character]]" in app.editor.text


async def test_jump_to_existing_entity(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.manuscript_dir / "02-tavern.md")
        # place cursor inside [[Elara Vance]] (line 2, inside the brackets)
        app.editor.move_cursor((2, 5))
        await pilot.pause()
        app.action_jump()
        await pilot.pause()
        assert app.current_path is not None
        assert app.current_path.name == "elara-vance.md"
        assert "name: Elara Vance" in app.editor.text


async def test_jump_to_unresolved_link_creates_entity(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # cursor inside [[New Character]] in the sample scene (line 3)
        app.editor.move_cursor((3, 10))
        await pilot.pause()
        app.action_jump()
        await pilot.pause()
        # entity-type modal is up; choose "Character"
        await pilot.click("#character")
        await pilot.pause()
        assert app.current_path is not None
        assert app.current_path.name == "new-character.md"
        assert (project.entities_dir / "characters" / "new-character.md").is_file()


async def test_autosave_and_backlinks(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.manuscript_dir / "02-tavern.md")
        app.editor.move_cursor((2, 5))  # inside [[Elara Vance]]
        await pilot.pause()
        app.update_panel_for_cursor()
        await pilot.pause()
        body = app.query_one("#entity-body", Markdown)
        assert body is not None
        backlinks = app.query_one("#backlinks", ListView)
        # Elara is linked once from 02-tavern.md
        assert len(backlinks.children) == 1
        # autosave wrote the file
        await pilot.pause(1.0)
        assert "Elara Vance" in (project.manuscript_dir / "02-tavern.md").read_text()


async def test_link_highlighting_styles(project: Project):
    """Resolved links render with the resolved link style (underline).

    Locks in the private-API rendering hook: if Textual internals change,
    this should fail loudly rather than silently lose highlighting.
    Works with any active theme by comparing against the editor's style.
    """
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.manuscript_dir / "02-tavern.md")
        await pilot.pause()
        strip = app.editor.render_line(2)  # real cached render path
        underlined_colors = {
            seg.style.color.get_truecolor()
            for seg in strip
            if seg.style and seg.style.underline and seg.style.color
        }
        expected = app.editor.resolved_style.color.get_truecolor()
        assert expected in underlined_colors, (expected, underlined_colors)


async def test_ctrl_s_saves_and_status_bar(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.manuscript_dir / "02-tavern.md")
        app.editor.move_cursor((3, 0))
        await pilot.press("H", "i", " ")
        await pilot.pause()
        assert app._dirty
        status = app._status_text
        assert "modified" in status
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not app._dirty
        assert "Hi " in (project.manuscript_dir / "02-tavern.md").read_text()
        status = app._status_text
        assert "saved" in status
        assert "words" in status and "Ln" in status


async def test_teardown_with_pending_autosave_does_not_crash(project: Project):
    """Regression: autosave timer fired during teardown raised NoMatches."""
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.manuscript_dir / "02-tavern.md")
        app.editor.move_cursor((3, 0))
        await pilot.press("X")  # schedule autosave, exit before it fires
    # run_test re-raises app exceptions; reaching here means teardown was clean
    assert "X" in (project.manuscript_dir / "02-tavern.md").read_text()


async def test_status_bar_link_hint(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.manuscript_dir / "02-tavern.md")
        app.editor.move_cursor((2, 5))  # inside [[Elara Vance]]
        await pilot.pause()
        status = app._status_text
        assert "ctrl+j" in status
        assert "Elara Vance" in status


# -- no brackets needed: plain mentions -----------------------------------------------


async def test_select_name_and_ctrl_j_creates_note_then_mentions_resolve(tmp_path: Path):
    proj = Project.create(tmp_path / "plain", title="Plain")
    scene = proj.manuscript_dir / "02-road.md"
    scene.write_text("# Road\n\nBorin drank.\n", encoding="utf-8")
    earlier = proj.manuscript_dir / "03-inn.md"
    earlier.write_text("# Inn\n\nLater, Borin slept.\n", encoding="utf-8")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.editor.selection = ((2, 0), (2, 5))  # "Borin"
        await pilot.pause()
        app.action_jump()
        await pilot.pause()
        await pilot.click("#character")
        await pilot.pause()
        assert app.current_path.name == "borin.md"
        # scene text untouched: no brackets were added
        assert scene.read_text(encoding="utf-8") == "# Road\n\nBorin drank.\n"
        borin = next(e for e in app.entities if e.name == "Borin")
        # both scenes now count, including one never opened
        sources = {b.source for b in app.idx.backlinks(borin)}
        assert sources == {"manuscript/02-road.md", "manuscript/03-inn.md"}
        # ctrl+j on a plain mention opens the note
        app.open_file(earlier)
        app.editor.move_cursor((2, 9))
        await pilot.pause()
        assert "Borin — ctrl+j to open" in app._status_text
        app.action_jump()
        await pilot.pause()
        assert app.current_path.name == "borin.md"


async def test_mentions_colored_and_brackets_faded(project: Project):
    scene = project.manuscript_dir / "02-tavern.md"
    scene.write_text("# The Tavern\n\nElara Vance sat. [[Elara Vance]] rose.\n",
                     encoding="utf-8")
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        strip = app.editor.render_line(2)
        mention_color = app.editor.mention_style.color.get_truecolor()
        plain_mention = [s for s in strip if s.text.strip() == "Elara Vance"
                         and s.style and not s.style.underline]
        assert plain_mention and all(
            s.style.color.get_truecolor() == mention_color for s in plain_mention)
        brackets = [s for s in strip if s.text in ("[[", "]]")]
        faded = app.editor.bracket_style
        assert brackets and all(
            s.style and (s.style.dim if faded.color is None else
                         s.style.color == faded.color) for s in brackets)


async def test_entity_notes_do_not_highlight_plain_names(project: Project):
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        note = project.entities_dir / "characters" / "elara-vance.md"
        app.open_file(note)
        await pilot.pause()
        assert app.editor.mention_names == []
        app.open_file(project.manuscript_dir / "02-tavern.md")
        await pilot.pause()
        assert "Elara Vance" in app.editor.mention_names
