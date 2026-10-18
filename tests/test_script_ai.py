"""Script-aware drafting: Fountain prompts, cleaned replies, drafts that start a new block (ai/writing.py)."""

from types import SimpleNamespace

import pytest

from chisel.ai import writing
from chisel.ai.writing import (
    ASK_SYSTEM_PROMPT, SCRIPT_ASK_SYSTEM_PROMPT, SCRIPT_SYSTEM_PROMPT, SYSTEM_PROMPT, ask_system_prompt,
    clean_script_output, generate, generate_instructions,
)
from chisel.core import drafts, fountain
from chisel.gui import api as api_module
from chisel.gui.api import Api
from tests.test_script_export import make_script

SCENE_ID = "manuscript/01-act-one/01-kitchen.md"


def _client(content):
    seen = {}

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                                   usage=SimpleNamespace(cost=0.001))

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions())), seen


# -- prompts -------------------------------------------------------------------------------------


def test_the_script_prompt_teaches_fountain_and_forbids_notes():
    p = SCRIPT_SYSTEM_PROMPT
    for needle in ("Fountain", "INT. KITCHEN - DAY", "character cue", "parenthetical", "<<CURSOR>>",
                   "[[ ]] or <!-- -->", "ONLY the requested script text"):
        assert needle in p, needle
    assert "novelist" not in p
    assert SYSTEM_PROMPT != SCRIPT_SYSTEM_PROMPT and "Fountain" not in SYSTEM_PROMPT


@pytest.mark.parametrize("mode,marker", [("draft", "INSTRUCTION: x"), ("expand", "AUTHOR'S NOTE: x"),
                                          ("rewrite", "PASSAGE:\nold")])
def test_script_requests_ask_for_fountain_in_every_mode(mode, marker):
    client, seen = _client("INT. A - DAY\n\nHi.")
    generate(mode, "x", "CTX", "m", client=client, selection="old" if mode == "rewrite" else None, script=True)
    system, user = (m["content"] for m in seen["messages"])
    assert system == SCRIPT_SYSTEM_PROMPT
    assert "Fountain" in user and marker in user and "CTX" in user
    if mode == "rewrite":
        assert "scene headings, cues, who speaks" in user


def test_story_requests_are_unchanged():
    client, seen = _client("New prose.")
    out = generate("draft", "describe", "CTX", "m", client=client)
    assert out == "New prose."
    assert seen["messages"][0]["content"] == SYSTEM_PROMPT
    assert seen["messages"][1]["content"] == "CTX\n\nTASK: Write new prose to be inserted at <<CURSOR>>.\n\nINSTRUCTION: describe"
    assert generate_instructions("draft", "x").text == generate_instructions("draft", "x", None, False).text
    assert generate_instructions("draft", "x", None, True).text.startswith(SCRIPT_SYSTEM_PROMPT)


def test_the_chat_prompt_for_scripts_says_fountain_and_keeps_the_rules():
    assert ask_system_prompt() is ASK_SYSTEM_PROMPT and ask_system_prompt(True) is SCRIPT_ASK_SYSTEM_PROMPT
    assert "screenwriter's script editor" in SCRIPT_ASK_SYSTEM_PROMPT and "novelist" not in SCRIPT_ASK_SYSTEM_PROMPT
    assert "valid Fountain" in SCRIPT_ASK_SYSTEM_PROMPT
    assert "You can only suggest" in SCRIPT_ASK_SYSTEM_PROMPT and 'Never write HTML comments' in SCRIPT_ASK_SYSTEM_PROMPT


# -- replies ---------------------------------------------------------------------------------------


def test_replies_lose_notes_bold_cues_and_blank_runs():
    raw = "```\n**KEITH**\n(quietly)\nBurnt again. [[check this]]\n\n\n\n\nCUT TO: /* old */\n```"
    out = generate("draft", "x", "c", "m", client=_client(raw)[0], script=True)
    assert out == "KEITH\n(quietly)\nBurnt again. \n\nCUT TO:"
    assert fountain.parse(out)[0].kind == fountain.CHARACTER
    with pytest.raises(ValueError):
        clean_script_output("[[only a note]]")


def test_a_story_reply_keeps_its_brackets():
    out = generate("draft", "x", "c", "m", client=_client("She read [[Mara]] twice.")[0])
    assert out == "She read [[Mara]] twice."


# -- inserting a draft ---------------------------------------------------------------------------------


