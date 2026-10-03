"""core/timeline.py: optional story time (when:, born:, [timeline]), fact tags."""

import datetime
from pathlib import Path

import pytest

from chisel.core import drafts, scenemeta, timeline
from chisel.core import entities as ent
from chisel.core.project import Project
from chisel.core.timeline import FactTag, StoryTime, parse_fact_tags, parse_story_time

T = StoryTime


def make(tmp_path: Path, scenes: dict[str, str | None]) -> Project:
    project = Project.create(tmp_path / "book", "Book")
    (project.manuscript_dir / "01-opening.md").unlink()
    for name, when in scenes.items():
        path = project.manuscript_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        head = f"---\nwhen: {when}\n---\n" if when is not None else ""
        path.write_text(f"{head}# {path.stem}\n\nText.\n", encoding="utf-8", newline="\n")
    return project


def short(result) -> list[str]:
    return [s.id.split("/")[-1][:4] for s in result.scenes]


# -- parsing and comparing ---------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("2187", T(2187)), ("2187-03", T(2187, 3)), ("2187-03-14", T(2187, 3, 14)),
    ("  2187-3-4 ", T(2187, 3, 4)), ("-120", T(-120)), ("0", T(0)), ("-120-03-14", T(-120, 3, 14)),
    ("123456789012", T(123456789012)), ("99999-12", T(99999, 12)),
])
def test_parse_forms(text, expected):
    assert parse_story_time(text) == expected
    assert StoryTime.parse(text) == expected


@pytest.mark.parametrize("text", [
    "", "   ", "soon", "2187-13", "2187-00", "2187-03-32", "2187-03-00", "2187-03-14-01",
    "year 2187", "2187.5", "--5", "2187/03/14", "+2187", "1234567890123", None, True, 2.5, [],
    "2187 AE",
])
def test_parse_rejects(text):
    assert parse_story_time(text) is None


def test_parse_yaml_values_and_era():
    assert parse_story_time(2187) == T(2187)
    assert parse_story_time(-5) == T(-5)
    assert parse_story_time(datetime.date(2187, 3, 14)) == T(2187, 3, 14)
    assert parse_story_time("2187 AE", era="AE") == T(2187)
    assert parse_story_time("2187-03 ae", era="AE") == T(2187, 3)
    assert parse_story_time("2187AE", era="AE") is None
    assert parse_story_time("AE", era="AE") is None


def test_format_and_round_trip():
    assert T(2187).format() == "2187"
    assert T(2187, 3).format() == "2187-03"
    assert T(2187, 3, 4).format("AE") == "2187-03-04 AE"
    assert T(-120).format("BE") == "-120 BE"
    assert parse_story_time(T(5, 6, 7).format()) == T(5, 6, 7)


def test_invalid_story_time_objects_refuse():
    with pytest.raises(ValueError):
        T(2187, None, 4)
    with pytest.raises(ValueError):
        T(2187, 13)


def test_ordering_missing_month_and_day_sort_first():
    assert T(2187) < T(2187, 1) < T(2187, 1, 1) < T(2187, 1, 2) < T(2187, 2) < T(2188)
    assert T(-120) < T(-1) < T(0) < T(1) < T(10 ** 9)
    assert sorted([T(2187, 3), T(2187), T(2186, 12, 31), T(2187, 3, 1)]) == [
        T(2186, 12, 31), T(2187), T(2187, 3), T(2187, 3, 1)]
    assert T(2187, 3) == T(2187, 3) and T(2187) != T(2187, 1)
    assert T(2187, 3) >= T(2187) and T(2187) <= T(2187)


# -- scenes in reading order ---------------------------------------------------------------


def test_scene_times_explicit_inherited_and_none_first(tmp_path):
    project = make(tmp_path, {"01-a.md": None, "02-b.md": "2187", "03-c.md": None,
                              "04-d.md": "2190-06", "05-e.md": None})
    times = timeline.scene_times(project)
    assert [(t.when, t.source) for t in times] == [
        (None, "none"), (T(2187), "explicit"), (T(2187), "inherited"),
        (T(2190, 6), "explicit"), (T(2190, 6), "inherited")]
    assert times[0].id == "manuscript/01-a.md"
    assert timeline.mode(project).mode == "chronological"


