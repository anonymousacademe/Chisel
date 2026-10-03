"""Api: spelling spans (UTF-16), suggestions, dictionaries, ignore, settings."""

from chisel.core import settings as user_settings
from chisel.core import spelling
from chisel.gui.api import Api
from tests.gui_helpers import make_project

SCENE = "01-arrival.md"


def open_api(tmp_path, text=None):
    root = tmp_path / "p"
    make_project(root)
    if text is not None:
        (root / "manuscript" / SCENE).write_text(text, encoding="utf-8")
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def doc_id():
    return f"manuscript/{SCENE}"


def test_spans_for_the_editor_buffer(tmp_path):
    api, _ = open_api(tmp_path)
    r = api.spelling(doc_id(), "Mara would recieve it. Elias smiled.")
    assert r["ok"] and r["enabled"]
    assert r["spans"] == [{"start": 11, "end": 18, "word": "recieve"}]


def test_entity_names_are_accepted(tmp_path):
    api, _ = open_api(tmp_path)
    r = api.spelling(doc_id(), "Mara Vale met Elias in Lower Meridian.")
    assert r["spans"] == []


def test_offsets_are_utf16_with_astral_characters(tmp_path):
    api, _ = open_api(tmp_path)
    text = "\U0001F600\U0001F600 recieve"  # two astral chars = 4 UTF-16 units
    [span] = api.spelling(doc_id(), text)["spans"]
    assert (span["start"], span["end"]) == (5, 12)


def test_only_scenes_are_checked(tmp_path):
    api, root = open_api(tmp_path)
    ent = next(iter((root / "entities").glob("*/*.md"))).relative_to(root).as_posix()
    assert api.spelling(ent, "recieve") == {"ok": True, "enabled": False, "spans": []}


def test_setting_off_disables(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.set_settings(spellcheck=False)["ok"]
    assert api.get_settings()["spellcheck"] is False
    assert user_settings.get("spellcheck") is False  # the TUI's key
    assert api.spelling(doc_id(), "recieve")["enabled"] is False
    api.set_settings(spellcheck=True)
    assert api.spelling(doc_id(), "recieve")["spans"]


def test_suggestions(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.spelling_suggestions("Recieve")["suggestions"][0] == "Receive"


def test_add_project_and_personal(tmp_path):
    api, root = open_api(tmp_path)
    assert api.add_to_dictionary("recieve", "project") == {"ok": True, "added": True}
    assert api.add_to_dictionary("recieve", "project")["added"] is False
    assert spelling.load_dictionary(root / "dictionary.txt") == ["recieve"]
    assert api.add_to_dictionary("snarfblat", "personal")["added"]
    assert spelling.load_dictionary(spelling.personal_dictionary_path()) == ["snarfblat"]
    r = api.spelling(doc_id(), "recieve snarfblat zzyzx")
    assert [s["word"] for s in r["spans"]] == ["zzyzx"]


def test_add_phrase_and_validation(tmp_path):
    api, _ = open_api(tmp_path)
    assert api.add_to_dictionary("maglev spur", "project")["ok"]
    assert api.spelling(doc_id(), "the maglev spur")["spans"] == []
    assert api.add_to_dictionary("x", "nowhere")["ok"] is False
    assert api.add_to_dictionary("   ", "project")["ok"] is False


def test_ignore_is_session_only(tmp_path):
    api, root = open_api(tmp_path)
    assert api.ignore_word("zzyzx")["ok"]
    assert api.spelling(doc_id(), "zzyzx")["spans"] == []
    assert not (root / "dictionary.txt").exists()
    other = Api()
    other.open_project(str(root))
    assert other.spelling(doc_id(), "zzyzx")["spans"]


def test_open_dictionary_and_edit_by_hand(tmp_path):
    api, root = open_api(tmp_path)
    assert api.open_dictionary() == {"ok": True, "id": "dictionary.txt"}
    doc = api.read_document("dictionary.txt")
    assert doc["kind"] == "dictionary" and doc["text"].startswith("#")
    text = doc["text"] + "zzyzx\n"
    r = api.save_document("dictionary.txt", text, doc["mtime"])
    assert r["ok"] and r["saved"]
    assert api.spelling(doc_id(), "zzyzx")["spans"] == []
    # not a scene / entity / indexed file
    assert api.read_document("notes.txt")["ok"] is False


def test_dictionary_in_the_binder(tmp_path):
    api, _ = open_api(tmp_path)
    binder = api.get_workspace()["workspace"]["binder"]
    node = next(n for n in binder if n["kind"] == "dictionary")
    assert node["id"] == "dictionary.txt" and node["title"] == "Dictionary"


def test_bridge_never_raises(tmp_path):
    api = Api()
    assert api.spelling("x.md", "y")["ok"] is False
    assert api.add_to_dictionary("a")["ok"] is False
