"""Regressions found by the independent review of script mode (notes next to text, import speed, word counts)."""

import time

from chisel.core import fountain as f
from chisel.core import fountainio
from chisel.core.project import Project
from chisel.gui import workspace as ws
from tests.test_script_export import make_script


def printed(text):
    """What a reader sees: (kind, lines) of every printing block."""
    return [(b.kind, b.lines) for b in f.blocks(text) if b.kind not in (f.SECTION, f.SYNOPSIS)]


def test_text_beside_a_note_or_boneyard_is_kept():
    assert printed("<!-- note --> Real action text.\n") == [(f.ACTION, [" Real action text."])] or \
        printed("<!-- note --> Real action text.\n")[0][1][0].strip() == "Real action text."
    assert printed("/* old */ kept text\n")[0][1][0].strip() == "kept text"
    assert printed("<!-- long\nnote --> then stops here.\n")[0][1][0].strip() == "then stops here."
    assert f.word_count("<!-- note --> Real action text.\n") == 3


def test_a_note_mid_line_or_across_lines_never_prints():
    rows = printed("He runs. <!-- long\nnote --> then stops.\n")
    assert [ln.strip() for _k, lines in rows for ln in lines] == ["He runs.", "then stops."]
    assert "note" not in str(rows) and "<!--" not in str(rows)
    assert printed("Hi <!-- x --> there\n")[0][1] == ["Hi there"]          # no double space left behind


def test_a_note_between_a_cue_and_its_speech_does_not_end_the_speech():
    kinds = [ln.kind for ln in f.parse("BOB\n<!-- n -->\nHello there.\n") if ln.kind not in (f.NOTE, f.BLANK)]
    assert kinds == [f.CHARACTER, f.DIALOGUE]
    kinds = [ln.kind for ln in f.parse("BOB\nHi.\n<!-- n -->\nMore here.\n") if ln.kind not in (f.NOTE, f.BLANK)]
    assert kinds == [f.CHARACTER, f.DIALOGUE, f.DIALOGUE]
    assert [b.lines for b in f.blocks("BOB\nHi.\n<!-- n -->\nMore here.\n") if b.kind == f.DIALOGUE] == [["Hi.", "More here."]]


def test_a_cue_or_parenthetical_with_a_trailing_note_keeps_its_type():
    assert [b.kind for b in f.blocks("BOB <!-- hi -->\nHello\n")] == [f.CHARACTER, f.DIALOGUE]
    assert [b.kind for b in f.blocks("BOB\n(beat) <!-- x -->\nHello\n")] == [f.CHARACTER, f.PARENTHETICAL, f.DIALOGUE]
    assert [c[2] for c in f.cues("INT. A - DAY\n\nBOB <!-- hi -->\nHello\n")] == ["BOB"]


def test_a_forced_action_with_an_indent_loses_only_the_bang():
    assert printed("  !Text here\n") == [(f.ACTION, ["  Text here"])]


def test_import_keeps_a_second_synopsis_and_ignores_an_empty_one():
    got = f.import_text("= a\n= b\nINT. X\n\nHi.\n").parts[0].scenes[0]
    assert got.title == "a" and "= b" in got.text and "INT. X" in got.text
    assert "=" in f.import_text("INT. X\n\n=\n\nHi.\n").parts[0].scenes[0].text   # an empty "=" is just text


def test_a_synopsis_with_a_note_before_the_heading_still_names_the_scene():
    scene = f.import_text("= The call\n<!-- n -->\nINT. X\n\nHi.\n").parts[0].scenes[0]
    assert scene.title == "The call"


def test_long_runs_of_synopsis_lines_are_not_quadratic():
    text = "\n\n".join("= syn" for _ in range(20000)) + "\n\nINT. X - DAY\n\nHi.\n"
    t = time.perf_counter()
    imp = f.import_text(text)
    assert time.perf_counter() - t < 5
    assert imp.scenes == 1


def test_import_of_a_long_script_is_fast(tmp_path):
    project = Project.create(tmp_path / "p", "P", "script")
    (project.manuscript_dir / "01-opening.md").unlink()
    text = "\n".join(f"INT. ROOM {i} - DAY\n\nSomething happens.\n" for i in range(600))
    t = time.perf_counter()
    got = fountainio.import_into(project, text)
    assert got["scenes"] == 600
    assert time.perf_counter() - t < 20            # was quadratic: 1500 scenes took 35 s
    names = [p.name for p in Project.open(tmp_path / "p").list_scenes()]
    assert names[0].startswith("01-") and names[99].startswith("100-") and len(set(names)) == 600


def test_every_word_counter_agrees_for_a_script(tmp_path):
    project = make_script(tmp_path / "s")
    text = "# T\n\nINT. A - DAY\n\nBOB\nTwo words.\n\n<!-- a long note about nothing at all -->\n\n= a synopsis line\n\n/* boneyard text */\n"
    assert project.count_words(text) == f.word_count(text)
    assert project.count_words(text) == 7       # heading (4 tokens), the cue, two words of speech; no notes
    path = project.list_scenes()[0]
    path.write_text(text, encoding="utf-8", newline="\n")
    [row] = [s for s in ws.scene_summaries(Project.open(tmp_path / "s")) if s["id"].endswith(path.name)]
    assert row["words"] == project.count_words(text)
    # stories are untouched
    story = Project.create(tmp_path / "n", "N")
    assert story.count_words("one <!-- two --> three") == 5
