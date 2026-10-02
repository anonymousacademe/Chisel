"""AI alias finder: prompt, parse, validate — plus the TUI flow (mocked AI)."""

import json
from pathlib import Path

import pytest

import lorewrite.tui.app as app_mod
from lorewrite.ai.links import (
    Suggestion,
    alias_form,
    build_prompt,
    parse_suggestions,
    validate_suggestions,
)
from lorewrite.core import entities as ent
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.linkreview import AliasReviewScreen, LinkReviewScreen

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


def _raw(text, surface, entity="Borin", nth=0):
    start = -1
    for _ in range(nth + 1):
        start = text.index(surface, start + 1)
    return {"entity": entity, "start": start, "end": start + len(surface),
            "surface": surface}


TEXT = "# T\n\nThe old blacksmith spat. Borin nodded. The old blacksmith left.\n"


def test_validate_accepts_descriptive_reference():
    valid = validate_suggestions(TEXT, [_raw(TEXT, "The old blacksmith")], ENTITIES)
    assert [(v.entity, v.surface) for v in valid] == [("Borin", "The old blacksmith")]


def test_validate_drops_existing_name_and_alias_spans():
    text = "Elara Vance walked in. The old smith was drunk. Borin waved.\n"
    raw = [
        _raw(text, "Elara Vance", "Elara Vance"),   # canonical name
        _raw(text, "The old smith"),                # known alias (sentence start)
        _raw(text, "Borin"),                        # canonical name
    ]
    assert validate_suggestions(text, raw, ENTITIES) == []


def test_validate_drops_span_inside_known_mention():
    text = "Borin's boots were wet.\n"
    raw = [_raw(text, "Bori")]
    assert validate_suggestions(text, raw, ENTITIES) == []
    inside = [_raw(text, "orin")]
    assert validate_suggestions(text, inside, ENTITIES) == []


def test_validate_keeps_reference_that_merely_touches_a_known_name():
    text = "Borin's wife smiled.\n"
    valid = validate_suggestions(text, [_raw(text, "Borin's wife", "Elara Vance")],
                                 ENTITIES)
    assert [v.surface for v in valid] == ["Borin's wife"]


def test_validate_drops_pronouns_case_insensitively():
    text = "He said she would. They left, and I stayed. Its door. You too.\n"
    raw = [_raw(text, w, "Borin") for w in ("He", "she", "They", "I", "Its", "You")]
    assert validate_suggestions(text, raw, ENTITIES) == []


def test_validate_drops_too_short_and_too_long_surfaces():
    text = "x " + "very " * 12 + "old smith.\n"
    long_surface = text[:-2]
    assert len(long_surface) > 40
    raw = [
        {"entity": "Borin", "start": 0, "end": 1, "surface": "x"},
        {"entity": "Borin", "start": 0, "end": len(long_surface),
         "surface": long_surface},
    ]
    assert validate_suggestions(text, raw, ENTITIES) == []


def test_validate_dedupes_same_surface_and_entity():
    raw = [_raw(TEXT, "The old blacksmith"), _raw(TEXT, "The old blacksmith", nth=1)]
    assert len(validate_suggestions(TEXT, raw, ENTITIES)) == 1
    lower = [_raw(TEXT, "The old blacksmith"),
             {"entity": "Borin", "start": TEXT.rindex("The old blacksmith"),
              "end": TEXT.rindex("The old blacksmith") + 18,
              "surface": "The old blacksmith"}]
    assert len(validate_suggestions(TEXT, lower, ENTITIES)) == 1


def test_validate_drops_offset_drift():
    raw = [{"entity": "Borin", "start": 0, "end": 5, "surface": "Borin"}]
    assert validate_suggestions(SCENE, raw, ENTITIES) == []


def test_validate_drops_unknown_entity():
    raw = [_raw(TEXT, "The old blacksmith", "Gandalf")]
    assert validate_suggestions(TEXT, raw, ENTITIES) == []


def test_validate_skips_spans_touching_explicit_links_and_resolves_alias_entity():
    text = "[[Elara Vance]] and the forge master"
    raw = [
        {"entity": "Elara Vance", "start": 2, "end": 13, "surface": "Elara Vance"},
        {"entity": "the old smith", "start": 20, "end": 36,
         "surface": "the forge master"},
    ]
    valid = validate_suggestions(text, raw, ENTITIES)
    assert [(v.entity, v.surface) for v in valid] == [("Borin", "the forge master")]


def test_validate_dedupes_overlaps():
    raw = [_raw(TEXT, "The old blacksmith"), _raw(TEXT, "old blacksmith")]
    assert len(validate_suggestions(TEXT, raw, ENTITIES)) == 1


def test_alias_form_lowercases_leading_article_only():
    assert alias_form("The old smith") == "the old smith"
    assert alias_form("Her ladyship") == "her ladyship"
    assert alias_form("Thornwick's heir") == "Thornwick's heir"
    assert alias_form("The") == "The"


def test_apply_suggestions_is_gone():
    import lorewrite.ai.links as links_mod

    assert not hasattr(links_mod, "apply_suggestions")


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


def _tavern(tmp_path: Path):
    proj = Project.create(tmp_path / "novel", title="AI")
    proj.create_entity("Borin")
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text("# Tavern\n\nThe old smith drank.\n", encoding="utf-8", newline="\n")
    return proj, scene


async def test_find_aliases_accept_adds_alias_and_leaves_scene_untouched(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_links", _suggestions_for)
    proj, scene = _tavern(tmp_path)
    before = scene.read_bytes()

    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_find_aliases()
        await pilot.pause(1.0)
        assert isinstance(app.screen, AliasReviewScreen)
        await pilot.press("enter")  # accept all (default)
        await pilot.pause()
        assert app.editor.text == before.decode()
        note = (proj.entities_dir / "characters" / "borin.md").read_text()
        assert "the old smith" in note
        # index rebuilt: the alias is now recognized as a mention everywhere
        entity = ent.resolve("the old smith", app.entities)
        assert entity is not None and entity.name == "Borin"
        app.save_current()
    assert scene.read_bytes() == before


async def test_find_aliases_cancel_changes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_links", _suggestions_for)
    proj, scene = _tavern(tmp_path)
    note_path = proj.entities_dir / "characters" / "borin.md"
    note_before = note_path.read_text()

    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        before = app.editor.text
        app.action_find_aliases()
        await pilot.pause(1.0)
        assert isinstance(app.screen, AliasReviewScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert app.editor.text == before
    assert note_path.read_text() == note_before


async def test_alias_review_row_shows_context_and_toggle_excludes(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_links", _suggestions_for)
    proj, scene = _tavern(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_find_aliases()
        await pilot.pause(1.0)
        row = app.screen._row_text(0).plain
        assert row.startswith('[x] "The old smith" → Borin')
        assert "line 3: The old smith drank." in row
        await pilot.press("space")  # untick
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        note = (proj.entities_dir / "characters" / "borin.md").read_text()
        assert "old smith" not in note


async def test_find_aliases_failure_notifies(tmp_path: Path, monkeypatch):
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
        app.action_find_aliases()
        await pilot.pause(1.0)
        assert any("failed" in m for m in notified), notified


def test_old_names_still_resolve():
    assert LinkReviewScreen is AliasReviewScreen
    assert LorewriteApp.action_link_mentions is LorewriteApp.action_find_aliases
