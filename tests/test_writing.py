"""AI drafting: context builder, output cleaning, generate(), and the ctrl+g flow."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from textual.widgets.text_area import Selection

import chisel.tui.app as app_mod
from chisel.ai.usage import LEDGER
from chisel.ai.writing import (
    CURSOR,
    ENTITY_CHARS,
    ENTITY_TOTAL_CHARS,
    build_context,
    clean_output,
    generate,
)
from chisel.core import drafts
from chisel.core import entities as ent
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.promptscreen import PromptScreen

BORIN = ent.Entity(name="Borin", type="character", aliases=["the old smith"],
                   body="Borin is a smith.")
ELARA = ent.Entity(name="Elara", type="character", body="Elara is a captain.")


# -- context builder -------------------------------------------------------------------


def test_context_has_style_cursor_and_mentioned_entities_only():
    text = "Borin sat down.\n\nMore text here."
    ctx = build_context(text, 15, [BORIN, ELARA],
                        {"Borin": "Borin has one arm.", "Elara": "SHOULD NOT APPEAR"},
                        "## Voice\n- close third")
    assert "STYLE GUIDE:\n## Voice\n- close third" in ctx
    assert f"Borin sat down.{CURSOR}" in ctx
    assert "### Borin (character)\nBorin has one arm." in ctx
    assert "SHOULD NOT APPEAR" not in ctx


def test_context_without_style_or_entities():
    ctx = build_context("hello world", 5, [], {}, None)
    assert "STYLE GUIDE" not in ctx and "CHARACTERS" not in ctx
    assert f"hello{CURSOR} world" in ctx


def test_context_window_is_500_words_each_side_at_word_boundaries():
    before = " ".join(f"b{i}" for i in range(800))
    after = " ".join(f"a{i}" for i in range(800))
    text = before + " " + after
    ctx = build_context(text, len(before) + 1, [], {}, None)
    scene = ctx.split("):\n", 1)[1]
    head, tail = scene.split(CURSOR)
    assert head.startswith("…b300 ") and head.rstrip().endswith("b799")
    assert len(head.split()) == 500
    assert tail.endswith("a499…") and len(tail.split()) == 500
    assert "b299" not in ctx and "a500" not in ctx


def test_context_strips_pending_drafts_and_places_cursor_around_them():
    text = "Start " + drafts.wrap("GHOST") + " middle. End."
    ctx = build_context(text, len(text) - 4, [], {}, None)
    assert "GHOST" not in ctx and "<!--" not in ctx
    assert "Start  middle." in ctx
    # a cursor inside a draft is marked just before it
    inside = text.index("GHOST") + 2
    ctx = build_context(text, inside, [], {}, None)
    assert f"Start {CURSOR} middle." in ctx


def test_context_span_is_replaced_by_the_sentinel():
    text = "Before {{expand: the rain}} after."
    start = text.index("{{")
    ctx = build_context(text, start, [], {}, None, span=(start, text.index("}}") + 2))
    assert f"Before {CURSOR} after." in ctx and "{{expand" not in ctx


def test_context_caps_entity_notes():
    big = ent.Entity(name="Big", body="x" * 5000)
    ctx = build_context("Big is here.", 0, [big], {"Big": "y" * 5000}, None)
    assert ctx.count("y") == ENTITY_CHARS
    many = [ent.Entity(name=f"Name{i}", body="z" * 1000) for i in range(10)]
    scene = " ".join(e.name for e in many)
    ctx = build_context(scene, 0, many, {e.name: e.body for e in many}, None)
    assert ctx.count("z") <= ENTITY_TOTAL_CHARS


# -- output cleaning ---------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("Plain prose.", "Plain prose."),
    ("```\nFenced prose.\n```", "Fenced prose."),
    ("```markdown\nFenced\nlines\n```", "Fenced\nlines"),
    ("Here's the paragraph:\n\nThe rain fell.", "The rain fell."),
    ("Draft: The rain fell.", "The rain fell."),
    ('"The rain fell. It kept falling."', "The rain fell. It kept falling."),
    ("“The rain fell. It kept falling.”", "The rain fell. It kept falling."),
    ('"Come in," she said.', '"Come in," she said.'),
    ('"Come in."', '"Come in."'),                       # lone dialogue stays
    ('"One." "Two." Three.', '"One." "Two." Three.'),   # inner quotes stay
    ("Text with <!-- sneaky --> comment.", "Text with  sneaky --> comment."),
    ("  padded  \n", "padded"),
])
def test_clean_output(raw, expected):
    assert clean_output(raw) == expected


def test_clean_output_keeps_quotes_when_selection_was_quoted():
    raw = '"It was late. She left."'
    assert clean_output(raw, selection='"It was late."') == raw


@pytest.mark.parametrize("raw", ["", "   ", "```\n```", None, "<!--", "Here's it:"])
def test_clean_output_empty_is_error(raw):
    with pytest.raises(ValueError):
        clean_output(raw)


# -- generate() with a fake client ---------------------------------------------------------


def _client(content, cost=0.004):
    seen = {}

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(cost=cost))

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions())), seen


@pytest.mark.parametrize("mode,marker", [
    ("draft", "INSTRUCTION: describe"),
    ("expand", "AUTHOR'S NOTE: describe"),
    ("rewrite", "PASSAGE:\nold text"),
])
def test_generate_modes_plain_text_and_cost(mode, marker):
    client, seen = _client("```\nNew prose.\n```")
    out = generate(mode, "describe", "CTX", "w/model", client=client,
                   selection="old text" if mode == "rewrite" else None)
    assert out == "New prose."
    assert seen["model"] == "w/model"
    assert "response_format" not in seen  # plain text, no JSON schema
    assert seen["extra_body"] == {"usage": {"include": True}}
    assert marker in seen["messages"][1]["content"]
    assert "CTX" in seen["messages"][1]["content"]
    assert "<!--" in seen["messages"][0]["content"]  # told never to write it
    assert LEDGER.last().feature == mode and LEDGER.session_total() == 0.004


def test_generate_rejects_bad_mode_and_empty_reply():
    with pytest.raises(ValueError):
        generate("nope", "x", "c", "m", client=_client("x")[0])
    with pytest.raises(ValueError):
        generate("draft", "x", "c", "m", client=_client("  ")[0])


# -- TUI flow (generate mocked) --------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="Write")
    proj.create_entity("Borin")
    return proj


def _scene(proj, body):
    path = proj.manuscript_dir / "02-scene.md"
    path.write_text(body, encoding="utf-8")
    return path


def _fake(calls, body="Generated prose."):
    def fake(mode, instruction, context, model, client=None, selection=None):
        calls.append(SimpleNamespace(mode=mode, instruction=instruction,
                                     context=context, model=model,
                                     selection=selection))
        return body
    return fake


async def _open(app, pilot, scene):
    await pilot.pause()
    app.open_file(scene)
    await pilot.pause()


async def test_ctrl_g_draft_mode_inserts_pending_span_at_cursor(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls))
    scene = _scene(project, "# S\n\nFirst para.\n\nSecond para.\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        app.editor.move_cursor((3, 0))  # blank line between paragraphs
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        await pilot.press(*"the busy street")
        await pilot.press("ctrl+g")  # submit
        await pilot.pause(1.0)
        assert calls[0].mode == "draft" and calls[0].instruction == "the busy street"
        assert calls[0].model == app._ai_model("writing")
        assert CURSOR in calls[0].context
        assert app.editor.text == (
            "# S\n\nFirst para.\n" + drafts.wrap("Generated prose.")
            + "\nSecond para.\n")
        (p,) = drafts.find_pending(app.editor.text)
        assert p.id is None
        # reject removes exactly the insertion
        app.editor.move_cursor((3, 5))
        await pilot.pause()
        app.action_reject_draft()
        await pilot.pause()
        assert app.editor.text == "# S\n\nFirst para.\n\nSecond para.\n"


async def test_draft_mid_line_gets_a_space_inside_the_draft(project, monkeypatch):
    monkeypatch.setattr(app_mod, "generate", _fake([], "Then more."))
    scene = _scene(project, "# S\n\nEnd of line.\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        app.editor.move_cursor((2, 12))
        await pilot.press("ctrl+g")
        await pilot.pause()
        await pilot.press("x", "ctrl+g")
        await pilot.pause(1.0)
        assert "End of line.<!--ai--> Then more.<!--/ai-->" in app.editor.text
        app.editor.move_cursor((2, 20))
        await pilot.pause()
        app.action_accept_draft()
        await pilot.pause()
        assert app.editor.text == "# S\n\nEnd of line. Then more.\n"


async def test_ctrl_g_prompt_escape_cancels(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls))
    scene = _scene(project, "# S\n\ntext\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        before = app.editor.text
        await pilot.press("ctrl+g")
        await pilot.pause()
        await pilot.press(*"abc", "escape")
        await pilot.pause(0.5)
        assert not isinstance(app.screen, PromptScreen)
        assert calls == [] and app.editor.text == before
        # an empty prompt also does nothing
        await pilot.press("ctrl+g")
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause(0.5)
        assert calls == [] and app.editor.text == before


async def test_ctrl_g_expand_marker_replaces_and_reject_restores(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls, "The rain hammered."))
    body = "# S\n\nBefore {{expand: describe the rain}} after.\n"
    scene = _scene(project, body)
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        app.editor.move_cursor((2, 12))
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
        assert not isinstance(app.screen, PromptScreen)  # no modal for expand
        assert calls[0].mode == "expand" and calls[0].instruction == "describe the rain"
        assert "{{expand" not in calls[0].context
        text = app.editor.text
        assert text.startswith('# S\n\nBefore <!--ai id="')
        (p,) = drafts.find_pending(text)
        assert drafts.load_originals(project.root, scene)[p.id] == "{{expand: describe the rain}}"
        assert text.endswith("<!--/ai--> after.\n")
        app.editor.move_cursor((2, 30))
        await pilot.pause()
        app.action_reject_draft()
        await pilot.pause()
        assert app.editor.text == body
        # accept path
        app.editor.load_text(body)
        app.editor.move_cursor((2, 12))
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
        app.editor.move_cursor((2, 30))
        app.action_accept_draft()
        await pilot.pause()
        assert app.editor.text == "# S\n\nBefore The rain hammered. after.\n"


async def test_ctrl_g_rewrite_selection(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls, "Rewritten line."))
    body = "# S\n\nKeep this. Change this bit. Keep that.\n"
    scene = _scene(project, body)
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        line = body.split("\n")[2]
        a = line.index("Change")
        app.editor.selection = Selection((2, a), (2, a + len("Change this bit.")))
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        prompt = app.screen.query_one("#prompt-input").text
        assert prompt == "Rewrite this in my style."
        await pilot.press("ctrl+g")  # accept the prefilled instruction
        await pilot.pause(1.0)
        assert calls[0].mode == "rewrite"
        assert calls[0].selection == "Change this bit."
        assert calls[0].instruction == "Rewrite this in my style."
        text = app.editor.text
        (p,) = drafts.find_pending(text)
        assert drafts.load_originals(project.root, scene)[p.id] == "Change this bit."
        assert text.startswith('# S\n\nKeep this. <!--ai id="')
        assert text.endswith("Rewritten line.<!--/ai--> Keep that.\n")
        app.editor.move_cursor((2, 40))
        await pilot.pause()
        app.action_reject_draft()
        await pilot.pause()
        assert app.editor.text == body


async def test_generation_failure_notifies_and_changes_nothing(project, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key")

    monkeypatch.setattr(app_mod, "generate", boom)
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    scene = _scene(project, "# S\n\nA {{expand: x}} B\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        before = app.editor.text
        app.editor.move_cursor((2, 5))
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
        assert app.editor.text == before
    assert any("AI writing failed" in m for m in notified)


async def test_style_tip_shown_once_and_writing_model_used(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls))
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    scene = _scene(project, "# S\n\nA {{expand: x}} B {{expand: y}} C\n")
    from chisel.core import settings as user_settings

    user_settings.set("writing_model", "vendor/prose")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        app.editor.move_cursor((2, 5))
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
        app.editor.move_cursor((2, app.editor.text.split("\n")[2].index("y") + 1))
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
    assert sum("learn a style guide" in m for m in notified) == 1
    assert {c.model for c in calls} == {"vendor/prose"}
    assert any("Drafting… (vendor/prose)" in m for m in notified)


async def test_style_guide_and_canon_flow_into_context(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls))
    (project.root / "style.md").write_text("## Voice\n- terse\n")
    note = project.entities_dir / "characters" / "borin.md"
    note.write_text(note.read_text() + "Borin has one arm.\n")
    scene = _scene(project, "# S\n\nBorin waits. {{expand: a sound}}\n")
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        app.editor.move_cursor((2, 25))
        await pilot.press("ctrl+g")
        await pilot.pause(1.0)
    ctx = calls[0].context
    assert "- terse" in ctx and "### Borin (character)" in ctx and CURSOR in ctx


async def test_generate_needs_a_scene(project, monkeypatch):
    calls = []
    monkeypatch.setattr(app_mod, "generate", _fake(calls))
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(project.entities_dir / "characters" / "borin.md")
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert not isinstance(app.screen, PromptScreen)


async def test_scene_changed_while_drafting_discards(project, monkeypatch):
    other = _scene(project, "# Other\n\nx\n")
    scene = project.manuscript_dir / "03-b.md"
    scene.write_text("# B\n\nA {{expand: q}} B\n")

    def fake(mode, instruction, context, model, client=None, selection=None):
        return "late"

    monkeypatch.setattr(app_mod, "generate", fake)
    app = ChiselApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot, scene)
        app.editor.move_cursor((2, 5))
        app.action_generate()
        app.open_file(other)  # user flips scenes before the model answers
        await pilot.pause(1.0)
        assert "late" not in app.editor.text
    assert "late" not in scene.read_text() and "late" not in other.read_text()
