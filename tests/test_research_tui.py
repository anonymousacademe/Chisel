"""Research notes and the assistant window in the terminal app (Wave 3.3). AI is mocked."""

from pathlib import Path

from textual.widgets import Input, Static

from chisel.core import research as rs
from chisel.core.project import Project
from chisel.tui import app as app_module
from chisel.tui.app import ConfirmScreen, ChiselApp, NamePrompt
from chisel.tui.assistantscreen import AssistantScreen
from chisel.tui.commands import ActionProvider, ResearchProvider
from chisel.tui.structurescreens import ChoiceScreen


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").write_text("# Rain\n\nthe rain fell on the spur\n")
    return p


def _texts(screen) -> str:
    return "\n".join(str(s.render()) for s in screen.query("#as-log Static"))


def test_palette_lists_the_research_actions_and_provider():
    methods = {m for _, m, _ in ActionProvider.ACTIONS}
    assert {"new_research_note_prompt", "new_research_from_link_prompt", "delete_research_note_confirm",
            "open_assistant", "open_research_question", "send_selection_to_notebook"} <= methods
    assert ResearchProvider.__name__ in {c.__name__ for c in ChiselApp.COMMANDS}


async def test_new_note_link_open_and_delete(tmp_path: Path):
    p = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.new_research_note_prompt()
        await pilot.pause()
        assert isinstance(app.screen, NamePrompt)
        app.screen.query_one(Input).value = "Tide almanac"
        await pilot.press("enter")
        await pilot.pause()
        note = p.root / "notebook" / "tide-almanac.md"
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
        (item,) = p.list_trash()                                           # kept in the Trash, not gone
        assert item.kind == "research" and item.original.startswith("notebook/")

        app.open_trash()                                                   # and the Trash view restores it
        await pilot.pause()
        assert "notebook note" in app.screen._row(item)
        await pilot.press("r")
        await pilot.pause()
        assert len(rs.list_notes(p)) == 2 and p.list_trash() == []
        await pilot.press("escape")
        await pilot.pause()

        app.delete_research_note_confirm()                       # a scene is open: refused
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)


async def test_research_question_cites_notes_and_chat_mode_asks(tmp_path: Path, monkeypatch):
    p = _project(tmp_path)
    app = ChiselApp(p)
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
        assert "Your notebook is empty" in _texts(app.screen) and "research" not in calls
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
        assert app.current_path == p.root / "notebook" / "tides.md"

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


async def test_conversations_are_saved_listed_reopened_and_replies_saved_to_notes(tmp_path: Path, monkeypatch):
    from chisel.core import chats
    from chisel.tui.assistantscreen import ChatsScreen

    p = _project(tmp_path)
    app = ChiselApp(p)
    monkeypatch.setattr(app_module, "ask_writer", lambda prompt, context, model, history=None, client=None: f"Re: {prompt}")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_assistant()
        await pilot.pause()
        for q in ("first idea?", "second idea?"):
            app.screen.query_one(Input).value = q
            await pilot.press("enter")
            await pilot.pause(0.3)
            await pilot.pause()
        (info,) = chats.list_chats(p)
        assert info.title == "first idea?" and info.count == 4       # saved after each answer, one chat

        await pilot.press("ctrl+s")                                  # save the last answer to notes
        await pilot.pause()
        notes = (p.root / "notebook" / "assistant-notes.md").read_text()
        assert "**Prompt:** second idea?" in notes and "Re: second idea?" in notes and "first idea" not in notes.split("##")[-1]

        await pilot.press("ctrl+n")                                  # a new chat: empty window, old one stays on disk
        await pilot.pause()
        assert isinstance(app.screen, AssistantScreen) and app.screen.messages == []
        app.screen.query_one(Input).value = "other topic"
        await pilot.press("enter")
        await pilot.pause(0.3)
        await pilot.pause()
        assert [c.title for c in chats.list_chats(p)] == ["other topic", "first idea?"]

        await pilot.press("ctrl+t")
        await pilot.pause()
        assert isinstance(app.screen, ChatsScreen)
        await pilot.press("down")                                    # the older chat
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, AssistantScreen)
        assert [m.text for m in app.screen.messages] == ["first idea?", "Re: first idea?", "second idea?", "Re: second idea?"]

        await pilot.press("ctrl+t")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        app.screen.query_one(Input).value = "Plot ideas"
        await pilot.press("enter")
        await pilot.pause()
        assert "Plot ideas" in [c.title for c in chats.list_chats(p)]
        assert isinstance(app.screen, ChatsScreen)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert len(chats.list_chats(p)) == 1


def test_saved_conversations_key_is_not_a_terminal_control_code():
    from chisel.tui.assistantscreen import AssistantScreen
    keys = {b.key for b in AssistantScreen.BINDINGS}
    assert "ctrl+t" in keys and not keys & {"ctrl+h", "ctrl+i", "ctrl+m", "ctrl+["}


async def test_send_selection_to_notebook(tmp_path: Path):
    p = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.send_selection_to_notebook()                           # nothing selected: refused
        await pilot.pause()
        assert not (p.root / "notebook" / "clippings.md").exists()
        app.editor.text = "Alpha beta gamma."
        app.editor.select_all()
        before = app.editor.text
        app.send_selection_to_notebook()
        await pilot.pause()
        assert "> Alpha beta gamma." in (p.root / "notebook" / "clippings.md").read_text()
        assert app.editor.text == before
