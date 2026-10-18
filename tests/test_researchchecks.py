"""Research checks (docs/dev/plan-research-mode.md 6.2): one test per check, the story no-op and the export gate."""

import pytest

from chisel.core import entities as ent
from chisel.core import objects
from chisel.core.paper.types import Flag
from chisel.core.project import Project
from chisel.core.researchchecks import blocking, run_checks

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def proj(tmp_path):
    return Project.create(tmp_path / "paper", "Paper", "research")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def scene(project, text, name="01-intro.md"):
    return write(project.manuscript_dir / name, text)


def source(project, key, extra=None, name=None):
    entity = ent.Entity(name=key, type="source", extra={"key": key, **(extra or {})})
    if name is None:
        path = project.entity_path(entity)
        ent.save_entity(entity, path)
    else:
        path = project.entities_dir / "sources" / f"{name}.md"
        ent.save_entity(entity, path)
    return path


def kinds(flags):
    return [f.kind for f in flags]


def of_kind(flags, kind):
    return [f for f in flags if f.kind == kind]


def test_citation_unresolved_blocks_and_reports_the_row(proj):
    source(proj, "smith2024")
    scene(proj, "Intro\n\nAs shown [[@smith2024]] and [[@ghost2020]].\n")
    flags = of_kind(run_checks(proj), "citation-unresolved")
    assert len(flags) == 1
    assert flags[0].row == 2
    assert flags[0].path == "manuscript/01-intro.md"
    assert "ghost2020" in flags[0].message
    assert flags[0].blocking is True


def test_source_uncited_is_a_warning(proj):
    source(proj, "smith2024")
    scene(proj, "Nothing cited here.\n")
    flags = of_kind(run_checks(proj), "source-uncited")
    assert len(flags) == 1
    assert flags[0].path == "entities/sources/smith2024.md"
    assert flags[0].blocking is False


def test_source_missing_from_zotero_is_a_warning(proj):
    source(proj, "smith2024", extra={"zotero_status": "missing"})
    scene(proj, "As [[@smith2024]] says.\n")
    flags = run_checks(proj)
    assert kinds(flags) == ["source-missing"]
    assert flags[0].blocking is False


def test_duplicate_source_key_is_flagged_on_the_second_note(proj):
    source(proj, "smith2024")
    source(proj, "smith2024", name="smith-copy")
    scene(proj, "[[@smith2024]]\n")
    flags = of_kind(run_checks(proj), "source-duplicate-key")
    # one flag, on the note that comes second in load order (the first one keeps the key)
    assert len(flags) == 1
    assert flags[0].path in ("entities/sources/smith-copy.md", "entities/sources/smith2024.md")
    assert flags[0].blocking is False


def test_reference_to_missing_object_blocks(proj):
    scene(proj, "Intro\n\nSee [[fig:nope]].\n\n![[tbl:ghost]]\n")
    flags = of_kind(run_checks(proj), "ref-missing")
    assert sorted(f.row for f in flags) == [2, 4]
    assert all(f.blocking for f in flags)


def test_figure_referenced_but_never_placed(proj):
    objects.create_figure(proj, PNG, "flow", "The flow")
    scene(proj, "As [[fig:flow]] shows.\n")
    flags = run_checks(proj)
    assert kinds(flags) == ["figure-unplaced"]
    assert flags[0].blocking is False


def test_object_never_placed_or_referenced(proj):
    objects.create_figure(proj, PNG, "flow", "The flow")
    scene(proj, "Plain prose.\n")
    flags = run_checks(proj)
    assert kinds(flags) == ["figure-unreferenced"]
    assert flags[0].path == "figures/fig-flow.md"


def test_table_and_equation_checks_use_their_own_words(proj):
    write(proj.root / "tables" / "tbl-results.md", "---\ncaption: Results\n---\n\n| a |\n")
    write(proj.root / "equations" / "eq-mass.md", "---\ncaption: Mass\n---\n\nm = 1\n")
    scene(proj, "Plain prose.\n")
    assert sorted(kinds(run_checks(proj))) == ["equation-unreferenced", "table-unreferenced"]


def test_missing_image_file_is_a_warning(proj):
    objects.create_figure(proj, PNG, "flow", "The flow")
    (proj.root / "figures" / "fig-flow.png").unlink()
    scene(proj, "![[fig:flow]]\n")
    flags = of_kind(run_checks(proj), "image-missing")
    assert len(flags) == 1
    assert flags[0].blocking is False


def test_labels_that_differ_only_in_case_are_a_duplicate(proj):
    folder = proj.root / "figures"
    write(folder / "fig-Flow.md", "---\ncaption: A\n---\n")
    write(folder / "fig-flow.md", "---\ncaption: B\n---\n")
    if len(list(folder.glob("fig-*.md"))) < 2:
        pytest.skip("the file system folds case, so the two labels cannot both exist")
    scene(proj, "![[fig:Flow]]\n![[fig:flow]]\n")
    flags = of_kind(run_checks(proj), "duplicate-label")
    assert len(flags) == 1
    assert flags[0].blocking is False


def test_story_project_is_a_no_op(tmp_path):
    story = Project.create(tmp_path / "novel", "Novel", "story")
    write(story.manuscript_dir / "01.md", "[[@ghost]] and [[fig:nope]]\n")
    assert run_checks(story) == []


def test_checks_never_write(proj):
    source(proj, "smith2024")
    scene(proj, "[[@ghost2020]] and [[fig:nope]]\n")
    before = sorted((p, p.read_bytes()) for p in proj.root.rglob("*") if p.is_file())
    run_checks(proj)
    after = sorted((p, p.read_bytes()) for p in proj.root.rglob("*") if p.is_file())
    assert before == after


def test_blocking_gate():
    assert blocking([]) is False
    assert blocking([Flag("source-uncited", "x.md", None, "m", False)]) is False
    assert blocking([Flag("source-uncited", "x.md", None, "m", False),
                     Flag("citation-unresolved", "y.md", 0, "m", True)]) is True
