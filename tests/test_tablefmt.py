"""Generated tables: CSV plus a formatting spec to Markdown, grid and LaTeX forms (plan 7.4)."""

import pytest

from chisel.core import tablefmt
from chisel.core.project import Project
from chisel.core.tablefmt import build_table, format_csv

CSV = "Method,Time,Acc,Note\nalpha,1234.5,0.912,fast\nbeta,98.25,0.9,a|b\ngamma,,0.95,\n"


def fmt(spec, csv=CSV, caption=""):
    return format_csv(csv, spec, caption)


def md_lines(built):
    return built.markdown.split("\n")


def test_default_spec_shows_every_column_numbers_right_aligned():
    b = fmt(None)
    lines = md_lines(b)
    assert lines[0] == "| Method | Time | Acc | Note |"
    assert lines[1] == "| :------ | ------: | -----: | :---- |"
    assert lines[2] == "| alpha | 1234.5 | 0.912 | fast |"
    assert "a\\|b" in b.markdown
    assert b.warnings == []


def test_decimals_sig_thousands_and_missing():
    b = fmt({"columns": [
        "Method",
        {"key": "Time", "header": "Run time", "unit": "s", "decimals": 1, "thousands": True, "missing": "n/a"},
        {"key": "Acc", "sig": 2},
    ]})
    lines = md_lines(b)
    assert lines[0] == "| Method | Run time (s) | Acc |"
    assert lines[2] == "| alpha | 1,234.5 | 0.91 |"
    assert lines[3] == "| beta | 98.2 | 0.90 |"          # 98.25 -> 98.2 (binary float, round half even)
    assert lines[4] == "| gamma | n/a | 0.95 |"


def test_significant_figures_across_magnitudes():
    b = fmt({"columns": [{"key": "v", "sig": 3}]}, csv="v\n12345.678\n0.00123456\n0\n-1.5\n")
    assert [l.strip("| ") for l in md_lines(b)[2:]] == ["12300", "0.00123", "0.00", "-1.50"]


def test_negative_zero_is_not_shown():
    b = fmt({"columns": [{"key": "v", "decimals": 1}]}, csv="v\n-0.04\n")
    assert md_lines(b)[2] == "| 0.0 |"


def test_best_values_are_bold_and_ties_all_bold():
    b = fmt({"columns": ["Method", {"key": "Acc", "best": "max"}]}, csv="Method,Acc\na,0.9\nb,0.95\nc,0.95\n")
    assert [l.split("|")[2].strip() for l in md_lines(b)[2:]] == ["0.9", "**0.95**", "**0.95**"]
    assert "\\textbf{0.95}" in b.latex and "\\textbf{0.9}" not in b.latex
    m = fmt({"columns": [{"key": "Time", "best": "min"}]})
    assert "**98.25**" in m.markdown


def test_sort_and_order_of_columns():
    b = fmt({"columns": ["Acc", "Method"], "sort": {"by": "Acc", "descending": True}})
    assert [l.split("|")[2].strip() for l in md_lines(b)[2:]] == ["gamma", "alpha", "beta"]
    c = fmt({"columns": ["Method", "Time"], "sort": "Time"})
    assert [l.split("|")[1].strip() for l in md_lines(c)[2:]] == ["beta", "alpha", "gamma"]   # empty last


def test_footnotes_follow_every_form():
    b = fmt({"columns": ["Method"], "footnotes": ["Mean of 5 runs.", "$p<0.05$"]})
    assert b.footnotes == ["Mean of 5 runs.", "$p<0.05$"]
    assert b.markdown.endswith("\n\nMean of 5 runs.\n\n$p<0.05$")
    assert "\\footnotesize Mean of 5 runs." in b.latex and "$p<0.05$" in b.latex
    assert b.grid.endswith("Mean of 5 runs.\n\n$p<0.05$")


def test_caption_is_carried():
    assert fmt(None, caption="Results").caption == "Results"


def test_markdown_data_cells_are_escaped_headers_are_author_text():
    b = fmt({"columns": [{"key": "a", "header": "Rate $\\mu$"}]}, csv="a\n*x* _y_ $5 [z]\n")
    assert "Rate $\\mu$" in md_lines(b)[0]
    assert md_lines(b)[2] == "| \\*x\\* \\_y\\_ \\$5 \\[z\\] |"


def test_latex_form_is_booktabs_and_escapes_data():
    b = fmt({"columns": ["Method", {"key": "Time", "decimals": 1}, "Note"]}, csv="Method,Time,Note\nx_1,5,50% & more\n")
    lines = b.latex.split("\n")
    assert lines[0] == "\\begin{tabular}{lrl}" and lines[1] == "\\toprule"
    assert "\\midrule" in lines and "\\bottomrule" in lines and lines[-1] == "\\end{tabular}"
    assert "x\\_1 & 5.0 & 50\\% \\& more \\\\" in b.latex


def test_grid_form_has_alignment_marks_and_equal_widths():
    b = fmt({"columns": ["Method", "Time"]})
    lines = b.grid.split("\n")
    assert lines[0].startswith("+-")
    assert lines[2].startswith("+:=") and lines[2].endswith("=:+")
    assert len({len(l) for l in lines}) == 1
    assert lines[1].startswith("| Method")


def test_spanners_are_latex_only_and_warned():
    b = fmt({"columns": ["Method", "Time", "Acc"], "spanners": [{"label": "Scores", "columns": ["Time", "Acc"]}]})
    assert "\\multicolumn{2}{c}{Scores}" in b.latex and "\\cmidrule(lr){2-3}" in b.latex
    assert "Scores" not in b.markdown and "Scores" not in b.grid
    assert any("spanning header" in w for w in b.warnings)
    with pytest.raises(ValueError):
        fmt({"columns": ["Method", "Time", "Acc"], "spanners": [{"label": "x", "columns": ["Method", "Acc"]}]})


