"""Pipe tables: canonical form, byte-exact round trip, parsing tolerance."""

import pytest

from chisel.core.tables import Table, parse_pipe, to_pipe

CANON = (
    "| Name | Score | Note |\n"
    "| :----------- | -----: | :------: |\n"
    "| a | 1 | x \\| y |\n"
    "| longer name | 22 |  |"
)


def test_canonical_round_trip_is_byte_exact():
    t = parse_pipe(CANON)
    assert t.align == ["left", "right", "center"]
    assert t.cells[1] == ["a", "1", "x | y"] and t.cells[2][2] == ""
    assert to_pipe(t) == CANON


def test_dash_counts_are_deterministic_and_at_least_three():
    t = Table([["a", "wide column"], ["1", "2"]], ["default", "right"])
    lines = to_pipe(t).split("\n")
    assert lines[1] == "| --- | -----------: |"
    assert to_pipe(parse_pipe(to_pipe(t))) == to_pipe(t)


def test_hand_written_table_is_normalised_once():
    raw = "intro text\n\n|a|b|\n|:-|-:|\n|1|2|\n\nafter"
    t = parse_pipe(raw)
    out = to_pipe(t)
    assert out == "| a | b |\n| :--- | ---: |\n| 1 | 2 |"
    assert to_pipe(parse_pipe(out)) == out


def test_ragged_rows_are_padded_and_trimmed():
    t = parse_pipe("| a | b |\n| - | - |\n| 1 |\n| 1 | 2 | 3 |")
    assert t.cells == [["a", "b"], ["1", ""], ["1", "2"]]


def test_newlines_and_pipes_in_cells_are_made_safe():
    out = to_pipe(Table([["h"], ["a\nb | c"]], ["default"]))
    assert "\n" not in out.split("\n")[2] and "a b \\| c" in out
    assert parse_pipe(out).cells[1] == ["a b | c"]


def test_backslash_before_pipe_round_trips():
    t = Table([["h"], ["a\\|b"]], ["default"])
    assert parse_pipe(to_pipe(t)).cells == t.cells


def test_unicode_and_crlf():
    t = parse_pipe("| é | 日本 |\r\n| --- | --- |\r\n| ß | ✓ |\r\n")
    assert t.cells[1] == ["ß", "✓"]
    assert to_pipe(parse_pipe(to_pipe(t))) == to_pipe(t)


@pytest.mark.parametrize("text", ["", "no table here", "| a |\n| not a delimiter |", "a | b\n--- | ---x"])
def test_no_table_is_an_error(text):
    with pytest.raises(ValueError):
        parse_pipe(text)


def test_bad_alignment_or_empty_table_refused():
    with pytest.raises(ValueError):
        to_pipe(Table([["a"]], ["middle"]))
    with pytest.raises(ValueError):
        to_pipe(Table([], []))
