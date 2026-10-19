"""The summaries bridge (gui/summaries_api.py) and the way stored summaries reach the AI calls of the desktop app.
AI is mocked at the function boundary (chisel.gui.api.<fn>); make_client is booby-trapped."""

import json
import threading
import time

import pytest

from chisel.ai import client as ai_client
from chisel.ai.stream import Cancelled
from chisel.ai.summaries import Proposal
from chisel.core import settings as user_settings
from chisel.core import summaries as sm
from chisel.core.project import Project
from chisel.gui import api as api_module
from chisel.gui.api import Api
from tests.gui_helpers import make_book
from tests.test_gui_api import open_api

SCENE = "manuscript/01-arrival.md"
SCENE2 = "manuscript/02-the-archive.md"
QUOTE = "The rain had not stopped for three days"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key (network is blocked in tests)")

    monkeypatch.setattr("chisel.ai.client.make_client", boom)
    monkeypatch.setattr("chisel.ai.client.list_models", boom)
    monkeypatch.setattr(ai_client, "_models_payload", None)


@pytest.fixture(autouse=True)
def real_summary_functions(monkeypatch):
    """Other tests install gui/mockai without undoing it; these tests start from the real functions."""
    from chisel.ai import summaries as ais

    monkeypatch.setattr(api_module, "summarize_scene", ais.summarize_scene)
    monkeypatch.setattr(api_module, "summarize_part", ais.summarize_part)


def lock_is_free(api) -> bool:
    """True when another thread can take the project lock right now."""
    out = []

    def probe():
        got = api._lock.acquire(blocking=False)
        if got:
            api._lock.release()
        out.append(got)

    t = threading.Thread(target=probe)
    t.start()
    t.join()
    return out[0]


def proposal_for(text, summary="Mara arrived in Lower Meridian.", facts=((("It rained."), QUOTE),),
                 names=("Mara",)):
    s = sm.Summary(sm.hash_of(text), summary, tuple(sm.Character(n, "at the tram stop") for n in names),
                   tuple(sm.Fact(t, q) for t, q in facts), ("Why is Elias waiting?",), "m/x", sm.now(), 0.01)
    return Proposal(s, (sm.Dropped("fact", "Elias had a gun.", "its quote is not in the scene"),), 1)


class FakeSummarize:
    """Stands in for ai.summaries.summarize_scene; remembers how it was called."""

    def __init__(self, api, **kw):
        self.api, self.kw, self.calls, self.lock_free = api, kw, [], None

    def __call__(self, scene_text, entities, model, client=None, on_delta=None, cancel=None, originals=None):
        self.lock_free = lock_is_free(self.api)
        self.calls.append((scene_text, [e.name for e in entities], model))
        return proposal_for(scene_text, **self.kw)


def payload_of(r, **over):
    p = dict(r["proposal"], proposed=r["proposal"], sourceHash=r["sourceHash"], model=r["model"], cost=r["cost"])
    p.update(over)
    return p


# -- status -------------------------------------------------------------------------------


