"""Inspiration images in the terminal app. AI mocked at chisel.tui.app; nothing is opened."""

from pathlib import Path

import pytest
from textual.widgets import Checkbox, Input, TextArea

from chisel.ai.usage import LEDGER
from chisel.core import inspiration as store
from chisel.core import settings as user_settings
from chisel.core.project import Project
from chisel.tui import app as app_module
from chisel.tui.app import ConfirmScreen, ChiselApp
from chisel.tui.commands import ActionProvider
from chisel.tui.inspirationscreens import InspirationListScreen, InspirationPromptScreen
from chisel.tui.settingscreen import ModelPicker, SettingsScreen
from chisel.tui.structurescreens import TrashScreen

PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 30
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 30


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").write_text("# Opening\n\nMara waited on the dark platform.\n")
    return p


@pytest.fixture
def opened(monkeypatch):
    """Record every 'open in the desktop' request instead of starting a viewer."""
    seen = []
    monkeypatch.setattr(ChiselApp, "open_external", lambda self, path: seen.append(Path(path)) or True)
    return seen


async def _settle(pilot, cond, n=30):
    for _ in range(n):
        await pilot.pause()
        if cond():
            return True
    return False


def test_palette_lists_the_inspiration_actions():
    got = {m: t for t, m, _ in ActionProvider.ACTIONS}
    assert got["inspiration_prompt"] == "Inspiration image…"
    assert {"open_inspiration", "open_last_inspiration", "open_inspiration_folder"} <= set(got)
    assert all(hasattr(ChiselApp, m) for m in got if "inspiration" in m)


async def test_describe_then_generate_saves_pinned_images_and_reports_the_path(tmp_path, monkeypatch, opened):
    p = _project(tmp_path)
    calls = []

    def fake_suggest(context, model, client=None):
        calls.append(("suggest", context, model))
        LEDGER.record(model, "image-prompt", 0.001)
        return "A dark subway platform, one flickering tube."

    def fake_generate(prompt, model, client=None, style=None):
        calls.append(("generate", prompt, model))
        LEDGER.record(model, "image", 0.034)
        return [(JPEG, "jpg")]

    monkeypatch.setattr(app_module, "suggest_image_prompt", fake_suggest)
    monkeypatch.setattr(app_module, "generate_image", fake_generate)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.inspiration_prompt()
        await pilot.pause()
        assert isinstance(app.screen, InspirationPromptScreen)
        await pilot.press("ctrl+d")                              # describe this scene
        assert await _settle(pilot, lambda: isinstance(app.screen, InspirationPromptScreen) and calls)
        await _settle(pilot, lambda: app.screen.query_one("#insp-input", TextArea).text)
        assert app.screen.query_one("#insp-input", TextArea).text == "A dark subway platform, one flickering tube."
        kind, context, model = calls[0]
        assert "Mara waited" in context and "<<CURSOR>>" in context and model == "google/gemini-2.5-flash"
        assert store.list_images(p) == []                         # describing generates and saves nothing
        await pilot.press("ctrl+g")                              # generate
        assert await _settle(pilot, lambda: store.list_images(p))
        (img,) = store.list_images(p)
        assert calls[1] == ("generate", "A dark subway platform, one flickering tube.", "google/gemini-3.1-flash-lite-image")
        assert img.path.read_bytes() == JPEG and img.scene == "manuscript/01-opening.md"
        assert img.pinned and img.cost == pytest.approx(0.034)
        assert opened == []                                       # nothing was opened by itself


async def test_generate_needs_a_description_and_failure_keeps_it(tmp_path, monkeypatch, opened):
    p = _project(tmp_path)
    from chisel.ai.images import ImageError

    def boom(prompt, model, client=None, style=None):
        raise ImageError("The model did not return an image: nope")

    monkeypatch.setattr(app_module, "generate_image", boom)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.inspiration_prompt()
        await pilot.pause()
        await pilot.press("ctrl+g")                              # empty: refused, window stays
        await pilot.pause()
        assert isinstance(app.screen, InspirationPromptScreen) and store.list_images(p) == []
        app.screen.query_one("#insp-input", TextArea).text = "A pier at dawn"
        await pilot.press("ctrl+g")
        await _settle(pilot, lambda: isinstance(app.screen, InspirationPromptScreen)
                      and app.screen.query_one("#insp-input", TextArea).text == "A pier at dawn" and not app.workers._workers)
        assert isinstance(app.screen, InspirationPromptScreen)   # back, with the text intact
        assert store.list_images(p) == []


