"""Settings bridge: keys, models, editor prefs. Keyring and network are mocked."""

import pytest

from chisel.ai.client import DEFAULT_FAST_MODEL, ModelInfo
from chisel.gui import api as api_module
from tests.test_gui_api import open_api


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    store = {}
    monkeypatch.setattr(api_module, "get_api_key", lambda: store.get("key"))
    monkeypatch.setattr(api_module, "_set_api_key", lambda k: store.__setitem__("key", k))
    monkeypatch.setattr(api_module, "_clear_api_key", lambda: store.pop("key", None))

    def no_net(*a, **k):
        raise AssertionError("network")

    monkeypatch.setattr("chisel.ai.client.make_client", no_net)
    return store


def test_defaults_before_any_choice(tmp_path):
    api, _ = open_api(tmp_path)
    s = api.get_settings()
    assert s["hasKey"] is False and s["keySource"] == "none"
    assert s["models"]["fast"] == {"value": "", "default": DEFAULT_FAST_MODEL,
                                   "effective": DEFAULT_FAST_MODEL, "projectOverride": ""}
    assert s["editor"] == {"zoom": 100, "reflow": True}


def test_key_roundtrip_never_returns_the_key(tmp_path, fakes):
    api, _ = open_api(tmp_path)
    assert api.set_api_key("  ")["ok"] is False
    assert api.set_api_key("sk-or-secret")["ok"]
    s = api.get_settings()
    assert s["hasKey"] and s["keySource"] == "keyring"
    assert "sk-or-secret" not in str(s)
    assert api.ai_status()["hasKey"] is True
    assert api.clear_api_key()["stillSet"] is False
    assert api.get_settings()["hasKey"] is False


def test_environment_key_survives_clear(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert api.get_settings()["keySource"] == "environment"
    r = api.clear_api_key()
    assert r["stillSet"] is True and "environment" in r["note"]


def test_keyring_failure_is_reported_not_raised(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)

    def boom(k):
        raise RuntimeError("no secret service")

    monkeypatch.setattr(api_module, "_set_api_key", boom)
    r = api.set_api_key("k")
    assert r["ok"] is False and "OPENROUTER_API_KEY" in r["error"]


def test_model_choices_precedence_and_reset(tmp_path):
    api, root = open_api(tmp_path)
    assert api.set_settings(models={"fast": "vendor/fast-1", "writing": " vendor/write "})["ok"]
    m = api.get_settings()["models"]
    assert m["fast"]["value"] == "vendor/fast-1" and m["fast"]["effective"] == "vendor/fast-1"
    assert m["writing"]["effective"] == "vendor/write"
    assert api.set_settings(models={"fast": ""})["ok"]
    assert api.get_settings()["models"]["fast"]["effective"] == DEFAULT_FAST_MODEL
    # a project.toml [ai] override wins, and the dialog can say so
    (root / "project.toml").write_text('title = "T"\n[ai]\nstrong_model = "proj/strong"\n')
    assert api.open_project(str(root))["ok"]
    strong = api.get_settings()["models"]["strong"]
    assert strong["effective"] == "proj/strong" and strong["projectOverride"] == "proj/strong"
    assert api.set_settings(models={"bogus": "x"})["ok"] is False


def test_editor_prefs_validate(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.set_settings(editor={"zoom": 110, "reflow": False})["ok"]
    assert api.get_settings()["editor"] == {"zoom": 110, "reflow": False}
    assert api.set_settings(editor={"zoom": 111})["ok"] is False
    assert api.set_settings(editor={"font": "x"})["ok"] is False


def test_list_models_filters_by_structured_outputs(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    seen = []

    def fake(timeout=10, structured_only=True):
        seen.append(structured_only)
        return [ModelInfo("a/b", "A B", 1.0, 2.0, 8000)]

    monkeypatch.setattr(api_module, "_list_models", fake)
    r = api.list_models(True)
    assert r["models"] == [{"id": "a/b", "name": "A B", "promptPerM": 1.0, "completionPerM": 2.0, "context": 8000, "imagePrice": None}]
    api.list_models(False)
    assert seen == [True, False]
    monkeypatch.setattr(api_module, "_list_models", lambda **k: (_ for _ in ()).throw(OSError("offline")))
    assert api.list_models()["ok"] is False
