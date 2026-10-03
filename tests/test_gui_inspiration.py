"""Api: inspiration images - list, generate (mocked at the function boundary), pin, Trash, safety."""

import base64
import inspect

import pytest

from lorewrite.ai.usage import LEDGER
from lorewrite.gui import api as api_module
from lorewrite.gui import mockai
from lorewrite.core import inspiration as store
from tests.test_gui_api import open_api

JPEG = b"\xff\xd8\xff\xe0" + b"j" * 30
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 30
SCENE = "manuscript/01-arrival.md"


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []

    def fake_generate(prompt, model, client=None, style=None):
        calls.append(("generate", prompt, model, style))
        LEDGER.record(model, "image", 0.04, 10, 1000)
        return [(JPEG, "jpg"), (PNG, "png")]

    def fake_suggest(context, model, client=None):
        calls.append(("suggest", context, model))
        LEDGER.record(model, "image-prompt", 0.001, 10, 10)
        return "A rain-lit tram stop under a copper sky."

    monkeypatch.setattr(api_module, "generate_images", fake_generate)
    monkeypatch.setattr(api_module, "suggest_image_prompt", fake_suggest)
    a, root = open_api(tmp_path)
    a.calls, a.root = calls, root
    return a


def test_generate_saves_every_picture_and_splits_the_cost(api):
    r = api.generate_inspiration("A tram stop in the rain", SCENE, True)
    assert r["ok"] and r["cost"] == 0.04 and len(r["images"]) == 2
    assert [i["ext"] for i in r["images"]] == ["jpg", "png"]
    assert all(i["cost"] == 0.02 and i["scene"] == SCENE for i in r["images"])
    assert [i["pinned"] for i in r["images"]] == [True, False]       # only the first is pinned
    assert api.calls[0][:3] == ("generate", "A tram stop in the rain", "google/gemini-3.1-flash-lite-image")
    assert api.calls[0][3] == "cinematic, atmospheric, no text, no watermark"
    listed = api.list_inspiration()
    assert listed["ok"] and len(listed["images"]) == 2 and listed["model"].endswith("-image")


def test_generate_without_an_item_and_pin_needs_an_item(api):
    r = api.generate_inspiration("A pier", None, True)               # pin ignored: no item
    assert r["ok"] and not any(i["pinned"] for i in r["images"]) and r["images"][0]["for"] == ""
    assert api.generate_inspiration("   ")["ok"] is False
    assert api.generate_inspiration("A pier", "entities/characters/nobody.md")["ok"] is False   # names nothing
    assert api.generate_inspiration("A pier", "../x.md")["ok"] is False
    assert api.list_inspiration()["images"][0]["for"] == ""
    ok = api.generate_inspiration("A pier", "entities/characters/mara-vale.md", True)   # any kind is an item
    assert ok["ok"] and ok["images"][0]["for"] == "entities/characters/mara-vale.md" and ok["images"][0]["pinned"]


def test_image_model_and_style_settings_reach_the_call(api):
    assert api.set_settings(models={"image": "x/img"}, image_style="oil on canvas")["ok"]
    api.generate_inspiration("A pier")
    assert api.calls[-1][2:] == ("x/img", "oil on canvas")
    s = api.get_settings()
    assert s["models"]["image"]["effective"] == "x/img" and s["imageStyle"] == "oil on canvas"
    assert s["models"]["image"]["default"] == "google/gemini-3.1-flash-lite-image"
    assert api.ai_status()["models"]["image"] == "x/img"
    api.set_settings(models={"image": ""}, image_style="")
    assert api.get_settings()["models"]["image"]["value"] == ""


def test_regenerate_reuses_prompt_and_scene_and_keeps_the_old_one(api):
    first = api.generate_inspiration("Same prompt", SCENE, False)["images"][0]
    r = api.regenerate_inspiration(first["id"])
    assert r["ok"] and len(r["images"]) == 2
    assert all(i["prompt"] == "Same prompt" and i["scene"] == SCENE and not i["pinned"] for i in r["images"])
    assert len(api.list_inspiration()["images"]) == 4
    assert api.regenerate_inspiration("nope")["ok"] is False


def test_a_failed_generation_saves_nothing(api, monkeypatch):
    from lorewrite.ai.images import ImageError

    def boom(*a, **k):
        raise ImageError("The model did not return an image: no")

    monkeypatch.setattr(api_module, "generate_images", boom)
    r = api.generate_inspiration("A pier", SCENE)
    assert r["ok"] is False and "did not return an image" in r["error"]
    assert api.list_inspiration()["images"] == []


def test_describe_scene_sends_the_passage_and_notes(api):
    r = api.describe_scene(SCENE, None, 40)
    assert r["ok"] and r["prompt"].startswith("A rain-lit tram stop") and r["model"] == "google/gemini-2.5-flash"
    _, context, model = api.calls[-1]
    assert "<<CURSOR>>" in context and "Lower Meridian" in context and "STYLE GUIDE" not in context
    assert api.list_inspiration()["images"] == []                    # nothing generated or saved
    assert api.describe_scene("entities/characters/nobody.md")["ok"] is False
    assert api.describe_scene("manuscript/nope.md")["ok"] is False


def test_describe_scene_leaves_pending_ai_text_out(api):
    r = api.describe_scene("manuscript/02-the-archive.md", None, 10)
    assert r["ok"] and "unaccepted AI draft" not in api.calls[-1][1]


