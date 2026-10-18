"""Dialogue by speaker (core/voice.py): speeches, filing under characters, references from other scenes."""

from chisel.core import entities as ent
from chisel.core import voice
from chisel.core.project import Project

SCENE = """\
---
pov: Keith
---
# Kitchen

INT. KITCHEN - DAY

Keith burns the toast.

KEITH (V.O.)
(to himself)
Burnt again.
<!-- a note between lines -->
Every single time.

MARA
Don't start.


KEITH
Fine.

WAITER
Anything else?
"""


def entities():
    keith = ent.Entity(name="Keith", type="character", aliases=["Keefer"])
    return [keith, ent.Entity(name="Mara", type="character")]


def test_speeches_group_a_cue_with_its_spoken_lines():
    got = voice.speeches(SCENE, entities())
    assert [(s.speaker, s.cue, s.lines) for s in got] == [
        ("Keith", "KEITH", ("Burnt again.", "Every single time.")),
        ("Mara", "MARA", ("Don't start.",)),
        ("Keith", "KEITH", ("Fine.",)),
        ("Waiter", "WAITER", ("Anything else?",)),
    ]
    first = got[0]
    assert first.text == "Burnt again. Every single time." and first.words == 5
    lines = SCENE.split("\n")
    assert lines[first.row].startswith("KEITH (V.O.)")                  # rows are rows of the text given
    assert [lines[r] for r in first.rows] == ["Burnt again.", "Every single time."]


def test_a_note_or_parenthetical_does_not_end_a_speech_but_action_does():
    text = "\nBOB\n(softly)\nHi.\n<!-- n -->\nThere.\nAction line.\nMore text.\n"
    [s] = voice.speeches(text)
    assert s.lines == ("Hi.", "There.", "Action line.", "More text.")   # nothing ended it: no blank line
    text = "\nBOB\nHi.\n\nA stranger walks in.\n"
    assert [x.lines for x in voice.speeches(text)] == [("Hi.",)]


def test_a_two_space_line_keeps_a_speech_going():
    [s] = voice.speeches("\nBOB\nOne.\n  \nTwo.\n")
    assert s.lines == ("One.", "Two.")


def test_a_cue_with_no_speech_is_not_a_speech():
    assert voice.speeches("\nBOB\n\nINT. A - DAY\n") == []
    assert voice.speeches("") == []


def test_aliases_and_case_file_a_cue_under_the_note():
    text = "\nKEEFER\nHi.\n\n@keith\nHo.\n\n@mara ^\nHm.\n"
    assert [s.speaker for s in voice.speeches(text, entities())] == ["Keith", "Keith", "Mara"]
    assert voice.speaker_key("MRS. ALLEN") == "Mrs. Allen"             # no note: the cue as written


def test_by_speaker_keeps_order_of_first_appearance():
    filed = voice.by_speaker(SCENE, entities())
    assert list(filed) == ["Keith", "Mara", "Waiter"]
    assert voice.line_count(filed["Keith"]) == 3


def _script(tmp_path):
    p = Project.create(tmp_path / "s", "S", "script")
    (p.manuscript_dir / "01-opening.md").unlink()
    act = p.new_part("Act One")
    scenes = {}
    for n, (title, body) in enumerate([
        ("One", "INT. A - DAY\n\nKEITH\nOne a.\nOne b.\n\nMARA\nMara one.\n"),
        ("Two", "INT. B - DAY\n\nKEITH\nTwo a.\n"),
        ("Three", "INT. C - DAY\n\nKEITH\nThree a.\n\nWAITER\nWaiter three.\n"),
        ("Four", "INT. D - DAY\n\nKEITH\nFour a.\n"),
        ("Five", "INT. E - DAY\n\nKEITH\nFive a.\n<!--ai-->\nKEITH\nDrafted line.\n<!--/ai-->\n"),
    ], 1):
        path = p.next_scene_path(title, act)
        path.write_text(f"# {title}\n\n{body}", encoding="utf-8", newline="\n")
        scenes[title] = path
    return Project.open(tmp_path / "s"), scenes


def test_references_are_the_same_speakers_lines_in_other_scenes_nearest_first(tmp_path):
    p, scenes = _script(tmp_path)
    refs = voice.gather_references(p, entities(), scenes["Three"], {"Keith", "Mara"})
    assert set(refs) == {"Keith", "Mara"}                            # the Waiter was not asked for
    assert [(e.scene, e.distance) for e in refs["Keith"]] == [("Two", 1), ("Four", 1), ("One", 2), ("Five", 2)]
    assert [e.lines for e in refs["Keith"]][:2] == [("Two a.",), ("Four a.",)]
    assert voice.reference_lines(refs["Keith"]) == 5                  # the scene being checked is never its own reference
    assert "Drafted line." not in str(refs)                           # an unaccepted AI draft is not canon
    text = voice.format_reference(refs["Mara"])
    assert text == "[One]\n- Mara one."


def test_references_for_every_speaker_when_none_are_named(tmp_path):
    p, scenes = _script(tmp_path)
    refs = voice.gather_references(p, entities(), scenes["One"])
    assert set(refs) == {"Keith", "Waiter"}


def test_a_parked_scene_has_every_scene_as_a_reference(tmp_path):
    p, scenes = _script(tmp_path)
    parked = p.manuscript_dir / "_unplaced" / "01-loose.md"
    parked.parent.mkdir(parents=True, exist_ok=True)
    parked.write_text("# Loose\n\nINT. X - DAY\n\nKEITH\nLoose a.\n", encoding="utf-8", newline="\n")
    refs = voice.gather_references(Project.open(tmp_path / "s"), entities(), parked, {"Keith"})
    assert [e.scene for e in refs["Keith"]][0] == "Five"             # nearest to "after the book" first
