"""AI spend tracking: ledger, response parsing, extra_body, status bar."""

import threading
from types import SimpleNamespace

from chisel.ai import usage
from chisel.ai.client import usage_extra_body
from chisel.ai.usage import LEDGER, UsageLedger, record_response
from chisel.core.project import Project
from chisel.tui import app as app_mod
from chisel.tui.app import ChiselApp


def test_ledger_math():
    ledger = UsageLedger()
    assert ledger.session_total() == 0
    assert ledger.last() is None
    ledger.record("m", "links", 0.01, 10, 5)
    ledger.record("m", "links", None)
    ledger.record("m", "canon", 0.0025)
    assert abs(ledger.session_total() - 0.0125) < 1e-9
    assert ledger.last().feature == "canon"
    assert ledger.count() == 3


def test_ledger_thread_safety_smoke():
    ledger = UsageLedger()

    def work():
        for _ in range(200):
            ledger.record("m", "f", 0.001)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ledger.count() == 1600
    assert abs(ledger.session_total() - 1.6) < 1e-6


def test_record_response_with_cost():
    resp = SimpleNamespace(usage=SimpleNamespace(
        cost=0.0031, prompt_tokens=100, completion_tokens=20))
    entry = record_response(resp, "some/model", "links")
    assert entry.cost == 0.0031
    assert (entry.prompt_tokens, entry.completion_tokens) == (100, 20)
    assert LEDGER.last() is entry


def test_record_response_tolerates_missing_usage():
    assert record_response(SimpleNamespace(), "m", "f").cost is None
    assert record_response(SimpleNamespace(usage=None), "m", "f").cost is None
    assert record_response(
        SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3)), "m", "f"
    ).cost is None
    assert record_response(
        SimpleNamespace(usage={"cost": "0.5"}), "m", "f").cost == 0.5
    assert record_response(
        SimpleNamespace(usage=SimpleNamespace(cost="junk")), "m", "f").cost is None
    assert LEDGER.session_total() == 0.5


def test_usage_extra_body_merges_provider():
    body = usage_extra_body({"provider": {"require_parameters": True}})
    assert body == {"provider": {"require_parameters": True},
                    "usage": {"include": True}}
    assert usage_extra_body(None) == {"usage": {"include": True}}


def test_call_sites_request_usage_and_record(monkeypatch):
    from chisel.ai.links import suggest_links

    seen = {}

    class Completions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content='{"mentions": []}'))],
                usage=SimpleNamespace(cost=0.002),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    suggest_links("text", [], "m", client=client)
    assert seen["extra_body"]["usage"] == {"include": True}
    assert seen["extra_body"]["provider"] == {"require_parameters": True}
    assert LEDGER.session_total() == 0.002


async def test_status_bar_shows_session_total(tmp_path, monkeypatch):
    proj = Project.create(tmp_path / "novel", title="Cost")
    proj.create_entity("Borin")

    def fake_suggest(text, entities, model):
        LEDGER.record(model, "links", 0.0123)
        return []

    monkeypatch.setattr(app_mod, "suggest_links", fake_suggest)
    notified: list[str] = []
    monkeypatch.setattr(
        ChiselApp, "notify",
        lambda self, message, **kw: notified.append(str(message)))
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "AI $" not in app._status_text
        app.action_find_aliases()
        await pilot.pause(1.0)
        assert "AI $0.0123" in app._status_text
        assert any("(AI $0.0123)" in m for m in notified), notified
