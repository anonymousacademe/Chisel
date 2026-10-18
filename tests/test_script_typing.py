"""Typing aids for script scenes: Tab cycles a line's element (core/fountain.cycle_element, Api.script_cycle)."""

from chisel.core import fountain as f
from chisel.gui.api import Api


def test_the_ring_walks_forward_and_back():
    assert f.cycle_element("", "blank") == "INT. "
    assert f.cycle_element("walks in", "action") == "INT. WALKS IN"
    assert f.cycle_element("INT. KITCHEN - DAY", "scene_heading") == "KITCHEN - DAY"
    assert f.cycle_element("KEITH", "character") == "(keith)"
    assert f.cycle_element("(quietly)", "parenthetical") == "QUIETLY TO:"
    assert f.cycle_element("CUT TO:", "transition") == "Cut"
    assert f.cycle_element("CUT TO:", "transition", reverse=True) == "(cut)"
    assert f.cycle_element("KEITH", "character", reverse=True) == "INT. KEITH"
    assert f.cycle_element("INT. A", "scene_heading", reverse=True) == "A"


def test_marks_are_stripped_not_stacked():
    assert f.cycle_element(".THE GARDEN", "scene_heading") == "THE GARDEN"
    assert f.cycle_element("@McCLANE ^", "character") == "(mcclane)"
    assert f.cycle_element("> FADE OUT.", "transition") == "Fade out."
    assert f.cycle_element("INT. KITCHEN - DAY #12#", "scene_heading") == "KITCHEN - DAY"
    assert f.cycle_element("EXT. STREET", "scene_heading", reverse=True) == "Street"   # an action line is not shouted
    assert f.cycle_element("INT. EXT. X", "action").startswith("INT. ")


def test_unknown_elements_count_as_action_and_nothing_is_lost():
    assert f.cycle_element("Rain falls.", "dialogue") == "INT. RAIN FALLS."
    assert f.cycle_element("Rain falls.", "synopsis", reverse=True) == "RAIN FALLS TO:"
    assert f.cycle_element("NASA", "transition") == "Nasa"          # the ring ends by un-shouting a cue
    # going all the way round keeps the words you typed (only marks and case change)
    line = "walks in"
    for element in f.CYCLE:
        line = f.cycle_element(line, element)
    assert line.lower() == "walks in"


def test_the_bridge_method_is_pure_text_in_text_out():
    api = Api()
    assert api.script_cycle("", "blank") == {"line": "INT. ", "ok": True}
    assert api.script_cycle("KEITH", "character", True)["line"] == "INT. KEITH"
    assert hasattr(api.facade(), "script_cycle")
    # no project needed, and a non-string never raises
    assert api.script_cycle(None, None)["ok"] is True