def test_inheritance_is_by_reading_order_not_by_time(tmp_path):
    project = make(tmp_path, {"01-a.md": "2200", "02-b.md": None, "03-c.md": "2100", "04-d.md": None})
    assert [t.when for t in timeline.scene_times(project)] == [T(2200), T(2200), T(2100), T(2100)]


def test_invalid_when_is_reported_not_explicit_and_not_dropped(tmp_path):
    project = make(tmp_path, {"01-a.md": "2187", "02-b.md": "someday", "03-c.md": "soon"})
    times = timeline.scene_times(project)
    assert [(t.source, t.invalid, t.raw) for t in times] == [
        ("explicit", False, "2187"), ("inherited", True, "someday"), ("inherited", True, "soon")]
    assert "someday" in (project.manuscript_dir / "02-b.md").read_text(encoding="utf-8")
    only_bad = make(tmp_path / "x", {"01-a.md": "nope"})
    t = timeline.scene_times(only_bad)[0]
    assert (t.when, t.source, t.invalid) == (None, "none", True)
    assert timeline.mode(only_bad).mode == "reading-order"


def test_parked_scenes_are_not_in_reading_order(tmp_path):
    project = make(tmp_path, {"01-a.md": "2187"})
    un = project.manuscript_dir / "_unplaced" / "01-spare.md"
    un.parent.mkdir()
    un.write_text("---\nwhen: 1900\n---\n# Spare\n\nx\n", encoding="utf-8")
    assert [t.id for t in timeline.scene_times(project)] == ["manuscript/01-a.md"]
    assert timeline.mode(project).scenes == 1


def test_mode_sentences(tmp_path):
    none = make(tmp_path / "a", {"01-a.md": None, "02-b.md": None})
    m = timeline.mode(none)
    assert m.mode == "reading-order" and m.scenes == 0
    assert m.sentence == "No story times set; using reading order"
    one = make(tmp_path / "b", {"01-a.md": "2187", "02-b.md": None})
    assert timeline.mode(one).sentence == "Using story time from 1 scene"
    two = make(tmp_path / "c", {"01-a.md": "2187", "02-b.md": "2188"})
    m = timeline.mode(two)
    assert m.sentence == "Using story time from 2 scenes"
    assert m.to_dict() == {"mode": "chronological", "scenes": 2, "sentence": m.sentence}
    empty = Project.create(tmp_path / "d", "E")
    (empty.manuscript_dir / "01-opening.md").unlink()
    assert timeline.mode(empty).mode == "reading-order"


def test_era_accepted_in_scene_when(tmp_path):
    project = make(tmp_path, {"01-a.md": "2187 AE"})
    assert timeline.scene_times(project)[0].invalid is True   # no era configured: not a time
    project.update_timeline_settings(era="AE")
    t = timeline.scene_times(project)[0]
    assert (t.when, t.invalid) == (T(2187), False)
    assert t.format("AE") == "2187 AE"


# -- scenes_up_to ------------------------------------------------------------------------------


def test_scenes_up_to_reading_order_when_no_story_times(tmp_path):
    project = make(tmp_path, {"01-a.md": None, "02-b.md": None, "03-c.md": None})
    r = timeline.scenes_up_to(project, "manuscript/02-b.md")
    assert r.mode == "reading-order"
    assert [s.id for s in r.scenes] == ["manuscript/01-a.md", "manuscript/02-b.md"]
    assert r.sentence == "No story times set; using reading order"
    assert r.target.id == "manuscript/02-b.md"


def test_scenes_up_to_by_story_time_flashback_and_ties(tmp_path):
    # reading order: a(2190) b(2185 flashback) c(2190 again) d(inherits 2190) e(2195)
    project = make(tmp_path, {"01-a.md": "2190", "02-b.md": "2185", "03-c.md": "2190",
                              "04-d.md": None, "05-e.md": "2195"})
    r = timeline.scenes_up_to(project, "manuscript/02-b.md")
    assert r.mode == "chronological" and short(r) == ["02-b"]
    r = timeline.scenes_up_to(project, "manuscript/03-c.md")
    assert short(r) == ["01-a", "02-b", "03-c"]
    r = timeline.scenes_up_to(project, "manuscript/01-a.md")
    # b (2185) is earlier in story time than a although later in the book, so it counts;
    # c ties with a at 2190 but is after it in reading order, so it does not
    assert short(r) == ["01-a", "02-b"]
    r = timeline.scenes_up_to(project, "manuscript/04-d.md")
    assert short(r) == ["01-a", "02-b", "03-c", "04-d"]
    r = timeline.scenes_up_to(project, "manuscript/05-e.md")
    assert short(r) == ["01-a", "02-b", "03-c", "04-d", "05-e"]


