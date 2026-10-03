"""Optional story time through the GUI bridge and the places that must ignore it."""

import datetime
import tomllib
from pathlib import Path

import pytest

from lorewrite.ai import continuity as ai_cont
from lorewrite.ai.writing import build_context
from lorewrite.core import drafts, scenemeta, snapshots, spelling, timeline
from lorewrite.core import entities as ent
from lorewrite.core.project import Project
from lorewrite.core.style import sample_manuscript
from lorewrite.gui.api import Api
from tests.gui_helpers import make_project

A = "manuscript/01-arrival.md"
B = "manuscript/02-the-archive.md"


@pytest.fixture(autouse=True)
def _clear_daily():
    snapshots._daily_done.clear()
    yield
    snapshots._daily_done.clear()


def open_api(tmp_path: Path) -> tuple[Api, Path]:
    root = tmp_path / "p"
    make_project(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def scenes(api) -> dict:
    return {s["id"]: s for s in api.get_workspace()["workspace"]["scenes"]}


def put_when(root: Path, rel: str, when: str) -> None:
    path = root / rel
    path.write_text(f"---\nwhen: {when}\n---\n" + path.read_text(encoding="utf-8"),
                    encoding="utf-8", newline="\n")


# -- workspace payload ---------------------------------------------------------------------------


def test_workspace_without_story_time_says_reading_order(tmp_path):
    api, _ = open_api(tmp_path)
    w = api.get_workspace()["workspace"]
    assert w["timeline"] == {"mode": "reading-order", "scenes": 0, "era": "", "unit": "year",
                             "sentence": "No story times set; using reading order"}
    for s in w["scenes"]:
        assert s["when"] == {"value": "", "label": "", "source": "none", "raw": "", "invalid": False}
        assert s["details"]["when"] == ""


def test_workspace_explicit_inherited_and_invalid(tmp_path):
    api, root = open_api(tmp_path)
    put_when(root, A, "2187-03")
    api.open_project(str(root))
    s = scenes(api)
    assert s[A]["when"] == {"value": "2187-03", "label": "2187-03", "source": "explicit",
                            "raw": "2187-03", "invalid": False}
    assert s[B]["when"]["source"] == "inherited" and s[B]["when"]["value"] == "2187-03"
    assert s[B]["details"]["when"] == ""      # the scene's own field stays empty
    t = api.get_workspace()["workspace"]["timeline"]
    assert t["mode"] == "chronological" and t["sentence"] == "Using story time from 1 scene"
    # an invalid value is flagged, kept, and does not become the inherited time
    put_when(root, B, "someday")
    s = scenes(api) if api.open_project(str(root)) else None
    assert s[B]["when"]["invalid"] is True and s[B]["when"]["raw"] == "someday"
    assert s[B]["when"]["source"] == "inherited" and s[B]["details"]["when"] == "someday"
    assert "someday" in (root / B).read_text(encoding="utf-8")


def test_workspace_era_label_and_parked_scene(tmp_path):
    api, root = open_api(tmp_path)
    project = Project.open(root)
    project.update_timeline_settings(era="AE")
    put_when(root, A, "2187")
    un = root / "manuscript" / "_unplaced" / "01-spare.md"
    un.parent.mkdir()
    un.write_text("---\nwhen: 1900-05\n---\n# Spare\n\nx\n", encoding="utf-8")
    api.open_project(str(root))
    w = api.get_workspace()["workspace"]
    s = {x["id"]: x for x in w["scenes"]}
    assert s[A]["when"]["label"] == "2187 AE" and s[A]["when"]["value"] == "2187"
    parked = s["manuscript/_unplaced/01-spare.md"]
    assert parked["when"]["source"] == "explicit" and parked["when"]["label"] == "1900-05 AE"
    assert w["timeline"]["era"] == "AE" and w["timeline"]["scenes"] == 1   # parked scenes do not count


def test_workspace_matches_core_timeline(tmp_path):
    api, root = open_api(tmp_path)
    put_when(root, B, "2190")
    api.open_project(str(root))
    project = Project.open(root)
    for t in timeline.scene_times(project):
        got = scenes(api)[t.id]["when"]
        assert (got["value"], got["source"]) == (t.format(), t.source)


# -- set_scene_details / read_document / check_story_time ------------------------------------------


def test_set_scene_details_when_via_bridge(tmp_path):
    api, root = open_api(tmp_path)
    doc = api.read_document(A)
    assert doc["details"]["when"] == ""
    r = api.set_scene_details(A, doc["text"], {"when": "2187-03-14"})
    assert r["ok"] and r["details"]["when"] == "2187-03-14"
    assert r["edit"]["insert"].startswith("---\nwhen:") and r["bodyStart"] > 0
    new = r["edit"]["insert"] + doc["text"][r["edit"]["to"]:]
    assert api.save_document(A, new, doc["mtime"])["ok"]
    assert api.read_document(A)["details"]["when"] == "2187-03-14"
    assert scenes(api)[A]["when"]["value"] == "2187-03-14"
    # clear it again
    cur = api.read_document(A)
    r = api.set_scene_details(A, cur["text"], {"when": ""})
    assert r["ok"] and r["edit"]["insert"] == "" and r["details"]["when"] == ""
    # an invalid value is kept as text, not an error
    r = api.set_scene_details(A, cur["text"], {"when": "the long winter"})
    assert r["ok"] and r["details"]["when"] == "the long winter"


def test_scene_details_other_keys_survive_and_when_is_last_known_key_order(tmp_path):
    text = "---\ntags: [x]\npov: Mara\n---\n# T\n"
    out = scenemeta.set_details(text, when="2187", status="draft")
    meta = scenemeta.find(out).meta
    assert meta["tags"] == ["x"] and meta["when"] == 2187 and meta["status"] == "draft"


def test_check_story_time_bridge(tmp_path):
    api, root = open_api(tmp_path)
    assert api.check_story_time("2187-03-14") == {"ok": True, "valid": True, "normalized": "2187-03-14"}
    assert api.check_story_time("")["valid"] is True
    assert api.check_story_time("later")["valid"] is False
    assert api.check_story_time("-120")["normalized"] == "-120"
    Project.open(root).update_timeline_settings(era="AE")
    api.open_project(str(root))
    assert api.check_story_time("2187 AE") == {"ok": True, "valid": True, "normalized": "2187 AE"}


# -- born and the age line ---------------------------------------------------------------------------


def test_entity_payload_born_and_age_now(tmp_path):
    api, root = open_api(tmp_path)
    plain = api.get_entity("Mara Vale")
    assert plain["born"] == "" and plain["bornInvalid"] is False and plain["ageNow"] == ""
    r = api.set_entity_born("Mara Vale", "2165-03")
    assert r == {"ok": True, "born": "2165-03", "invalid": False}
    put_when(root, A, "2189-05")
    api.open_project(str(root))
    got = api.get_entity("Mara", A)       # by alias, with the open scene
    assert got["born"] == "2165-03" and got["ageNow"] == "age 24 at 2189-05"
    assert api.get_entity("Mara", B)["ageNow"] == "age 24 at 2189-05"   # inherited
    assert api.get_entity("Mara Vale")["ageNow"] == ""                    # no scene open
    project = Project.open(root)
    project.update_timeline_settings(era="AE")
    api.open_project(str(root))
    assert api.get_entity("Mara", A)["ageNow"] == "age 24 at 2189-05 AE"


def test_age_now_is_empty_without_the_pieces(tmp_path):
    api, root = open_api(tmp_path)
    api.set_entity_born("Mara Vale", "2165")
    assert api.get_entity("Mara Vale", A)["ageNow"] == ""     # no story time anywhere
    put_when(root, A, "2100")
    api.open_project(str(root))
    assert api.get_entity("Mara Vale", A)["ageNow"] == ""     # before birth: nothing, not a negative
    api.set_entity_born("Mara Vale", "unknown")
    got = api.get_entity("Mara Vale", A)
    assert got["bornInvalid"] is True and got["born"] == "unknown" and got["ageNow"] == ""


def test_set_entity_born_keeps_other_keys_and_clears(tmp_path):
    api, root = open_api(tmp_path)
    path = root / "entities" / "characters" / "mara-vale.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "aliases:\n- Mara\n", "aliases:\n- Mara\ntags: [pilot]\neyes: grey\n"), encoding="utf-8")
    api.open_project(str(root))
    r = api.set_entity_born("Mara Vale", "-120")
    assert r["ok"] and r["born"] == "-120" and r["invalid"] is False
    e = ent.load_entity(path)
    assert e.extra == {"tags": ["pilot"], "eyes": "grey", "born": -120}
    assert "born: -120\n" in path.read_text(encoding="utf-8")   # a plain number
    assert api.set_entity_born("Mara Vale", "2165-03-14")["ok"]
    assert ent.load_entity(path).extra["born"] in ("2165-03-14",)
    assert api.set_entity_born("Mara Vale", "  ")["born"] == ""
    assert list(ent.load_entity(path).extra) == ["tags", "eyes"]
    assert api.set_entity_born("Nobody", "2000")["ok"] is False


def test_born_round_trips_through_every_save_path(tmp_path):
    api, root = open_api(tmp_path)
    path = root / "entities" / "characters" / "mara-vale.md"
    api.set_entity_born("Mara Vale", "2165-03-14")

    def born_ok():
        return ent.load_entity(path).extra.get("born") in ("2165-03-14", datetime.date(2165, 3, 14))

    doc = api.read_document("entities/characters/mara-vale.md")
    assert api.save_document(doc["id"], doc["text"] + "More.\n", doc["mtime"])["ok"] and born_ok()
    assert api.add_alias("Mara Vale", "Cap")["ok"] and born_ok()
    assert api.apply_aliases([{"entity": "Mara Vale", "surface": "the archivist"}])["added"] == 1
    assert born_ok()
    from lorewrite.core.continuity import apply_canon_update
    apply_canon_update(ent.resolve("Mara Vale", api.entities), ["Left-handed (age 6)."])
    assert born_ok()
    prev = api.rename_preview("Mara Vale", "Mara Okoye")
    assert prev["ok"]
    done = api.rename_apply(prev["plan"], [o["id"] for f in prev["files"] for o in f["occurrences"] if o["defaultOn"]])
    assert done["ok"]
    renamed = root / "entities" / "characters" / "mara-okoye.md"
    assert ent.load_entity(renamed).extra.get("born") is not None
    assert api.get_entity("Mara Okoye")["born"] == "2165-03-14"
    assert api.rename_undo(done["undoId"])["ok"]
    assert born_ok()


# -- never prose, never sent ---------------------------------------------------------------------------


STORY = ("---\npov: Mara Vale\nwhen: 2187-03-14\npurpose: First contact\n---\n"
         "# A City\n\nShe walked.\n\nThen she stopped.\n")


def test_when_is_not_in_ai_context_or_prompts():
    mara = ent.Entity(name="Mara Vale", type="character", body="An archivist.")
    ctx = build_context(STORY, STORY.index("Then"), [mara], {}, None)
    assert "2187" not in ctx and "when" not in ctx.split("SCENE (the new text goes at")[1]
    prompt = ai_cont.build_check_prompt(STORY, {"Mara Vale": "An archivist."})
    assert "2187" not in prompt
    assert scenemeta.header(STORY) == "- POV: Mara Vale\n- Purpose: First contact"


def test_when_is_not_counted_spell_checked_or_sampled(tmp_path):
    text = "---\nwhen: qwxzvk plorb\n---\n# A\n\nOne two three.\n"
    assert drafts.count_words(text) == 5
    assert [m.word for m in spelling.check(text)] == []
    proj = Project.create(tmp_path / "n", "N")
    (proj.manuscript_dir / "01-opening.md").unlink()
    body = " ".join(["word"] * 40)
    (proj.manuscript_dir / "01-a.md").write_text(f"---\nwhen: {' '.join(['plan'] * 40)}\n---\n# A\n\n{body}\n")
    assert all("plan" not in para for _, para in sample_manuscript(proj))


def test_when_does_not_appear_in_workspace_excerpt_or_headings(tmp_path):
    api, root = open_api(tmp_path)
    put_when(root, A, "2187-03-14")
    api.open_project(str(root))
    s = scenes(api)[A]
    assert "2187" not in s["excerpt"] and s["headings"] == [] and s["words"] == ws_words(root)


def ws_words(root):
    return drafts.count_words((root / A).read_text(encoding="utf-8"))


def test_toml_stays_valid_after_timeline_write(tmp_path):
    api, root = open_api(tmp_path)
    Project.open(root).update_timeline_settings(era="AE")
    data = tomllib.loads((root / "project.toml").read_text(encoding="utf-8"))
    assert data["timeline"] == {"era": "AE", "unit": "year"} and data["title"] == "Test Novel"


def test_no_story_time_project_files_are_untouched_by_reading_features(tmp_path):
    api, root = open_api(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*.md")}
    api.get_workspace()
    api.get_entity("Mara Vale", A)
    api.read_document(A)
    api.check_story_time("2187")
    assert before == {p: p.read_bytes() for p in root.rglob("*.md")}
    assert "[timeline]" not in (root / "project.toml").read_text(encoding="utf-8")
