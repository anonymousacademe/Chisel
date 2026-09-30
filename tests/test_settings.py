"""Settings screen + return-to-main-menu tests."""

from pathlib import Path

from textual.widgets import Checkbox, Input, ListView

import lorewrite.tui.settingscreen as settingscreen_mod
from lorewrite.core import settings as user_settings
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.launch import LaunchScreen
from lorewrite.tui.settingscreen import SettingsScreen


def _project(tmp_path: Path, name: str, title: str) -> Project:
    return Project.create(tmp_path / name, title=title)


# -- core: editor settings write -------------------------------------------------


def test_update_editor_settings_writes_toml(tmp_path: Path):
    proj = _project(tmp_path, "n", "T")
    proj.update_editor_settings(padding=4, line_numbers=False)
    text = (proj.root / "project.toml").read_text()
    assert "[editor]" in text and "padding = 4" in text
    assert "line_numbers = false" in text
    assert 'title = "T"' in text  # other content preserved
    # round-trips through open()
    assert Project.open(proj.root).editor_settings() == {
        "padding": 4, "line_numbers": False,
    }
    # update again: replaces the section, doesn't duplicate it
    proj2 = Project.open(proj.root)
    proj2.update_editor_settings(padding=1)
    text = (proj.root / "project.toml").read_text()
    assert text.count("[editor]") == 1
    assert "padding = 1" in text and "line_numbers = false" in text


# -- settings screen ----------------------------------------------------------------


async def test_settings_screen_shows_key_status(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settingscreen_mod, "get_api_key", lambda: "sk-or-xyz1234abcd")
    proj = _project(tmp_path, "n", "T")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_settings()
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        from textual.widgets import Label
        status = str(app.screen.query_one("#key-status", Label).render())
        assert "abcd" in status  # masked to last 4
        assert "sk-or-xyz" not in status  # never the full key


async def test_settings_save_models_and_editor_prefs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settingscreen_mod, "get_api_key", lambda: None)
    proj = _project(tmp_path, "n", "T")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_settings()
        await pilot.pause()
        screen = app.screen
        screen.query_one("#fast-model", Input).value = "openai/gpt-5-nano"
        screen.query_one("#strong-model", Input).value = "openai/gpt-5"
        screen.query_one("#writing-model", Input).value = "anthropic/claude-opus-x"
        screen.query_one("#padding", Input).value = "3"
        screen.query_one("#line-numbers", Checkbox).value = False
        await pilot.click("#save")
        await pilot.pause()
        assert user_settings.get("fast_model") == "openai/gpt-5-nano"
        assert user_settings.get("strong_model") == "openai/gpt-5"
        assert app._ai_fast_model() == "openai/gpt-5-nano"
        assert app._ai_strong_model() == "openai/gpt-5"
        assert user_settings.get("writing_model") == "anthropic/claude-opus-x"
        assert app._ai_model("writing") == "anthropic/claude-opus-x"
        # editor prefs applied live
        assert app.editor.show_line_numbers is False
        assert app.editor.styles.padding.right == 3


async def test_settings_without_project(tmp_path: Path, monkeypatch):
    """From the launch screen: AI section only, no editor section."""
    monkeypatch.setattr(settingscreen_mod, "get_api_key", lambda: None)
    app = LorewriteApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LaunchScreen)
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert not app.screen.query("#padding")


# -- return to main menu -------------------------------------------------------------


