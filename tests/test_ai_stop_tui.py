"""The terminal's AI working state and Stop key (plan 1.5): the status line, live
preview, ctrl+x / escape, and that a stopped job inserts, saves and registers nothing."""

import threading
import time
from pathlib import Path

import pytest

import lorewrite.tui.app as app_mod
from lorewrite.ai.stream import Cancelled
from lorewrite.core import drafts
from lorewrite.core import research as rs
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.assistantscreen import AssistantScreen
from textual.widgets import Input


@pytest.fixture
def project(tmp_path):
    proj = Project.create(tmp_path / "novel", title="Stop")
    (proj.manuscript_dir / "02-scene.md").write_text("# S\n\nFirst para.\n", encoding="utf-8")
    return proj


def slow_generate(started, words=200):
    def fake(mode, instruction, context, model, client=None, selection=None,
             on_delta=None, cancel=None):
        started.set()
        for i in range(words):
            if cancel.is_set():
                raise Cancelled()
            on_delta(f"word{i} ")
            time.sleep(0.02)
        return "Generated prose."
    return fake


async def start_draft(app, pilot, scene):
    await pilot.pause()
    app.open_file(scene)
    await pilot.pause()
    app.editor.move_cursor((2, 0))
    await pilot.press("ctrl+g")
    await pilot.pause()
    await pilot.press("x", "ctrl+g")


async def test_draft_shows_status_and_preview_and_ctrl_x_stops_it(project, monkeypatch):
    started = threading.Event()
    monkeypatch.setattr(app_mod, "generate", slow_generate(started))
    scene = project.manuscript_dir / "02-scene.md"
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await start_draft(app, pilot, scene)
        await pilot.pause(0.6)
        assert app.ai_running
        assert "AI: drafting... " in app._status_text and "(ctrl+x to stop)" in app._status_text
        assert app._ai_preview.display and "word" in str(app._ai_preview.render())
        before = app.editor.text
        await pilot.press("ctrl+x")                      # not "cut": the job is stopped
        await pilot.pause(0.3)
        assert not app.ai_running and not app._ai_preview.display
        assert "AI: drafting" not in app._status_text
        await pilot.pause(0.5)
        assert app.editor.text == before and not drafts.find_pending(app.editor.text)
        assert not (project.root / ".drafts").exists() or not any((project.root / ".drafts").iterdir())


async def test_escape_stops_a_running_draft_and_ctrl_x_is_cut_otherwise(project, monkeypatch):
    started = threading.Event()
    monkeypatch.setattr(app_mod, "generate", slow_generate(started))
    scene = project.manuscript_dir / "02-scene.md"
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await start_draft(app, pilot, scene)
        await pilot.pause(0.3)
        assert app.ai_running
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert not app.ai_running and not drafts.find_pending(app.editor.text)
        # no job: ctrl+x still cuts the selection
        app.editor.text = "# S\n\nCut me.\n"
        app.editor.select_all()
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert app.editor.text == ""


async def test_a_second_ai_request_is_refused_while_one_runs(project, monkeypatch):
    started = threading.Event()
    calls = []

    def fake(mode, instruction, context, model, client=None, selection=None, on_delta=None, cancel=None):
        calls.append(mode)
        return slow_generate(started)(mode, instruction, context, model, on_delta=on_delta, cancel=cancel)

    monkeypatch.setattr(app_mod, "generate", fake)
    scene = project.manuscript_dir / "02-scene.md"
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await start_draft(app, pilot, scene)
        await pilot.pause(0.3)
        app._start_generate("draft", "again", 0, 0)
        await pilot.pause(0.2)
        assert calls == ["draft"]
        app.action_stop_ai()
        await pilot.pause(0.3)


async def test_finished_draft_still_inserts_and_clears_the_status(project, monkeypatch):
    def fast(mode, instruction, context, model, client=None, selection=None, on_delta=None, cancel=None):
        on_delta("Generated ")
        on_delta("prose.")
        return "Generated prose."

    monkeypatch.setattr(app_mod, "generate", fast)
    scene = project.manuscript_dir / "02-scene.md"
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await start_draft(app, pilot, scene)
        await pilot.pause(1.0)
        assert drafts.wrap("Generated prose.") in app.editor.text
        assert not app.ai_running and "AI: " not in app._status_text.split("|")[0]


async def test_chat_streams_live_and_a_stopped_answer_is_a_note_not_a_message(project, monkeypatch):
    started = threading.Event()

    def slow_ask(prompt, context, model, history=None, client=None, on_delta=None, cancel=None):
        started.set()
        for i in range(200):
            if cancel.is_set():
                raise Cancelled()
            on_delta(f"tok{i} ")
            time.sleep(0.02)
        return "never"

    monkeypatch.setattr(app_mod, "ask_writer", slow_ask)
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_assistant("chat")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, AssistantScreen)
        screen.query_one(Input).value = "what now?"
        await pilot.press("enter")
        await pilot.pause(0.6)
        assert screen.busy and "tok0" in "".join(str(s.render()) for s in screen.query(".as-live"))
        assert "AI: answering... " in app._status_text
        await pilot.press("escape")                       # stops the answer; the window stays open
        await pilot.pause(0.4)
        assert app.screen is screen and not screen.busy and not app.ai_running
        texts = " ".join(str(s.render()) for s in screen.query("Static"))
        assert "(stopped)" in texts and "never" not in texts
        assert [m.role for m in screen.messages] == ["user"]     # no assistant answer was kept
        assert not list(screen.query(".as-live"))
        await pilot.press("escape")                       # idle: escape closes it
        await pilot.pause()
        assert not isinstance(app.screen, AssistantScreen)


async def test_non_streaming_call_is_abandoned_on_stop(project, monkeypatch):
    release = threading.Event()
    finished = []

    def slow_aliases(scene_text, entities, model):
        release.wait(5)
        finished.append(True)
        return []

    monkeypatch.setattr(app_mod, "suggest_links", slow_aliases)
    scene = project.manuscript_dir / "02-scene.md"
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app._fetch_suggestions()
        await pilot.pause(0.4)
        assert "AI: finding aliases... " in app._status_text
        await pilot.press("ctrl+x")
        await pilot.pause(0.2)
        assert not app.ai_running            # the app moved on while the request is still in flight
        assert not finished
        release.set()
        await pilot.pause(0.3)
        assert finished == [True]