@pytest.mark.parametrize("text,at,expect", [
    ("Keith stares.", 13, "Keith stares.<!--ai-->\n\nBOB\nHi.<!--/ai-->"),                 # after a line: a blank line
    ("Keith stares.\n", 14, "Keith stares.\n<!--ai-->\nBOB\nHi.<!--/ai-->"),               # after a break: one more
    ("Keith stares.\n\n", 15, "Keith stares.\n\n<!--ai-->BOB\nHi.<!--/ai-->"),             # already a gap
    ("Keith stares.\n\nNext.", 15, "Keith stares.\n\n<!--ai-->BOB\nHi.\n\n<!--/ai-->Next."),   # runs into text: a gap
    ("A.\n\n\nNext.", 4, "A.\n\n<!--ai-->BOB\nHi.\n<!--/ai-->\nNext."),
])
def test_a_script_draft_starts_a_new_block(text, at, expect):
    insert, a, b = drafts.prepare_draft(text, "draft", "BOB\nHi.", at, at, script=True)
    assert (a, b) == (at, at)
    assert text[:a] + insert + text[b:] == expect
    # accepting it leaves valid Fountain: the speaker, then the speech
    accepted = drafts.accept_all(expect)
    kinds = [ln.kind for ln in fountain.parse(accepted) if ln.kind != fountain.BLANK]
    assert fountain.CHARACTER in kinds and kinds.count(fountain.DIALOGUE) == 1


def test_a_story_draft_still_glues_with_a_space():
    insert, _, _ = drafts.prepare_draft("Elias", "draft", "He smiled.", 5, 5)
    assert insert == "<!--ai--> He smiled.<!--/ai-->"
    insert, _, _ = drafts.prepare_draft("Elias", "draft", "He smiled.", 5, 5, script=False)
    assert insert == "<!--ai--> He smiled.<!--/ai-->"


def test_rewrite_and_expand_replace_in_place_even_in_a_script():
    insert, a, b = drafts.prepare_draft("A. old text. B.", "rewrite", "new", 3, 11, "abc123", script=True)
    assert (a, b) == (3, 11) and insert == '<!--ai id="abc123"-->new<!--/ai-->'


# -- the desktop bridge ----------------------------------------------------------------------------------


def _open(tmp_path):
    root = tmp_path / "s"
    make_script(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def test_generate_passes_script_only_for_scripts(tmp_path, monkeypatch):
    api, root = _open(tmp_path)
    seen = {}

    def fake(mode, instruction, context, model, selection=None, **kw):
        seen.update(kw, context=context)
        return "BOB\nHello there."

    monkeypatch.setattr(api_module, "generate_text", fake)
    text = (root / SCENE_ID).read_text(encoding="utf-8")
    at = len(text)
    r = api.generate("draft", "Bob arrives", SCENE_ID, text, at, at)
    assert r["ok"], r
    assert seen["script"] is True
    assert "Fountain" in seen["context"] or "SCENE" in seen["context"]
    assert r["insert"].startswith("<!--ai-->\n") and r["insert"].endswith("BOB\nHello there.<!--/ai-->")
    assert (root / SCENE_ID).read_text(encoding="utf-8") == text          # nothing written: the author decides


def test_story_generate_has_no_script_argument(tmp_path, monkeypatch):
    from tests.gui_helpers import make_project
    make_project(tmp_path / "p")
    api = Api()
    api.open_project(str(tmp_path / "p"))
    seen = {}

    def fake(mode, instruction, context, model, selection=None, **kw):
        seen.update(kw)
        return "He smiled."

    monkeypatch.setattr(api_module, "generate_text", fake)
    text = (tmp_path / "p" / "manuscript" / "01-arrival.md").read_text(encoding="utf-8")
    assert api.generate("draft", "a smile", "manuscript/01-arrival.md", text, 5, 5)["ok"]
    assert "script" not in seen


def test_a_chat_reply_inserted_into_a_script_starts_a_block(tmp_path):
    api, root = _open(tmp_path)
    text = (root / SCENE_ID).read_text(encoding="utf-8")
    r = api.draft_from_reply(SCENE_ID, text, "BOB\nHi.", len(text))
    assert r["ok"] and r["insert"].startswith("<!--ai-->\n")


def test_the_chat_uses_the_script_prompt_for_scripts(tmp_path, monkeypatch):
    api, root = _open(tmp_path)
    captured = {}
    real = api_module.chat_instructions

    def spy(system, prompt, history=None):
        captured["system"] = system
        return real(system, prompt, history)

    monkeypatch.setattr(api_module, "chat_instructions", spy)
    monkeypatch.setattr(api_module, "ask_writer", lambda *a, **k: "ok")
    assert api.ask("what next?", "project")["ok"]
    assert captured["system"] is SCRIPT_ASK_SYSTEM_PROMPT


def test_the_mock_writes_fountain_for_a_script(tmp_path, monkeypatch):
    from chisel.gui import mockai
    for name in ("generate_text",):
        monkeypatch.setattr(api_module, name, getattr(api_module, name))
    mockai.install(api_module)
    out = api_module.generate_text("draft", "x", "ctx", "m", script=True)
    assert out == "A vendor laughs at nothing. The neon koi turn once in the haze.\n\nROOK\n(under his breath)\nThat is not a good sign."
    assert [ln.kind for ln in fountain.parse("\n" + out) if ln.kind not in (fountain.BLANK,)][-3:] == [
        fountain.CHARACTER, fountain.PARENTHETICAL, fountain.DIALOGUE]


def test_module_exports_are_stable():
    assert writing.MODES == ("draft", "expand", "rewrite")
