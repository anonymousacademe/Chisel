"""The reading model (core/reader.py): what is read, in which voice, from where; no audio."""

import pytest

from chisel.core import entities as ent
from chisel.core import reader
from chisel.core.reader import ReadOptions, plan

KEITH = ent.Entity(name="Keith", type="character", aliases=["Keefer"], extra={"say": "Kee-eth"})
MARA = ent.Entity(name="Mara", type="character")

SCRIPT = """\
---
pov: Keith
---
# Kitchen

INT. KITCHEN - DAY

Keith burns the *toast*. <!-- keep it quick -->
He sighs.

KEITH (V.O.)
(to himself)
Burnt again.
Every single time.

MARA
Don't start.

CUT TO:

EXT. GARDEN - NIGHT #4#

Rain.
"""


def kinds(p):
    return [(u.kind, u.voice, u.say) for u in p.utterances]


# -- script -------------------------------------------------------------------------------------------------


def test_a_script_is_read_scene_heading_action_and_dialogue_by_speaker():
    p = plan(SCRIPT, "script", [KEITH, MARA])
    assert kinds(p) == [
        ("title", "narrator", "Kitchen"),
        ("scene-heading", "narrator", "Interior, Kitchen, Day"),
        ("narration", "narrator", "Kee-eth burns the toast. He sighs."),     # Keith has a pronunciation (say:)
        ("dialogue", "Keith", "Burnt again. Every single time."),             # the voice is still the character's
        ("dialogue", "Mara", "Don't start."),
        ("scene-heading", "narrator", "Exterior, Garden, Night"),
        ("narration", "narrator", "Rain."),
    ]


def test_the_details_notes_and_cues_are_not_read_and_the_speaker_keeps_the_voice():
    spoken = " ".join(u.say for u in plan(SCRIPT, "script", [KEITH, MARA]).utterances)
    for left_out in ("pov", "keep it quick", "V.O.", "to himself", "CUT TO", "KEITH", "#4#"):
        assert left_out not in spoken
    assert plan(SCRIPT, "script", [KEITH]).voices() == {"narrator": 5, "Keith": 1, "Mara": 1}   # Mara: no note, as written


def test_parentheticals_and_transitions_are_read_only_when_asked():
    p = plan(SCRIPT, "script", [KEITH, MARA], ReadOptions(directions=True, transitions=True))
    assert ("direction", "narrator", "to himself") in kinds(p)
    assert ("transition", "narrator", "Cut to") in kinds(p)
    # the speech goes on under the same speaker after a parenthetical
    assert [u.voice for u in p.utterances if u.kind == "dialogue"] == ["Keith", "Mara"]
    short = plan(SCRIPT, "script", [KEITH], ReadOptions(titles=False, headings=False))
    assert [u.kind for u in short.utterances] == ["narration", "dialogue", "dialogue", "narration"]


def test_source_ranges_point_at_what_is_read():
    p = plan(SCRIPT, "script", [KEITH, MARA])
    for u in p.utterances:
        chunk = SCRIPT[u.start:u.end]
        assert chunk.strip() == chunk and chunk
        assert SCRIPT.count("\n", 0, u.start) == u.row
    dialogue = next(u for u in p.utterances if u.kind == "dialogue")
    assert SCRIPT[dialogue.start:dialogue.end] == "Burnt again.\nEvery single time."
    heading = next(u for u in p.utterances if u.kind == "scene-heading")
    assert SCRIPT[heading.start:heading.end] == "INT. KITCHEN - DAY"


def test_a_scene_heading_is_spoken_as_words():
    for heading, said in [("INT. KITCHEN - DAY", "Interior, Kitchen, Day"), ("EXT. WARD 6 - NIGHT", "Exterior, Ward 6, Night"),
                          ("INT./EXT. CAR - MOVING", "Interior and exterior, Car, Moving"), ("I/E CAFE - DAY", "Interior and exterior, Cafe, Day"),
                          (".THE GARDEN", "The Garden"), ("EST. CITY - DAWN #12#", "Establishing, City, Dawn")]:
        assert reader.spoken_heading(heading) == said


def test_pending_ai_drafts_are_not_read():
    text = "INT. A - DAY\n\nKEITH\nHello.\n\n<!--ai-->KEITH\nAn unaccepted line.<!--/ai-->\n\nHe waits.\n"
    spoken = " ".join(u.say for u in plan(text, "script", [KEITH]).utterances)
    assert "unaccepted" not in spoken and "Hello." in spoken and "He waits." in spoken


# -- story -----------------------------------------------------------------------------------------------------


STORY = """\
# Rain on the Spur

The rain in the Hollow Market came down warm. Rook sat at
the far end of [[Lin's counter|Lin's]] counter.

"You're brooding," said Wren. "It's **unattractive** in a man."

## Later

"I'm thinking."
"""


def test_story_prose_is_narration_with_quoted_speech_split_out():
    p = plan(STORY, "story", [KEITH])
    assert kinds(p) == [
        ("title", "narrator", "Rain on the Spur"),
        ("narration", "narrator", "The rain in the Hollow Market came down warm. Rook sat at the far end of Lin's counter."),
        ("quote", "quote", "You're brooding,"),
        ("narration", "narrator", "said Wren."),
        ("quote", "quote", "It's unattractive in a man."),
        ("heading", "narrator", "Later"),
        ("quote", "quote", "I'm thinking."),
    ]
    quote = p.utterances[2]
    assert STORY[quote.start:quote.end] == "You're brooding,"
    para = p.utterances[1]
    assert STORY[para.start:para.end].startswith("The rain") and STORY[para.start:para.end].endswith("counter.")


