"""Inspiration pictures can be for any item: sidecar ``for:`` (legacy ``scene:`` still read),
remap on moves and renames, listing / pinning / generating for entity and notebook notes,
and the author's own uploads."""

import base64
from pathlib import Path

import pytest

from lorewrite.ai.usage import LEDGER
from lorewrite.core import inspiration as store
from lorewrite.core.project import Project
from lorewrite.gui import api as api_module
from lorewrite.gui import inspiration as insp_api
from tests.gui_helpers import make_book, make_project
from tests.test_gui_api import open_api

JPEG = b"\xff\xd8\xff\xe0" + b"j" * 30
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 30
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 " + b"w" * 20
GIF = b"GIF89a" + b"g" * 30
SCENE = "manuscript/01-arrival.md"
MARA = "entities/characters/mara-vale.md"


def url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path / "p")


@pytest.fixture
def api(tmp_path, monkeypatch):
    calls = []

    def fake_generate(prompt, model, client=None, style=None):
        calls.append(("generate", prompt))
        LEDGER.record(model, "image", 0.04, 10, 1000)
        return [(PNG, "png")]

    def fake_suggest(context, model, client=None):
        calls.append(("suggest", context))
        return "A described picture."

    monkeypatch.setattr(api_module, "generate_images", fake_generate)
    monkeypatch.setattr(api_module, "suggest_image_prompt", fake_suggest)
    a, root = open_api(tmp_path)
    a.calls, a.root = calls, root
    return a


# -- the sidecar ---------------------------------------------------------------------


def test_new_sidecars_write_for_and_never_scene(project):
    img = store.save(project, JPEG, "jpg", {"prompt": "p", "scene": SCENE, "pinned": True})
    text = img.meta_path.read_text(encoding="utf-8")
    assert f"for: {SCENE}" in text and "scene:" not in text
    assert (img.link, img.scene, img.pinned) == (SCENE, SCENE, True)
    other = store.save(project, JPEG, "jpg", {"prompt": "q", "for": MARA})
    assert other.link == MARA and "for: " + MARA in other.meta_path.read_text(encoding="utf-8")
    assert insp_api.row(other)["for"] == MARA


def test_legacy_scene_sidecars_still_read_and_show_for_scenes(project):
    img = store.save(project, JPEG, "jpg", {"prompt": "old", "pinned": True, "for": SCENE})
    img.meta_path.write_text(
        f"---\nprompt: old\nscene: {SCENE}\ncreated: '2026-10-01T10:00:00'\npinned: true\n---\nn\n",
        encoding="utf-8")
    got = store.get(project, img.id)
    assert got.link == SCENE and got.scene == SCENE and got.pinned and got.notes == "n"
    assert [i.id for i in store.list_images(project, SCENE)] == [img.id]
    assert [i.id for i in store.pinned_for(project, SCENE)] == [img.id]
    assert insp_api.row(got)["for"] == SCENE
    # the next write migrates it to for:
    store.update(project, img.id, title="T")
    text = img.meta_path.read_text(encoding="utf-8")
    assert f"for: {SCENE}" in text and "scene:" not in text


def test_pin_works_for_any_kind_and_needs_an_item(project):
    note = store.save(project, JPEG, "jpg", {"prompt": "p"})
    with pytest.raises(ValueError, match="item"):
        store.update(project, note.id, pinned=True)
    got = store.update(project, note.id, pinned=True, link=MARA)
    assert got.pinned and got.link == MARA
    assert [i.id for i in store.pinned_for(project, MARA)] == [note.id]
    nb = "notebook/tides.md"
    assert store.update(project, note.id, scene=nb).link == nb and store.get(project, note.id).pinned
    assert store.update(project, note.id, link="").pinned is False        # detaching unpins


# -- remap -----------------------------------------------------------------------------


