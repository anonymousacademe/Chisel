"""Draft originals live in <project>/.drafts/<scene>.json, not in the prose."""

import json
from pathlib import Path

import pytest

import lorewrite.tui.app as app_mod
from lorewrite.core import drafts
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project.create(tmp_path / "novel", title="Sidecar")


def _sidecar(project: Project, scene: Path) -> Path:
    return project.root / ".drafts" / f"{scene.name}.json"


async def _rewrite(app, pilot, scene, monkeypatch, body="Rewritten line."):
    monkeypatch.setattr(app_mod, "generate",
                        lambda *a, **k: body)
    from textual.widgets.text_area import Selection

    line = app.editor.text.split("\n")[2]
    a = line.index("Change")
    app.editor.selection = Selection((2, a), (2, a + len("Change this bit.")))
    await pilot.pause()
    await pilot.press("ctrl+g")
    await pilot.pause()
    await pilot.press("ctrl+g")
    await pilot.pause(1.0)


def _mk(project: Project, name="02-scene.md") -> Path:
    scene = project.manuscript_dir / name
    scene.write_text("# S\n\nKeep this. Change this bit. Keep that.\n")
    return scene


async def test_rewrite_uses_short_id_and_sidecar_then_reject_restores(project, monkeypatch):
    scene = _mk(project)
    before = scene.read_text()
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        await _rewrite(app, pilot, scene, monkeypatch)
        text = app.editor.text
        (p,) = drafts.find_pending(text)
        assert p.id is not None and len(p.id) == 6
        assert "Change this bit." not in text  # no encoded blob, no copy either
        assert "replaces" not in text
        assert json.loads(_sidecar(project, scene).read_text()) == {
            p.id: "Change this bit."}
        app.editor.move_cursor((2, 30))
        await pilot.pause()
        app.action_reject_draft()
        await pilot.pause()
        assert app.editor.text == before
        assert not _sidecar(project, scene).exists()


async def test_accept_removes_marker_and_sidecar_entry(project, monkeypatch):
    scene = _mk(project)
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        await _rewrite(app, pilot, scene, monkeypatch)
        assert _sidecar(project, scene).is_file()
        app.editor.move_cursor((2, 30))
        await pilot.pause()
        app.action_accept_draft()
        await pilot.pause()
        assert app.editor.text == "# S\n\nKeep this. Rewritten line. Keep that.\n"
        assert not _sidecar(project, scene).exists()


async def test_missing_original_reject_refuses_and_changes_nothing(project, monkeypatch):
    scene = _mk(project)
    notified = []
    monkeypatch.setattr(LorewriteApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        await _rewrite(app, pilot, scene, monkeypatch)
        _sidecar(project, scene).unlink()          # sidecar deleted by hand
        before = app.editor.text
        app.editor.move_cursor((2, 30))
        await pilot.pause()
        app.action_reject_draft()
        await pilot.pause()
        assert app.editor.text == before           # nothing deleted
        assert any("Original text for this draft is missing" in m for m in notified)
        # reject-all skips it and says so, then accept still works
        app.reject_all_drafts()
        await pilot.pause()
        assert app.editor.text == before
        assert any("left because the original text is missing" in m for m in notified)
        app.action_accept_draft()
        await pilot.pause()
        assert "Rewritten line." in app.editor.text and "<!--" not in app.editor.text


async def test_nothing_written_under_lorewrite_cache(project, monkeypatch):
    scene = _mk(project)
    app = LorewriteApp(project)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        await pilot.pause()
        await _rewrite(app, pilot, scene, monkeypatch)
        app.save_current()
    assert _sidecar(project, scene).is_file()
    assert not any("drafts" in str(p) or p.suffix == ".json" and p.name == scene.name + ".json"
                   for p in (project.root / ".lorewrite").rglob("*"))
    gi = (project.root / ".gitignore").read_text()
    assert ".drafts" not in gi


def test_ids_are_unique_across_the_project(project):
    a, b = _mk(project, "02-a.md"), _mk(project, "03-b.md")
    drafts.add_original(project.root, a, "aaaaaa", "x")
    drafts.add_original(project.root, b, "bbbbbb", "y")
    assert drafts.all_ids(project.root) == {"aaaaaa", "bbbbbb"}
    for _ in range(50):
        assert drafts.new_id(drafts.all_ids(project.root)) not in {"aaaaaa", "bbbbbb"}


def test_move_scene_carries_sidecars_for_both_scenes(project):
    (project.manuscript_dir / "01-opening.md").unlink()
    a, b = _mk(project, "01-a.md"), _mk(project, "02-b.md")
    drafts.add_original(project.root, a, "aaaaaa", "from a")
    drafts.add_original(project.root, b, "bbbbbb", "from b")
    new_a = project.move_scene(a, 1)          # a becomes 02-a.md, b becomes 01-b.md
    assert new_a.name == "02-a.md"
    assert drafts.load_originals(project.root, new_a) == {"aaaaaa": "from a"}
    assert drafts.load_originals(project.root, project.manuscript_dir / "01-b.md") == {
        "bbbbbb": "from b"}
    assert sorted(p.name for p in (project.root / ".drafts").iterdir()) == [
        "01-b.md.json", "02-a.md.json"]


def test_move_scene_with_sidecar_on_only_one_side(project):
    (project.manuscript_dir / "01-opening.md").unlink()
    a, b = _mk(project, "01-a.md"), _mk(project, "02-b.md")
    drafts.add_original(project.root, b, "bbbbbb", "from b")
    project.move_scene(a, 1)
    assert drafts.load_originals(project.root, project.manuscript_dir / "01-b.md") == {
        "bbbbbb": "from b"}
    assert not (project.root / ".drafts" / "02-a.md.json").exists()


def test_delete_scene_removes_its_sidecar(project):
    a = _mk(project, "02-a.md")
    drafts.add_original(project.root, a, "aaaaaa", "x")
    project.delete_scene(a)
    assert not _sidecar(project, a).exists()


def test_rename_scene_title_keeps_sidecar(project):
    a = _mk(project, "02-a.md")
    drafts.add_original(project.root, a, "aaaaaa", "x")
    project.rename_scene(a, "New Title")     # title change; filename unchanged
    assert drafts.load_originals(project.root, a) == {"aaaaaa": "x"}


def test_word_count_and_context_use_sidecar(project):
    from lorewrite.ai.writing import CURSOR, build_context

    text = "one two " + drafts.wrap("ghost ghost", "abc123") + " three"
    originals = {"abc123": "REAL WORDS"}
    assert app_mod._word_count(text, originals) == 5
    ctx = build_context(text, 0, [], {}, None, originals=originals)
    assert "REAL WORDS" in ctx and "ghost" not in ctx
    assert CURSOR in ctx
