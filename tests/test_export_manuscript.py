import shutil
from pathlib import Path

import pytest

from tests.export_helpers import make_structured
from chisel.core.export.manuscript import (
    Break, ExportOptions, Paragraph, Run, assemble, parse_blocks, parse_inline, roman,
)
from chisel.core.project import Project

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "residual"


def alltext(book):
    return "\n".join(b.text for c in book.chapters() for b in c.blocks if isinstance(b, Paragraph))


def test_inline_formatting():
    assert parse_inline("a *b* **c** ***d*** `e` _f_") == (
        Run("a "), Run("b", italic=True), Run(" "), Run("c", bold=True), Run(" "),
        Run("d", italic=True, bold=True), Run(" e "), Run("f", italic=True))
    # unmatched markers and snake_case stay literal; escapes are honoured
    assert parse_inline("2 * 3 and snake_case_name") == (Run("2 * 3 and snake_case_name"),)
    assert parse_inline("a \\*star\\*")[0].text == "a *star*"
    assert parse_inline("*open") == (Run("*open"),)


def test_blocks_join_wrapped_lines_and_find_breaks():
    blocks = parse_blocks("One\ntwo.\n\n***\n\nThree.\n\n- - -\n\n___\n\nFour.\n\n***\n")
    assert [type(b).__name__ for b in blocks] == ["Paragraph", "Break", "Paragraph", "Break", "Paragraph"]
    assert blocks[0].text == "One two."
    assert parse_blocks("## Sub\n\n> quoted <!-- note -->\n")[1].text == "quoted"


def test_roman():
    assert [roman(n) for n in (1, 4, 9, 14, 2026)] == ["I", "IV", "IX", "XIV", "MMXXVI"]


def test_order_exclusions_and_text(tmp_path):
    book = assemble(make_structured(tmp_path / "p"))
    assert book.title == "Test Novel" and book.author == "Jane Writer"
    assert [p.title for p in book.parts] == ["Front Matter", "The Recall", "Ghost Frequency"]
    assert [[c.title for c in p.chapters] for p in book.parts] == [
        ["Dedication"], ["Rain on the Spur", "Capsule 7-19"], ["Signal"]]
    text = alltext(book)
    for gone in ("Never in the book", "Going to the trash", "Research only", "notes for me",
                 "pov:", "status:"):
        assert gone not in text
    assert [c.label for c in book.chapters()] == ["", "Scene 1", "Scene 2", "Scene 3"]
    assert [p.label for p in book.parts] == ["", "Part I", "Part II"]
    assert book.parts[0].front and book.scenes == 4


def test_links_formatting_markers_and_drafts(tmp_path):
    book = assemble(make_structured(tmp_path / "p"))
    rain, capsule = book.parts[1].chapters
    first = rain.blocks[0]
    assert first.text.startswith("Mara stepped off the tram. Elias waited under the clock,")
    assert Run("clock", italic=True) in first.runs and Run("heavy", bold=True) in first.runs
    assert "{{expand" not in alltext(book) and "describe the platform" not in alltext(book)
    assert [type(b).__name__ for b in rain.blocks] == ["Paragraph", "Paragraph", "Break", "Paragraph"]
    assert rain.blocks[-1].text == "The second half began with a code word and an escaped *star*."
    assert capsule.blocks[0].text == "Original sentence. The capsule hummed. Then silence."
    assert "grand rewritten" not in alltext(book) and "invented line" not in alltext(book)
    assert capsule.blocks[-1].text == "Lower Meridian slept."
    assert [w.kind for w in book.warnings] == ["expand"]
    assert "describe the platform" in book.warnings[0].message
    assert book.draft_scenes == ["manuscript/01-the-recall/02-capsule-7-19.md"]


def test_include_drafts_option(tmp_path):
    book = assemble(make_structured(tmp_path / "p"), ExportOptions(include_drafts=True))
    text = alltext(book)
    assert "A grand rewritten sentence. The capsule hummed. Then an invented linesilence." in text
    assert "Original sentence" not in text and "<!--" not in text
    assert len(book.draft_scenes) == 1  # still reported


def test_missing_original_is_reported(tmp_path):
    project = make_structured(tmp_path / "p")
    (tmp_path / "p" / ".drafts" /
     "manuscript__01-the-recall__02-capsule-7-19.md.json").unlink()
    book = assemble(project)
    assert "draft-missing" in [w.kind for w in book.warnings]


def test_front_matter_numbering_and_continuous(tmp_path):
    project = make_structured(tmp_path / "p")
    book = assemble(project, ExportOptions(include_front_matter=False, numbering="titles-only"))
    assert [p.title for p in book.parts] == ["The Recall", "Ghost Frequency"]
    assert all(c.label == "" for c in book.chapters()) and all(p.label == "" for p in book.parts)
    numbers = assemble(project, ExportOptions(numbering="numbers"))
    assert [c.label for c in numbers.chapters()] == ["", "1", "2", "3"]
    recall = assemble(project, ExportOptions(continuous=True)).parts[1]
    assert len(recall.chapters) == 1 and recall.chapters[0].title == ""
    # the scene's own break, the break joining the two scenes, the second scene's own
    assert sum(isinstance(b, Break) for b in recall.chapters[0].blocks) == 3
    project.update_manuscript_settings(unit="chapter")
    assert assemble(project).parts[1].chapters[0].label == "Chapter 1"


def test_word_count(tmp_path):
    book = assemble(make_structured(tmp_path / "p"))
    assert book.words == sum(len(b.text.split()) for c in book.chapters()
                             for b in c.blocks if isinstance(b, Paragraph))
    assert book.summary()["draft_scenes"] == 1 and book.summary()["parts"] == 2


def test_example_project_flat_and_read_only(tmp_path):
    dst = tmp_path / "residual"
    shutil.copytree(EXAMPLE, dst)
    before = {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}
    book = assemble(Project.open(dst))
    assert [p.title for p in book.parts] == [None]
    assert book.scenes == 4 and book.words > 500
    assert all("[[" not in b.text for c in book.chapters() for b in c.blocks if isinstance(b, Paragraph))
    assert before == {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}


def test_options_validation():
    assert ExportOptions.from_dict({"format": "epub", "bogus": 1}).format == "epub"
    for bad in ({"format": "rtf"}, {"toc": "yes"}, {"numbering": "x"}, {"page_size": "b5"}, {"font": 3}):
        with pytest.raises(ValueError):
            ExportOptions.from_dict(bad)