async def test_main_menu_switch_projects(tmp_path: Path):
    from lorewrite.core.recents import add_recent

    proj_a = _project(tmp_path, "a", "Book A")
    proj_b = _project(tmp_path, "b", "Book B")
    add_recent(proj_b.root, proj_b.title)  # B is an older recent
    app = LorewriteApp(proj_a)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.project.title == "Book A"
        # write something, then go to the main menu
        app.editor.move_cursor((0, 0))
        await pilot.press("X")
        await pilot.pause()
        app.action_main_menu()
        await pilot.pause()
        assert isinstance(app.screen, LaunchScreen)
        # the edit was saved before leaving
        assert "X" in (proj_a.manuscript_dir / "01-opening.md").read_text()
        # recents list has both; pick Book B (most recent first = A)
        lv = app.screen.query_one("#recents", ListView)
        lv.index = 1
        await pilot.press("enter")
        await pilot.pause()
        assert app.project.title == "Book B"
        assert "Welcome to lorewrite" in app.editor.text


async def test_main_menu_cancel_stays(tmp_path: Path):
    proj = _project(tmp_path, "a", "Book A")
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_main_menu()
        await pilot.pause()
        assert isinstance(app.screen, LaunchScreen)
        await pilot.press("q")  # dismiss without choosing
        await pilot.pause()
        assert app.project is not None
        assert app.project.title == "Book A"


# -- API key prompt: ctrl+v reads the system clipboard ------------------------------


