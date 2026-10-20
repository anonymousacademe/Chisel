"""Canon proposals in the front ends: the bridge returns what was left out, the mock passes verification, the TUI says
how many facts were left out and keeps quotes with their facts."""

import json
from pathlib import Path

import pytest

import chisel.ai.continuity as ai_cont
from chisel.ai.continuity import CanonDropped, CanonProposal, CanonUpdate
from chisel.gui import api as api_module
from chisel.tui.app import ChiselApp
from chisel.tui.noteupdates import NoteUpdateScreen
from tests.test_continuity_ui import _project
from tests.test_gui_api import open_api

SCENE = "manuscript/01-arrival.md"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key (network is blocked in tests)")

    monkeypatch.setattr("chisel.ai.client.make_client", boom)


def test_bridge_returns_dropped_tolerant_and_the_left_out_sentence(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    update = CanonUpdate("Mara Vale", ("has a scar",), "she rubbed the scar", "", ("she rubbed the scar",), ("appearance",))
    dropped = (CanonDropped("Mara Vale", "drinks tea", "its quote is not in the scene"),
               CanonDropped("Mara Vale", "is tall", "it has no quote"),
               CanonDropped("Mara Vale", "is thin", "its quote is not in the scene"))
    monkeypatch.setattr(api_module, "propose_canon", lambda t, e, m: CanonProposal([update], dropped, 2))
    r = api.propose_canon(SCENE)
    assert r["ok"]
    assert r["updates"] == [{"entity": "Mara Vale", "facts": ["has a scar"], "evidence": "she rubbed the scar",
                             "existing": "", "quotes": ["she rubbed the scar"], "kinds": ["appearance"]}]
    assert r["dropped"][0] == {"entity": "Mara Vale", "fact": "drinks tea", "reason": "its quote is not in the scene"}
    assert len(r["dropped"]) == 3 and r["tolerant"] == 2
    assert r["left_out"] == ("3 proposed facts were left out because the passage it quoted is not in the scene; "
                             "the others for other reasons.")
    assert "sent" in r and "cost" in r


def test_bridge_with_nothing_left_out_has_empty_fields(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    monkeypatch.setattr(api_module, "propose_canon", lambda t, e, m: CanonProposal([]))
    r = api.propose_canon(SCENE)
    assert (r["updates"], r["dropped"], r["tolerant"], r["left_out"]) == ([], [], 0, "")


def test_bridge_through_a_fake_client_drops_unquoted_facts(tmp_path, monkeypatch):
    """The whole path with only the network faked: an old-shape reply is dropped for having no quote."""
    from unittest.mock import MagicMock

    api, _ = open_api(tmp_path)
    raw = json.dumps({"updates": [{"entity": "Mara Vale", "new_facts": ["has a scar"], "evidence": "x"}]})
    msg = MagicMock()
    msg.content = raw
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg)])
    real = ai_cont.propose_canon
    monkeypatch.setattr(api_module, "propose_canon", lambda t, e, m, **kw: real(t, e, m, client=client, **kw))
    r = api.propose_canon(SCENE)
    assert r["updates"] == [] and [d["reason"] for d in r["dropped"]] == ["it has no quote"]
    assert r["left_out"].startswith("1 proposed fact was left out")


def test_mock_proposal_passes_the_real_verification(tmp_path, monkeypatch):
    from chisel.gui import mockai

    for name in ("propose_canon", "propose_canon_updates", "get_api_key", "_set_api_key", "_clear_api_key",
                 "_list_models", "_list_local_models", "suggest_links", "check_scene", "voice_check",
                 "suggest_relationships", "learn_style", "generate_text", "ask_writer", "research_writer",
                 "brainstorm_writer", "generate_images", "suggest_image_prompt", "summarize_scene",
                 "summarize_part", "suggest_latex", "suggest_plot_code"):
        monkeypatch.setattr(api_module, name, getattr(api_module, name, None), raising=False)
    monkeypatch.setattr(mockai, "_pause", lambda *a, **k: None)
    mockai.install(api_module)
    api, _ = open_api(tmp_path)
    r = api.propose_canon(SCENE)
    assert r["ok"], r
    assert r["updates"] and r["dropped"] == []
    (u,) = r["updates"][:1]
    assert u["quotes"] and u["quotes"][0] in api.read_document(SCENE)["text"].replace("\n", " ")
    assert u["evidence"] == " / ".join(u["quotes"])
    # the plain function too: its result is a CanonProposal that survived parse_canon
    p = api_module.propose_canon("# T\n\nMara walked in.\n", [api.entities[0]], "m")
    assert isinstance(p, CanonProposal) and p.dropped == () and p.updates[0].quotes == ("Mara walked in.",)


async def test_tui_says_how_many_facts_were_left_out(tmp_path: Path, monkeypatch):
    update = CanonUpdate("Elara Vance", ("has green eyes",), "q", "", ("q",), ("appearance",))
    dropped = (CanonDropped("Elara Vance", "is tall", "it has no quote"),
               CanonDropped("Elara Vance", "is old", "it has no quote"))
    monkeypatch.setattr(ai_cont, "propose_canon", lambda text, entities, model, client=None: CanonProposal([update], dropped))
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify", lambda self, message, **kwargs: notified.append(str(message)))
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_update_bible()
        await pilot.pause(1.0)
        assert isinstance(app.screen, NoteUpdateScreen)
    assert any("2 proposed facts were left out because it came without a quote" in m for m in notified)


async def test_tui_all_facts_left_out_still_says_so(tmp_path: Path, monkeypatch):
    dropped = (CanonDropped("Elara Vance", "is tall", "its quote is not in the scene"),)
    monkeypatch.setattr(ai_cont, "propose_canon", lambda text, entities, model, client=None: CanonProposal([], dropped))
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify", lambda self, message, **kwargs: notified.append(str(message)))
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_update_bible()
        await pilot.pause(1.0)
    assert any(m.startswith("No new canon found in this scene; 1 proposed fact was left out") for m in notified)


def test_review_screen_keeps_quotes_with_the_accepted_facts():
    u = CanonUpdate("E", ("a", "b", "c"), "qa / qb / qc", "", ("qa", "qb", "qc"), ("age", "place", "other"))
    screen = NoteUpdateScreen([u])
    screen._accepted = {(0, 0), (0, 2)}
    out = []
    screen.dismiss = out.append
    screen.action_apply()
    (kept,) = out[0]
    assert (kept.new_facts, kept.quotes, kept.kinds, kept.evidence) == (("a", "c"), ("qa", "qc"), ("age", "other"), "qa / qc")
