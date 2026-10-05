"""The AI job bridge (plan 1.5): ai_start / ai_poll / ai_cancel over the same
methods the synchronous bridge has. AI is mocked at the function boundary."""

import time

import pytest

from chisel.ai.stream import Cancelled
from chisel.gui import aijobs
from chisel.gui import api as api_module
from chisel.gui.aijobs import AiJobs
from tests.test_gui_api import open_api

SCENE = "manuscript/01-arrival.md"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network is blocked in tests")

    monkeypatch.setattr("chisel.ai.client.make_client", boom)


def wait(api, job, states=("done", "cancelled", "error"), timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = api.ai_poll(job)
        if r["state"] in states:
            return r
        time.sleep(0.01)
    raise AssertionError("job still running")


def fake_stream_ask(words, delay=0.0):
    def fake(prompt, context, model, history=None, client=None, on_delta=None, cancel=None):
        for w in words:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            on_delta(w)
            time.sleep(delay)
        return "".join(words).strip()
    return fake


def test_ask_job_streams_text_then_returns_the_sync_result(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "ask_writer", fake_stream_ask(["Hello ", "there."], 0.05))
    job = api.ai_start("ask", {"prompt": "hi", "scope": "project"})["job"]
    first = api.ai_poll(job)
    assert first["state"] in ("running", "done") and first["ok"]
    done = wait(api, job)
    assert done["state"] == "done" and done["length"] == len("Hello there.")
    assert done["result"]["reply"] == "Hello there." and done["result"]["ok"] is True
    # `since` returns only the new text
    assert api.ai_poll(job, 6)["text"] == "there."
    assert api.ai_poll(job, 0)["text"] == "Hello there."


def test_stop_discards_the_result_and_is_idempotent(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "ask_writer", fake_stream_ask(["w "] * 200, 0.02))
    job = api.ai_start("ask", {"prompt": "hi", "scope": "project"})["job"]
    time.sleep(0.1)
    assert api.ai_cancel(job)["state"] == "cancelled"
    assert api.ai_cancel(job)["state"] == "cancelled"
    r = api.ai_poll(job)
    assert r["state"] == "cancelled" and "result" not in r
    time.sleep(0.2)
    final = api.ai_poll(job)
    assert final["state"] == "cancelled" and final["length"] == r["length"] < 200 * 2


def test_stopped_generate_registers_and_inserts_nothing(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "generate_text", lambda mode, instruction, context, model,
                        selection=None, on_delta=None, cancel=None: fake_stream_ask(["x "] * 100, 0.02)(
                            "", "", "", on_delta=on_delta, cancel=cancel))
    text = (root / SCENE).read_text()
    before_files = sorted(p.name for p in root.rglob("*.json"))
    job = api.ai_start("generate", {"mode": "draft", "instruction": "go", "doc_id": SCENE,
                                    "text": text, "start": 0, "end": 0})["job"]
    time.sleep(0.1)
    api.ai_cancel(job)
    time.sleep(0.3)
    assert api.ai_poll(job)["state"] == "cancelled"
    assert (root / SCENE).read_text() == text
    assert sorted(p.name for p in root.rglob("*.json")) == before_files
    assert not (root / ".drafts").exists() or not list((root / ".drafts").iterdir())


def test_errors_and_bad_calls_are_reported_not_raised(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    assert api.ai_start("nope", {})["ok"] is False
    bad = api.ai_start("ask", {"prompt": "x", "scope": "scene", "bogus": 1})
    assert bad["ok"] is False and "bad arguments" in bad["error"]
    assert api.ai_poll("a999")["ok"] is False and api.ai_cancel("a999")["ok"] is False
    job = api.ai_start("research", {"prompt": "tides?"})["job"]     # no notes: refuses
    r = wait(api, job)
    assert r["state"] == "error" and "notebook is empty" in r["error"]


def test_non_streaming_kind_is_abandoned_on_stop(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    saved = []

    def slow_images(prompt, model, client=None, style=None):
        time.sleep(0.3)
        return [(b"png", "png")]

    monkeypatch.setattr(api_module, "generate_images", slow_images)
    monkeypatch.setattr(api_module.insp_api, "save_pictures", lambda *a, **k: saved.append(a) or {})
    job = api.ai_start("image", {"prompt": "a pier", "doc_id": SCENE})["job"]
    assert api.ai_poll(job)["state"] == "running" and api.ai_poll(job)["text"] == ""
    api.ai_cancel(job)
    assert api.ai_poll(job)["state"] == "cancelled"
    time.sleep(0.6)
    assert api.ai_poll(job)["state"] == "cancelled" and saved == []
    # and when not stopped it does save
    job = api.ai_start("image", {"prompt": "a pier", "doc_id": SCENE})["job"]
    assert wait(api, job)["state"] == "done" and len(saved) == 1


def test_continuity_job_returns_the_sync_result(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    monkeypatch.setattr(api_module, "check_scene", lambda *a, **k: [])
    r = wait(api, api.ai_start("continuity", {"doc_id": SCENE})["job"])
    assert r["state"] == "done" and r["result"]["issues"] == [] and r["text"] == ""


def test_finished_jobs_expire():
    jobs = AiJobs(retention=0.2)
    job_id = jobs.start(lambda job: {"ok": True, "v": 1})
    time.sleep(0.05)
    assert jobs.poll(job_id)["state"] == "done"
    time.sleep(0.3)
    jobs.start(lambda job: {"ok": True})        # pruning happens on use
    with pytest.raises(LookupError):
        jobs.poll(job_id)


def test_checkpoint_outside_a_job_is_a_no_op():
    aijobs.checkpoint()


MOCKED = ("suggest_links", "suggest_relationships", "check_scene", "propose_canon_updates", "learn_style",
          "generate_text",
          "ask_writer", "research_writer", "brainstorm_writer", "generate_images",
          "suggest_image_prompt", "get_api_key", "_set_api_key", "_clear_api_key", "_list_models")


@pytest.fixture
def mock_ai(monkeypatch):
    from chisel.gui import mockai

    for name in MOCKED:
        monkeypatch.setattr(api_module, name, getattr(api_module, name))   # undone after the test
    mockai.install(api_module)
    return mockai


def test_mock_streams_word_by_word_and_honours_stop(tmp_path, mock_ai, monkeypatch):
    monkeypatch.setattr(mock_ai, "WORD_DELAY", 0.01)
    api, root = open_api(tmp_path)
    done = wait(api, api.ai_start("ask", {"prompt": "hi", "scope": "project"})["job"])
    assert done["state"] == "done" and done["length"] > 40
    assert done["result"]["reply"].startswith("Three options") and done["text"] != ""
    # the plain synchronous call is still instant and unchanged
    assert api.ask("hi", "project")["reply"] == done["result"]["reply"]

    monkeypatch.setattr(mock_ai, "WORD_DELAY", 0.05)
    text = (root / SCENE).read_text()
    job = api.ai_start("generate", {"mode": "draft", "instruction": "go", "doc_id": SCENE,
                                    "text": text, "start": 0, "end": 0})["job"]
    time.sleep(0.2)
    mid = api.ai_poll(job)
    assert mid["state"] == "running" and 0 < mid["length"]
    api.ai_cancel(job)
    time.sleep(0.2)
    end = api.ai_poll(job)
    assert end["state"] == "cancelled" and end["length"] < 150 and "result" not in end


def test_mock_non_streaming_job_runs_and_can_be_stopped(tmp_path, mock_ai):
    api, _ = open_api(tmp_path)
    job = api.ai_start("aliases", {"doc_id": SCENE})["job"]
    time.sleep(0.2)
    assert api.ai_poll(job)["state"] == "running"
    api.ai_cancel(job)
    assert api.ai_poll(job)["state"] == "cancelled"


def test_image_regenerate_job_saves_unless_stopped(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    saved = []
    old = type("Old", (), {"prompt": "a pier", "link": "", "source": ""})()
    monkeypatch.setattr(api_module.insp_api, "get", lambda project, image_id: old)
    monkeypatch.setattr(api_module, "generate_images",
                        lambda prompt, model, client=None, style=None: (time.sleep(0.3), [(b"p", "png")])[1])
    monkeypatch.setattr(api_module.insp_api, "save_pictures", lambda *a, **k: saved.append(a) or {})
    job = api.ai_start("image_regenerate", {"image_id": "x"})["job"]
    api.ai_cancel(job)
    time.sleep(0.6)
    assert api.ai_poll(job)["state"] == "cancelled" and saved == []
    assert wait(api, api.ai_start("image_regenerate", {"image_id": "x"})["job"])["state"] == "done"
    assert len(saved) == 1


@pytest.mark.parametrize("url", ["https://example.com/a?b=1", "http://example.com", "mailto:a@b.co"])
def test_open_external_opens_allowed_links(tmp_path, monkeypatch, url):
    api, _ = open_api(tmp_path)
    opened = []
    monkeypatch.setattr(api_module.webbrowser, "open", lambda u: opened.append(u) or True)
    assert api.open_external(url) == {"opened": True, "ok": True} and opened == [url]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "ftp://x.org", "/etc/passwd",
                                 "https://", "mailto:", "", "https://a.com/ b", "https://a.com/\nx",
                                 "data:text/html,hi", "vscode://x"])
def test_open_external_rejects_everything_else(tmp_path, monkeypatch, url):
    api, _ = open_api(tmp_path)
    opened = []
    monkeypatch.setattr(api_module.webbrowser, "open", lambda u: opened.append(u) or True)
    r = api.open_external(url)
    assert r["ok"] is False and r["error"] and opened == []
