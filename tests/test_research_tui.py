"""Research notes and the assistant window in the terminal app (Wave 3.3). AI is mocked."""

from pathlib import Path

from textual.widgets import Input, Static

from lorewrite.core import research as rs
from lorewrite.core.project import Project
from lorewrite.tui import app as app_module
from lorewrite.tui.app import ConfirmScreen, LorewriteApp, NamePrompt
from lorewrite.tui.assistantscreen import AssistantScreen
from lorewrite.tui.commands import ActionProvider, ResearchProvider
from lorewrite.tui.structurescreens import ChoiceScreen


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").write_text("# Rain\n\nthe rain fell on the spur\n")
    return p


def _texts(screen) -> str:
    return "\n".join(str(s.render()) for s in screen.query("#as-log Static"))


def test_palette_lists_the_research_actions_and_provider():
    methods = {m for _, m, _ in ActionProvider.ACTIONS}
    assert {"new_research_note_prompt", "new_research_from_link_prompt", "delete_research_note_confirm",
            "open_assistant", "open_research_question"} <= methods
    assert ResearchProvider.__name__ in {c.__name__ for c in LorewriteApp.COMMANDS}


async def test_new_note_link_open_and_delete(tmp_path: Path):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.new_research_note_prompt()
        await pilot.pause()
        assert isinstance(app.screen, NamePrompt)
        app.screen.query_one(Input).value = "Tide almanac"
        await pilot.press("enter")
        await pilot.pause()
        note = p.root / "research" / "tide-almanac.md"
        assert note.read_text() == "# Tide almanac\n\n" and app.current_path == note

        app.new_research_from_link_prompt()
        await pilot.pause()
        app.screen.query_one(Input).value = "not a link"
        await pilot.press("enter")
        await pilot.pause()
        assert len(rs.list_notes(p)) == 1                       # refused with a warning
        app.new_research_from_link_prompt()
        await pilot.pause()
        app.screen.query_one(Input).value = "https://example.org/trams/timetable"
        await pilot.press("enter")
        await pilot.pause()
        assert [n.title for n in rs.list_notes(p)] == ["example.org - timetable", "Tide almanac"]

        # editing and saving a research note never reaches the link index
        app.editor.insert("[[Mara]] floods at dusk")
        app.save_current()
        rel = str(app.current_path.relative_to(p.root))
        assert app.idx._conn.execute("select count(*) from links where source = ?", (rel,)).fetchone()[0] == 0

        app.delete_research_note_confirm()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        assert len(rs.list_notes(p)) == 1
        assert app.current_path == p.manuscript_dir / "01-opening.md"      # moved on to a scene

        app.delete_research_note_confirm()                       # a scene is open: refused
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)


async def test_research_question_cites_notes_and_chat_mode_asks(tmp_path: Path, monkeypatch):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    calls = {}

    def fake_research(prompt, context, model, history=None, client=None):
        calls["research"] = (prompt, context, history)
        return "It floods at dusk [1]."

    def fake_ask(prompt, context, model, history=None, client=None):
        calls["ask"] = (prompt, context, history)
        return "Try a stranger echoing him."

    monkeypatch.setattr(app_module, "research_answer", fake_research)
    monkeypatch.setattr(app_module, "ask_writer", fake_ask)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_research_question()                              # no notes at all: a clear message, no AI call
        await pilot.pause()
        assert isinstance(app.screen, AssistantScreen)
        app.screen.query_one(Input).value = "when does it flood?"
        await pilot.press("enter")
        await pilot.pause()
        assert "no research notes" in _texts(app.screen) and "research" not in calls
        await pilot.press("escape")
        await pilot.pause()

        rs.new_note(p, "Tides", "The spur floods at dusk.")
        app.open_research_question()
        await pilot.pause()
        app.screen.query_one(Input).value = "when does the spur flood?"
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.pause()
        text = _texts(app.screen)
        assert "It floods at dusk [1]." in text and "[1] Tides" in text
        assert "[1] Tides" in calls["research"][1] and "floods at dusk" in calls["research"][1]
        await pilot.press("ctrl+o")                               # open the cited note
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_path == p.root / "research" / "tides.md"

        # ctrl+r switches the same window to plain chat about the open file
        app.open_assistant("research")
        await pilot.pause()
        await pilot.press("ctrl+r")
        app.screen.query_one(Input).value = "what now?"
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.pause()
        assert calls["ask"][0] == "what now?"
        assert "Try a stranger" in _texts(app.screen)
        assert {"role": "user", "text": "when does the spur flood?"} in calls["ask"][2]   # history carries over
