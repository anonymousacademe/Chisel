import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from tests.export_helpers import make_structured
from lorewrite.core import desktop, export
from lorewrite.core.export import markdown, pandoc
from lorewrite.core.export.manuscript import ExportOptions, assemble
from lorewrite.core.project import Project

NOW = datetime(2026, 10, 1, 14, 30)
has_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")


def run(tmp_path, **kw):
    project = make_structured(tmp_path / "p") if not (tmp_path / "p").exists() else Project.open(tmp_path / "p")
    return project, export.run_export(project, ExportOptions(**kw), now=NOW)


def test_markdown_export_and_naming(tmp_path):
    project, res = run(tmp_path, format="md")
    assert res.rel == "exports/test-novel-md-20261001-1430.md"
    text = res.path.read_text()
    assert text.startswith("# Test Novel\n\n*Jane Writer*")
    assert "# Part I: The Recall" in text and "## Scene 1: Rain on the Spur" in text
    assert "Elias waited under the *clock*" in text and "**heavy**" in text
    assert "* * *" in text and "Never in the book" not in text and "<!--" not in text
    assert res.pages is None and res.words > 20 and res.scenes == 4
    assert any("unaccepted AI drafts" in w for w in res.warnings)
    # never overwrites
    again = export.run_export(project, ExportOptions(format="md"), now=NOW)
    assert again.path.name.endswith("1430-2.md") and res.path.exists()
    assert not list((tmp_path / "p" / "exports").glob(".*"))  # no partial files


def test_options_are_remembered_in_project_toml(tmp_path):
    project, _ = run(tmp_path, format="md", numbering="numbers", toc=False, copyright='Ed "1"')
    assert "[export]" in (tmp_path / "p" / "project.toml").read_text()
    loaded = export.load_options(Project.open(tmp_path / "p"))
    assert (loaded.format, loaded.numbering, loaded.toc, loaded.copyright) == ("md", "numbers", False, 'Ed "1"')
    assert export.load_options(project).include_drafts is False


def test_nothing_to_export_and_bad_input(tmp_path):
    project = Project.create(tmp_path / "e", "Empty")
    (tmp_path / "e" / "manuscript" / "01-opening.md").unlink()
    with pytest.raises(ValueError, match="nothing to export"):
        export.run_export(project, ExportOptions(format="md"))


def test_markdown_escaping_survives_pandoc_input():
    from lorewrite.core.export.manuscript import parse_blocks, Book, Part, Chapter
    blocks = parse_blocks("1. not a list\n\n- nor this\n\nPrice is $5 # [x] <b> a_b @me")
    book = Book(title="T", author="", options=ExportOptions(), parts=[Part(None, chapters=[Chapter("C", blocks=blocks)])])
    md = markdown.to_markdown(book, pandoc=True)
    assert "1\\. not a list" in md and "\\- nor this" in md and "\\$5 \\# \\[x\\] \\<b\\> a\\_b \\@me" in md


def test_describe_and_summarize(tmp_path):
    project = make_structured(tmp_path / "p")
    info = export.describe(project)
    assert [f["key"] for f in info["formats"]] == ["pdf", "docx", "epub", "md", "tex"]
    assert [l["name"] for l in info["layouts"]] == ["book", "manuscript", "plain"]
    s = export.summarize(project, ExportOptions())
    assert (s["scenes"], s["parts"], s["draft_scenes"]) == (4, 2, 1)
    assert any("unaccepted AI drafts" in m for m in s["messages"])


def test_resolve_export_is_a_narrow_door(tmp_path):
    project, res = run(tmp_path, format="md")
    assert export.resolve_export(project, res.path.name) == res.path
    assert export.resolve_export(project, "") == res.path.parent
    for bad in ("../project.toml", "a/b.md", ".hidden"):
        with pytest.raises(ValueError):
            export.resolve_export(project, bad)
    with pytest.raises(FileNotFoundError):
        export.resolve_export(project, "gone.md")


def test_open_in_desktop_hands_the_path_to_the_desktop(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(desktop, "open_path", lambda path: seen.append(path) or True)
    export.open_in_desktop(tmp_path)
    assert seen == [tmp_path]
    monkeypatch.setattr(desktop, "open_path", lambda path: False)
    with pytest.raises(RuntimeError):
        export.open_in_desktop(tmp_path)


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext missing")
def test_pdf_run_reports_pages_and_font_fallback(tmp_path, monkeypatch):
    project, res = run(tmp_path, format="pdf", layout="book")
    assert res.pages >= 6 and res.path.suffix == ".pdf" and res.path.name.startswith("test-novel-book-")
    from lorewrite.core.export import pdfkit
    monkeypatch.setattr(pdfkit, "fonts_present", lambda: frozenset({"liberation-serif"}))
    res2 = export.run_export(project, ExportOptions(format="pdf", layout="book"), now=NOW)
    assert any("Noto Serif is not installed" in w for w in res2.warnings)


@has_pandoc
def test_docx_epub_and_tex_via_pandoc(tmp_path):
    project = make_structured(tmp_path / "p")
    docx = export.run_export(project, ExportOptions(format="docx"), now=NOW)
    with zipfile.ZipFile(docx.path) as z:
        body = z.read("word/document.xml").decode()
    assert "Rain on the Spur" in body and "Never in the book" not in body and "grand rewritten" not in body
    epub = export.run_export(project, ExportOptions(format="epub"), now=NOW)
    with zipfile.ZipFile(epub.path) as z:
        names = z.namelist()
        text = "".join(z.read(n).decode() for n in names if n.endswith(".xhtml"))
    assert sum(n.endswith(".xhtml") and "ch0" in n for n in names) >= 5  # split per part / scene
    assert "Capsule 7-19" in text and "Jane Writer" in text
    tex = export.run_export(project, ExportOptions(format="tex"), now=NOW)
    src = tex.path.read_text()
    assert "\\begin{document}" in src and "Signal" in src and "Never in the book" not in src


@has_pandoc
def test_pandoc_failure_is_a_clear_error(tmp_path, monkeypatch):
    project = make_structured(tmp_path / "p")
    monkeypatch.setattr(pandoc, "_TARGETS", {"docx": "nonsense"})
    with pytest.raises(RuntimeError, match="pandoc failed"):
        export.run_export(project, ExportOptions(format="docx"))
    assert not list((tmp_path / "p" / "exports").glob("*"))


def test_missing_pandoc_is_reported(tmp_path, monkeypatch):
    project = make_structured(tmp_path / "p")
    monkeypatch.setattr(pandoc, "find", lambda: None)
    with pytest.raises(RuntimeError, match="pandoc is not installed"):
        export.run_export(project, ExportOptions(format="epub"))
    docx = [f for f in export.describe(project)["formats"] if f["key"] == "docx"][0]
    assert not docx["available"] and docx["reason"] == "install pandoc"