def test_scenes_up_to_flashback_target_includes_earlier_time_from_later_in_book(tmp_path):
    project = make(tmp_path, {"01-a.md": "2190", "02-b.md": "2185", "03-c.md": "2100"})
    r = timeline.scenes_up_to(project, "manuscript/02-b.md")
    # c (2100) is before b (2185) in story time even though it is later in the book
    assert short(r) == ["02-b", "03-c"]


def test_scenes_up_to_future_in_story_is_excluded(tmp_path):
    project = make(tmp_path, {"01-a.md": "2200", "02-b.md": "2100", "03-c.md": "2150"})
    r = timeline.scenes_up_to(project, "manuscript/03-c.md")
    assert short(r) == ["02-b", "03-c"]


def test_target_without_story_time_falls_back_and_says_so(tmp_path):
    project = make(tmp_path, {"01-a.md": None, "02-b.md": "2187", "03-c.md": None})
    r = timeline.scenes_up_to(project, "manuscript/01-a.md")
    assert r.mode == "reading-order" and short(r) == ["01-a"]
    assert "no story time" in r.sentence and "reading order" in r.sentence
    r = timeline.scenes_up_to(project, "manuscript/03-c.md")
    assert r.mode == "chronological"
    # the undated opening scene is placed by reading order, and listed as such
    assert r.undated == ["manuscript/01-a.md"]
    assert short(r) == ["01-a", "02-b", "03-c"]


def test_scenes_up_to_excludes_parked_and_unknown(tmp_path):
    project = make(tmp_path, {"01-a.md": "2187"})
    un = project.manuscript_dir / "_unplaced" / "01-spare.md"
    un.parent.mkdir()
    un.write_text("# Spare\n\nx\n", encoding="utf-8")
    r = timeline.scenes_up_to(project, "manuscript/_unplaced/01-spare.md")
    assert r.scenes == [] and "not in the book" in r.sentence
    assert timeline.scenes_up_to(project, "manuscript/nope.md").scenes == []
    r = timeline.scenes_up_to(project, "manuscript/01-a.md")
    assert all("_unplaced" not in s.id for s in r.scenes)


def test_scenes_up_to_never_touches_or_reorders_files(tmp_path):
    project = make(tmp_path, {"01-a.md": "2190", "02-b.md": "2185"})
    before = {p: p.read_bytes() for p in project.manuscript_dir.glob("*.md")}
    timeline.scenes_up_to(project, "manuscript/02-b.md")
    assert before == {p: p.read_bytes() for p in project.manuscript_dir.glob("*.md")}
    assert [p.name for p in project.list_scenes()] == ["01-a.md", "02-b.md"]


# -- ages ---------------------------------------------------------------------------------------


def person(born) -> ent.Entity:
    return ent.Entity(name="Mara", extra={} if born is None else {"born": born})


@pytest.mark.parametrize("born, when, years", [
    ("2165", T(2189), 24),
    ("2165-03", T(2189, 2), 23), ("2165-03", T(2189, 3), 24), ("2165-03", T(2189, 4), 24),
    ("2165-03-14", T(2189, 3, 13), 23), ("2165-03-14", T(2189, 3, 14), 24),
    ("2165-03-14", T(2189, 3, 15), 24),
    ("2165-03-14", T(2189), 24),          # when has no month: year difference
    ("2165", T(2189, 1, 1), 24),          # born has no month: year difference
    ("2165-03", T(2189, 3, 1), 24),       # born has no day: month decides
    ("2165-03-14", T(2189, 3), 24),       # when has no day
    ("2165", T(2165), 0), ("2165-03-14", T(2165, 3, 14), 0), ("2165-03", T(2165, 3), 0),
    (-120, T(-100), 20), (-1, T(1), 2), (0, T(0), 0),
    (datetime.date(2165, 3, 14), T(2190, 3, 14), 25),
    ("99999-06", T(100010, 6), 11),
])
def test_age_at(born, when, years):
    age = timeline.age_at(person(born), when)
    assert age.years == years and bool(age) and age.reason == ""


