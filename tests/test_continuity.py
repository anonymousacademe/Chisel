"""Core continuity logic: Contradiction, waivers, canon, locate_evidence."""

from pathlib import Path

import pytest

from chisel.core.continuity import (
    CANON_HEADER,
    Contradiction,
    apply_canon_update,
    contradiction_from_dict,
    filter_waived,
    get_canon,
    load_waivers,
    locate_evidence,
    save_waiver,
    set_canon,
)
from chisel.core import entities as ent


# -- Contradiction.waiver_key --------------------------------------------------


def test_waiver_key_stable_across_different_ids():
    c1 = Contradiction("timeline", "error", "Elara", "arrived before departing", "fix", scene="s1.md", row=3)
    c2 = Contradiction("timeline", "error", "Elara", "arrived before departing", "fix", scene="s2.md", row=99)
    assert c1.waiver_key() == c2.waiver_key()


def test_waiver_key_differs_on_different_evidence():
    c1 = Contradiction("timeline", "error", "Elara", "arrived before departing", "fix")
    c2 = Contradiction("timeline", "error", "Elara", "left before arriving", "fix")
    assert c1.waiver_key() != c2.waiver_key()


# -- contradiction_from_dict --------------------------------------------------


def test_contradiction_from_dict_valid():
    data = {"type": "timeline", "severity": "error", "entity": "Elara",
            "evidence": "arrived before departing", "suggested_fix": "reorder"}
    c = contradiction_from_dict(data, scene="ch1.md", row=5)
    assert c is not None
    assert c.type == "timeline"
    assert c.scene == "ch1.md"
    assert c.row == 5


def test_contradiction_from_dict_bad_type():
    data = {"type": "bogus", "severity": "error", "entity": "Elara",
            "evidence": "x", "suggested_fix": "fix"}
    assert contradiction_from_dict(data) is None


def test_contradiction_from_dict_bad_severity():
    data = {"type": "timeline", "severity": "critical", "entity": "Elara",
            "evidence": "x", "suggested_fix": "fix"}
    assert contradiction_from_dict(data) is None


def test_contradiction_from_dict_missing_fields():
    for bad in [
        {"type": "timeline", "severity": "error"},
        {"type": "timeline", "severity": "error", "entity": "Elara"},
        None,
        "not a dict",
    ]:
        assert contradiction_from_dict(bad) is None  # type: ignore[arg-type]


def test_contradiction_from_dict_empty_entity_or_evidence():
    data = {"type": "timeline", "severity": "error", "entity": "",
            "evidence": "x", "suggested_fix": "fix"}
    assert contradiction_from_dict(data) is None
    data2 = {"type": "timeline", "severity": "error", "entity": "Elara",
             "evidence": "", "suggested_fix": "fix"}
    assert contradiction_from_dict(data2) is None


# -- waivers -------------------------------------------------------------------


def test_waiver_save_load_roundtrip(tmp_path: Path):
    c = Contradiction("timeline", "error", "Elara", "arrived before departing", "fix")
    save_waiver(tmp_path, c.waiver_key())
    waived = load_waivers(tmp_path)
    assert c.waiver_key() in waived


def test_filter_waived_removes_waived():
    c1 = Contradiction("timeline", "error", "Elara", "arrived before departing", "fix")
    c2 = Contradiction("physical_attribute", "warning", "Borin", "blue eyes then brown", "fix")
    waived = {c1.waiver_key()}
    result = filter_waived([c1, c2], waived)
    assert result == [c2]


def test_load_waivers_corrupt_file_tolerated(tmp_path: Path):
    wpath = tmp_path / ".chisel" / "waivers.json"
    wpath.parent.mkdir(parents=True, exist_ok=True)
    wpath.write_text("NOT JSON{{{{", encoding="utf-8")
    assert load_waivers(tmp_path) == set()


# -- canon sections -------------------------------------------------------------


def test_get_canon_empty_when_absent():
    assert get_canon("Some author text\n") == ""


def test_set_canon_appends_to_empty_body():
    result = set_canon("", "Elara has blue eyes.")
    assert CANON_HEADER in result
    assert "Elara has blue eyes." in result


def test_set_canon_preserves_author_text():
    body = "Author wrote this.\n\n## Notes\n\nSome notes.\n"
    result = set_canon(body, "Canon fact.")
    assert "Author wrote this." in result
    assert "## Notes" in result
    assert "Some notes." in result
    assert "Canon fact." in result


