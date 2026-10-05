"""The TUI flow for AI relationship suggestions (AI mocked at the module boundary)."""

from pathlib import Path

import pytest

import chisel.tui.app as app_mod
from chisel.ai.relationships import Suggestion
from chisel.core import entities as ent
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.relationreview import RelationshipReviewScreen

ROW = "- [[Imogen Sallow]] — owes her a favour"


def _project(tmp_path: Path):
    proj = Project.create(tmp_path / "novel", title="Rel")
    rook = proj.entities_dir / "characters" / "rook-tanaka.md"
    imogen = proj.entities_dir / "characters" / "imogen-sallow.md"
    ent.save_entity(ent.Entity(name="Rook Tanaka",
                               body="Captain of the Ember Rose.\n"), rook)
    ent.save_entity(ent.Entity(name="Imogen Sallow",
                               body="Harbourmaster of Grey Harbour.\n"), imogen)
    return proj, rook


def _suggestions(entity, others, model):
    return [Suggestion("Imogen Sallow", "owes her a favour")]


async def test_suggest_relationships_accept_writes_note_and_rereads_buffer(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_relationships", _suggestions)
    proj, rook = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(rook)
        await pilot.pause()
        app.action_suggest_relationships()
        await pilot.pause(1.0)
        assert isinstance(app.screen, RelationshipReviewScreen)
        assert app.screen._row_text(0).plain == \
            f"[x] owes her a favour — [[Imogen Sallow]]"
        await pilot.press("enter")  # accept all (default)
        await pilot.pause()
        note = rook.read_text(encoding="utf-8")
        assert "## Relationships" in note
        assert ROW in note
        assert ROW in app.editor.text  # the buffer was re-read from disk
        assert app._dirty is False


async def test_suggest_relationships_cancel_changes_nothing(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_relationships", _suggestions)
    proj, rook = _project(tmp_path)
    before = rook.read_text(encoding="utf-8")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(rook)
        await pilot.pause()
        text_before = app.editor.text
        app.action_suggest_relationships()
        await pilot.pause(1.0)
        assert isinstance(app.screen, RelationshipReviewScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert app.editor.text == text_before
    assert rook.read_text(encoding="utf-8") == before


async def test_suggest_relationships_needs_an_entity_note(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_relationships", _suggestions)
    proj, rook = _project(tmp_path)
    scene = proj.manuscript_dir / "01-harbour.md"
    scene.write_text("# Harbour\n\nRook Tanaka drank.\n",
                     encoding="utf-8", newline="\n")
    app = ChiselApp(proj)
    notified: list[str] = []
    monkeypatch.setattr(
        ChiselApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        app.action_suggest_relationships()
        await pilot.pause(1.0)
        assert not isinstance(app.screen, RelationshipReviewScreen)
        assert any("entity note" in m for m in notified), notified
        assert not any("Added" in m for m in notified), notified


async def test_suggest_relationships_needs_another_entity(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app_mod, "suggest_relationships", _suggestions)
    proj = Project.create(tmp_path / "solo", title="Solo")
    rook = proj.entities_dir / "characters" / "rook-tanaka.md"
    ent.save_entity(ent.Entity(name="Rook Tanaka", body="Alone.\n"), rook)
    app = ChiselApp(proj)
    notified: list[str] = []
    monkeypatch.setattr(
        ChiselApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(rook)
        await pilot.pause()
        app.action_suggest_relationships()
        await pilot.pause(1.0)
        assert not isinstance(app.screen, RelationshipReviewScreen)
        assert any("other entities" in m for m in notified), notified