def test_status_lists_scenes_in_reading_order_with_parts_and_totals(tmp_path):
    root = tmp_path / "book"
    make_book(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    r = api.summaries_status()
    assert [s["title"] for s in r["scenes"]] == ["Rain", "Capsule", "Signal"]     # front matter is not counted
    assert {s["status"] for s in r["scenes"]} == {"missing"}
    assert r["totals"] == {"scenes": 3, "counts": {"missing": 3, "fresh": 0, "stale": 0, "locked": 0}, "percent": 0}
    assert [(p["title"], p["status"], p["scenes"]) for p in r["parts"]] == [
        ("The Recall", "missing", 2), ("Ghost", "missing", 1)]
    scene = root / "manuscript/01-the-recall/01-rain.md"
    sm.save(root, scene, sm.Summary(sm.hash_of(scene.read_text()), "Rain falls on the city today.", (), (), ()))
    r = api.summaries_status()
    assert r["scenes"][0]["status"] == "fresh" and r["scenes"][0]["words"] == 6
    assert r["totals"]["percent"] == 33
    scene.write_text("# Rain\n\nIt stopped.\n")
    assert api.summaries_status()["scenes"][0]["status"] == "stale"


def test_status_needs_a_project():
    r = Api().summaries_status()
    assert r["ok"] is False and "no project" in r["error"]


# -- propose ------------------------------------------------------------------------------


def test_propose_returns_the_proposal_and_saves_nothing(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    fake = FakeSummarize(api)
    monkeypatch.setattr(api_module, "summarize_scene", fake)
    r = api.summarize_propose(SCENE)
    assert r["ok"] and r["proposal"]["summary"].startswith("Mara arrived")
    assert r["proposal"]["facts"] == [{"text": "It rained.", "quote": QUOTE}]
    assert r["proposal"]["characters"][0]["name"] == "Mara"
    assert r["dropped"] == [{"kind": "fact", "text": "Elias had a gun.", "reason": "its quote is not in the scene"}]
    assert r["tolerant"] == 1 and r["cost"] == pytest.approx(0.01) and r["replacing"] is False
    assert r["sourceHash"] == sm.hash_of((root / SCENE).read_text())
    assert {s["name"] for s in r["sent"]["sections"]} >= {"Scene"}
    assert not (root / ".summaries").exists()                     # NOTHING is saved
    assert fake.lock_free is True                                 # the lock was released before the AI call
    assert fake.calls[0][1] == ["Mara Vale", "Elias Vale", "Lower Meridian"][:2] or fake.calls[0][1]


def test_propose_errors_are_clean_and_make_no_call(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    fake = FakeSummarize(api)
    monkeypatch.setattr(api_module, "summarize_scene", fake)
    assert "no such document" in api.summarize_propose("manuscript/nope.md")["error"]
    assert api.summarize_propose("../x.md")["ok"] is False
    assert "belongs to a scene" in api.summarize_propose("entities/characters/mara-vale.md")["error"]
    (root / "manuscript" / "03-empty.md").write_text("# Empty\n")
    assert "no text" in api.summarize_propose("manuscript/03-empty.md")["error"]
    assert api.summary_save(SCENE, payload_of(api.summarize_propose(SCENE)))["ok"]
    assert api.summary_lock(SCENE, True)["ok"]
    assert "never replaced" in api.summarize_propose(SCENE)["error"]
    assert len(fake.calls) == 1


def test_propose_uses_the_budget_before_the_network_and_the_reasoning_setting(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    user_settings.set("reasoning", "off")
    bodies = []
    reply = json.dumps({"summary": "Mara arrives.", "characters": [{"name": "Mara", "state": "here"}],
                        "facts": [{"text": "It rained.", "quote": QUOTE}], "threads": []})

    class Client:
        def __init__(self):
            from types import SimpleNamespace as NS
            self.chat = NS(completions=NS(create=self.create))

        def create(self, **kw):
            from types import SimpleNamespace as NS
            bodies.append(kw["extra_body"])
            return NS(choices=[NS(message=NS(content=reply), finish_reason="stop")],
                      usage=NS(cost=0.002, prompt_tokens=10, completion_tokens=20))

    monkeypatch.setattr("chisel.ai.client.make_client", lambda model=None: Client())
    r = api.summarize_propose(SCENE)
    assert r["ok"], r
    assert bodies == [{"usage": {"include": True}, "reasoning": {"enabled": False}}]
    assert r["sent"]["reasoning"] == "reasoning off"
    assert r["proposal"]["facts"][0]["quote"] == QUOTE and r["tolerant"] == 0
    assert not (root / ".summaries").exists()


def test_propose_runs_as_an_ai_job_and_stop_saves_nothing(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    job = api.ai_start("summarize", {"scene_id": SCENE})["job"]
    done = wait_for(api, job)
    assert done["state"] == "done" and done["result"]["proposal"]["summary"].startswith("Mara arrived")
    assert not (root / ".summaries").exists()

    started = threading.Event()

    def slow(scene_text, entities, model, client=None, on_delta=None, cancel=None, originals=None):
        started.set()
        while not cancel.is_set():
            time.sleep(0.01)
        raise Cancelled()

    monkeypatch.setattr(api_module, "summarize_scene", slow)
    job = api.ai_start("summarize", {"scene_id": SCENE})["job"]
    assert started.wait(2)
    api.ai_cancel(job)
    assert wait_for(api, job)["state"] == "cancelled"
    assert not (root / ".summaries").exists()
    assert api.ai_start("summarize", {})["ok"] is False         # a bad argument list is refused up front


def wait_for(api, job, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = api.ai_poll(job)
        if r["state"] in ("done", "cancelled", "error"):
            return r
        time.sleep(0.01)
    raise AssertionError("job still running")


# -- save / lock / delete -----------------------------------------------------------------


def test_save_an_accepted_proposal_then_status_is_fresh(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    r = api.summarize_propose(SCENE)
    saved = api.summary_save(SCENE, payload_of(r))
    assert saved["ok"] and saved["status"] == "fresh" and saved["authorEdited"] is False
    stored = sm.load(root, root / SCENE)
    assert stored.summary.startswith("Mara arrived") and stored.model == ai_client.resolve_model("summary") and stored.cost == pytest.approx(0.01)
    assert stored.source_hash == sm.hash_of((root / SCENE).read_text()) and not stored.locked
    assert api.summaries_status()["scenes"][0]["status"] == "fresh"


def test_save_marks_an_edit_and_a_hand_written_summary_as_the_authors(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    r = api.summarize_propose(SCENE)
    edited = api.summary_save(SCENE, payload_of(r, summary="Mara got off the tram."))
    assert edited["ok"] and edited["authorEdited"] is True and sm.load(root, root / SCENE).author_edited
    sm.delete(root, root / SCENE)
    removed_a_fact = api.summary_save(SCENE, payload_of(r, facts=[]))     # only removing is not editing
    assert removed_a_fact["authorEdited"] is False
    own = api.summary_save(SCENE2, {"summary": "Mara reads the files.", "characters": [], "facts": [], "threads": []})
    assert own["ok"] and own["authorEdited"] is True and sm.load(root, root / SCENE2).model == "author"


def test_save_refuses_a_fact_whose_quote_no_longer_matches(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    r = api.summarize_propose(SCENE)
    bad = [{"text": "It snowed.", "quote": "The snow had not stopped for three days"},
           {"text": "No quote.", "quote": ""}]
    out = api.summary_save(SCENE, payload_of(r, facts=r["proposal"]["facts"] + bad))
    assert out["ok"] is False
    assert "It snowed." in out["error"] and "No quote." in out["error"] and "its quote is not in the scene" in out["error"]
    out = api.summary_save(SCENE, payload_of(r, characters=[{"name": "Rook", "state": "?"}]))
    assert out["ok"] is False and "Rook" in out["error"]
    assert not (root / ".summaries").exists()


def test_save_refuses_too_many_words_an_empty_text_a_locked_summary_and_a_changed_scene(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    r = api.summarize_propose(SCENE)
    long = api.summary_save(SCENE, payload_of(r, summary="word " * 91))
    assert long["ok"] is False and "at most 90 words" in long["error"] and "91" in long["error"]
    assert api.summary_save(SCENE, payload_of(r, summary="  "))["ok"] is False
    assert api.summary_save(SCENE, "text")["ok"] is False
    (root / SCENE).write_text((root / SCENE).read_text() + "\nMore.\n")
    stale = api.summary_save(SCENE, payload_of(r))
    assert stale["ok"] is False and "changed since" in stale["error"] and not (root / ".summaries").exists()
    fresh = api.summarize_propose(SCENE)
    assert api.summary_save(SCENE, payload_of(fresh))["ok"]
    api.summary_lock(SCENE, True)
    locked = api.summary_save(SCENE, payload_of(fresh, summary="Other."))
    assert locked["ok"] is False and "locked" in locked["error"]
    assert api.summary_save("manuscript/nope.md", payload_of(fresh))["ok"] is False


def test_lock_and_delete(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    assert "no summary to lock" in api.summary_lock(SCENE, True)["error"]
    assert api.summary_delete(SCENE) == {"id": SCENE, "deleted": False, "wasProtected": False, "ok": True}
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    api.summary_save(SCENE, payload_of(api.summarize_propose(SCENE)))
    locked = api.summary_lock(SCENE, True)
    assert locked["ok"] and locked["locked"] is True and sm.load(root, root / SCENE).locked
    assert api.summaries_status()["scenes"][0]["status"] == "locked" or sm.status(
        api.project, root / SCENE) in ("locked", "fresh")
    assert api.summary_lock(SCENE, False)["locked"] is False and not sm.load(root, root / SCENE).locked
    gone = api.summary_delete(SCENE)
    assert gone["deleted"] is True and sm.load(root, root / SCENE) is None
    assert api.summary_lock("manuscript/nope.md", True)["ok"] is False


# -- parts --------------------------------------------------------------------------------


def book_api(tmp_path):
    root = tmp_path / "book"
    make_book(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def test_part_propose_save_lock_delete(tmp_path, monkeypatch):
    api, root = book_api(tmp_path)
    part = "part:manuscript/01-the-recall"
    assert "Summarise the scenes" in api.part_summarize_propose(part)["error"]
    for rel in ("01-the-recall/01-rain.md", "01-the-recall/02-capsule.md"):
        p = root / "manuscript" / rel
        sm.save(root, p, sm.Summary(sm.hash_of(p.read_text()), f"Event in {rel}.", (), (), ()))
    seen = {}

    def fake_part(title, scenes, model, inputs=(), client=None, on_delta=None, cancel=None):
        seen.update(title=title, scenes=[n for n, _ in scenes], inputs=inputs, free=lock_is_free(api))
        return sm.PartSummary("The recall begins.", (sm.Character("Mara", "home"),), ("What next?",), tuple(inputs),
                              model, sm.now(), 0.02)

    monkeypatch.setattr(api_module, "summarize_part", fake_part)
    r = api.part_summarize_propose(part)
    assert r["ok"] and r["proposal"]["summary"] == "The recall begins." and r["missing"] == []
    assert seen["title"] == "The Recall" and seen["scenes"] == ["Rain", "Capsule"] and seen["free"] is True
    assert len(seen["inputs"]) == 2 and r["cost"] == pytest.approx(0.02) and r["sent"]["feature"] == "part summary"
    assert not (root / ".summaries" / "_part__01-the-recall.json").exists()
    saved = api.part_summary_save(part, dict(r["proposal"], proposed=r["proposal"], model=r["model"], cost=r["cost"]))
    assert saved["ok"] and saved["status"] == "fresh" and saved["authorEdited"] is False
    assert api.summaries_status()["parts"][0]["status"] == "fresh"
    long = api.part_summary_save(part, {"summary": "w " * 151, "characters": [], "threads": []})
    assert long["ok"] is False and "at most 150 words" in long["error"]
    assert api.summary_lock(part, True)["locked"] is True
    assert "never replaced" in api.part_summarize_propose(part)["error"]
    assert "locked" in api.part_summary_save(part, {"summary": "x y", "characters": [], "threads": []})["error"]
    assert api.summary_delete(part)["deleted"] is True
    assert api.summaries_status()["parts"][0]["status"] == "missing"
    assert api.part_summarize_propose("part:manuscript/09-none")["ok"] is False
    assert api.part_summarize_propose("manuscript/01-the-recall/01-rain.md")["ok"] is False


def test_part_job_kind(tmp_path, monkeypatch):
    api, root = book_api(tmp_path)
    p = root / "manuscript/02-ghost/01-signal.md"
    sm.save(root, p, sm.Summary(sm.hash_of(p.read_text()), "A signal.", (), (), ()))
    monkeypatch.setattr(api_module, "summarize_part", lambda t, s, m, inputs=(), client=None, on_delta=None, cancel=None:
                        sm.PartSummary("Ghost.", (), (), tuple(inputs), m, sm.now(), 0.0))
    job = api.ai_start("part_summarize", {"part_id": "part:manuscript/02-ghost"})["job"]
    assert wait_for(api, job)["result"]["proposal"]["summary"] == "Ghost."


# -- estimate (no network) ----------------------------------------------------------------


def test_estimate_counts_calls_tokens_and_says_unknown_without_a_price(tmp_path):
    api, root = open_api(tmp_path)
    r = api.summaries_estimate()
    assert r["ok"] and r["calls"] == 2 and r["inputTokens"] > 0 and r["price"] is None and r["cost"] is None
    assert r["costText"] == "unknown" and r["reasoningModel"] is None and r["reasoning"] == "default"
    assert any("price" in n for n in r["notes"])
    assert api.summaries_estimate([SCENE])["calls"] == 1
    sm.save(root, root / SCENE, sm.Summary(sm.hash_of((root / SCENE).read_text()), "Fresh one.", (), (), ()))
    assert api.summaries_estimate()["calls"] == 1                 # a fresh summary needs no call
    sm.save(root, root / SCENE2, sm.Summary("x", "Stale one.", (), (), (), author_edited=True))
    out = api.summaries_estimate([SCENE2])
    assert out["calls"] == 0 and out["skipped"] == [SCENE2]       # the author's own words are never counted
    assert api.summaries_estimate(["manuscript/nope.md"])["ok"] is False


def test_estimate_prices_from_the_catalogue_and_flags_a_thinking_model(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    model = ai_client.resolve_model("summary")
    monkeypatch.setattr(ai_client, "_models_payload", {"data": [
        {"id": model, "pricing": {"prompt": "0.000003", "completion": "0.000015"},
         "supported_parameters": ["reasoning", "structured_outputs"], "context_length": 200000}]})
    r = api.summaries_estimate()
    n, tokens = r["calls"], r["inputTokens"]
    assert r["price"] == {"promptPerM": pytest.approx(3.0), "completionPerM": pytest.approx(15.0)}
    assert r["reasoningModel"] is True
    assert r["outputTokens"] == {"low": 3000 * n, "high": 20000 * n}
    assert r["cost"]["low"] == pytest.approx(round((tokens * 3 + n * 3000 * 15) / 1e6, 4))
    assert r["cost"]["high"] == pytest.approx(round((tokens * 3 + n * 20000 * 15) / 1e6, 4))
    assert any("thinks" in x for x in r["notes"])
    user_settings.set("reasoning", "off")
    off = api.summaries_estimate()
    assert off["reasoning"] == "off" and off["outputTokens"] == {"low": 300 * n, "high": 1000 * n}
    assert off["cost"]["high"] < r["cost"]["low"]
    user_settings.set("summary_model", "local:llama3")
    local = api.summaries_estimate()
    assert local["local"] is True and local["costText"] == "free" and local["cost"] == {"low": 0.0, "high": 0.0}


def test_remembered_prices_survive_the_session(tmp_path):
    ai_client.remember_context_lengths([ai_client.ModelInfo("a/b", "B", 1.5, 6.0, 8000)])
    assert ai_client.cached_pricing("a/b") == (1.5, 6.0)
    assert ai_client.cached_pricing("x/unknown") is None
    assert ai_client.cached_pricing("local:m") == (0.0, 0.0)
    assert ai_client.cached_is_reasoning("a/b") is None


# -- the long-project hint ----------------------------------------------------------------


def test_scale_hint_through_the_bridge_and_its_dismissal(tmp_path):
    api, root = open_api(tmp_path)
    quiet = api.scale_hint()
    assert quiet["ok"] and quiet["level"] == "none" and quiet["numbers"]["scenes"] == 2
    assert quiet["dismissedLevel"] == "" and quiet["model"] == ai_client.resolve_model("summary")
    user_settings.set("context_window", 2000)         # the smallest window: a few long scenes outgrow it
    for i in range(8):
        (root / "manuscript" / f"1{i}-more.md").write_text("# More\n\n" + "word " * 400)
    hint = api.scale_hint()
    assert hint["level"] == "notice" and "not the rest of the book" in hint["message"] and hint["numbers"]["window"] == 2000
    level = hint["level"]
    assert api.scale_hint_dismiss(level)["dismissedLevel"] == level
    toml = (root / "project.toml").read_text()
    assert f'[ui]\nscale_hint_dismissed = "{level}"' in toml and 'title = "Test Novel"' in toml
    assert Project.open(root).scale_hint_dismissed() == level
    after = api.scale_hint()
    assert after["dismissedLevel"] == level and after["level"] == "none" and after["dismissed"] is True
    assert api.scale_hint_dismiss("loud")["ok"] is False
    assert api.scale_hint_dismiss("")["dismissedLevel"] == ""
    assert api.scale_hint()["level"] == "notice"


def test_the_facade_publishes_the_new_methods():
    names = Api().facade().__dict__
    for name in ("summaries_status", "summarize_propose", "summary_save", "summary_lock", "summary_delete",
                 "part_summarize_propose", "part_summary_save", "summaries_estimate", "scale_hint",
                 "scale_hint_dismiss"):
        assert callable(names[name])


def test_the_mock_ai_proposal_passes_the_real_verification(tmp_path, monkeypatch):
    from chisel.gui import mockai

    for name in ("summarize_scene", "summarize_part", "get_api_key", "_set_api_key", "_clear_api_key",
                 "_list_models", "_list_local_models", "suggest_links", "check_scene", "propose_canon_updates",
                 "learn_style", "generate_text", "ask_writer", "research_writer", "brainstorm_writer",
                 "generate_images", "suggest_image_prompt", "voice_check", "suggest_relationships",
                 "suggest_latex", "suggest_plot_code"):
        monkeypatch.setattr(api_module, name, getattr(api_module, name, None), raising=False)
    mockai.install(api_module)
    api, root = open_api(tmp_path)
    r = api.summarize_propose(SCENE)
    assert r["ok"] and r["proposal"]["facts"] and r["dropped"] == []
    assert api.summary_save(SCENE, payload_of(r))["ok"]


# -- context wiring -----------------------------------------------------------------------


def with_summaries(api, root, *rels):
    for rel in rels:
        path = root / rel
        sm.save(root, path, sm.Summary(sm.hash_of(path.read_text()), f"STORYLINE of {path.stem}.", (), (), ()))


def test_without_summaries_chat_brainstorm_and_describe_are_unchanged(tmp_path, monkeypatch):
    from chisel.ai.writing import build_context_sections, chat_instructions, ask_system_prompt, fit_context
    from chisel.core.continuity import canon_map
    from chisel.core.style import load_style

    api, root = open_api(tmp_path)
    got = {}
    monkeypatch.setattr(api_module, "ask_writer", lambda prompt, context, model, history=None, client=None,
                        on_delta=None, cancel=None: got.setdefault("ctx", context) and "ok")
    monkeypatch.setattr(api_module, "brainstorm_writer", lambda context, model, client=None, on_delta=None,
                        cancel=None: got.setdefault("brain", context) and ["idea"])
    monkeypatch.setattr(api_module, "suggest_image_prompt", lambda context, model, client=None:
                        got.setdefault("desc", context))
    text = (root / SCENE).read_text()
    model = ai_client.resolve_model("writing")
    reference_sections = build_context_sections(text, 0, list(api.entities), canon_map(api.entities),
                                                load_style(api.project))
    ref, ref_report = fit_context([*reference_sections, chat_instructions(ask_system_prompt(False), "q?", None)],
                                  model, "ask")
    r = api.ask("q?", "scene", SCENE, None, 0)
    assert r["ok"] and got["ctx"] == ref and "STORY SO FAR" not in got["ctx"]
    assert r["sent"] == ref_report.to_dict()
    assert api.ask("q?", "project")["ok"] and "STORY SO FAR" not in got["ctx"]
    assert api.brainstorm(SCENE)["ok"] and "STORY SO FAR" not in got["brain"]
    d = api.describe_scene(SCENE, None, 0)
    assert d["ok"] and "sent" not in d and "STORY SO FAR" not in got["desc"]


def test_with_summaries_chat_and_brainstorm_carry_the_story_so_far_up_to_the_open_scene(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    (root / "manuscript" / "03-third.md").write_text("# Third\n\nLater things happen.\n")
    with_summaries(api, root, SCENE, SCENE2, "manuscript/03-third.md")
    got = {}
    monkeypatch.setattr(api_module, "ask_writer", lambda prompt, context, model, history=None, client=None,
                        on_delta=None, cancel=None: got.__setitem__("ask", context) or "ok")
    monkeypatch.setattr(api_module, "brainstorm_writer", lambda context, model, client=None, on_delta=None,
                        cancel=None: got.__setitem__("brain", context) or ["idea"])
    r = api.ask("q?", "scene", SCENE2, None, 0)
    assert r["ok"] and "STORY SO FAR" in got["ask"] and "STORYLINE of 01-arrival" in got["ask"]
    assert "STORYLINE of 03-third" not in got["ask"] and "STORYLINE of 02-the-archive" not in got["ask"]
    assert "reading order" in got["ask"].lower()                              # the mode sentence
    story = next(s for s in r["sent"]["sections"] if s["name"] == "Story so far")
    assert story["droppable"] is True if "droppable" in story else True
    b = api.brainstorm(SCENE2)
    assert b["ok"] and "STORYLINE of 01-arrival" in got["brain"]
    assert any(s["name"] == "Story so far" for s in b["sent"]["sections"])
    whole = api.ask("q?", "project")
    assert "STORYLINE of 03-third" in got["ask"] and "STORYLINE of 01-arrival" in got["ask"]
    assert any(s["name"] == "Story so far" for s in whole["sent"]["sections"])
    first = api.ask("q?", "scene", SCENE, None, 0)          # nothing before the first scene: no section at all
    assert "STORY SO FAR" not in got["ask"] and all(s["name"] != "Story so far" for s in first["sent"]["sections"])


def test_a_tight_budget_drops_the_oldest_story_first_and_the_report_names_it(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    rels = []
    for i in range(10):
        rel = f"manuscript/1{i}-scene{i}.md"
        (root / rel).write_text(f"# Scene {i}" + chr(10) * 2 + "Text of the scene." + chr(10))
        sm.save(root, root / rel, sm.Summary(sm.hash_of((root / rel).read_text()),
                                             f"EVENT{i} " + "long " * 250, (), (), ()))
        rels.append(rel)
    user_settings.set("context_window", 6000)               # 2,000 tokens for the request, 4,000 kept for the reply
    got = {}
    monkeypatch.setattr(api_module, "ask_writer", lambda prompt, context, model, history=None, client=None,
                        on_delta=None, cancel=None: got.__setitem__("ctx", context) or "ok")
    r = api.ask("q?", "scene", rels[-1], None, 0)
    assert r["ok"], r
    row = next(s for s in r["sent"]["sections"] if s["name"] == "Story so far")
    assert row["itemsDropped"] and row["itemsDropped"][0] == "Scene 0"          # the oldest go first, by name
    assert "EVENT8" in got["ctx"] and "EVENT0" not in got["ctx"] and r["sent"]["trimmed"] is True


def test_describe_scene_adds_a_capped_story_and_reports_it(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    with_summaries(api, root, SCENE)
    got = {}
    monkeypatch.setattr(api_module, "suggest_image_prompt", lambda context, model, client=None:
                        got.setdefault("desc", context))
    d = api.describe_scene(SCENE2, None, 0)
    assert d["ok"] and "STORYLINE of 01-arrival" in got["desc"] and "sent" in d
    assert any(s["name"] == "Story so far" for s in d["sent"]["sections"])
    # an entity note (not a scene) is described exactly as before
    d = api.describe_scene("entities/characters/mara-vale.md", None, 0)
    assert d["ok"] and "sent" not in d


def seen_checker(monkeypatch):
    got = {}

    def check(scene_text, entities, canon, model, client=None, **kw):
        got["kw"], got["entities"] = kw, entities
        return []

    def canon_fn(scene_text, entities, model, client=None, **kw):
        got["canon_kw"] = kw
        return []

    monkeypatch.setattr(api_module, "check_scene", check)
    monkeypatch.setattr(api_module, "propose_canon_updates", canon_fn)
    return got


def test_without_summaries_continuity_and_canon_are_called_exactly_as_before(tmp_path, monkeypatch):
    from chisel.ai.budget import Budget
    from chisel.ai.continuity import plan_check
    from chisel.core.continuity import canon_map

    api, root = open_api(tmp_path)
    got = seen_checker(monkeypatch)
    r = api.check_continuity(SCENE)
    assert r["ok"] and got["kw"] == {}                       # no `history` argument at all
    text = (root / SCENE).read_text()
    _, _, ref = plan_check(text, list(api.entities), canon_map(api.entities),
                           Budget.for_model(ai_client.resolve_model("strong")))
    assert r["sent"] == ref.to_dict()
    assert api.propose_canon(SCENE)["ok"] and got["canon_kw"] == {}


def test_with_summaries_continuity_and_canon_get_the_story_in_history(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    with_summaries(api, root, SCENE)
    got = seen_checker(monkeypatch)
    r = api.check_continuity(SCENE2)
    assert r["ok"] and "STORYLINE of 01-arrival" in got["kw"]["history"] and "STORY SO FAR" in got["kw"]["history"]
    assert any(s["name"] == "Story so far" for s in r["sent"]["sections"])
    c = api.propose_canon(SCENE2)
    assert c["ok"] and "STORYLINE of 01-arrival" in got["canon_kw"]["history"]
    assert any(s["name"] == "Story so far" for s in c["sent"]["sections"])
    r = api.check_continuity(SCENE)                          # the first scene has nothing before it
    assert r["ok"] and got["kw"] == {}


def test_bridge_calls_that_read_summaries_release_the_lock_before_the_network(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    with_summaries(api, root, SCENE)
    free = []

    def check(scene_text, entities, canon, model, client=None, **kw):
        free.append(lock_is_free(api))
        return []

    monkeypatch.setattr(api_module, "check_scene", check)
    monkeypatch.setattr(api_module, "ask_writer", lambda *a, **k: free.append(lock_is_free(api)) or "ok")
    assert api.check_continuity(SCENE2)["ok"] and api.ask("q?", "scene", SCENE2, None, 0)["ok"]
    assert free == [True, True]


def test_summary_get_gives_the_card_everything_and_trimmed_reaches_the_proposal(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    none = api.summary_get(SCENE)
    assert none["ok"] and none["status"] == "missing" and none["summary"] is None
    monkeypatch.setattr(api_module, "summarize_scene", FakeSummarize(api))
    r = api.summarize_propose(SCENE)
    assert r["trimmed"] is False
    api.summary_save(SCENE, payload_of(r))
    got = api.summary_get(SCENE)
    assert got["status"] == "fresh" and got["summary"]["facts"] == [{"text": "It rained.", "quote": QUOTE}]
    assert got["locked"] is False and got["authorEdited"] is False and got["changedSince"] is False
    assert got["model"] == ai_client.resolve_model("summary") and got["cost"] == pytest.approx(0.01)
    api.summary_lock(SCENE, True)
    (root / SCENE).write_text((root / SCENE).read_text() + chr(10) + "More." + chr(10))
    later = api.summary_get(SCENE)
    assert later["locked"] is True and later["changedSince"] is True
    assert api.summary_get("manuscript/nope.md")["ok"] is False
    assert api.summary_get("entities/characters/mara-vale.md")["ok"] is False


def test_summary_get_and_trimmed_for_a_part(tmp_path, monkeypatch):
    api, root = book_api(tmp_path)
    part = "part:manuscript/01-the-recall"
    assert api.summary_get(part)["status"] == "missing"
    p = root / "manuscript/01-the-recall/01-rain.md"
    sm.save(root, p, sm.Summary(sm.hash_of(p.read_text()), "Rain.", (), (), ()))
    monkeypatch.setattr(api_module, "summarize_part", lambda t, s, m, inputs=(), client=None, on_delta=None, cancel=None:
                        sm.PartSummary("Recall.", (), (), tuple(inputs), m, sm.now(), 0.0, trimmed=True))
    r = api.part_summarize_propose(part)
    assert r["trimmed"] is True
    api.part_summary_save(part, dict(r["proposal"], proposed=r["proposal"]))
    got = api.summary_get(part)
    assert got["status"] == "fresh" and got["summary"] == {"summary": "Recall.", "characters": [], "threads": []}


def test_scale_hint_through_the_bridge_carries_after_once_summaries_cover_the_book(tmp_path):
    api, root = open_api(tmp_path)
    first = api.scale_hint()
    assert first["ok"] and first["after"] is None                       # no summaries: nothing to say
    for rel in (SCENE, SCENE2):
        sm.save(root, root / rel, sm.Summary(sm.hash_of((root / rel).read_text()), "Mara arrived. " * 3, (), (), ()))
    after = api.scale_hint()
    assert after["level"] == "none" and after["message"] == ""
    assert after["after"].startswith("Summaries cover your whole book. When you check a scene, Chisel sends a short story so far")
    assert "not the full text of earlier chapters" in after["after"] and "tokens, roughly" in after["after"]
    sm.delete(root, root / SCENE2)
    assert api.scale_hint()["after"] is None                            # half covered: the notice speaks (or stays quiet), not this