def test_remap_paths_handles_scenes_and_entity_notes_and_ignores_the_rest(project):
    root = project.root
    a = store.save(project, JPEG, "jpg", {"prompt": "a", "for": SCENE})
    b = store.save(project, JPEG, "jpg", {"prompt": "b", "for": MARA})
    c = store.save(project, JPEG, "jpg", {"prompt": "c", "for": "notebook/stays.md"})
    pairs = {
        root / "manuscript" / "01-arrival.md": root / "manuscript" / "02-arrival.md",
        root / "entities" / "characters" / "mara-vale.md": root / "entities" / "characters" / "nia-vale.md",
        root / "manuscript" / "01-part": root / "manuscript" / "02-part",        # a folder: ignored
        Path("/elsewhere/x.md"): Path("/elsewhere/y.md"),                      # outside: ignored
    }
    assert store.remap_paths(project, pairs) == 2
    assert store.get(project, a.id).link == "manuscript/02-arrival.md"
    assert store.get(project, b.id).link == "entities/characters/nia-vale.md"
    assert store.get(project, c.id).link == "notebook/stays.md"
    assert store.remap_paths(project, {}) == 0


def test_remap_swaps_do_not_collide(project):
    a = store.save(project, JPEG, "jpg", {"prompt": "a", "for": "manuscript/a.md"})
    b = store.save(project, JPEG, "jpg", {"prompt": "b", "for": "manuscript/b.md"})
    root = project.root
    store.remap_paths(project, {root / "manuscript/a.md": root / "manuscript/b.md",
                                root / "manuscript/b.md": root / "manuscript/a.md"})
    assert store.get(project, a.id).link == "manuscript/b.md" and store.get(project, b.id).link == "manuscript/a.md"


def test_scene_move_remaps_via_structure(tmp_path):
    book = make_book(tmp_path / "b")
    scene = "manuscript/01-the-recall/02-capsule.md"
    img = store.save(book, JPEG, "jpg", {"prompt": "x", "for": scene, "pinned": True})
    book.move_scene(book.root / scene, -1)
    got = store.get(book, img.id)
    assert got.link == "manuscript/01-the-recall/01-capsule.md" and got.pinned
    assert (book.root / got.link).is_file()


def test_trashing_an_item_keeps_the_link_and_shows_unlinked(api):
    img = api.generate_inspiration("p", "manuscript/02-the-archive.md", True)["images"][0]
    assert api.delete_scene("manuscript/02-the-archive.md")["ok"]
    row = [i for i in api.list_inspiration()["images"] if i["id"] == img["id"]][0]
    assert row["for"] == "manuscript/02-the-archive.md" and row["unlinked"] is True and row["pinned"]
    assert api.list_inspiration("manuscript/01-arrival.md")["mine"] == []


# -- listing and generating for any kind ------------------------------------------------


def test_list_pin_and_generate_for_an_entity_and_a_notebook_note(api):
    nb = api.new_research_note("Tide tables")["id"]
    for item in (MARA, nb):
        r = api.generate_inspiration("A picture for it", item, True)
        assert r["ok"] and r["images"][0]["for"] == item and r["images"][0]["pinned"]
    api.generate_inspiration("Loose", None, False)
    for item in (MARA, nb):
        listed = api.list_inspiration(item)
        assert listed["ok"] and len(listed["mine"]) == 1 and len(listed["images"]) == 3
        mine = [i for i in listed["images"] if i["id"] in listed["mine"]][0]
        assert mine["for"] == item and mine["pinned"] and mine["unlinked"] is False
    loose = [i for i in api.list_inspiration()["images"] if i["for"] == ""][0]
    pinned = api.update_inspiration(loose["id"], {"pinned": True, "for": nb})
    assert pinned["ok"] and pinned["image"]["for"] == nb and pinned["image"]["scene"] == nb
    assert len(api.list_inspiration(nb)["mine"]) == 2
    assert api.list_inspiration("entities/characters/nobody.md")["ok"] is False
    assert api.list_inspiration("../x.md")["ok"] is False


