"""Core continuity logic: Contradiction, waivers, canon, locate_evidence."""

from pathlib import Path

import pytest

from lorewrite.core.continuity import (
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
from lorewrite.core import entities as ent


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
    wpath = tmp_path / ".lorewrite" / "waivers.json"
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
    apply_canon_update(entity, "Elara has blue eyes.")
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
