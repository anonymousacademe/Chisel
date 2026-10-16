"""Research mode objects: placements, references, numbering, figures, math stripping, path containment."""

import os

import pytest

from chisel.core import objects
from chisel.core.objects import (
    create_figure, find_placements, find_refs, list_objects, numbering, read_figure, safe_project_path,
    strip_math, _figure_file,
)
from chisel.core.project import Project

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
def proj(tmp_path):
    return Project.create(tmp_path / "paper", "Paper", "research")


def scene(project, folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


# -- parsing ---------------------------------------------------------------------------


def test_placement_must_be_alone_on_its_line():
    text = "Intro\n![[fig:a-b]]\nsee [[fig:a-b]] and ![[tbl:x]] inline\n  ![[eq:m.1]]  \n"
    ps = find_placements(text)
    assert [(p.kind, p.label) for p in ps] == [("fig", "a-b"), ("eq", "m.1")]
    assert text[ps[0].start:ps[0].end] == "![[fig:a-b]]"
    assert text[ps[1].start:ps[1].end] == "![[eq:m.1]]"


def test_refs_exclude_placements_and_other_links():
    text = "![[fig:a]]\nSee [[fig:a]], [[tbl:t]] and [[Elara]] and [[@key]] and ![[tbl:inline]] x"
    refs = find_refs(text)
    assert [(r.kind, r.label) for r in refs] == [("fig", "a"), ("tbl", "t")]
    assert text[refs[0].start:refs[0].end] == "[[fig:a]]"


# -- strip_math ------------------------------------------------------------------------


def test_strip_math_is_a_noop_outside_research_mode():
    t = "a $x + y$ b $$z$$"
    assert strip_math(t) == t
    assert strip_math(t, mode="story") == t


def test_strip_math_keeps_length_and_newlines():
    t = "a $x+y$ b\n$$\nz\n$$ c"
    out = strip_math(t, mode="research")
    assert len(out) == len(t) and out.count("\n") == t.count("\n")
    assert "x" not in out and "z" not in out
    assert out.startswith("a ") and out.endswith(" c")
    assert strip_math("a $x$ b", keep_length=False, mode="research") == "a  b"


@pytest.mark.parametrize("text", [
    "It cost $5 and $10 today",
    "price $ 5 $ here",           # spaces inside
    "pay $20 or $30.",
    "a \\$x\\$ literal",
    "closing digit $x$5 no",
    "lonely $ sign",
    "$a\n\nb$",                   # blank line ends inline math
])
def test_strip_math_dollar_rule(text):
    assert strip_math(text, mode="research") == text


def test_strip_math_inline_adjacent_to_punctuation():
    assert strip_math("($x$).", mode="research") == "(   )."


# -- files -----------------------------------------------------------------------------


def test_create_figure_png_and_list(proj):
    obj = create_figure(proj, PNG, "flow-model", "Flow model")
    assert obj.kind == "fig" and obj.label == "flow-model" and obj.caption == "Flow model"
    assert obj.path == "figures/fig-flow-model.md" and obj.file == "figures/fig-flow-model.png"
    assert obj.status == "current" and obj.source == "static"
    assert (proj.root / "figures" / "fig-flow-model.png").read_bytes() == PNG
    assert list_objects(proj) == [obj]


def test_figure_kind_is_decided_from_bytes(proj):
    obj = create_figure(proj, JPG, "photo", "")
    assert obj.file == "figures/fig-photo.jpg"
    with pytest.raises(ValueError):
        create_figure(proj, b"GIF89a....", "anim", "")
    with pytest.raises(ValueError):
        create_figure(proj, b"<svg></svg>", "vec", "")
    assert not (proj.root / "figures" / "fig-anim.md").exists()


def test_figure_size_cap_and_label_checks(proj):
    with pytest.raises(ValueError):
        create_figure(proj, PNG + b"\x00" * objects.MAX_IMAGE_BYTES, "big", "")
    for bad in ("", "a b", "../x", "a/b", ".hidden", "x:y"):
        with pytest.raises(ValueError):
            create_figure(proj, PNG, bad, "")
    create_figure(proj, PNG, "ok", "")
    with pytest.raises(ValueError):
        create_figure(proj, JPG, "ok", "")          # a label in use, even with another type


def test_caption_survives_yaml_specials(proj):
    obj = create_figure(proj, PNG, "q", 'Flow: "a" # b')
    assert list_objects(proj)[0].caption == 'Flow: "a" # b'
    assert obj.caption == 'Flow: "a" # b'


def test_list_objects_reads_tables_and_equations(proj):
    (proj.root / "tables").mkdir()
    (proj.root / "tables" / "tbl-results.md").write_text("---\ncaption: Results\n---\n| a |\n| --- |\n| 1 |\n", encoding="utf-8", newline="\n")
    (proj.root / "tables" / "tbl-results.csv").write_text("a\n1\n", encoding="utf-8", newline="\n")
    (proj.root / "equations").mkdir()
    (proj.root / "equations" / "eq-mass.md").write_text("E = mc^2\n", encoding="utf-8", newline="\n")
    (proj.root / "equations" / "notes.md").write_text("ignored: no prefix\n", encoding="utf-8", newline="\n")
    objs = {(o.kind, o.label): o for o in list_objects(proj)}
    assert set(objs) == {("tbl", "results"), ("eq", "mass")}
    assert objs[("tbl", "results")].file == "tables/tbl-results.csv" and objs[("tbl", "results")].caption == "Results"
    assert objs[("eq", "mass")].file is None


def test_missing_image_status(proj):
    create_figure(proj, PNG, "gone", "")
    (proj.root / "figures" / "fig-gone.png").unlink()
    assert list_objects(proj)[0].status == "missing" and list_objects(proj)[0].file is None


# -- the _figure_file door -------------------------------------------------------------


def test_figure_file_serves_only_plain_labels(proj):
    create_figure(proj, PNG, "a", "")
    assert read_figure(proj, "a") == (PNG, "image/png")
    for bad in ("../a", "a/../a", "", "fig-a/../../project.toml", None, "a\\b"):
        with pytest.raises(ValueError):
            _figure_file(proj, bad)
    with pytest.raises(FileNotFoundError):
        _figure_file(proj, "nope")


def test_figure_file_refuses_symlinks(proj, tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(PNG)
    (proj.root / "figures").mkdir()
    link = proj.root / "figures" / "fig-evil.png"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises(ValueError):
        _figure_file(proj, "evil")


def test_safe_project_path_refuses_escapes(proj, tmp_path):
    ok = safe_project_path(proj, "data/results.csv")
    assert ok == (proj.root / "data" / "results.csv").resolve()
    for bad in ("../x.csv", "data/../../x.csv", "/etc/passwd", str(tmp_path / "x.csv"), "C:\\x.csv", "\\\\srv\\x", "", "data\\..\\..\\x"):
        with pytest.raises(ValueError):
            safe_project_path(proj, bad)


# -- numbering -------------------------------------------------------------------------


def book(proj):
    m = proj.manuscript_dir
    p1, p2 = proj.new_part("Methods"), proj.new_part("Results")
    scene(proj, m, "01-intro.md", "Intro\n\n![[fig:a]]\n\n![[tbl:t1]]\n")
    scene(proj, p1, "01-m.md", "x\n\n![[fig:b]]\n\nsee [[fig:c]] only a reference\n\n![[eq:e1]]\n")
    scene(proj, p2, "01-r.md", "![[fig:c]]\n\n![[fig:b]]\n\n![[fig:d]]\n\n![[tbl:t2]]\n")
    return p1, p2


def test_plain_numbering_in_reading_order(proj):
    book(proj)
    n = numbering(proj)
    assert {k: v.display for k, v in n.items()} == {
        "fig:a": "1", "tbl:t1": "1", "fig:b": "2", "eq:e1": "1", "fig:c": "3", "fig:d": "4", "tbl:t2": "2"}
    assert n["fig:c"].seq == 3


def test_reference_alone_does_not_number(proj):
    scene(proj, proj.manuscript_dir, "01-a.md", "only [[fig:zz]] here\n")
    assert numbering(proj) == {}


def test_numbering_follows_reorders(proj):
    p1, p2 = book(proj)
    proj.move_part(p2, -1)
    n = numbering(proj)
    # Results now precedes Methods, so c and b are first placed there
    assert [n[k].display for k in ("fig:a", "fig:c", "fig:b", "fig:d")] == ["1", "2", "3", "4"]


def test_per_section_numbering(proj):
    book(proj)
    n = numbering(proj, "per-section")
    assert n["fig:a"].display == "1"                      # outside any part: plain
    assert n["fig:b"].display == "1.1" and n["eq:e1"].display == "1.1"
    assert n["fig:c"].display == "2.1" and n["fig:d"].display == "2.2" and n["tbl:t2"].display == "2.1"


def test_supplementary_numbering_and_setting(proj):
    book(proj)
    n = numbering(proj, "supplementary")
    assert [n[k].display for k in ("fig:a", "fig:b", "fig:c")] == ["S1", "S2", "S3"]
    proj.meta["research"] = {"numbering": "supplementary"}
    assert numbering(proj)["fig:a"].display == "S1"
    proj.meta["research"] = {"numbering": "nonsense"}
    assert numbering(proj)["fig:a"].display == "1"


def test_duplicate_placement_shares_the_first_number(proj):
    scene(proj, proj.manuscript_dir, "01-a.md", "![[fig:x]]\n\n![[fig:y]]\n\n![[fig:x]]\n")
    n = numbering(proj)
    assert n["fig:x"].display == "1" and n["fig:y"].display == "2" and len(n) == 2


def test_parked_scenes_pending_drafts_math_and_details_do_not_number(proj):
    scene(proj, proj.unplaced_dir, "01-parked.md", "![[fig:parked]]\n")
    scene(proj, proj.manuscript_dir, "01-a.md",
          '---\nnote: "![[fig:meta]]"\n---\n<!--ai id="abc123"-->\n![[fig:ai]]\n<!--/ai-->\n$$\n![[fig:math]]\n$$\n![[fig:real]]\n')
    assert list(numbering(proj)) == ["fig:real"]


def test_story_project_does_not_strip_math_when_numbering(tmp_path):
    story = Project.create(tmp_path / "s", "S")
    scene(story, story.manuscript_dir, "01-a.md", "$$\n![[fig:m]]\n$$\n")
    assert "fig:m" in numbering(story)
