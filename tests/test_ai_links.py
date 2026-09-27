"""M2 AI linking: prompt, parse, validate, apply — plus the TUI flow (mocked AI)."""

import json
from pathlib import Path

import pytest

import lorewrite.tui.app as app_mod
from lorewrite.ai.links import (
    Suggestion,
    apply_suggestions,
    build_prompt,
    parse_suggestions,
    validate_suggestions,
)
from lorewrite.core import entities as ent
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.linkreview import LinkReviewScreen

ELARA = ent.Entity(name="Elara Vance", aliases=["the captain"])
BORIN = ent.Entity(name="Borin", aliases=["the old smith"])
ENTITIES = [ELARA, BORIN]

SCENE = "# Tavern\n\nElara Vance walked in. The old smith was drunk. Borin waved.\n"


# -- prompt ---------------------------------------------------------------------


def test_build_prompt_includes_roster_and_scene():
    prompt = build_prompt(SCENE, ENTITIES)
    assert "Elara Vance (character)" in prompt
    assert "aliases: the captain" in prompt
    assert SCENE in prompt


# -- parse ------------------------------------------------------------------------


def test_parse_good_json():
    raw = json.dumps({"mentions": [{"entity": "Borin", "start": 0, "end": 5,
                                    "surface": "Borin"}]})
    assert len(parse_suggestions(raw)) == 1


def test_parse_junk_returns_empty():
    assert parse_suggestions("not json") == []
    assert parse_suggestions('{"mentions": "oops"}') == []
    assert parse_suggestions("[]") == []


# -- validate -----------------------------------------------------------------------


def test_validate_accepts_mentions_and_skips_linked():
    raw = [
        {"entity": "Elara Vance", "start": 10, "end": 21,
         "surface": "Elara Vance"},
        {"entity": "Borin", "start": SCENE.index("The old smith"),
         "end": SCENE.index("The old smith") + len("The old smith"),
         "surface": "The old smith"},
        {"entity": "Borin", "start": SCENE.index("Borin waved"),
         "end": SCENE.index("Borin waved") + 5, "surface": "Borin"},
    ]
    valid = validate_suggestions(SCENE, raw, ENTITIES)
    assert len(valid) == 3
    assert valid[0].entity == "Elara Vance"


def test_validate_drops_offset_drift():
    raw = [{"entity": "Borin", "start": 0, "end": 5, "surface": "Borin"}]
    assert validate_suggestions(SCENE, raw, ENTITIES) == []


def test_validate_drops_unknown_entity():
    start = SCENE.index("The old smith")
    raw = [{"entity": "Gandalf", "start": start, "end": start + 13,
            "surface": "The old smith"}]
    assert validate_suggestions(SCENE, raw, ENTITIES) == []


def test_validate_skips_already_linked_and_resolves_alias():
    text = "[[Elara Vance]] and The old smith"
    raw = [
        {"entity": "Elara Vance", "start": 2, "end": 13,
         "surface": "Elara Vance"},
        {"entity": "the old smith", "start": 20, "end": 33,
         "surface": "The old smith"},
    ]
    valid = validate_suggestions(text, raw, ENTITIES)
    assert [v.entity for v in valid] == ["Borin"]  # alias resolved to canonical


def test_validate_dedupes_overlaps():
    raw = [
        {"entity": "Elara Vance", "start": 10, "end": 21,
         "surface": "Elara Vance"},
        {"entity": "Elara Vance", "start": 10, "end": 15, "surface": "Elara"},
    ]
    valid = validate_suggestions(SCENE, raw, ENTITIES)
    assert len(valid) == 1


# -- apply ---------------------------------------------------------------------------


def test_apply_wraps_spans_back_to_front():
    suggestions = validate_suggestions(SCENE, [
        {"entity": "Elara Vance", "start": 10, "end": 21,
         "surface": "Elara Vance"},
        {"entity": "Borin", "start": SCENE.index("Borin waved"),
         "end": SCENE.index("Borin waved") + 5, "surface": "Borin"},
    ], ENTITIES)
    result = apply_suggestions(SCENE, suggestions)
    assert "[[Elara Vance]] walked in" in result
    assert "[[Borin]] waved" in result
    # untouched text stays put
    assert "The old smith was drunk." in result


# -- aliases ---------------------------------------------------------------------------


def test_add_alias_dedupes_and_saves(tmp_path: Path):
    path = tmp_path / "borin.md"
    ent.save_entity(ent.Entity(name="Borin", aliases=["the old smith"]), path)
    entity = ent.load_entity(path)
    ent.add_alias(entity, "smithy")
    ent.add_alias(entity, "SMITHY")  # duplicate, case-insensitive
    ent.add_alias(entity, "borin")   # same as the name
    loaded = ent.load_entity(path)
    assert loaded.aliases == ["the old smith", "smithy"]


# -- TUI flow (AI mocked) -----------------------------------------------------------------


def _suggestions_for(text, entities, model):
    start = text.index("The old smith")
    return [Suggestion("Borin", start, start + 13, "The old smith")]


async def test_link_mentions_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_links", _suggestions_for)
    proj = Project.create(tmp_path / "novel", title="AI")
    proj.create_entity("Borin")
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text("# Tavern\n\nThe old smith drank.\n")

    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_link_mentions()
        await pilot.pause(1.0)
        assert isinstance(app.screen, LinkReviewScreen)
        await pilot.press("enter")  # accept all (default)
        await pilot.pause()
        assert "[[The old smith]]" in app.editor.text
        # alias-learning confirm is up: surface isn't a known alias
        from lorewrite.tui.app import ConfirmScreen
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        note = (proj.entities_dir / "characters" / "borin.md").read_text()
        assert "The old smith" in note


async def test_link_mentions_cancel_changes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_links", _suggestions_for)
    proj = Project.create(tmp_path / "novel", title="AI")
    proj.create_entity("Borin")
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text("# Tavern\n\nThe old smith drank.\n")

    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        before = app.editor.text
        app.action_link_mentions()
        await pilot.pause(1.0)
        await pilot.press("escape")
        await pilot.pause()
        assert app.editor.text == before


async def test_link_mentions_failure_notifies(tmp_path: Path, monkeypatch):
    def boom(text, entities, model):
        raise RuntimeError("No OpenRouter API key")

    monkeypatch.setattr(app_mod, "suggest_links", boom)
    proj = Project.create(tmp_path / "novel", title="AI")
    proj.create_entity("Borin")

    app = LorewriteApp(proj)
    notified: list[str] = []
    monkeypatch.setattr(
        LorewriteApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_link_mentions()
        await pilot.pause(1.0)
        assert any("failed" in m for m in notified), notified