def test_update_pin_notes_title(api):
    img = api.generate_inspiration("p")["images"][0]
    assert api.update_inspiration(img["id"], {"pinned": True})["ok"] is False        # no scene yet
    r = api.update_inspiration(img["id"], {"pinned": True, "scene": SCENE, "title": "Tram", "notes": "n"})
    assert r["ok"] and r["image"]["pinned"] and r["image"]["scene"] == SCENE
    assert (r["image"]["title"], r["image"]["notes"]) == ("Tram", "n")
    assert api.update_inspiration(img["id"], {"pinned": False})["image"]["pinned"] is False
    assert api.update_inspiration(img["id"], {"prompt": "hack"})["ok"] is False
    assert api.update_inspiration(img["id"], {"scene": "entities/x.md"})["ok"] is False      # names nothing
    assert api.update_inspiration(img["id"], {"scene": ""})["image"]["scene"] == ""


def test_image_data_url_and_traversal_refused(api):
    img = api.generate_inspiration("p")["images"][0]
    r = api.inspiration_image(img["id"])
    assert r["ok"] and r["dataUrl"] == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    (api.root / "secret.jpg").write_bytes(b"\xff\xd8\xff secret")
    (api.root / "inspiration" / "x.md").write_text("---\nprompt: x\n---\n")
    for bad in ("../secret", "../secret.jpg", "..", "/etc/passwd", "a/b", "", ".x", "x"):
        assert api.inspiration_image(bad)["ok"] is False, bad
        assert api.update_inspiration(bad, {"notes": "n"})["ok"] is False, bad
        assert api.delete_inspiration(bad)["ok"] is False, bad
        assert api.reveal_inspiration(bad)["ok"] is False, bad
    assert (api.root / "secret.jpg").exists()


def test_delete_goes_to_the_trash_and_restores(api):
    img = api.generate_inspiration("p", SCENE, True)["images"][0]
    assert api.delete_inspiration(img["id"])["ok"]
    assert all(i["id"] != img["id"] for i in api.list_inspiration()["images"])
    items = api.list_trash()["items"]
    assert [(i["kind"], i["title"], i["original"]) for i in items] == [
        ("inspiration", "p", f"inspiration/{img['id']}.md")]
    r = api.restore_trash(items[0]["name"])
    assert r["ok"] and r["kind"] == "inspiration" and r["id"] == img["id"]
    back = [i for i in api.list_inspiration()["images"] if i["id"] == img["id"]][0]
    assert back["pinned"] and back["scene"] == SCENE
    assert api.inspiration_image(img["id"])["ok"]


def test_delete_forever_removes_the_picture(api):
    img = api.generate_inspiration("p")["images"][0]
    api.delete_inspiration(img["id"])
    name = api.list_trash()["items"][0]["name"]
    assert api.delete_forever(name)["ok"]
    assert not list((api.root / ".trash").glob("*")) if (api.root / ".trash").exists() else True


def test_reveal_reports_the_path_without_opening_outside_the_real_window(api):
    img = api.generate_inspiration("p")["images"][0]
    r = api.reveal_inspiration(img["id"])
    assert r["ok"] and r["path"].endswith(f"{img['id']}.jpg") and r["opened"] is False


def test_scene_rename_follows_in_the_bridge(api):
    img = api.generate_inspiration("p", "manuscript/02-the-archive.md", True)["images"][0]
    api.move_scene("manuscript/02-the-archive.md", -1)
    moved = api.list_inspiration()["images"]
    assert moved[0]["scene"] == "manuscript/01-the-archive.md"


def test_the_image_calls_are_in_the_bridge_and_the_mock_matches(api, monkeypatch):
    for name in ("list_inspiration", "inspiration_image", "describe_scene", "generate_inspiration",
                 "regenerate_inspiration", "update_inspiration", "delete_inspiration", "reveal_inspiration"):
        assert name in api.bridge_methods()
    from lorewrite.ai import images as image_ai

    real = {"generate_images": image_ai.generate, "suggest_image_prompt": image_ai.suggest_prompt}
    mockai.install(api_module)
    for name, fn in real.items():
        P = inspect.Parameter
        need = [p for p in inspect.signature(fn).parameters.values()
                if p.default is P.empty and p.kind in (P.POSITIONAL_ONLY, P.POSITIONAL_OR_KEYWORD)]
        have = list(inspect.signature(getattr(api_module, name)).parameters)
        assert len(have) >= len(need), name
        # every keyword the real call can take, the mock takes too
        assert set(inspect.signature(fn).parameters) - {"context", "prompt"} <= set(have), name


def test_mock_ai_makes_a_real_png_and_costs_like_an_image(api):
    mockai.install(api_module)
    r = api.generate_inspiration("A dark subway platform, flickering lights", SCENE, True)
    assert r["ok"] and r["cost"] == pytest.approx(0.0336)
    data = base64.b64decode(api.inspiration_image(r["images"][0]["id"])["dataUrl"].split(",", 1)[1])
    assert data.startswith(b"\x89PNG") and len(data) > 500
    d = api.describe_scene(SCENE, None, 5)
    assert d["ok"] and d["prompt"]
    m = api.list_models(False, "image")
    assert [x["id"] for x in m["models"]] == ["mock/lumen-image", "mock/dusk-image"]
    assert m["models"][1]["imagePrice"] == 0.04


def test_mock_png_without_pillow(monkeypatch):
    import builtins, struct, zlib
    real_import = builtins.__import__

    def no_pil(name, *a, **k):
        if name.startswith("PIL"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pil)
    png = mockai.placeholder_png("a b c", (16, 8))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (16, 8)
    idat = png.index(b"IDAT")
    n = struct.unpack(">I", png[idat - 4:idat])[0]
    assert len(zlib.decompress(png[idat + 4:idat + 4 + n])) == (1 + 16 * 3) * 8