def test_set_canon_replaces_existing_section():
    body = set_canon("", "Old canon.")
    result = set_canon(body, "New canon.")
    assert "Old canon." not in result
    assert "New canon." in result


def test_set_canon_does_not_touch_other_sections():
    body = f"Intro\n\n{CANON_HEADER}\n\nOld canon.\n\n## Notes\n\nKeep me.\n"
    result = set_canon(body, "New canon.")
    assert "## Notes" in result
    assert "Keep me." in result
    assert "Old canon." not in result
    assert "New canon." in result


def test_apply_canon_update_saves_to_disk(tmp_path: Path):
    path = tmp_path / "elara.md"
    ent.save_entity(ent.Entity(name="Elara", type="character"), path)
    entity = ent.load_entity(path)
    apply_canon_update(entity, ["Elara has blue eyes."])
    reloaded = ent.load_entity(path)
    canon = get_canon(reloaded.body)
    assert "Elara has blue eyes." in canon


# -- locate_evidence -----------------------------------------------------------


def test_locate_evidence_finds_row():
    text = "Line zero.\nElara arrived at dawn.\nLine two.\n"
    assert locate_evidence(text, "Elara arrived at dawn") == 1


def test_locate_evidence_absent_returns_none():
    text = "Nothing relevant here.\n"
    assert locate_evidence(text, "Elara arrived at dawn") is None


def test_add_canon_facts_appends_and_never_removes():
    from chisel.core.continuity import add_canon_facts

    body = "Author text.\n\n## Canon (auto)\n\n- Blue eyes\n- Left-handed\n\n## Notes\n\nKeep.\n"
    out = add_canon_facts(body, ["Owns a boat", "blue eyes.", "  - Owns a boat "])
    canon = get_canon(out)
    assert canon.splitlines() == ["- Blue eyes", "- Left-handed", "- Owns a boat"]
    assert out.startswith("Author text.") and "## Notes\n\nKeep." in out


def test_add_canon_facts_creates_section_and_noop_when_all_dupes():
    from chisel.core.continuity import add_canon_facts

    out = add_canon_facts("Intro.\n", ["First fact"])
    assert out.startswith("Intro.") and get_canon(out) == "- First fact"
    assert add_canon_facts(out, ["first fact"]) == out


def test_second_update_never_removes_first_facts(tmp_path: Path):
    path = tmp_path / "elara.md"
    ent.save_entity(ent.Entity(name="Elara", type="character"), path)
    entity = ent.load_entity(path)
    apply_canon_update(entity, ["Has blue eyes"])
    apply_canon_update(ent.load_entity(path), ["Scar on left hand"])
    lines = get_canon(ent.load_entity(path).body).splitlines()
    assert lines == ["- Has blue eyes", "- Scar on left hand"]


def test_waivers_record_scene_and_clear_by_scene(tmp_path: Path):
    from chisel.core.continuity import clear_scene_waivers, remove_waiver

    save_waiver(tmp_path, "k1", "manuscript/01.md")
    save_waiver(tmp_path, "k2", "manuscript/01.md")
    save_waiver(tmp_path, "k3", "manuscript/02.md")
    assert clear_scene_waivers(tmp_path, "manuscript/01.md") == 2
    assert load_waivers(tmp_path) == {"k3"}
    assert clear_scene_waivers(tmp_path, "manuscript/01.md") == 0
    remove_waiver(tmp_path, "k3")
    assert load_waivers(tmp_path) == set()


def test_legacy_waivers_file_without_scenes_still_loads(tmp_path: Path):
    wpath = tmp_path / ".chisel" / "waivers.json"
    wpath.parent.mkdir(parents=True)
    wpath.write_text('{"waived": ["old1"]}')
    assert load_waivers(tmp_path) == {"old1"}
    save_waiver(tmp_path, "new1", "manuscript/01.md")
    assert load_waivers(tmp_path) == {"old1", "new1"}


def test_locate_evidence_across_hard_wrapped_lines():
    from chisel.core.continuity import locate_evidence

    text = "First line.\nShe stood in the kitchen with one hand\naround a cup gone cold.\n"
    assert locate_evidence(text, "She stood in the kitchen with one hand around a cup") == 1
    assert locate_evidence(text, "First line.") == 0
    assert locate_evidence(text, "not there at all") is None