def test_decimal_alignment_is_exact_with_decimals_and_warned_otherwise():
    exact = fmt({"columns": [{"key": "Time", "decimals": 2, "align": "decimal"}]})
    assert md_lines(exact)[1].endswith("-: |")
    assert not any("approximated" in w for w in exact.warnings)
    assert any("shown as right alignment" in w for w in exact.warnings)
    approx = fmt({"columns": [{"key": "Acc", "sig": 2, "align": "decimal"}]})
    assert any("approximated" in w for w in approx.warnings)


def test_text_in_a_numeric_column_is_kept_and_warned():
    b = fmt({"columns": [{"key": "v", "decimals": 1}]}, csv="v\n1\nabc\n")
    assert md_lines(b)[3] == "| abc |" and md_lines(b)[2] == "| 1.0 |"    # the text stays as written
    assert any("not a number" in w for w in b.warnings)


def test_bad_specs_are_errors_in_plain_words():
    for spec in ({"columns": ["Nope"]}, {"columns": [{"key": "Time", "decimals": 1, "sig": 2}]},
                 {"columns": [{"key": "Time", "decimals": -1}]}, {"columns": [{"key": "Time", "align": "up"}]},
                 {"columns": [{"key": "Time", "best": "big"}]}, {"sort": "Nope"}, {"columns": []}):
        with pytest.raises(ValueError):
            fmt(spec)
    with pytest.raises(ValueError):
        format_csv("", {})


def test_pipe_output_round_trips_through_the_canonical_writer():
    from chisel.core.tables import parse_pipe, to_pipe
    b = fmt({"columns": ["Method", "Note"]})
    assert to_pipe(parse_pipe(b.markdown)) == b.markdown
    assert b.export == {"grid": b.grid, "latex": b.latex}


# -- files -------------------------------------------------------------------------------


@pytest.fixture
def proj(tmp_path):
    p = Project.create(tmp_path / "paper", "Paper", "research")
    (p.root / "tables").mkdir(exist_ok=True)
    (p.root / "data").mkdir(exist_ok=True)
    (p.root / "data" / "results.csv").write_text(CSV, encoding="utf-8", newline="\n")
    (p.root / "tables" / "tbl-results.md").write_text(
        "---\ncaption: Results\nsource: data\ndata: data/results.csv\nformat:\n  columns:\n    - Method\n"
        "    - {key: Acc, decimals: 2, best: max}\n---\nold body\n", encoding="utf-8", newline="\n")
    return p


def test_build_table_reads_the_csv_and_spec(proj):
    b = build_table(proj, "results")
    assert b.caption == "Results"
    assert md_lines(b)[2:] == ["| alpha | 0.91 |", "| beta | 0.90 |", "| gamma | **0.95** |"]
    assert (proj.root / "tables" / "tbl-results.md").read_text(encoding="utf-8").endswith("old body\n")  # read-only


def test_apply_writes_generated_body_and_status_follows_the_data(proj):
    assert tablefmt.table_status(proj, "results") == "stale"          # never built
    tablefmt.apply_table(proj, "tbl:results")
    text = (proj.root / "tables" / "tbl-results.md").read_text(encoding="utf-8")
    assert "\r" not in text and "built:" in text and "caption: Results" in text
    assert text.split("---\n", 2)[2].startswith("<!-- generated by Chisel from data/results.csv")
    assert "old body" not in text and "| gamma | **0.95** |" in text
    assert tablefmt.table_status(proj, "results") == "current"
    (proj.root / "data" / "results.csv").write_text(CSV + "delta,1,0.5,x\n", encoding="utf-8", newline="\n")
    assert tablefmt.table_status(proj, "results") == "stale"
    tablefmt.apply_table(proj, "results")
    assert tablefmt.table_status(proj, "results") == "current"


def test_status_failed_and_missing(proj):
    md = proj.root / "tables" / "tbl-results.md"
    md.write_text(md.read_text(encoding="utf-8").replace("- Method", "- Nope"), encoding="utf-8")
    assert tablefmt.table_status(proj, "results") == "failed"
    (proj.root / "data" / "results.csv").unlink()
    assert tablefmt.table_status(proj, "results") == "missing"
    with pytest.raises(FileNotFoundError):
        build_table(proj, "results")


def test_data_path_must_stay_inside_the_project_and_be_csv(proj):
    md = proj.root / "tables" / "tbl-results.md"
    original = md.read_text(encoding="utf-8")
    for bad in ("../outside.csv", "data/results.txt"):
        md.write_text(original.replace("data/results.csv", bad), encoding="utf-8")
        with pytest.raises(ValueError):
            build_table(proj, "results")
    md.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        build_table(proj, "../results")


def test_a_hand_typed_table_is_not_built(proj):
    (proj.root / "tables" / "tbl-hand.md").write_text("---\ncaption: x\n---\n| a |\n| - |\n| 1 |\n", encoding="utf-8")
    with pytest.raises(ValueError):
        build_table(proj, "hand")


def test_fiction_projects_are_unaffected(tmp_path):
    story = Project.create(tmp_path / "novel", "Novel")
    before = sorted(p.relative_to(story.root).as_posix() for p in story.root.rglob("*"))
    with pytest.raises(ValueError):
        build_table(story, "results")
    with pytest.raises(ValueError):
        tablefmt.apply_table(story, "results")
    assert sorted(p.relative_to(story.root).as_posix() for p in story.root.rglob("*")) == before
