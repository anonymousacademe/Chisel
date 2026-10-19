"""core/paper/citefmt.py: on-screen citation display strings, and the span field."""

from chisel.core import entities as ent
from chisel.core.links import find_citations
from chisel.core.paper.citefmt import CiteSource, format_citation, source_record, suffixes
from chisel.core.spans import compute_spans

SRC = {
    "smith2024": CiteSource(["Smith"], "2024", "A"),
    "sj2024": CiteSource(["Brown", "Jones"], "2024", "B"),
    "many2024": CiteSource(["Green", "Jones", "Wu"], "2024", "C"),
    "who2020": CiteSource(["World Health Organization"], "2020", "D"),
    "nodate": CiteSource(["Lee"], "", "E"),
}


def fmt(text, sources=SRC):
    cites = find_citations(text)
    assert len(cites) == 1
    return format_citation(cites[0], sources)


def test_author_counts_parenthetical_and_narrative():
    assert fmt("[[@smith2024]]") == "(Smith, 2024)"
    assert fmt("[[@sj2024]]") == "(Brown & Jones, 2024)"
    assert fmt("[[@many2024]]") == "(Green et al., 2024)"
    assert fmt("[[+@smith2024]]") == "Smith (2024)"
    assert fmt("[[+@sj2024]]") == "Brown and Jones (2024)"
    assert fmt("[[+@many2024]]") == "Green et al. (2024)"


def test_corporate_nodate_unresolved():
    assert fmt("[[@who2020]]") == "(World Health Organization, 2020)"
    assert fmt("[[@nodate]]") == "(Lee, n.d.)"
    assert fmt("[[@nope]]") == "(nope)"


def test_locator_suppress_and_several():
    assert fmt("[[@many2024, p. 3]]") == "(Green et al., 2024, p. 3)"
    assert fmt("[[+@many2024, p. 3]]") == "Green et al. (2024, p. 3)"
    assert fmt("[[-@smith2024]]") == "(2024)"
    assert fmt("[[@smith2024; @sj2024]]") == "(Smith, 2024; Brown & Jones, 2024)"


def test_disambiguation_letters_are_stable():
    src = {"b": CiteSource(["Zhang", "Lee"], "2026", "Beta"), "a": CiteSource(["Zhang", "Lee"], "2026", "Alpha"),
           "w": CiteSource(["Wang", "X", "Y"], "2026", "W"), "z": CiteSource(["Zhang"], "2025", "Z")}
    assert suffixes(src) == {"a": "a", "b": "b"}
    assert fmt("[[@w; @b]]", src) == "(Wang et al., 2026; Zhang & Lee, 2026b)"
    src["other"] = CiteSource(["Quux"], "2026", "AAA")   # an unrelated source never moves a letter
    assert suffixes(src) == {"a": "a", "b": "b"}
    assert fmt("[[+@a]]", src) == "Zhang and Lee (2026a)"


def test_source_record_from_csl():
    s = source_record({"author": [{"family": "Smith", "given": "J"}, {"literal": "ACME"}],
                       "issued": {"date-parts": [[2021, 3]]}, "title": "T"})
    assert s == CiteSource(["Smith", "ACME"], "2021", "T")
    assert source_record(None) == CiteSource([], "", "")


def test_span_display_field():
    csl = {"title": "Digital twins", "author": [{"family": "Daneshgar"}, {"family": "B"}, {"family": "C"}],
           "issued": {"date-parts": [[2024]]}}
    e = ent.Entity(name="d2024", type="source", aliases=["Daneshgar et al. 2024"],
                   extra={"key": "d2024", "csl": csl})
    text = "x [[@d2024, p. 3]] y [[+@d2024]] z [[@gone]]"
    spans = [s for s in compute_spans(text, [e], citations=True) if s["kind"] == "citation"]
    assert [s["display"] for s in spans] == ["(Daneshgar et al., 2024, p. 3)", "Daneshgar et al. (2024)", "(gone)"]
    assert spans[0]["label"] == "Daneshgar et al. 2024" and spans[2]["status"] == "unresolved"


def test_year_falls_back_to_raw_and_literal():
    assert source_record({"issued": {"raw": "March 2021"}}).year == "2021"
    assert source_record({"issued": {"literal": "2019-05"}}).year == "2019"
    assert source_record({"issued": {"raw": "soon"}}).year == ""
    s = {"a": source_record({"author": [{"family": "A"}], "issued": {"raw": "2021"}}, "T")}
    assert fmt("[[@a]]", s) == "(A, 2021)"


def test_letters_group_by_displayed_authors():
    src = {"l": CiteSource(["Zhang", "Lee"], "2026", "T1"), "v": CiteSource(["Zhang", "Valeo"], "2026", "T2"),
           "e1": CiteSource(["Zhang", "A", "B"], "2026", "T3"), "e2": CiteSource(["Zhang", "C", "D"], "2026", "T4")}
    assert suffixes(src) == {"e1": "a", "e2": "b"}   # both display as Zhang et al.; Lee / Valeo differ
    assert fmt("[[@l]]", src) == "(Zhang & Lee, 2026)"


def test_letters_continue_past_z():
    src = {f"k{i:02d}": CiteSource(["X"], "2020", f"T{i:02d}") for i in range(28)}
    out = suffixes(src)
    assert out["k25"] == "z" and out["k26"] == "aa" and out["k27"] == "ab"


def test_no_authors_uses_short_title():
    src = {"t": CiteSource([], "2020", "A very long title indeed")}
    assert fmt("[[@t]]", src) == '("A very long, 2020)'.replace('"A very long', '"A very long"')
    assert fmt("[[+@t]]", src) == '"A very long" (2020)'
    assert fmt("[[-@t]]", src) == "(2020)"
