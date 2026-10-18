"""Fountain parsing, layout and the Chisel <-> Fountain text conversions (core/fountain.py)."""

from chisel.core import fountain as f

SCENE = """\
# Kitchen

INT. KITCHEN - DAY

Keith stares at the *toast*.

KEITH (V.O.)
Burnt again.
(beat)
I give up.

CUT TO:

.THE GARDEN

Birds sing. A [[Keith]] link.

> THE END <
"""


def kinds(text):
    return [(ln.kind, ln.text) for ln in f.parse(text) if ln.kind != f.BLANK]


def test_parse_classifies_the_standard_elements():
    got = kinds(SCENE)
    assert got == [
        (f.TITLE, "# Kitchen"),
        (f.SCENE_HEADING, "INT. KITCHEN - DAY"),
        (f.ACTION, "Keith stares at the *toast*."),
        (f.CHARACTER, "KEITH (V.O.)"),
        (f.DIALOGUE, "Burnt again."),
        (f.PARENTHETICAL, "(beat)"),
        (f.DIALOGUE, "I give up."),
        (f.TRANSITION, "CUT TO:"),
        (f.SCENE_HEADING, ".THE GARDEN"),
        (f.ACTION, "Birds sing. A [[Keith]] link."),
        (f.CENTERED, "> THE END <"),
    ]


def test_offsets_are_code_points_of_each_line():
    text = "é INT\n\nINT. A - DAY\n"
    lines = f.parse(text)
    heading = next(ln for ln in lines if ln.kind == f.SCENE_HEADING)
    assert text[heading.start:heading.end] == "INT. A - DAY"


def test_character_needs_a_line_after_it_and_a_gap_before():
    assert kinds("BANG\n\nNext.\n")[0][0] == f.ACTION                  # alone: action
    assert [k for k, _ in kinds("Some text\nKEITH\nHello\n")] == [f.ACTION] * 3   # no gap before: not a cue
    assert kinds("\nKEITH\nHello\n")[0][0] == f.CHARACTER


def test_forced_elements_and_dual_dialogue():
    assert kinds("!INT. NOT A HEADING\n")[0] == (f.ACTION, "!INT. NOT A HEADING")
    assert kinds("@McCLANE\nYippee.\n")[0][0] == f.CHARACTER
    assert kinds("> FADE OUT.\n")[0][0] == f.TRANSITION
    assert kinds("~la la la\n")[0][0] == f.LYRICS
    lines = f.parse("\nBRICK\nScrew you.\n\nSTEEL ^\nNo, you.\n")
    cues = [ln for ln in lines if ln.kind == f.CHARACTER]
    assert [c.dual for c in cues] == [False, True]


def test_sections_synopses_notes_boneyard_and_page_breaks():
    lines =[ln.kind for ln in f.parse("x\n\n## Act\n= syn\n===\n<!-- n -->\n<!--\nmulti\n-->\n/* a\nb */\nAction.\n") if ln.kind != f.BLANK]
    assert lines == [f.ACTION, f.SECTION, f.SYNOPSIS, f.PAGE_BREAK, f.NOTE, f.NOTE, f.NOTE, f.NOTE,
                     f.BONEYARD, f.BONEYARD, f.ACTION]


def test_two_spaces_keep_dialogue_going():
    lines = f.parse("\nANNA\nOne.\n  \nTwo.\n\nBob does a thing.\n")
    assert [ln.kind for ln in lines if ln.kind != f.BLANK] == [
        f.CHARACTER, f.DIALOGUE, f.DIALOGUE, f.DIALOGUE, f.ACTION]


def test_the_title_line_only_counts_at_the_top():
    assert f.parse("# Scene\n\n# Later\n")[0].kind == f.TITLE
    assert [ln.kind for ln in f.parse("# Scene\n\n# Later\n")][2] == f.SECTION


def test_prepare_blanks_frontmatter_and_ai_markers_keeping_offsets():
    text = '---\npov: Keith\n---\n# T\n\nINT. A - DAY\n\n<!--ai id="x"-->\nKEITH\nHi.\n<!--/ai-->\n'
    prepared = f.prepare(text)
    assert len(prepared) == len(text)
    kinds_ = [ln.kind for ln in f.parse_scene(text) if ln.kind != f.BLANK]
    assert f.SCENE_HEADING in kinds_ and f.CHARACTER in kinds_ and f.DIALOGUE in kinds_


def test_spans_skip_action_and_blank():
    spans = f.spans(SCENE)
    assert {s["element"] for s in spans} >= {"title", "scene_heading", "character", "dialogue",
                                             "parenthetical", "transition", "centered"}
    assert all(s["kind"] == "script" and s["element"] not in ("action", "blank") for s in spans)


