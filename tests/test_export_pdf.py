import re
from dataclasses import replace
import shutil
import subprocess

import pytest

pytest.importorskip("reportlab")

from tests.export_helpers import make_structured
from chisel.core.export import layouts, pdfkit
from chisel.core.export.manuscript import ExportOptions, assemble

needs = lambda tool: pytest.mark.skipif(shutil.which(tool) is None, reason=f"{tool} not installed")


def build(tmp_path, layout, **kw):
    project = make_structured(tmp_path / "p")
    lay = layouts.get(layout)
    opts = lay.resolve(ExportOptions(**kw))
    if opts.font not in pdfkit.fonts_present():  # e.g. Liberation Serif is not on Windows
        opts = replace(opts, font=pdfkit.fallback_font(opts.font, lay.fonts))
    book = assemble(project, opts)
    out = tmp_path / f"{layout}.pdf"
    pages = lay.render(book, opts, out)
    return out, pages, book


def text_of(pdf, first=None, last=None):
    args = ["pdftotext", "-layout"]
    if first:
        args += ["-f", str(first), "-l", str(last or first)]
    return subprocess.run(args + [str(pdf), "-"], capture_output=True, text=True, check=True).stdout


def test_registry():
    assert [l.name for l in layouts.all_layouts()] == ["book", "manuscript", "plain"]
    book = layouts.get("book")
    forced = book.resolve(ExportOptions(page_size="a4", font="liberation-mono"))
    assert (forced.page_size, forced.font) == ("trade", "noto-serif")
    with pytest.raises(ValueError):
        layouts.get("nope")
    assert pdfkit.smarten("\"Hi,\" she said -- it's 'fine'...") == "“Hi,” she said — it’s ‘fine’…"


@needs("pdftotext")
@pytest.mark.parametrize("layout", ["book", "manuscript", "plain"])
def test_every_layout_writes_a_valid_pdf(tmp_path, layout):
    out, pages, book = build(tmp_path, layout)
    assert out.stat().st_size > 2000 and 3 <= pages <= 12
    if shutil.which("qpdf"):
        subprocess.run(["qpdf", "--check", str(out)], check=True, capture_output=True)
    text = text_of(out)
    if layout == "manuscript":  # titles are set in capitals there
        text = text.replace("RAIN ON THE SPUR", "Rain on the Spur").replace("SIGNAL", "Signal")
    for want in ("Rain on the Spur", "Elias waited under the clock", "Original sentence.", "Signal"):
        assert want in text
    for gone in ("Never in the book", "Going to the trash", "describe the platform", "grand rewritten",
                 "[[", "{{"):
        assert gone not in text
    if shutil.which("pdffonts"):  # every font embedded
        fonts = subprocess.run(["pdffonts", str(out)], capture_output=True, text=True).stdout.splitlines()[2:]
        assert fonts and all(re.search(r"\s+yes\s+", l) for l in fonts), fonts


@needs("pdftotext")
def test_book_contents_point_at_the_right_pages(tmp_path):
    out, pages, _ = build(tmp_path, "book", copyright="First edition")
    assert "First edition" in text_of(out, 1)
    toc = text_of(out, 2)
    assert "Contents" in toc
    for title, num in re.findall(r"(Capsule 7-19|Signal)[ .]+(\d+)", toc):
        assert title in text_of(out, int(num))
    part2 = int(re.search(r"Part II: Ghost Frequency[ .]+(\d+)", toc).group(1))
    assert "part ii" in text_of(out, part2).lower()


@needs("pdftotext")
def test_book_without_contents_and_running_heads(tmp_path):
    project = make_structured(tmp_path / "p")
    f = tmp_path / "p" / "manuscript" / "02-ghost-frequency" / "01-signal.md"
    f.write_text(f.read_text() + "\n\nThe signal grew louder and stranger every hour. " * 200)
    lay = layouts.get("book")
    opts = lay.resolve(ExportOptions(toc=False))
    out = tmp_path / "b.pdf"
    pages = lay.render(assemble(project, opts), opts, out)
    assert "Contents" not in text_of(out)
    # the long chapter spans pages: left pages carry the book title, right pages the chapter title
    heads = [text_of(out, p).strip().splitlines()[0].strip() for p in range(1, pages + 1)]
    assert "Signal" in heads and heads.count("Test Novel") >= 2  # right pages / left pages


@needs("pdftotext")
def test_manuscript_review_has_line_numbers_and_header(tmp_path):
    out, pages, book = build(tmp_path, "manuscript")
    first = text_of(out, 1)
    assert "about" in first and "words" in first and "TEST NOVEL" in first
    assert "Writer / TEST NOVEL / 1" not in first  # no header on the title page
    page3 = text_of(out, 4)
    assert "Writer / TEST NOVEL / 4" in page3
    nums = [int(m.group(1)) for m in re.finditer(r"^\s*(\d{1,2})\s", page3, re.M)]
    assert nums[:3] == [1, 2, 3] and nums == sorted(nums)
    assert "#" in text_of(out)  # scene breaks


@needs("pdftotext")
def test_continuous_book_has_no_chapter_headings(tmp_path):
    out, pages, _ = build(tmp_path, "book", continuous=True, toc=False)
    assert "Rain on the Spur" not in text_of(out) and "***" in "".join(text_of(out).split())


def test_fallback_font_prefers_the_same_kind_and_only_installed_ones(monkeypatch):
    monkeypatch.setattr(pdfkit, "fonts_present", lambda: frozenset({"noto-serif", "liberation-mono"}))
    fonts = ("liberation-serif", "liberation-mono", "noto-serif")
    assert pdfkit.fallback_font("liberation-serif", fonts) == "noto-serif"
    assert pdfkit.fallback_font("liberation-mono", fonts) == "liberation-mono"
    assert pdfkit.fallback_font("liberation-sans", ("liberation-sans",)) is None
    monkeypatch.setattr(pdfkit, "fonts_present", lambda: frozenset({"liberation-mono"}))
    assert pdfkit.fallback_font("liberation-serif", fonts) == "liberation-mono"  # any beats none