@pytest.mark.parametrize("born, when", [
    ("2165", T(2164)), ("2165-03", T(2165, 2)), ("2165-03-14", T(2165, 3, 13)),
    ("2165-03-14", T(2165, 2, 28)), ("2165", T(-5)),
])
def test_age_before_birth_is_none_with_reason(born, when):
    age = timeline.age_at(person(born), when)
    assert age.years is None and age.reason == "before birth" and not age


def test_age_reasons():
    assert timeline.age_at(person(None), T(2189)).reason == "no born"
    assert timeline.age_at(person(""), T(2189)).reason == "no born"
    assert timeline.age_at(person("long ago"), T(2189)).reason == "invalid born"
    assert timeline.age_at(person("2165"), None).reason == "no story time"
    assert timeline.age_at(person("2165 AE"), T(2189), era="AE").years == 24


def test_age_label():
    assert timeline.age_label(person("2165"), T(2189)) == "age 24 at 2189"
    assert timeline.age_label(person("2165"), T(2189, 3), era="AE") == "age 24 at 2189-03 AE"
    assert timeline.age_label(person("2165"), T(2100)) == ""
    assert timeline.age_label(person(None), T(2189)) == ""
    assert timeline.age_label(person("2165"), None) == ""


def test_born_of_reads_dates_and_ints():
    assert timeline.born_of(person(datetime.date(2165, 3, 14))) == ("2165-03-14", T(2165, 3, 14))
    assert timeline.born_of(person(2165)) == ("2165", T(2165))
    assert timeline.born_of(person("x y")) == ("x y", None)


# -- fact tags ------------------------------------------------------------------------------------


@pytest.mark.parametrize("line, clean, tag", [
    ("- Plays the cello (age 12)", "- Plays the cello", FactTag("at", age=12)),
    ("- Plays the cello (from age 15)", "- Plays the cello", FactTag("from", age=15)),
    ("- Plays the cello (until age 20)", "- Plays the cello", FactTag("until", age=20)),
    ("- Lives in Meridian (from 2185)", "- Lives in Meridian", FactTag("from", time=T(2185))),
    ("- Lives in Meridian (until 2190-06)", "- Lives in Meridian", FactTag("until", time=T(2190, 6))),
    ("Has a scar (UNTIL 2190-06-02)  ", "Has a scar", FactTag("until", time=T(2190, 6, 2))),
    ("- Soldier (from -120)", "- Soldier", FactTag("from", time=T(-120))),
    ("* Left-handed (age   7)", "* Left-handed", FactTag("at", age=7)),
    ("Born under a (red) moon (age 0)", "Born under a (red) moon", FactTag("at", age=0)),
])
def test_parse_fact_tags(line, clean, tag):
    assert parse_fact_tags(line) == (clean, tag)


@pytest.mark.parametrize("line", [
    "- Plays the cello", "", "- Plays (age twelve)", "- Plays (age)", "- Plays (from)",
    "- Plays (from 2185-13)", "- Plays (from soon)", "- Plays (age 12) and more",
    "(age 12)", "- (age 12)", "- Plays (age 12", "- Plays age 12)", "- Plays (age 12 13)",
    "- Plays (before 2185)", "- Plays (age -3)", "- Plays (from age x)", "- Plays (from age 12345)",
])
def test_parse_fact_tags_malformed_or_absent(line):
    assert parse_fact_tags(line) == (line, None)


# -- project.toml [timeline] ------------------------------------------------------------------------


def test_timeline_settings_defaults_and_round_trip(tmp_path):
    project = make(tmp_path, {"01-a.md": None})
    assert project.timeline_settings() == {"era": "", "unit": "year"}
    project.update_timeline_settings(era="AE")
    assert project.timeline_settings() == {"era": "AE", "unit": "year"}
    assert Project.open(project.root).timeline_settings() == {"era": "AE", "unit": "year"}
    text = (project.root / "project.toml").read_text(encoding="utf-8")
    assert '[timeline]\nera = "AE"\nunit = "year"' in text and 'title = "Book"' in text
    project.update_timeline_settings(era="")   # clearing keeps the unit
    assert Project.open(project.root).timeline_settings() == {"era": "", "unit": "year"}
    odd = 'Era "of" Ünïcode \\'
    project.update_timeline_settings(era=odd)
    assert Project.open(project.root).timeline_settings()["era"] == odd