def test_cues_give_the_speaker_without_extension():
    text = "# T\n\nINT. A - DAY\n\nKEITH (V.O.)\nHi.\n\n@Mum ^\nHm.\n"
    assert [c[2] for c in f.cues(text)] == ["KEITH", "Mum"]
    start, end, name = f.cues(text)[0]
    assert text[start:end] == "KEITH"


def test_blank_non_prose_keeps_offsets_and_dialogue():
    text = "# T\n\nINT. A - DAY\n\nKEITH\nHello there.\n"
    out = f.blank_non_prose(text)
    assert len(out) == len(text)
    assert "Hello there." in out and "KEITH" not in out and "INT." not in out


def test_inline_emphasis():
    segs = f.inline_runs("a *b* **c** ***d*** _e_ \\*f\\* *open")
    assert [(s.text, s.italic, s.bold, s.underline) for s in segs] == [
        ("a ", False, False, False), ("b", True, False, False), (" ", False, False, False),
        ("c", False, True, False), (" ", False, False, False), ("d", True, True, False),
        (" ", False, False, False), ("e", False, False, True), (" *f* *open", False, False, False)]
    assert f.plain("x *y*") == "x y"


def test_blocks_and_wrapping_positions():
    items = f.blocks(SCENE)
    assert [b.kind for b in items] == [f.SCENE_HEADING, f.ACTION, f.CHARACTER, f.DIALOGUE,
                                       f.PARENTHETICAL, f.DIALOGUE, f.TRANSITION, f.SCENE_HEADING, f.ACTION,
                                       f.CENTERED]
    laid = f.layout(items)
    heading = laid[0][2][0]
    assert "".join(s.text for s in heading.segs) == "INT. KITCHEN - DAY" and heading.indent == 0
    cue = next(r for b, _, rows in laid if b.kind == f.CHARACTER for r in rows)
    assert cue.indent == f.CUE_INDENT
    transition = next(r for b, _, rows in laid if b.kind == f.TRANSITION for r in rows)
    assert transition.indent + len("".join(s.text for s in transition.segs)) == f.ACTION_WIDTH


def test_action_keeps_the_authors_line_breaks():
    items = f.blocks("INT. A - DAY\n\nLine one\nLine two\n")
    rows = f.layout(items)[1][2]
    assert ["".join(s.text for s in r.segs) for r in rows] == ["Line one", "Line two"]


def test_long_lines_wrap_inside_their_width():
    long = " ".join(["word"] * 40)
    rows = f.layout(f.blocks(f"\nANNA\n{long}\n"))[1][2]
    assert len(rows) > 1
    assert all(len("".join(s.text for s in r.segs)) <= f.DIALOGUE_WIDTH for r in rows)
    assert all(r.indent == f.DIALOGUE_INDENT for r in rows)


def _script(scenes):
    return "\n".join(f"INT. PLACE {i} - DAY\n\n" + "Action line.\n\n" * 6 for i in range(scenes))


def test_paginate_fills_pages_and_page_breaks_start_new_ones():
    pages = f.paginate(f.blocks(_script(30)))
    assert len(pages) > 1
    assert all(len(p) <= f.LINES_PER_PAGE for p in pages)
    assert all(p[0] is not None for p in pages)                       # no blank row at the top
    forced = f.paginate(f.blocks("INT. A - DAY\n\nOne.\n\n===\n\nTwo.\n"))
    assert len(forced) == 2


def test_a_heading_or_cue_never_ends_a_page():
    for n in range(40, 60):
        text = "Action.\n\n" * n + "INT. A - DAY\n\nANNA\nHello there, friend.\n"
        pages = f.paginate(f.blocks(text))
        for p in pages:
            last = [r for r in p if r is not None][-1]
            assert last.kind not in (f.SCENE_HEADING, f.CHARACTER, f.PARENTHETICAL)


def test_a_block_taller_than_a_page_is_still_placed():
    text = "INT. A - DAY\n\n" + "\n".join(f"line {i}" for i in range(130)) + "\n"
    pages = f.paginate(f.blocks(text))
    assert sum(1 for p in pages for r in p if r is not None and r.kind == f.ACTION) == 130


def test_estimate_pages_in_eighths_and_formatting():
    assert f.estimate_pages("") == 0
    pages = f.estimate_pages(_script(10))
    assert pages == round(pages * 8) / 8 > 0
    assert f.format_pages(0.25) == "2/8" and f.format_pages(7.375) == "7 3/8" and f.format_pages(3.0) == "3"