async def test_key_prompt_ctrl_v_pastes_system_clipboard(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settingscreen_mod, "read_system_clipboard",
                        lambda: "sk-or-v1-secret\n")
    stored = []
    monkeypatch.setattr("lorewrite.tui.app.set_api_key", stored.append)
    app = LorewriteApp(_project(tmp_path, "k", "K"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_api_key()
        await pilot.pause()
        key_input = app.screen.query_one("#key-input", Input)
        assert key_input.password  # masked, never shown in clear
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert key_input.value == "sk-or-v1-secret"
        await pilot.press("enter")
        await pilot.pause()
    assert stored == ["sk-or-v1-secret"]


# -- model picker ---------------------------------------------------------------------


def test_parse_models_keeps_structured_output_models_sorted():
    from lorewrite.ai.client import parse_models

    payload = {"data": [
        {"id": "z/zeta", "name": "Zeta", "supported_parameters": ["structured_outputs"],
         "pricing": {"prompt": "0.0000003", "completion": "0.0000025"},
         "context_length": 128000},
        {"id": "a/plain", "name": "Plain", "supported_parameters": ["tools"]},
        {"id": "b/alpha", "name": "alpha [beta]",
         "supported_parameters": ["structured_outputs"], "pricing": {}},
        {"name": "no id"},
    ]}
    models = parse_models(payload)
    assert [m.id for m in models] == ["b/alpha", "z/zeta"]
    assert round(models[1].prompt_per_m, 2) == 0.3
    assert models[0].prompt_per_m is None


def _fake_models(structured_only=True):
    from lorewrite.ai.client import ModelInfo

    models = [
        ModelInfo("anthropic/claude-sonnet-4.5", "Anthropic: Claude Sonnet 4.5",
                  3.0, 15.0, 200000),
        ModelInfo("google/gemini-2.5-flash", "Google: Gemini 2.5 Flash",
                  0.3, 2.5, 1000000),
        ModelInfo("meta/llama-x", "Meta: Llama [x]", 0.0, 0.0, None),
    ]
    if not structured_only:
        models.append(ModelInfo("plain/prose-model", "Plain Prose", 1.0, 2.0, None))
    return models


async def test_model_picker_filters_and_fills_field(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settingscreen_mod, "list_models", _fake_models)
    app = LorewriteApp(_project(tmp_path, "m", "M"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SettingsScreen(app.project))
        await pilot.pause()
        settings = app.screen
        await pilot.click("#pick-fast")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, settingscreen_mod.ModelPicker)
        await pilot.press(*"gemini")
        await pilot.pause()
        assert [m.id for m in app.screen._shown] == ["google/gemini-2.5-flash"]
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is settings
        assert settings.query_one("#fast-model", Input).value == \
            "google/gemini-2.5-flash"


async def test_model_picker_load_failure_is_reported(tmp_path: Path, monkeypatch):
    def _boom(structured_only=True):
        raise OSError("offline")

    monkeypatch.setattr(settingscreen_mod, "list_models", _boom)
    app = LorewriteApp(_project(tmp_path, "f", "F"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(settingscreen_mod.ModelPicker())
        await pilot.pause()
        await pilot.pause()
        status = str(app.screen.query_one("#picker-status").render())
        assert "offline" in status
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, settingscreen_mod.ModelPicker)


async def test_settings_opens_after_saving_empty_model_fields(tmp_path: Path):
    # Save with blank model fields writes null; reopening used to crash the app
    user_settings.set("fast_model", None)
    user_settings.set("strong_model", None)
    app = LorewriteApp(_project(tmp_path, "z", "Z"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_settings()
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert app.screen.query_one("#fast-model", Input).value == ""


async def test_settings_opens_after_saving_empty_writing_model(tmp_path: Path):
    user_settings.set("writing_model", None)
    app = LorewriteApp(_project(tmp_path, "w", "W"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_settings()
        await pilot.pause()
        assert app.screen.query_one("#writing-model", Input).value == ""


async def test_settings_writing_model_round_trip(tmp_path: Path):
    user_settings.set("writing_model", "vendor/prose-1")
    app = LorewriteApp(_project(tmp_path, "r", "R"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_settings()
        await pilot.pause()
        assert app.screen.query_one("#writing-model", Input).value == "vendor/prose-1"


def test_model_precedence_project_over_user_over_default(tmp_path: Path):
    from lorewrite.ai.client import DEFAULT_WRITING_MODEL

    proj = _project(tmp_path, "p", "P")
    app = LorewriteApp(proj)
    assert app._ai_model("writing") == DEFAULT_WRITING_MODEL
    user_settings.set("writing_model", "user/writer")
    assert app._ai_model("writing") == "user/writer"
    proj.meta["ai"] = {"writing_model": "project/writer"}
    assert app._ai_model("writing") == "project/writer"
    assert app._ai_model("fast") != "project/writer"


def test_parse_models_structured_only_flag():
    from lorewrite.ai.client import parse_models

    payload = {"data": [
        {"id": "a/plain", "name": "Plain", "supported_parameters": ["tools"]},
        {"id": "b/struct", "name": "Struct",
         "supported_parameters": ["structured_outputs"]},
    ]}
    assert [m.id for m in parse_models(payload)] == ["b/struct"]
    assert [m.id for m in parse_models(payload, structured_only=False)] == [
        "a/plain", "b/struct"]


def test_list_models_caches_raw_payload_and_filters_per_call(monkeypatch):
    import io
    import json

    from lorewrite.ai import client

    payload = {"data": [
        {"id": "a/plain", "name": "Plain", "supported_parameters": []},
        {"id": "b/struct", "name": "Struct",
         "supported_parameters": ["structured_outputs"]},
    ]}
    calls = []

    def fake_urlopen(url, timeout=0):
        calls.append(url)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(client, "_models_payload", None)
    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    assert [m.id for m in client.list_models()] == ["b/struct"]
    assert [m.id for m in client.list_models(structured_only=False)] == [
        "a/plain", "b/struct"]
    assert len(calls) == 1


async def test_writing_picker_shows_non_structured_models(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settingscreen_mod, "list_models", _fake_models)
    app = LorewriteApp(_project(tmp_path, "wp", "WP"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SettingsScreen(app.project))
        await pilot.pause()
        settings = app.screen
        await pilot.click("#pick-writing")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, settingscreen_mod.ModelPicker)
        assert "plain/prose-model" in [m.id for m in app.screen._shown]
        await pilot.press(*"prose")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert settings.query_one("#writing-model", Input).value == "plain/prose-model"
        # the other pickers stay structured-only
        await pilot.click("#pick-fast")
        await pilot.pause()
        await pilot.pause()
        assert "plain/prose-model" not in [m.id for m in app.screen._shown]
