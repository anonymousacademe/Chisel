"""M3 TUI integration: continuity check + story-bible update flows (AI mocked)."""

from pathlib import Path

import lorewrite.ai.continuity as ai_cont
from lorewrite.core.continuity import Contradiction, get_canon, load_waivers
from lorewrite.core.project import Project
from lorewrite.tui.app import LorewriteApp
from lorewrite.tui.continuityscreen import ContinuityScreen
from lorewrite.tui.noteupdates import NoteUpdateScreen


def _project(tmp_path: Path) -> Project:
    proj = Project.create(tmp_path / "novel", title="M3")
    proj.create_entity("Elara Vance")
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text("# Tavern\n\nElara's eyes were blue as ice.\n")
    return proj


def _fake_contradiction(scene_rel: str = "") -> Contradiction:
    return Contradiction(
        type="physical_attribute",
        severity="error",
        entity="Elara Vance",
        evidence="Elara's eyes were blue as ice",
        suggested_fix="Change to green (established in her note)",
        scene=scene_rel,
        row=2,
    )


async def test_check_continuity_flow_waive_and_jump(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ai_cont, "check_scene",
        lambda text, entities, canon, model, client=None: [_fake_contradiction()],
    )
    proj = _project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_check_continuity()
        await pilot.pause(1.0)
        assert isinstance(app.screen, ContinuityScreen)

        await pilot.press("space")  # waive it
        await pilot.pause()
        key = _fake_contradiction().waiver_key()
        assert key in load_waivers(proj.root)

        await pilot.press("enter")  # jump to the evidence line
        await pilot.pause()
        assert app.editor.cursor_location[0] == 2


async def test_check_continuity_none_found(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ai_cont, "check_scene",
        lambda text, entities, canon, model, client=None: [],
    )
    notified: list[str] = []
    monkeypatch.setattr(
        LorewriteApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    proj = _project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_check_continuity()
        await pilot.pause(1.0)
        assert not isinstance(app.screen, ContinuityScreen)
        assert any("No continuity issues" in m for m in notified)


async def test_check_continuity_failure_notifies(tmp_path: Path, monkeypatch):
    def boom(text, entities, canon, model, client=None):
        raise RuntimeError("API down")

    monkeypatch.setattr(ai_cont, "check_scene", boom)
    notified: list[str] = []
    monkeypatch.setattr(
        LorewriteApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    proj = _project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_check_continuity()
        await pilot.pause(1.0)
        assert any("failed" in m for m in notified)


async def test_update_bible_flow(tmp_path: Path, monkeypatch):
    update = ai_cont.CanonUpdate(
        entity="Elara Vance",
        existing_canon="",
        new_canon="Green eyes (until the tavern scene says otherwise).",
        justification="Scene states her eye color.",
    )
    monkeypatch.setattr(
        ai_cont, "propose_canon_updates",
        lambda text, entities, model, client=None: [update],
    )
    proj = _project(tmp_path)
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_update_bible()
        await pilot.pause(1.0)
        assert isinstance(app.screen, NoteUpdateScreen)
        await pilot.press("enter")  # accept all
        await pilot.pause()
        note = (proj.entities_dir / "characters" / "elara-vance.md").read_text()
        assert "Green eyes" in get_canon(note)