def test_notes_round_trip_between_chisel_and_fountain():
    chisel = "Action.\n\n<!-- remember this -->\n\nMore.\n"
    fountain = f.notes_to_fountain(chisel)
    assert "[[remember this]]" in fountain and "<!--" not in fountain
    assert f.notes_from_fountain(fountain) == chisel
    # a pending-draft marker is not a note
    assert f.notes_to_fountain('<!--ai id="a"-->x<!--/ai-->') == '<!--ai id="a"-->x<!--/ai-->'


def test_a_multi_line_note_gets_the_spaces_fountain_needs():
    out = f.notes_to_fountain("<!-- one\n\ntwo -->")
    assert out == "[[one\n  \ntwo]]"


def test_title_page_split_and_build():
    page, rest = f.split_title_page("Title: Big Fish\nAuthor: Jo\nContact:\n    jo@x.com\n    555\n\nFADE IN:\n")
    assert page == {"title": "Big Fish", "author": "Jo", "contact": "jo@x.com\n555"}
    assert rest.strip() == "FADE IN:"
    # a script that starts with a transition is not a title page
    assert f.split_title_page("FADE IN:\n\nINT. A - DAY\n")[0] == {}
    built = f.title_page_text("Big Fish", "Jo", "jo@x.com\n555", "(c) 2026")
    assert built.startswith("Title: Big Fish\nCredit: Written by\nAuthor: Jo\n")
    assert "Contact:\n    jo@x.com\n    555\n" in built and built.endswith("\n\n")
    assert f.title_page_text("") == ""


FOUNTAIN = """\
Title: Big Fish
Author: Jo

FADE IN:

# Act One

= The kitchen
INT. KITCHEN - DAY

Keith burns toast. [[remember the toast]]

KEITH
Burnt again.

EXT. GARDEN - NIGHT #12#

Rain.
"""


def test_import_splits_parts_and_scenes_and_names_them():
    imp = f.import_text(FOUNTAIN)
    assert imp.title_page == {"title": "Big Fish", "author": "Jo"}
    assert [(p.title, [s.title for s in p.scenes]) for p in imp.parts] == [
        ("Act One", ["The kitchen", "EXT. GARDEN - NIGHT"])]
    kitchen = imp.parts[0].scenes[0].text
    # "FADE IN:" is not a scene of its own: it starts the first one
    assert kitchen.startswith("# The kitchen\n\nFADE IN:\n\nINT. KITCHEN - DAY\n")
    assert "<!-- remember the toast -->" in kitchen and "[[" not in kitchen
    assert imp.scenes == 2
    assert "INT. KITCHEN" not in imp.parts[0].scenes[1].text and "EXT. GARDEN - NIGHT #12#" in imp.parts[0].scenes[1].text


def test_import_handles_odd_input():
    assert f.import_text("").scenes == 0
    assert f.import_text("Title: X\n\n").scenes == 0
    only_action = f.import_text("Just some action.\n")
    assert only_action.parts[0].scenes[0].title == "Opening"
    prelude = f.import_text("FADE IN:\n\nINT. A - DAY\n\nHi.\n\nCUT TO:\n\nINT. B - DAY\n\nHo.\n")
    assert [s.title for s in prelude.parts[0].scenes] == ["INT. A - DAY", "INT. B - DAY"]
    assert prelude.parts[0].scenes[0].text.startswith("# INT. A - DAY\n\nFADE IN:\n\nINT. A - DAY\n")
    assert prelude.parts[0].scenes[0].text.rstrip().endswith("CUT TO:")   # a closing transition stays
    crlf = f.import_text("INT. A - DAY\r\n\r\nHi.\r\n")
    assert "\r" not in crlf.parts[0].scenes[0].text
    # a synopsis that is not above a heading stays in the scene
    kept = f.import_text("INT. A - DAY\n\n= beat\n\nHi.\n").parts[0].scenes[0].text
    assert "= beat" in kept


def test_export_text_inverts_import():
    imp = f.import_text(FOUNTAIN)
    parts = []
    for part in imp.parts:
        scenes = []
        for sc in part.scenes:
            body = sc.text.split("\n", 2)[2]          # drop the "# Title" line and the gap
            scenes.append((sc.title, f.notes_to_fountain(body)))
        parts.append((part.title, scenes))
    out = f.export_text(f.title_page_text("Big Fish", "Jo"), parts)
    again = f.import_text(out)
    assert [(p.title, [s.title for s in p.scenes]) for p in again.parts] == \
        [(p.title, [s.title for s in p.scenes]) for p in imp.parts]
    assert "= The kitchen" in out                       # the title differs from the heading
    assert "= EXT. GARDEN" not in out                   # the title is the heading: no synopsis
    assert "[[remember the toast]]" in out