def test_describe_a_note_sends_its_text_and_nothing_else(api):
    (api.root / "entities/characters/mara-vale.md").write_text(
        "---\nname: Mara Vale\ntype: character\naliases: [Mara]\n---\n\nTall, ink-stained fingers.\n",
        encoding="utf-8")
    api.reload_entities()
    r = api.describe_scene(MARA)
    assert r["ok"] and r["prompt"] == "A described picture."
    ctx = api.calls[-1][1]
    assert ctx.startswith("SUBJECT (character): Mara Vale") and "ink-stained" in ctx and "aliases" not in ctx
    nb = api.new_research_note("Tide tables")["id"]
    (api.root / nb).write_text("# Tide tables\n\nThe spur floods at dusk.\n", encoding="utf-8")
    assert api.describe_scene(nb)["ok"] and "floods at dusk" in api.calls[-1][1]
    assert api.generate_inspiration("p", None)["ok"]       # generation itself only ever sends the prompt
    assert api.calls[-1] == ("generate", "p")


# -- uploads -----------------------------------------------------------------------------


def test_upload_happy_path_goes_into_the_same_store(api):
    r = api.upload_inspiration("My Tram.JPG", url(JPEG, "image/jpeg"), SCENE)
    assert r["ok"]
    img = r["image"]
    assert (img["source"], img["model"], img["cost"], img["for"], img["ext"]) == ("upload", "upload", None, SCENE, "jpg")
    assert img["title"] == "My Tram" and img["label"] == "My Tram" and img["prompt"] == "" and not img["pinned"]
    assert img["id"].endswith("-my-tram")                                 # the slug of the title, not the file name
    on_disk = sorted(p.name for p in (api.root / "inspiration").iterdir())
    assert on_disk == [img["id"] + ".jpg", img["id"] + ".md"]
    text = (api.root / "inspiration" / (img["id"] + ".md")).read_text(encoding="utf-8")
    assert "source: upload" in text and f"for: {SCENE}" in text and "\r" not in text
    assert (api.root / "inspiration" / (img["id"] + ".jpg")).read_bytes() == JPEG
    listed = api.list_inspiration(SCENE)
    assert listed["mine"] == [img["id"]] and listed["images"][0]["source"] == "upload"
    assert api.inspiration_image(img["id"])["dataUrl"] == url(JPEG, "image/jpeg")
    # png and webp, no item
    assert api.upload_inspiration("a.png", url(PNG, "image/png"))["image"]["ext"] == "png"
    assert api.upload_inspiration("a.webp", url(WEBP, "image/webp"), MARA)["image"]["ext"] == "webp"
    assert api.upload_inspiration("a.png", url(PNG, "image/png"))["image"]["for"] == ""


def test_upload_for_a_notebook_note_and_pinning_afterwards(api):
    nb = api.new_research_note("Moodboard")["id"]
    img = api.upload_inspiration("m.png", url(PNG, "image/png"), nb)["image"]
    assert img["for"] == nb
    assert api.update_inspiration(img["id"], {"pinned": True})["image"]["pinned"] is True


@pytest.mark.parametrize("data, mime", [
    (GIF, "image/gif"), (b"<svg xmlns='x'/>", "image/svg+xml"), (b"%PDF-1.4", "application/pdf"),
    (JPEG, "text/plain"), (JPEG, ""), (JPEG, "image/gif"),
])
def test_upload_refuses_other_types(api, data, mime):
    r = api.upload_inspiration("x.jpg", url(data, mime))
    assert r["ok"] is False and ("JPG" in r["error"] or "picture" in r["error"])
    assert not (api.root / "inspiration").exists() or not any((api.root / "inspiration").iterdir())


