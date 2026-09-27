"""AI continuity checking: prompt, parse, check_scene, canon updates, jev gate.

Tests the contract pinned in docs/specification-guide.md §2.2.
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
        {"entity": "Elara Vance", "existing_canon": "blue eyes",
         "new_canon": "brown eyes", "justification": "scene says brown"},
    ]})
    result = parse_canon_updates(raw)
    assert len(result) == 1
    assert isinstance(result[0], CanonUpdate)
    assert result[0].entity == "Elara Vance"


def test_parse_canon_updates_junk_returns_empty():
    assert parse_canon_updates("not json") == []
    assert parse_canon_updates('{"updates": "bad"}') == []


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
        {"entity": "Elara Vance", "existing_canon": "blue eyes",
         "new_canon": "brown eyes", "justification": "scene says brown"},
    ]})
    client = _make_fake_client(raw)
    result = propose_canon_updates(SCENE, ENTITIES, model="test-model", client=client)
    assert len(result) >= 1
    client.chat.completions.create.assert_called_once()


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