async def test_not_pinning_and_no_scene(tmp_path, monkeypatch, opened):
    p = _project(tmp_path)
    monkeypatch.setattr(app_module, "generate_image", lambda prompt, model, client=None, style=None: [(PNG, "png")])
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.inspiration_prompt()
        await pilot.pause()
        app.screen.query_one("#insp-input", TextArea).text = "A pier"
        app.screen.query_one("#insp-pin", Checkbox).value = False
        await pilot.press("ctrl+g")
        assert await _settle(pilot, lambda: store.list_images(p))
        (img,) = store.list_images(p)
        assert img.scene == "manuscript/01-opening.md" and not img.pinned


async def test_list_open_pin_and_trash(tmp_path, opened):
    p = _project(tmp_path)
    scene = "manuscript/01-opening.md"
    a = store.save(p, JPEG, "jpg", {"prompt": "one", "scene": scene, "created": "2026-10-01T10:00:00"})
    b = store.save(p, PNG, "png", {"prompt": "two", "created": "2026-10-02T10:00:00"})
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_inspiration()
        await pilot.pause()
        assert isinstance(app.screen, InspirationListScreen)
        assert [i.id for i in app.screen._shown] == [a.id]       # this scene's pictures first
        await pilot.press("p")                                    # pin
        await pilot.pause()
        assert store.get(p, a.id).pinned
        assert isinstance(app.screen, InspirationListScreen)
        assert "pinned" in str(InspirationListScreen.row(store.get(p, a.id)))
        await pilot.press("a")                                    # all pictures
        await pilot.pause()
        assert [i.id for i in app.screen._shown] == [b.id, a.id]
        await pilot.press("o")                                    # open: only now is the viewer asked
        await pilot.pause()
        assert opened == [b.path]
        assert isinstance(app.screen, InspirationListScreen)       # reopened, scoped to the scene again
        await pilot.press("t")                                    # trash the highlighted one (a)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")
        await pilot.pause()
        assert [i.id for i in store.list_images(p)] == [b.id]
        assert p.list_trash()[0].kind == "inspiration"
        app.screen.dismiss(None)


async def test_open_last_and_open_folder_use_the_viewer_only_when_chosen(tmp_path, opened):
    p = _project(tmp_path)
    a = store.save(p, JPEG, "jpg", {"prompt": "old", "created": "2026-10-01T10:00:00"})
    b = store.save(p, PNG, "png", {"prompt": "new", "created": "2026-10-03T10:00:00"})
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert opened == []
        app.open_last_inspiration()
        app.open_inspiration_folder()
        assert opened == [b.path, p.root / "inspiration"]


async def test_trash_screen_lists_and_restores_images(tmp_path, opened):
    p = _project(tmp_path)
    a = store.save(p, JPEG, "jpg", {"prompt": "A tunnel"})
    p.trash_inspiration(a.id)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_trash()
        await pilot.pause()
        assert isinstance(app.screen, TrashScreen)
        assert "inspiration image" in TrashScreen._row(p.list_trash()[0])
        await pilot.press("enter")                                 # restore
        await pilot.pause()
        assert [i.id for i in store.list_images(p)] == [a.id]


async def test_settings_has_the_image_model_and_style(tmp_path):
    p = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.open_settings()
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert app.screen.query_one("#image-model", Input).placeholder == "google/gemini-3.1-flash-lite-image"
        assert app.screen.query_one("#image-style", Input).value == "cinematic, atmospheric, no text, no watermark"
        app.screen.query_one("#image-model", Input).value = "x/img"
        app.screen.query_one("#image-style", Input).value = "ink wash"
        app.screen._save()
        assert user_settings.get("image_model") == "x/img" and user_settings.get("image_style") == "ink wash"


async def test_image_picker_lists_only_image_models(tmp_path, monkeypatch):
    from chisel.ai.client import ModelInfo

    seen = {}

    def fake(timeout=10, structured_only=True, output_modality=None):
        seen.update(structured_only=structured_only, output_modality=output_modality)
        return [ModelInfo("g/img", "Img", 0.1, 30.0, 32000, ("image", "text"), 0.03)]

    monkeypatch.setattr("chisel.tui.settingscreen.list_models", fake)
    p = _project(tmp_path)
    app = ChiselApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ModelPicker("", structured_only=False, output_modality="image"))
        assert await _settle(pilot, lambda: seen)
        assert seen == {"structured_only": False, "output_modality": "image"}
