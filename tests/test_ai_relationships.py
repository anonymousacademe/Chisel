"""AI relationship suggestions: planning, parsing, applying."""

import json

import pytest

from chisel.ai import relationships as airel
from chisel.ai.budget import Budget, BudgetError
from chisel.core import relationships as rel
from chisel.core.entities import Entity, save_entity


def _entity(name, body="", etype="character", path=None):
    return Entity(name=name, type=etype, body=body, path=path)


def test_plan_sends_the_note_and_the_whole_roster():
    rook = _entity("Rook Tanaka", "The captain of the Vesper.")
    wren = _entity("Wren", "Rook's daughter.")
    dace = _entity("Dace Kuroda", "A smuggler.", etype="character")
    kept, report = airel.plan_suggestions(rook, [rook, wren, dace], Budget.unbounded())
    assert [e.name for e in kept] == ["Wren", "Dace Kuroda"]
    names = [s.name for s in report.sections]
    assert "Known characters" in names and "This note" in names


def test_plan_drops_the_roster_tail_when_it_does_not_fit():
    rook = _entity("Rook Tanaka", "The captain of the Vesper.")
    others = [_entity(f"Note {i:02d}", f"Body of note {i}.") for i in range(12)]
    # enough room for the instructions and the note, not for 12 roster lines
    kept, report = airel.plan_suggestions(rook, [rook, *others], Budget(300, 0))
    assert all(e.name != "Rook Tanaka" for e in kept)  # never sends the note itself
    assert kept and len(kept) < len(others)
    assert report.dropped  # the report names what was not sent


def test_plan_raises_when_even_the_note_does_not_fit():
    rook = _entity("Rook Tanaka", "The captain of the Vesper.")
    with pytest.raises(BudgetError):
        airel.plan_suggestions(rook, [rook], Budget(10, 0))


def test_parse_suggestions_filters_junk_and_known_rows():
    rook = _entity("Rook Tanaka", "## Relationships\n\n- [[Wren]] — daughter\n")
    wren = _entity("Wren", "")
    dace = _entity("Dace Kuroda", "")
    raw = json.dumps({"relations": [
        {"target": "Dace Kuroda", "label": "owes him money"},   # kept
        {"target": "Nobody Atall", "label": "unknown"},          # unknown target
        {"target": "Rook Tanaka", "label": "self"},              # self-reference
        {"target": "Wren", "label": "already declared"},         # note declares Wren
        {"target": "Dace Kuroda", "label": "owes him money"},    # repeat
        {"target": "Dace Kuroda", "label": ""},                  # empty label
        {"target": "Dace Kuroda", "label": "x" * 200},           # absurd label
        "not a dict",
    ]})
    out = airel.parse_suggestions(raw, rook, [rook, wren, dace])
    assert out == [airel.Suggestion("Dace Kuroda", "owes him money")]


def test_parse_suggestions_bad_json_is_empty():
    rook = _entity("Rook Tanaka", "")
    assert airel.parse_suggestions("not json at all", rook, [rook]) == []
    assert airel.parse_suggestions("[1, 2]", rook, [rook]) == []


def test_apply_suggestions_merges_and_keeps_frontmatter(tmp_path):
    note = tmp_path / "rook.md"
    note.write_text(
        "---\nname: Rook Tanaka\ntype: character\naliases: []\nrank: captain\n---\n"
        "## Lore\n\nCaptain of the Vesper.\n",
        encoding="utf-8")
    rook = Entity.from_markdown(note.read_text(encoding="utf-8"), note)
    wren = airel.Suggestion("Wren", "daughter")
    out = airel.apply_suggestions(rook, [wren], save_entity)
    text = note.read_text(encoding="utf-8")
    assert "rank: captain" in text                     # extra frontmatter survives
    assert "- [[Wren]] — daughter" in text
    assert "## Lore" in text and text.index("## Lore") < text.index("## Relationships")
    assert [r.target for r in rel.parse(out.body)] == ["Wren"]


def test_apply_suggestions_without_path_never_saves():
    rook = _entity("Rook Tanaka", "Prose.")
    calls = []
    airel.apply_suggestions(rook, [airel.Suggestion("Wren", "daughter")], lambda *a: calls.append(a))
    assert calls == []
    assert "- [[Wren]] — daughter" in rook.body
