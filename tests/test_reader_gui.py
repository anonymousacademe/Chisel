"""Api.read_plan: the utterances the desktop editor speaks (bridge side of core/reader.py)."""

from chisel.core import entities as ent
from chisel.core.project import Project
from chisel.gui.api import Api
from tests.gui_helpers import make_project
from tests.test_script_export import make_script

SCENE = "manuscript/01-act-one/01-kitchen.md"


def script_api(tmp_path):
    make_script(tmp_path / "s")
    api = Api()
    assert api.open_project(str(tmp_path / "s"))["ok"]
    return api


def test_a_script_scene_is_read_by_speaker(tmp_path):
    api = script_api(tmp_path)
    r = api.read_plan(SCENE)
    assert r["ok"] and r["mode"] == "script"
    voices = {v["voice"]: v["count"] for v in r["voices"]}
    assert voices["narrator"] >= 2 and voices["Keith"] == 1
    assert r["words"] > 10 and r["seconds"] > 0
    heading = next(u for u in r["utterances"] if u["kind"] == "scene-heading")
    assert heading["say"] == "Interior, Kitchen, Day"
    text = (tmp_path / "s" / SCENE).read_text(encoding="utf-8")
    assert text[heading["start"]:heading["end"]] == "INT. KITCHEN - DAY"        # no astral text: UTF-16 == code points


def test_the_editor_buffer_is_read_not_the_file_and_offsets_are_utf16(tmp_path):
    api = script_api(tmp_path)
    live = "# T\n\nINT. A - DAY\n\n\U0001F600 Smile.\n\nKEITH\nHello \U0001F600 there.\n"
    r = api.read_plan(SCENE, live)
    smile = next(u for u in r["utterances"] if u["kind"] == "narration")
    # the emoji is two UTF-16 units: ranges are in the units JavaScript counts
    units = live.encode("utf-16-le")
    chunk = units[smile["start"] * 2:smile["end"] * 2].decode("utf-16-le")
    assert chunk == "\U0001F600 Smile."
    said = next(u for u in r["utterances"] if u["kind"] == "dialogue")
    assert units[said["start"] * 2:said["end"] * 2].decode("utf-16-le") == "Hello \U0001F600 there."
    assert said["voice"] == "Keith"


def test_options_change_what_is_read(tmp_path):
    api = script_api(tmp_path)
    plain = api.read_plan(SCENE)
    more = api.read_plan(SCENE, options={"directions": True, "transitions": True})
    assert len(more["utterances"]) > len(plain["utterances"])
    assert any(u["kind"] == "direction" for u in more["utterances"])
    assert not api.read_plan(SCENE, options={"directions": "yes"})["ok"]


def test_story_research_and_notes_use_their_own_adapters(tmp_path):
    make_project(tmp_path / "p")
    api = Api()
    api.open_project(str(tmp_path / "p"))
    story = api.read_plan("manuscript/01-arrival.md")
    assert story["ok"] and story["mode"] == "story" and {v["voice"] for v in story["voices"]} == {"narrator"}
    note = api.read_plan("entities/characters/mara-vale.md")
    assert note["ok"] and note["mode"] == "note"
    paper = Project.create(tmp_path / "r", "Paper", "research")
    (paper.manuscript_dir / "01-opening.md").write_text("# Methods\n\nWe use [@k2020] and $x$.\n", encoding="utf-8", newline="\n")
    api2 = Api()
    api2.open_project(str(tmp_path / "r"))
    r = api2.read_plan("manuscript/01-opening.md")
    assert r["mode"] == "research" and [u["say"] for u in r["utterances"]] == ["Methods", "We use and equation."]


def test_pronunciations_come_from_the_notes(tmp_path):
    api = script_api(tmp_path)
    project = Project.open(tmp_path / "s")
    keith = next(e for e in project.load_entities() if e.name == "Keith")
    keith.extra["say"] = "Kee-eth"
    ent.save_entity(keith, keith.path)
    api.open_project(str(tmp_path / "s"))
    r = api.read_plan(SCENE)
    assert "Kee-eth" in " ".join(u["say"] for u in r["utterances"] if u["kind"] == "narration")


def test_what_cannot_be_read_is_a_plain_error(tmp_path):
    api = script_api(tmp_path)
    assert "nothing to read" in api.read_plan("style.md")["error"].lower() or not api.read_plan("style.md")["ok"]
    assert not api.read_plan("dictionary.txt")["ok"]
    assert not api.read_plan("manuscript/nope.md")["ok"]
    assert not Api().read_plan(SCENE)["ok"]


def test_it_is_a_bridge_method_and_changes_nothing(tmp_path):
    assert hasattr(Api().facade(), "read_plan")
    api = script_api(tmp_path)
    before = (tmp_path / "s" / SCENE).read_bytes()
    api.read_plan(SCENE)
    assert (tmp_path / "s" / SCENE).read_bytes() == before