def test_upload_refuses_a_lying_mime_type(api):
    for data, mime in ((GIF, "image/png"), (PNG, "image/jpeg"), (JPEG, "image/webp"), (b"not an image", "image/png"),
                       (b"<svg/>", "image/jpeg")):
        r = api.upload_inspiration("x.png", url(data, mime))
        assert r["ok"] is False and "real JPG, PNG or WebP" in r["error"], (data, mime)
    assert not (api.root / "inspiration").exists() or not any((api.root / "inspiration").iterdir())


def test_upload_refuses_empty_oversize_and_bad_base64(api, monkeypatch):
    assert api.upload_inspiration("x.png", "data:image/png;base64,")["ok"] is False
    assert "empty" in api.upload_inspiration("x.png", "data:image/png;base64,")["error"]
    assert api.upload_inspiration("x.png", "")["ok"] is False
    assert api.upload_inspiration("x.png", None)["ok"] is False
    assert api.upload_inspiration("x.png", "image/png;base64,AAAA")["ok"] is False        # not a data URL
    assert api.upload_inspiration("x.png", "data:image/png,rawbytes")["ok"] is False        # not base64
    bad = api.upload_inspiration("x.png", "data:image/png;base64,@@@@")
    assert bad["ok"] is False and "damaged" in bad["error"]
    big = PNG + b"\0" * (insp_api.UPLOAD_MAX + 1 - len(PNG))
    r = api.upload_inspiration("big.png", url(big, "image/png"))
    assert r["ok"] is False and "larger than 10 MB" in r["error"]
    just = PNG + b"\0" * (insp_api.UPLOAD_MAX - len(PNG))
    assert api.upload_inspiration("max.png", url(just, "image/png"))["ok"] is True          # exactly at the cap
    assert len(list((api.root / "inspiration").glob("*.md"))) == 1


def test_upload_never_uses_the_filename_and_unknown_items_fail_cleanly(api):
    for name in ("../../evil.png", "..\\..\\evil.png", "/etc/passwd", "C:\\x\\y\\z.png", "a/b/c.png",
                 "con.png", "", None, "x" * 500 + ".png", "..", "\x00\x01.png"):
        r = api.upload_inspiration(name, url(PNG, "image/png"))
        assert r["ok"], name
        assert Path(r["image"]["id"]).name == r["image"]["id"] and ".." not in r["image"]["id"]
    inside = {p.name for p in (api.root / "inspiration").iterdir()}
    assert all(not n.startswith(".") and "/" not in n and "\\" not in n for n in inside)
    assert not (api.root.parent / "evil.png").exists() and not (api.root / "evil.png").exists()
    titles = [i["title"] for i in api.list_inspiration()["images"]]
    assert "evil" in titles and "Added picture" in titles
    assert api.upload_inspiration("x.png", url(PNG, "image/png"), "entities/characters/nobody.md")["ok"] is False
    assert api.upload_inspiration("x.png", url(PNG, "image/png"), "../x.md")["ok"] is False


def test_regenerate_is_refused_for_uploads_and_calls_no_ai(api):
    img = api.upload_inspiration("x.png", url(PNG, "image/png"), SCENE)["image"]
    r = api.regenerate_inspiration(img["id"])
    assert r["ok"] is False and "cannot be regenerated" in r["error"]
    assert api.calls == []


def test_uploads_can_be_trashed_restored_renamed(api):
    img = api.upload_inspiration("x.png", url(PNG, "image/png"), SCENE)["image"]
    assert api.update_inspiration(img["id"], {"title": "Mine", "notes": "n"})["image"]["label"] == "Mine"
    assert api.delete_inspiration(img["id"])["ok"]
    item = api.list_trash()["items"][0]
    assert item["kind"] == "inspiration" and item["title"] == "Mine"
    assert api.restore_trash(item["name"])["ok"]
    back = api.list_inspiration()["images"][0]
    assert back["source"] == "upload" and back["for"] == SCENE


def test_upload_is_in_the_bridge(api):
    assert "upload_inspiration" in api.bridge_methods()
    assert api.upload_inspiration("x.png", url(PNG, "image/png"))["ok"]
