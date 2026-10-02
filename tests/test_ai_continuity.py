"""AI continuity checking: prompt, parse, check_scene, canon updates, jev gate.

Tests the contract pinned in docs/dev/specification-guide.md §2.2.
Skips cleanly if lorewrite.ai.continuity has not landed yet.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ai_cont = pytest.importorskip("lorewrite.ai.continuity")

from lorewrite.ai.continuity import (
    ACCUMULATION_SCHEMA,
    CONTRADICTION_SCHEMA,
    CanonUpdate,
    build_check_prompt,
    check_scene,
    parse_contradictions,
    parse_canon_updates,
    propose_canon_updates,
)
from lorewrite.core import entities as ent
from lorewrite.core.continuity import Contradiction

SCENE = "# Tavern\n\nElara Vance walked in. Her eyes were brown.\n"
ENTITIES = [ent.Entity(name="Elara Vance", type="character")]
CANON = {"Elara Vance": "Elara has blue eyes."}


# -- schemas exist --------------------------------------------------------------


def test_contradiction_schema_is_dict():
    assert isinstance(CONTRADICTION_SCHEMA, dict)
    assert "contradictions" in CONTRADICTION_SCHEMA["properties"]


def test_accumulation_schema_is_dict():
    assert isinstance(ACCUMULATION_SCHEMA, dict)
    assert "updates" in ACCUMULATION_SCHEMA["properties"]


# -- build_check_prompt ---------------------------------------------------------


def test_build_check_prompt_includes_canon_and_scene():
    prompt = build_check_prompt(SCENE, CANON)
    assert "Elara Vance" in prompt
    assert "blue eyes" in prompt
    assert SCENE in prompt


# -- parse_contradictions -------------------------------------------------------


def test_parse_contradictions_good_json():
    raw = json.dumps({"contradictions": [
        {"type": "physical_attribute", "severity": "error", "entity": "Elara Vance",
         "evidence": "eyes described as brown", "suggested_fix": "change to blue"},
    ]})
    result = parse_contradictions(raw, SCENE, "ch1.md")
    assert len(result) == 1
    assert isinstance(result[0], Contradiction)
    assert result[0].entity == "Elara Vance"
    assert result[0].scene == "ch1.md"


def test_parse_contradictions_locates_row():
    raw = json.dumps({"contradictions": [
        {"type": "physical_attribute", "severity": "error", "entity": "Elara Vance",
         "evidence": "Her eyes were brown", "suggested_fix": "change to blue"},
    ]})
    result = parse_contradictions(raw, SCENE, "ch1.md")
    assert result[0].row is not None


def test_parse_contradictions_junk_json_returns_empty():
    assert parse_contradictions("not json", SCENE, "ch1.md") == []
    assert parse_contradictions('{"contradictions": "oops"}', SCENE, "ch1.md") == []
    assert parse_contradictions("[]", SCENE, "ch1.md") == []


def test_parse_contradictions_invalid_items_dropped():
    raw = json.dumps({"contradictions": [
        {"type": "physical_attribute", "severity": "error", "entity": "Elara Vance",
         "evidence": "eyes brown", "suggested_fix": "fix"},
        {"type": "bogus_type", "severity": "error", "entity": "X",
         "evidence": "y", "suggested_fix": "z"},
    ]})
    result = parse_contradictions(raw, SCENE, "ch1.md")
    assert len(result) == 1


# -- parse_canon_updates --------------------------------------------------------


def test_parse_canon_updates_good_json():
    raw = json.dumps({"updates": [
        {"entity": "Elara Vance", "new_facts": ["Has brown eyes"],
         "evidence": "her eyes were brown"},
    ]})
    result = parse_canon_updates(raw)
    assert len(result) == 1
    assert isinstance(result[0], CanonUpdate)
    assert result[0].entity == "Elara Vance"
    assert result[0].new_facts == ("Has brown eyes",)


def test_parse_canon_updates_junk_returns_empty():
    assert parse_canon_updates("not json") == []
    assert parse_canon_updates('{"updates": "bad"}') == []
    assert parse_canon_updates('{"updates": [{"entity": "E", "new_facts": "x"}]}') == []


def test_parse_validates_against_entities():
    elara = ent.Entity(name="Elara Vance", aliases=["the captain"],
                       body="## Canon (auto)\n\n- Has blue eyes\n- Owns a boat\n")
    raw = json.dumps({"updates": [
        {"entity": "Gandalf", "new_facts": ["Grey"], "evidence": ""},
        {"entity": "the captain",
         "new_facts": ["has blue eyes.", "- Owns a BOAT", "", "  ", "Scar on hand",
                       "scar on hand", "Afraid of water"],
         "evidence": "e"},
    ]})
    (u,) = parse_canon_updates(raw, [elara])
    assert u.entity == "Elara Vance"  # canonicalized from the alias
    assert u.new_facts == ("Scar on hand", "Afraid of water")
    assert "Has blue eyes" in u.existing_canon


def test_parse_drops_entity_when_every_fact_is_a_duplicate():
    elara = ent.Entity(name="Elara", body="## Canon (auto)\n\n- Tall\n")
    raw = json.dumps({"updates": [
        {"entity": "Elara", "new_facts": ["tall"], "evidence": ""}]})
    assert parse_canon_updates(raw, [elara]) == []


# -- check_scene with fake client -----------------------------------------------


def _make_fake_client(raw_json: str):
    msg = MagicMock()
    msg.content = raw_json
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def test_check_scene_with_fake_client(monkeypatch):
    monkeypatch.setattr(
        "lorewrite.ai.continuity.pre_screen",
        lambda *a, **kw: None,
    )
    raw = json.dumps({"contradictions": [
        {"type": "physical_attribute", "severity": "error", "entity": "Elara Vance",
         "evidence": "eyes described as brown", "suggested_fix": "change to blue"},
    ]})
    client = _make_fake_client(raw)
    result = check_scene(SCENE, ENTITIES, CANON, model="test-model", client=client)
    assert len(result) >= 1
    client.chat.completions.create.assert_called_once()


# -- propose_canon_updates with fake client -------------------------------------


def test_propose_canon_updates_with_fake_client():
    raw = json.dumps({"updates": [
        {"entity": "Elara Vance", "new_facts": ["Has brown eyes"],
         "evidence": "scene says brown"},
    ]})
    client = _make_fake_client(raw)
    result = propose_canon_updates(SCENE, ENTITIES, model="test-model", client=client)
    assert [u.new_facts for u in result] == [("Has brown eyes",)]
    client.chat.completions.create.assert_called_once()


def test_propose_sends_existing_canon_capped_and_asks_for_additions():
    from lorewrite.ai.continuity import CANON_CAP

    long_canon = "- " + "x" * 3000
    elara = ent.Entity(name="Elara Vance", body=f"## Canon (auto)\n\n{long_canon}\n")
    other = ent.Entity(name="Borin", body="## Canon (auto)\n\n- Has one arm\n")
    client = _make_fake_client('{"updates": []}')
    propose_canon_updates(SCENE, [elara, other], model="m", client=client)
    kwargs = client.chat.completions.create.call_args.kwargs
    user = kwargs["messages"][1]["content"]
    assert "- Has one arm" in user
    assert "- " + "x" * (CANON_CAP - 2) in user
    assert "x" * (CANON_CAP - 1) not in user
    assert "ADDITIONS" in kwargs["messages"][0]["content"]
    assert "FULL replacement" not in kwargs["messages"][0]["content"]
    props = kwargs["response_format"]["json_schema"]["schema"]["properties"]["updates"]
    assert "new_facts" in props["items"]["properties"]


# -- jev gate -------------------------------------------------------------------


def test_check_scene_jev_gate_returns_empty_without_calling_client(monkeypatch):
    monkeypatch.setattr(
        "lorewrite.ai.continuity.pre_screen",
        lambda *a, **kw: [],
    )
    client = MagicMock()
    result = check_scene(SCENE, ENTITIES, CANON, model="test-model", client=client)
    assert result == []
    client.chat.completions.create.assert_not_called()


# -- Jev pre-screen reply parsing ------------------------------------------------


def test_pre_screen_reads_current_jev_reply_shape(monkeypatch):
    from lorewrite.core import jev_interface as J

    replies = {"Elara Vance": 0.85}
    monkeypatch.setattr(J, "jev_available", lambda: True)
    monkeypatch.setattr(J, "_ask", lambda state, q: {
        "answers": {"contradiction": {
            "type": "noul", "noul": replies.get(state["canon"]["entity"], 0.1)}},
        "ms": 250, "model": "typesafe/jev"})
    assert J.pre_screen(SCENE, ENTITIES, CANON) == ["Elara Vance"]


def test_pre_screen_fails_open_on_unknown_reply_shape(monkeypatch):
    from lorewrite.core import jev_interface as J

    monkeypatch.setattr(J, "jev_available", lambda: True)
    monkeypatch.setattr(J, "_ask", lambda state, q: {"something": "else"})
    assert J.pre_screen(SCENE, ENTITIES, CANON) is None  # None = check everything


def test_contradiction_score_shapes():
    from lorewrite.core.jev_interface import _contradiction_score as score

    assert score({"answers": {"contradiction": {"noul": 0.7}}}) == 0.7
    assert score({"answers": {"contradiction": 0.4}}) == 0.4
    assert score({"contradiction": 0.9}) == 0.9  # older top-level shape
    assert score({"answers": {}}) is None
    assert score({"answers": {"contradiction": {"noul": "x"}}}) is None


def test_make_client_sets_timeout_and_retries(monkeypatch):
    from lorewrite.ai import client as C

    monkeypatch.setattr(C, "get_api_key", lambda: "sk-test")
    c = C.make_client()
    assert c.max_retries == C.MAX_RETRIES
    assert float(getattr(c.timeout, "read", c.timeout)) == C.REQUEST_TIMEOUT