def test_timeline_settings_preserve_other_sections(tmp_path):
    project = make(tmp_path, {"01-a.md": None})
    project.update_editor_settings(padding=3)
    project.update_timeline_settings(era="AE")
    project.update_manuscript_settings(unit="chapter")
    reopened = Project.open(project.root)
    assert reopened.editor_settings()["padding"] == 3 and reopened.unit == "chapter"
    assert reopened.timeline_settings()["era"] == "AE"


def test_timeline_settings_validation(tmp_path):
    project = make(tmp_path, {"01-a.md": None})
    with pytest.raises(ValueError):
        project.update_timeline_settings(unit="month")
    for bad in (5, ["AE"], {"a": 1}):
        with pytest.raises(ValueError):
            project.update_timeline_settings(era=bad)
    with pytest.raises(ValueError):
        project.update_timeline_settings(era="x" * 25)
    assert project.timeline_settings() == {"era": "", "unit": "year"}
    assert "[timeline]" not in (project.root / "project.toml").read_text(encoding="utf-8")


@pytest.mark.parametrize("toml, expected", [
    ("[timeline]\nera = 5\n", {"era": "", "unit": "year"}),
    ("[timeline]\nera = [1, 2]\n", {"era": "", "unit": "year"}),
    ("[timeline]\nera = true\nunit = \"month\"\n", {"era": "", "unit": "year"}),
    ("[timeline]\nera = \"  AE \"\nunit = 3\n", {"era": "AE", "unit": "year"}),
    ("[timeline]\nera = \"" + "x" * 30 + "\"\n", {"era": "", "unit": "year"}),
])
def test_hand_written_timeline_section_never_crashes(tmp_path, toml, expected):
    project = make(tmp_path, {"01-a.md": None})
    path = project.root / "project.toml"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + toml, encoding="utf-8")
    assert Project.open(project.root).timeline_settings() == expected


def test_timeline_key_that_is_not_a_table_reads_as_default(tmp_path):
    project = make(tmp_path, {"01-a.md": None})
    project.meta["timeline"] = 4
    assert project.timeline_settings() == {"era": "", "unit": "year"}


# -- the scene field `when` -------------------------------------------------------------------------


def test_when_is_a_scene_detail_set_cleared_and_round_trips():
    text = "# T\n\nBody.\n"
    out = scenemeta.set_details(text, when="2187")
    assert out.startswith("---\nwhen: 2187\n---\n") and scenemeta.details(out)["when"] == "2187"
    out = scenemeta.set_details(out, when="2187-03-14", pov="Mara")
    assert scenemeta.details(out)["when"] == "2187-03-14" and scenemeta.details(out)["pov"] == "Mara"
    assert scenemeta.set_details(scenemeta.set_details(out, when=""), pov="") == text
    assert scenemeta.details(scenemeta.set_details(text, when="-120"))["when"] == "-120"
    # an invalid value is kept as typed
    kept = scenemeta.set_details(text, when="  some   day ")
    assert scenemeta.details(kept)["when"] == "some day"
    # hand-written values: YAML reads 2187-03-14 as a date, 2187 as a number
    assert scenemeta.details("---\nwhen: 2187-03-14\n---\n# T\n")["when"] == "2187-03-14"
    assert scenemeta.details("---\nwhen: 2187\n---\n# T\n")["when"] == "2187"
    assert scenemeta.details("---\nwhen: -120\n---\n# T\n")["when"] == "-120"
    assert timeline.explicit_when("---\nwhen: 2187-03-14\n---\n# T\n")[1] == T(2187, 3, 14)


def test_when_never_counts_as_prose_or_mention():
    text = "---\npov: Mara\nwhen: 2187-03-14\nplace: Meridian\n---\n# T\n\nOne two three.\n"
    assert "2187" not in scenemeta.strip(text)
    assert drafts.count_words(text) == drafts.count_words(scenemeta.strip(text)) == 5
    blanked = scenemeta.blank(text)
    assert "2187" not in blanked and len(blanked) == len(text)
    kept = scenemeta.blank(text, keep=scenemeta.MENTION_FIELDS)
    assert "Mara" in kept and "Meridian" in kept and "2187" not in kept and len(kept) == len(text)
    assert "2187" not in scenemeta.header(text)
