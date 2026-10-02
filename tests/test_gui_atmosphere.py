"""Typing-sound packs, ambience loops, stations and preferences (bridge + core)."""

import io
import os
import sys
import zipfile

import pytest

from lorewrite.core import atmosphere, soundpacks
from lorewrite.gui.api import Api

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 40
OGG = b"OggS" + b"\x00" * 30
MP3 = b"ID3\x03" + b"\x00" * 30


def make_pack(name="Clicks", files=None):
    folder = soundpacks.sounds_dir() / name
    folder.mkdir(parents=True)
    for leaf, data in (files or {"key-1.wav": WAV, "key-2.ogg": OGG, "space.wav": WAV, "pack.toml": b'name = "Clicks!"\nvolume = 0.5\n'}).items():
        (folder / leaf).write_bytes(data)
    return folder


def make_zip(tmp_path, entries, name="p.zip"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in entries.items():
            # Set the name after construction: ZipInfo(name) turns "\\" into "/"
            # on Windows, which would make the backslash test a no-op there.
            info = zipfile.ZipInfo("x")
            info.filename = n
            zf.writestr(info, data)
    return path


def test_list_and_read_pack():
    make_pack()
    assert soundpacks.list_packs() == [{"id": "Clicks", "name": "Clicks!", "volume": 0.5, "files": 3}]
    pack = soundpacks.read_pack("Clicks")
    assert len(pack["sounds"]["key"]) == 2 and len(pack["sounds"]["space"]) == 1
    assert "return" not in pack["sounds"]
    assert pack["sounds"]["key"][0].startswith("data:audio/wav;base64,")


def test_no_folder_is_empty():
    api = Api()
    r = api.get_atmosphere()
    assert r["packs"] == [] and r["loops"] == [] and r["prefs"]["typing"]["on"] is False


@pytest.mark.parametrize("bad", ["../x", "..", "a/b", "a\\b", "", "/etc", ".hidden", "x" * 80, "C:evil"])
def test_names_never_traverse(bad):
    api = Api()
    assert api.sound_pack(bad)["ok"] is False
    assert api.ambience_loop(bad)["ok"] is False
    assert api.export_sound_pack(bad, "x.zip")["ok"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_symlinks_are_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "key-1.wav").write_bytes(WAV)
    (soundpacks.sounds_dir()).mkdir(parents=True)
    os.symlink(outside, soundpacks.sounds_dir() / "Linked")
    assert soundpacks.list_packs() == []
    assert Api().sound_pack("Linked")["ok"] is False
    make_pack("Real", {"key-1.wav": WAV})
    os.symlink(outside / "key-1.wav", soundpacks.sounds_dir() / "Real" / "key-2.wav")
    assert len(soundpacks.read_pack("Real")["sounds"]["key"]) == 1  # the link is skipped


def test_bad_audio_content_is_refused():
    folder = make_pack("Fake", {"key-1.wav": b"MZ\x90\x00 not audio"})
    assert Api().sound_pack("Fake")["ok"] is False
    assert folder.exists()


def test_loops_listed_and_served():
    root = soundpacks.ambience_dir()
    root.mkdir(parents=True)
    (root / "Rain loop.ogg").write_bytes(OGG)
    (root / "notes.txt").write_text("x")
    api = Api()
    assert api.get_atmosphere()["loops"] == [{"id": "Rain loop.ogg", "name": "Rain loop"}]
    assert api.ambience_loop("Rain loop.ogg")["dataUrl"].startswith("data:audio/ogg;base64,")
    assert api.ambience_loop("notes.txt")["ok"] is False


def test_import_ok_flat_and_folder(tmp_path):
    api = Api()
    r = api.import_sound_pack(str(make_zip(tmp_path, {"key-a.wav": WAV, "return.mp3": MP3, "pack.toml": 'name = "My Pack"'})))
    assert r["imported"]["id"] == "My Pack"
    r = api.import_sound_pack(str(make_zip(tmp_path, {"Folder/key-a.wav": WAV}, "q.zip")))
    assert r["imported"]["id"] == "Folder"
    again = api.import_sound_pack(str(make_zip(tmp_path, {"Folder/key-a.wav": WAV}, "r.zip")))
    assert again["imported"]["id"] == "Folder 2"
    assert [p["id"] for p in again["packs"]] == ["Folder", "Folder 2", "My Pack"]


@pytest.mark.parametrize("entries,why", [
    ({"../evil.wav": WAV}, "unsafe"),
    ({"/abs/key-1.wav": WAV}, "unsafe"),
    pytest.param({"a\\key-1.wav": WAV}, "unsafe", marks=pytest.mark.skipif(
        os.name == "nt", reason="zipfile reads a backslash as '/' on Windows, so this "
        "is the allowed one-folder layout there; '..' is still caught by the '../' case")),
    ({"a/b/key-1.wav": WAV}, "one folder"),
    ({"a/key-1.wav": WAV, "b/key-1.wav": WAV}, "one pack"),
    ({"a/key-1.wav": WAV, "key-2.wav": WAV}, "one folder"),
    ({"run.exe": b"MZ" + b"\x00" * 30}, "only sound"),
    ({"key-1.wav": b"MZ" + b"\x00" * 30}, "not a wav"),
    ({"key-1.wav": b"ELF" + b"\x00" * 30}, "not a wav"),
    ({"readme.txt": b"hi", "key-1.wav": WAV}, "only sound"),
    ({"pack.toml": b"name = 'x'"}, "no sound"),
    ({"key-1.wav": WAV, "pack.toml": b"= = ="}, "TOML"),
])
def test_import_refuses(tmp_path, entries, why):
    r = Api().import_sound_pack(str(make_zip(tmp_path, entries)))
    assert r["ok"] is False and why in r["error"]
    assert not soundpacks.sounds_dir().exists() or not list(soundpacks.sounds_dir().iterdir())


def test_import_limits(tmp_path, monkeypatch):
    api = Api()
    many = {f"key-{i}.wav": WAV for i in range(soundpacks.MAX_FILES + 1)}
    assert "too many" in api.import_sound_pack(str(make_zip(tmp_path, many)))["error"]
    monkeypatch.setattr(soundpacks, "MAX_TOTAL_BYTES", 100)
    big = make_zip(tmp_path, {"key-1.wav": WAV + b"\x00" * 200}, "big.zip")
    assert "20 MB" in api.import_sound_pack(str(big))["error"]
    assert api.import_sound_pack(str(tmp_path / "missing.zip"))["ok"] is False
    notzip = tmp_path / "n.zip"
    notzip.write_bytes(b"nope")
    assert "zip" in api.import_sound_pack(str(notzip))["error"]


def test_import_zip_symlink_entry_refused(tmp_path):
    path = tmp_path / "l.zip"
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("key-1.wav")
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "/etc/passwd")
    assert "links" in Api().import_sound_pack(str(path))["error"]


