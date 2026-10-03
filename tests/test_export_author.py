"""Project & author details in the export: title page, copyright, PDF metadata,
pandoc metadata, manuscript header and contact, hyphenation language."""

import shutil
import subprocess
import zipfile

import pytest

from tests.export_helpers import make_structured
from chisel.core import export
from chisel.core.export import markdown, pdfkit
from chisel.core.export.manuscript import ExportOptions, assemble

needs = lambda tool: pytest.mark.skipif(shutil.which(tool) is None, reason=f"{tool} not installed")

INFO = dict(author="Jane Writer", pen_name="", subtitle="A Novel of Tomorrow",
            copyright_="© 2026 Jane Writer", contact="jane@example.com\nhttps://jane.example",
            language="fr")


def make(tmp_path, **info):
    project = make_structured(tmp_path / "p")
    project.update_author_info(**{**INFO, **info})
    return project


def export_to(project, tmp_path, **opts):
    return export.run_export(project, ExportOptions(**opts)).path


def text_of(pdf, first=None, last=None):
    args = ["pdftotext", "-layout"] + (["-f", str(first), "-l", str(last or first)] if first else [])
    return subprocess.run(args + [str(pdf), "-"], capture_output=True, text=True, check=True).stdout


def pdf_meta(pdf) -> dict:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return dict(line.split(":", 1) for line in out.splitlines() if ":" in line)


pytest.importorskip("reportlab")


def test_book_carries_the_details_and_copyright_override(tmp_path):
    project = make(tmp_path)
    book = assemble(project, ExportOptions())
    assert (book.subtitle, book.copyright, book.language) == ("A Novel of Tomorrow", "© 2026 Jane Writer", "fr")
    assert book.contact.startswith("jane@example.com")
    assert assemble(project, ExportOptions(copyright="Second edition")).copyright == "Second edition"
    assert assemble(project, ExportOptions(copyright="  ")).copyright == "© 2026 Jane Writer"


def test_pen_name_replaces_author(tmp_path):
    book = assemble(make(tmp_path, pen_name="J. Stone"), ExportOptions())
    assert book.author == "J. Stone"


@needs("pdftotext")
def test_book_title_page_and_copyright_line(tmp_path):
    project = make(tmp_path, pen_name="J. Stone")
    out = export_to(project, tmp_path, format="pdf", layout="book")
    page1 = text_of(out, 1)
    for want in ("Test Novel", "A Novel of Tomorrow", "J. Stone", "© 2026 Jane Writer"):
        assert want in page1
    assert "Jane Writer" in page1  # only inside the copyright line
    over = export_to(project, tmp_path, format="pdf", layout="book", copyright="Second edition")
    assert "Second edition" in text_of(over, 1) and "© 2026" not in text_of(over, 1)


@needs("pdfinfo")
@pytest.mark.parametrize("layout", ["book", "manuscript", "plain"])
def test_pdf_metadata_on_every_layout(tmp_path, layout):
    meta = pdf_meta(export_to(make(tmp_path), tmp_path, format="pdf", layout=layout))
    assert meta["Title"].strip() == "Test Novel"
    assert meta["Author"].strip() == "Jane Writer"
    assert meta["Subject"].strip() == "A Novel of Tomorrow"


@needs("pdftotext")
def test_manuscript_header_surname_and_contact(tmp_path):
    project = make(tmp_path)
    out = export_to(project, tmp_path, format="pdf", layout="manuscript")
    first = text_of(out, 1)
    top = [l.strip() for l in first.splitlines() if l.strip()]
    assert top[:3] == ["Jane Writer", "jane@example.com", "https://jane.example"]
    assert "A Novel of Tomorrow" in first
    assert "Writer / TEST NOVEL / 2" in text_of(out, 2)
    project.update_author_info(pen_name="Jo Stone")
    pen = export_to(project, tmp_path, format="pdf", layout="manuscript")
    assert "Stone / TEST NOVEL / 2" in text_of(pen, 2)
    assert "Writer / " not in text_of(pen, 2)


def test_hyphenation_language():
    pyphen = pytest.importorskip("pyphen")
    assert pdfkit.hyphenation_lang("fr") == "fr"
    assert pdfkit.hyphenation_lang("en-GB") == "en_GB"
    assert pdfkit.hyphenation_lang("en") == "en"
    assert pdfkit.hyphenation_lang("tlh") == "en_US"  # not in pyphen: fall back
    assert pdfkit.hyphenation_lang("") in pyphen.LANGUAGES


def test_pandoc_input_has_metadata(tmp_path):
    book = assemble(make(tmp_path, language="en_GB"), ExportOptions())
    text = markdown.to_markdown(book, pandoc=True)
    head = text.split("---")[1]
    for want in ('title: "Test Novel"', 'subtitle: "A Novel of Tomorrow"', 'author: "Jane Writer"',
                 'subject: "A Novel of Tomorrow"', 'rights: "© 2026 Jane Writer"', 'lang: "en-GB"'):
        assert want in head
    plain = markdown.to_markdown(book)
    assert plain.startswith("# Test Novel\n\n## A Novel of Tomorrow\n\n*Jane Writer*")
    assert "© 2026 Jane Writer" in plain


@needs("pandoc")
def test_epub_metadata(tmp_path):
    out = export_to(make(tmp_path), tmp_path, format="epub")
    with zipfile.ZipFile(out) as z:
        opf = z.read("EPUB/content.opf").decode() if "EPUB/content.opf" in z.namelist() else \
            next(z.read(n).decode() for n in z.namelist() if n.endswith(".opf"))
    for want in ("<dc:title", "Test Novel", "A Novel of Tomorrow", "Jane Writer",
                 "<dc:language>fr</dc:language>", "© 2026 Jane Writer"):
        assert want in opf


@needs("pandoc")
def test_docx_metadata(tmp_path):
    out = export_to(make(tmp_path), tmp_path, format="docx")
    with zipfile.ZipFile(out) as z:
        core = z.read("docProps/core.xml").decode()
        doc = z.read("word/document.xml").decode()
    assert "Test Novel" in core and "Jane Writer" in core and "A Novel of Tomorrow" in core
    assert "fr" in core and "© 2026 Jane Writer" in doc


@needs("pandoc")
def test_latex_has_title_author_subtitle(tmp_path):
    tex = export_to(make(tmp_path), tmp_path, format="tex").read_text()
    assert "Test Novel" in tex and "Jane Writer" in tex and "A Novel of Tomorrow" in tex
