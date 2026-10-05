"""Character relationships: parsing, rendering, derived inverses."""

from pathlib import Path

from chisel.core import relationships as rel
from chisel.core.entities import Entity


def test_parse_finds_list_items_with_labels():
    body = """## Lore

Some prose.

## Relationships

- [[Rook Tanaka]] — father; estranged
- [[Imogen Sallow]]
- [[Hollow Market]] -- the place that raised her
* [[Dace Kuroda]]: owes him money

## Later

More prose that is not a relationship.
"""
    parsed = rel.parse(body)
    assert [(r.target, r.label) for r in parsed] == [
        ("Rook Tanaka", "father; estranged"),
        ("Imogen Sallow", ""),
        ("Hollow Market", "the place that raised her"),
        ("Dace Kuroda", "owes him money"),
    ]


def test_parse_tolerates_junk_and_dedupes():
    body = """## Relationships

Not a list item.
- [[A]] — once
- [[A]] — twice is dropped
- no link here
- [[]] — empty target
- [[B

## Relationships

- [[C]] — a second section wins nothing extra
"""
    assert [(r.target, r.label) for r in rel.parse(body)] == [("A", "once"), ("C", "a second section wins nothing extra")]


def test_parse_case_insensitive_heading_and_no_section():
    assert rel.parse("## relationships\n\n- [[A]] — x") == [rel.Rel("A", "x")]
    assert rel.parse("plain body without any section") == []


def test_render_and_roundtrip():
    text = rel.render([rel.Rel("Rook Tanaka", "father"), rel.Rel("Imogen", "")])
    assert text == "## Relationships\n\n- [[Rook Tanaka]] — father\n- [[Imogen]]\n"
    assert rel.parse(text) == [rel.Rel("Rook Tanaka", "father"), rel.Rel("Imogen", "")]


def test_render_dedupes_and_empty_is_empty():
    assert rel.render([rel.Rel("A", "x"), rel.Rel("a", "y")]).count("[[A]]") == 1
    assert rel.render([]) == ""
    assert rel.render([rel.Rel("", "junk")]) == ""


def test_set_section_replaces_in_place_and_keeps_later_headings():
    body = "Intro.\n\n## Relationships\n\n- [[Old]] — old\n\n## After\n\nKept."
    out = rel.set_section(body, [rel.Rel("New", "new")])
    assert "Intro." in out and "## After" in out and "Kept." in out
    assert "- [[New]] — new" in out and "Old" not in out
    assert out.index("## Relationships") < out.index("## After")


def test_set_section_appends_when_missing_and_removes_when_empty():
    body = "Just prose.\n"
    out = rel.set_section(body, [rel.Rel("A", "b")])
    assert out.endswith("## Relationships\n\n- [[A]] — b\n") and "Just prose." in out
    assert rel.set_section(out, []) == "Just prose.\n"
    assert rel.set_section("Just prose.\n", []) == "Just prose.\n"


def test_rows_declared_derived_and_unresolved():
    rook = Entity(name="Rook Tanaka", type="character",
                  body="## Relationships\n\n- [[Wren]] — daughter\n- [[The Caller]] — a voice\n",
                  path=Path("w.md"))
    wren = Entity(name="Wren", type="character",
                  body="## Relationships\n\n- [[Rook Tanaka]] — father (from her side)\n",
                  path=Path("x.md"))
    rows = rel.rows(rook, [rook, wren])
    assert rows[0] == {"other": "Wren", "target": "Wren", "label": "daughter",
                       "side": "declared", "resolved": True}
    derived = [r for r in rows if r["side"] == "derived"]
    assert derived == [{"other": "Wren", "target": "Wren",
                        "label": "father (from her side)", "side": "derived", "resolved": True}]
    unresolved = [r for r in rows if not r["resolved"]]
    assert unresolved == [{"other": "", "target": "The Caller", "label": "a voice",
                           "side": "declared", "resolved": False}]
    # and the view from Wren's note shows Rook's declaration as derived
    wren_rows = rel.rows(wren, [rook, wren])
    assert [r["label"] for r in wren_rows if r["side"] == "derived"] == ["daughter"]


def test_rows_keep_both_sides_of_a_pair():
    a = Entity(name="A", body="## Relationships\n\n- [[B]] — partner\n", path=Path("a.md"))
    b = Entity(name="B", body="## Relationships\n\n- [[A]] — partner\n", path=Path("b.md"))
    rows = rel.rows(a, [a, b])
    assert [(r["side"], r["label"]) for r in rows] == [("declared", "partner"), ("derived", "partner")]
    # an identical derived row (same words) is not repeated
    rows2 = rel.rows(b, [a, b])
    assert len([r for r in rows2 if r["side"] == "derived"]) == 1