def test_export_round_trip(tmp_path):
    make_pack()
    api = Api()
    out = tmp_path / "out"
    out.mkdir()
    r = api.export_sound_pack("Clicks", str(out))
    assert r["path"].endswith("Clicks.zip")
    assert api.export_sound_pack("Clicks", str(out))["ok"] is False  # never overwrites
    soundpacks_dir = soundpacks.sounds_dir() / "Clicks"
    for p in soundpacks_dir.iterdir():
        p.unlink()
    soundpacks_dir.rmdir()
    got = api.import_sound_pack(r["path"])
    assert got["imported"]["id"] == "Clicks"  # name from pack.toml, made filename-safe
    assert len(soundpacks.read_pack("Clicks")["sounds"]["key"]) == 2


def test_dialog_methods_need_the_window():
    assert Api().import_sound_pack()["ok"] is False
    make_pack()
    assert Api().export_sound_pack("Clicks")["ok"] is False


def test_open_folder_creates_it_without_window():
    r = Api().open_sounds_folder("ambience")
    assert r["opened"] is False and soundpacks.ambience_dir().is_dir()


def test_default_stations_are_somafm_https():
    rows = Api().get_atmosphere()["stations"]
    assert [r["url"] for r in rows] == [
        f"https://ice1.somafm.com/{c}-128-mp3" for c in ("groovesalad", "dronezone", "deepspaceone", "fluid")]
    assert all(r["attribution"]["link"].startswith("https://somafm.com") for r in rows)
    assert "lo-fi" in rows[3]["name"]


def test_stations_edit_validate_reset():
    api = Api()
    r = api.set_stations([{"name": "  Mine ", "url": "http://example.org/stream"}, {"name": "Mine again", "url": "http://example.org/stream"}])
    assert r["stations"] == [{"name": "Mine", "url": "http://example.org/stream", "attribution": None}]
    assert api.get_atmosphere()["stations"][0]["name"] == "Mine"
    for bad in ("ftp://x.org/a", "javascript:alert(1)", "file:///etc/passwd", "https://", "http://a b.org", "x" * 400, ""):
        assert api.set_stations([{"name": "n", "url": bad}])["ok"] is False
    assert api.set_stations([{"name": "", "url": "https://x.org/a"}])["ok"] is False
    assert api.set_stations("nope")["ok"] is False
    assert api.set_stations([{"name": "n", "url": "https://x.org"}] * 1 + [{"name": str(i), "url": f"https://x.org/{i}"} for i in range(40)])["ok"] is False
    assert len(api.set_stations(None)["stations"]) == 4


def test_prefs_defaults_and_sanitising():
    api = Api()
    p = api.get_atmosphere()["prefs"]
    assert p["typing"] == {"on": False, "pack": "typewriter", "volume": 0.5}
    assert p["ambience"]["layers"] == {} and p["ambience"]["station"] is None
    saved = api.set_atmosphere({"typing": {"on": 1, "pack": "clicky", "volume": 9},
                                "ambience": {"layers": {"rain": 0.4, "bogus": 1, "wind": -3}, "station": "javascript:x",
                                             "presets": {"Rainy café": {"rain": 0.5, "fire": 0.2}}}})["prefs"]
    assert saved["typing"] == {"on": True, "pack": "clicky", "volume": 1.0}
    assert saved["ambience"]["layers"] == {"rain": 0.4}
    assert saved["ambience"]["station"] is None
    assert saved["ambience"]["presets"] == {"Rainy café": {"rain": 0.5, "fire": 0.2}}
    assert api.get_atmosphere()["prefs"] == saved
    assert atmosphere.clean_prefs("junk")["typing"]["on"] is False