def test_curly_quotes_split_too_and_an_unbalanced_quote_does_not():
    p = plan("“Stop,” she said.\n", "story")
    assert kinds(p) == [("quote", "quote", "Stop,"), ("narration", "narrator", "she said.")]
    odd = plan('He said "stop and she did.\n', "story")
    assert kinds(odd) == [("narration", "narrator", 'He said "stop and she did.')]


def test_markdown_marks_and_unreadable_blocks_are_dropped():
    text = ("# T\n\n- first *item*\n- second item\n\n```\ncode here\n```\n\n| a | b |\n|---|---|\n\n---\n\n"
            "See [the docs](http://x.test) and ![a picture](p.png) now.^[a footnote]\n\n> quoted text\n")
    said = [u.say for u in plan(text, "story").utterances]
    assert said == ["T", "first item", "second item", "See the docs and a picture now.", "quoted text"]


def test_expand_markers_and_comments_are_not_read():
    text = "# T\n\nOne {{expand: describe the room}} two <!-- note --> three.\n"
    assert [u.say for u in plan(text, "story").utterances][-1] == "One two three."


# -- research -----------------------------------------------------------------------------------------------------


RESEARCH = """\
# Methods

We follow [@kalman1960; @smith2020, p. 4] and fit the model $y = mx + b$ (see [[fig:flow]] and [[tbl:data]]).

$$E = mc^2$$

![[fig:flow]]

The results are in [[eq:main]].
"""


def test_research_drops_citations_and_speaks_math_and_references_as_words():
    p = plan(RESEARCH, "research")
    said = [u.say for u in p.utterances]
    assert said[0] == "Methods"
    assert said[1] == "We follow and fit the model equation (see the figure and the table)."
    assert said[2] == "equation"
    assert said[3] == "The results are in the equation."
    assert len(said) == 4                                   # the figure placement line is not read


def test_citations_can_be_spoken_as_the_word():
    p = plan("# T\n\nAs shown [@a2020].\n", "research", options=ReadOptions(citations=True))
    assert [u.say for u in p.utterances][-1] == "As shown citation."


def test_research_does_not_split_quotes():
    p = plan('# T\n\nThe term "robust" is used.\n', "research")
    assert [u.kind for u in p.utterances] == ["title", "narration"]


# -- notes and the rest ------------------------------------------------------------------------------------------


def test_any_note_is_read_without_its_frontmatter():
    text = "---\nname: Keith\ntype: character\naliases: [Keefer]\n---\nKeith is a cook.\n\n## Canon\n\n- Left-handed.\n"
    assert [u.say for u in plan(text, "note").utterances] == ["Keith is a cook.", "Canon", "Left-handed."]


def test_pronunciations_respell_names_and_aliases_only_in_what_is_said():
    p = plan("# T\n\nKeith met Keefer, and Keithley waved.\n", "story", [KEITH])
    u = p.utterances[-1]
    assert u.say == "Kee-eth met Kee-eth, and Keithley waved." and u.text.startswith("Keith met Keefer")
    assert reader.pronunciations([KEITH, MARA]) == {"Keith": "Kee-eth", "Keefer": "Kee-eth"}
    assert reader.pronunciations([ent.Entity(name="X", type="place", extra={"say": 5})]) == {}


# -- the plan ------------------------------------------------------------------------------------------------------


def test_duration_words_and_voices():
    p = plan(SCRIPT, "script", [KEITH, MARA])
    assert p.words == sum(len(u.say.split()) for u in p.utterances)
    assert p.seconds() == pytest.approx(sum(u.seconds for u in p.utterances))
    assert p.seconds(2.0) == pytest.approx(p.seconds() / 2)
    assert reader.estimate_seconds("narration", " ".join(["word"] * 160)) == pytest.approx(60.5)
    assert plan("", "story").utterances == [] and plan("\n\n", "script").seconds() == 0


def test_options_come_from_untrusted_input_safely():
    assert ReadOptions.from_dict({"directions": True, "bogus": 1}) == ReadOptions(directions=True)
    assert ReadOptions.from_dict(None) == ReadOptions()
    with pytest.raises(ValueError):
        ReadOptions.from_dict({"directions": "yes"})
    with pytest.raises(ValueError):
        plan("x", "poetry")


def test_big_documents_are_read_in_good_time():
    import time
    text = "# T\n\n" + "\n\n".join(f'"Line {i}," he said. Then more narration follows here, {i}.' for i in range(5000))
    t = time.perf_counter()
    p = plan(text, "story")
    assert len(p.utterances) > 10000 and time.perf_counter() - t < 8


def test_pieces_of_one_paragraph_are_marked_as_joining():
    text = ('"That\'s a dangerous thing." Derek said. Omar liked Derek\'s classics: "That\'s a dangerous thing." '
            'to the most benign.\n\n"SSDD" Same shit, different day.\n')
    us = reader.plan(text, "story").utterances
    assert [u.joins for u in us] == [False, True, True, True, False, True]
    assert us[4].say == "S S D D"                       # no vowel: spelled out
    assert reader.plan("NASA and the TV.", "story").utterances[0].say == "NASA and the T V."
    assert all(not u.joins for u in reader.plan("INT. WARD - NIGHT\n\nDana waits.\n", "script").utterances)
