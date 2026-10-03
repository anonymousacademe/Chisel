"""M3 TUI integration: continuity check + story-bible update flows (AI mocked)."""

from pathlib import Path

import chisel.ai.continuity as ai_cont
from chisel.core.continuity import Contradiction, get_canon, load_waivers
from chisel.core.project import Project
from chisel.tui.app import ChiselApp
from chisel.tui.continuityscreen import ContinuityScreen
from chisel.tui.noteupdates import NoteUpdateScreen


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
    app = ChiselApp(proj)
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
        assert not isinstance(app.screen, ContinuityScreen)  # report closed
        assert app.focused is app.editor


async def test_check_continuity_none_found(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ai_cont, "check_scene",
        lambda text, entities, canon, model, client=None: [],
    )
    notified: list[str] = []
    monkeypatch.setattr(
        ChiselApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    proj = _project(tmp_path)
    app = ChiselApp(proj)
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
        ChiselApp, "notify",
        lambda self, message, **kwargs: notified.append(str(message)),
    )
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_check_continuity()
        await pilot.pause(1.0)
        assert any("failed" in m for m in notified)


def _update(*facts, entity="Elara Vance", existing=""):
    return ai_cont.CanonUpdate(entity=entity, new_facts=tuple(facts),
                               evidence="scene says so", existing_canon=existing)


async def test_update_bible_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ai_cont, "propose_canon_updates",
        lambda text, entities, model, client=None: [_update("Green eyes")],
    )
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_update_bible()
        await pilot.pause(1.0)
        assert isinstance(app.screen, NoteUpdateScreen)
        await pilot.press("enter")  # accept all
        await pilot.pause()
        note = (proj.entities_dir / "characters" / "elara-vance.md").read_text()
        assert get_canon(note) == "- Green eyes"


async def test_second_bible_update_keeps_first_facts(tmp_path: Path, monkeypatch):
    replies = [[_update("Green eyes")], [_update("Left-handed", "Owns a boat")]]
    monkeypatch.setattr(
        ai_cont, "propose_canon_updates",
        lambda text, entities, model, client=None: replies.pop(0),
    )
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        for _ in range(2):
            app.action_update_bible()
            await pilot.pause(1.0)
            await pilot.press("enter")
            await pilot.pause()
    note = (proj.entities_dir / "characters" / "elara-vance.md").read_text()
    assert get_canon(note).splitlines() == [
        "- Green eyes", "- Left-handed", "- Owns a boat"]


async def test_bible_review_shows_long_facts_untruncated_and_toggles(
        tmp_path: Path, monkeypatch):
    long_fact = "Was born in the salt marshes of the far north, " * 6 + "END-MARK"
    monkeypatch.setattr(
        ai_cont, "propose_canon_updates",
        lambda text, entities, model, client=None: [
            _update(long_fact, "Short fact", existing="- Old fact one")],
    )
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_update_bible()
        await pilot.pause(1.0)
        screen = app.screen
        assert isinstance(screen, NoteUpdateScreen)
        first = screen._row_text(0).plain
        assert "END-MARK" in first and "..." not in first
        assert "- Old fact one" in first and first.startswith("Elara Vance")
        assert screen._row_text(1).plain == "[x] Short fact"
        # rendered: the long fact wraps over several lines inside the modal
        label = screen.query("#updates ListItem Label").first()
        assert label.size.height > 4 + 1                 # header lines + wrapped fact
        assert label.region.right <= screen.query_one("#updates").region.right
        await pilot.press("space")            # untick the long fact
        await pilot.pause()
        assert screen._row_text(0).plain.rstrip().endswith("END-MARK") is True
        assert "[ ] Was born" in screen._row_text(0).plain
        await pilot.press("enter")
        await pilot.pause()
    note = (proj.entities_dir / "characters" / "elara-vance.md").read_text()
    assert get_canon(note) == "- Short fact"


async def test_bible_review_cancel_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ai_cont, "propose_canon_updates",
        lambda text, entities, model, client=None: [_update("Green eyes")],
    )
    proj = _project(tmp_path)
    note_path = proj.entities_dir / "characters" / "elara-vance.md"
    before = note_path.read_text()
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_update_bible()
        await pilot.pause(1.0)
        await pilot.press("escape")
        await pilot.pause()
    assert note_path.read_text() == before


async def test_update_bible_strips_pending_drafts(tmp_path: Path, monkeypatch):
    from chisel.core import drafts

    seen = {}

    def fake(text, entities, model, client=None):
        seen["text"] = text
        return []

    monkeypatch.setattr(ai_cont, "propose_canon_updates", fake)
    proj = _project(tmp_path)
    scene = proj.manuscript_dir / "02-tavern.md"
    scene.write_text("# T\n\nElara sat. " + drafts.wrap("GHOST FACT") + "\n")
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.action_update_bible()
        await pilot.pause(1.0)
    assert "GHOST FACT" not in seen["text"]


async def test_restore_waived_clears_only_this_scenes_waivers(tmp_path: Path, monkeypatch):
    from chisel.core.continuity import save_waiver

    proj = _project(tmp_path)
    other = proj.manuscript_dir / "03-other.md"
    other.write_text("# Other\n\nx\n")
    scene = proj.manuscript_dir / "02-tavern.md"
    save_waiver(proj.root, "aaaa", "manuscript/02-tavern.md")
    save_waiver(proj.root, "bbbb", "manuscript/02-tavern.md")
    save_waiver(proj.root, "cccc", "manuscript/03-other.md")
    save_waiver(proj.root, "legacy")           # no scene recorded
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(scene)
        app.restore_waived()
        await pilot.pause()
    assert load_waivers(proj.root) == {"cccc", "legacy"}
    assert any("Restored 2 waived" in m for m in notified)


async def test_waive_via_report_records_scene_then_restore_reports_again(
        tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        ai_cont, "check_scene",
        lambda text, entities, canon, model, client=None: [_fake_contradiction()],
    )
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.action_check_continuity()
        await pilot.pause(1.0)
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        app.action_check_continuity()          # waived: nothing reported now
        await pilot.pause(1.0)
        assert not isinstance(app.screen, ContinuityScreen)
        app.restore_waived()
        await pilot.pause()
        assert load_waivers(proj.root) == set()
        app.action_check_continuity()
        await pilot.pause(1.0)
        assert isinstance(app.screen, ContinuityScreen)


async def test_restore_waived_with_nothing_to_restore_notifies(tmp_path: Path, monkeypatch):
    notified: list[str] = []
    monkeypatch.setattr(ChiselApp, "notify",
                        lambda self, message, **kw: notified.append(str(message)))
    proj = _project(tmp_path)
    app = ChiselApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_file(proj.manuscript_dir / "02-tavern.md")
        app.restore_waived()
        await pilot.pause()
    assert any("No waived continuity issues" in m for m in notified)


def test_restore_waived_in_palette():
    from chisel.tui.commands import ActionProvider

    assert "Restore waived continuity issues (this scene)" in [
        t for t, _, _ in ActionProvider.ACTIONS]
