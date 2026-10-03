"""Brainstorm (Wave 4.3): ai.writing.brainstorm, the GUI bridge and saved chats.
AI is mocked at the function boundary; nothing touches the network."""

import threading
from types import SimpleNamespace

import pytest

from chisel.ai import writing
from chisel.core import chats
from chisel.gui import api as api_module
from tests.test_gui_api import open_api

SCENE = "manuscript/01-arrival.md"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key (network is blocked in tests)")

    monkeypatch.setattr("chisel.ai.client.make_client", boom)


class FakeClient:
    """Just enough of the OpenAI client for ai.writing.brainstorm."""

    def __init__(self, content):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._content = content

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
                               usage=None)


def test_parse_numbered_list_with_wrapped_lines():
    raw = ("1. What if the tram never stopped?\n2. Let the rain stop mid-sentence,\n   so the market hears.\n"
           "3) **Pressure:** Wren hides something small.\n4. A fourth <!-- hidden --> idea.")
    ideas = writing.parse_ideas(raw)
    assert ideas[0] == "What if the tram never stopped?"
    assert ideas[1] == "Let the rain stop mid-sentence, so the market hears."
    assert ideas[2] == "Pressure: Wren hides something small."
    assert "<!--" not in ideas[3] and len(ideas) == 4


def test_parse_caps_at_five_bullets_and_paragraph_fallback():
    assert len(writing.parse_ideas("\n".join(f"- idea {i}" for i in range(9)))) == 5
    assert writing.parse_ideas("One thing.\n\nAnother thing.") == ["One thing.", "Another thing."]
    assert writing.parse_ideas("") == []


def test_brainstorm_sends_context_and_prompt_and_returns_ideas():
    client = FakeClient("1. First.\n2. Second.\n3. Third.")
    ideas = writing.brainstorm("SCENE\nMara <<CURSOR>> waited.", "some/model", client=client)
    assert ideas == ["First.", "Second.", "Third."]
    call = client.calls[0]
    assert call["model"] == "some/model"
    system, user = call["messages"][0]["content"], call["messages"][1]["content"]
    assert "3 and 5 ideas" in system and "what-if" in system and "Do not write the scene's prose" in system
    assert "Mara <<CURSOR>> waited." in user


def test_brainstorm_refuses_an_empty_reply():
    with pytest.raises(ValueError, match="no ideas"):
        writing.brainstorm("ctx", "m", client=FakeClient("   "))


def test_gui_brainstorm_uses_scene_canon_style_and_never_touches_files(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    seen = []
    monkeypatch.setattr(api_module, "brainstorm_writer",
                        lambda context, model, client=None: seen.append((context, model)) or ["Idea A.", "Idea B.", "Idea C."])
    before = {p.name: p.read_text() for p in (root / "manuscript").glob("*.md")}
    r = api.brainstorm(SCENE, None, 10)
    assert r["ok"] and r["ideas"] == ["Idea A.", "Idea B.", "Idea C."]
    assert r["reply"] == "1. Idea A.\n2. Idea B.\n3. Idea C."
    context = seen[-1][0]
    assert "<<CURSOR>>" in context and "Lower Meridian" in context
    r2 = api.brainstorm(None)                       # no scene open: the project and its canon
    assert r2["ok"] and "SCENES (in order)" in seen[-1][0] and "Mara Vale" in seen[-1][0]
    assert before == {p.name: p.read_text() for p in (root / "manuscript").glob("*.md")}


def test_gui_brainstorm_context_leaves_out_pending_ai_drafts(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    seen = []
    monkeypatch.setattr(api_module, "brainstorm_writer",
                        lambda context, model, client=None: seen.append(context) or ["x"])
    text = (root / SCENE).read_text() + "\n<!--ai-->UNACCEPTED SENTENCE<!--/ai-->\n"
    assert api.brainstorm(SCENE, text, 5)["ok"]
    assert "UNACCEPTED SENTENCE" not in seen[-1]


def test_gui_brainstorm_fails_cleanly_without_a_key(tmp_path):
    api, root = open_api(tmp_path)
    r = api.brainstorm(SCENE, None, 0)
    assert r["ok"] is False and "API key" in r["error"]


def test_a_slow_brainstorm_does_not_block_saves(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    started, release = threading.Event(), threading.Event()

    def slow(context, model, client=None):
        started.set()
        assert release.wait(10)
        return ["late idea"]

    monkeypatch.setattr(api_module, "brainstorm_writer", slow)
    out = {}
    t = threading.Thread(target=lambda: out.update(api.brainstorm(SCENE, None, 0)))
    t.start()
    assert started.wait(5)
    doc = api.read_document(SCENE)
    assert api.save_document(SCENE, doc["text"] + "\nmore\n", doc["mtime"])["ok"]   # not frozen
    release.set()
    t.join(5)
    assert out["ok"] and out["ideas"] == ["late idea"]


def test_chats_keep_the_ideas_of_a_brainstorm_reply(tmp_path):
    api, root = open_api(tmp_path)
    msgs = [{"id": "u1", "role": "user", "text": "Brainstorm"},
            {"id": "a1", "role": "assistant", "text": "1. A.\n2. B.", "ideas": ["A.", " B. ", "", 7]}]
    saved = api.save_chat(None, msgs, "scene", [])
    assert saved["ok"]
    loaded = api.open_chat(saved["id"])["chat"]
    assert loaded["messages"][1]["ideas"] == ["A.", "B."]
    assert "ideas" not in loaded["messages"][0]
    assert chats.MAX_IDEAS >= 5


# -- the terminal app ----------------------------------------------------------------------

async def test_tui_brainstorm_lists_ideas_saves_and_drafts(tmp_path, monkeypatch):
    from chisel.core.project import Project
    from chisel.tui import app as app_module
    from chisel.tui.app import ChiselApp
    from chisel.tui.brainstormscreen import BrainstormScreen
    from chisel.tui.promptscreen import PromptScreen

    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").write_text("# Opening\n\nMara waited at the stop.\n")
    seen = []
    monkeypatch.setattr(app_module, "brainstorm_ideas",
                        lambda context, model: seen.append(context) or ["Idea one.", "Idea two.", "Idea three."])
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.brainstorm()
        for _ in range(20):
            await pilot.pause()
            if isinstance(app.screen, BrainstormScreen):
                break
        assert isinstance(app.screen, BrainstormScreen)
        assert "Mara waited" in seen[0]
        before = (p.manuscript_dir / "01-opening.md").read_text()
        await pilot.press("down", "s")                      # save the second idea
        await pilot.pause()
        notes = (tmp_path / "novel" / "notebook" / "assistant-notes.md").read_text()
        assert "Idea two." in notes and "Brainstorm idea - Opening" in notes
        assert isinstance(app.screen, BrainstormScreen)       # reopened for the next one
        await pilot.press("d")                                 # draft from the first idea
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        assert app.screen.query_one("#prompt-input").text == "Idea one."
        await pilot.press("escape")
        await pilot.pause()
        assert (p.manuscript_dir / "01-opening.md").read_text() == before    # nothing written to the prose


def test_palette_lists_brainstorm():
    from chisel.tui.commands import ActionProvider
    assert any(a[0] == "Brainstorm" for a in ActionProvider.ACTIONS)
