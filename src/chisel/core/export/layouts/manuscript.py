"""Manuscript review layout: the standard manuscript format for printing and
red-pen review. US Letter, 1-inch margins, 12 pt, double spaced, line numbers
(restarting on every page) in the left margin, a running header
"Author / TITLE / page", each chapter starting a third of the way down its
page, ``#`` for scene breaks, the word count on the title page.

Everything sits on a 24 pt grid (27 lines per page), so the line numbers are
simply drawn at the baseline of every line of every paragraph."""

from __future__ import annotations

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate, Paragraph as RLParagraph,
    Spacer,
)

from .. import pdfkit
from ..manuscript import Book, Break, ExportOptions, Run
from . import Layout

SIZE = 12
GRID = 24  # double spacing


class Mark(Flowable):
    """Zero-size marker: the page it lands on has no running header."""

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        pass


class NumberedParagraph(RLParagraph):
    """A paragraph that writes the number of each of its lines in the margin;
    the count restarts on every page."""

    def draw(self):
        super().draw()
        canv: Canvas = self.canv
        page = canv.getPageNumber()
        seen, count = getattr(canv, "_lw_lines", (None, 0))
        if seen != page:
            count = 0
        style = self.style
        canv.saveState()
        canv.setFont(style.fontName, 8)
        canv.setFillGray(0.4)
        for i in range(len(self.blPara.lines)):
            count += 1
            canv.drawRightString(-0.18 * inch, self.height - style.fontSize - i * style.leading,
                                 str(count))
        canv.restoreState()
        canv._lw_lines = (page, count)


class Doc(BaseDocTemplate):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.bare: set[int] = set()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Mark):
            self.bare.add(self.page)


def _rounded_words(n: int) -> str:
    step = 1000 if n >= 10000 else 100 if n >= 1000 else 10
    return f"about {round(n / step) * step:,} words"


def _surname(author: str) -> str:
    """Last word of the name ("Jane Writer" -> "Writer"; "Writer, Jane" -> "Writer")."""
    if "," in author:
        author = author.split(",")[0]
    return author.split()[-1] if author.split() else ""


def render(book: Book, opts: ExportOptions, path) -> int:
    face = pdfkit.register_font(opts.font)
    width, height = pdfkit.PAGE_SIZES["letter"]
    margin = 1 * inch
    frame_h = height - 2 * margin  # 9 in = 27 lines
    base = ParagraphStyle("ms", fontName=face.regular, fontSize=SIZE, leading=GRID,
                          alignment=TA_LEFT, firstLineIndent=0.5 * inch, allowWidows=0,
                          allowOrphans=0, splitLongWords=1)
    centre = ParagraphStyle("ms-c", parent=base, alignment=TA_CENTER, firstLineIndent=0)
    first = ParagraphStyle("ms-1", parent=base, firstLineIndent=0.5 * inch)
    short_title = book.title.upper()
    if len(short_title) > 40:
        short_title = short_title[:39].rstrip() + "…"
    runner = f"{_surname(book.author)} / {short_title}".strip(" /")

    def head(canv, doc):
        if doc.page in doc.bare:
            return
        canv.saveState()
        canv.setFont(face.regular, SIZE)
        canv.drawRightString(width - margin, height - 0.6 * inch, f"{runner} / {doc.page}")
        canv.restoreState()

    def plain(text: str, style=base, cls=RLParagraph):
        return cls(pdfkit.markup((Run(text),)), style)

    story: list = [Mark()]
    corner = ParagraphStyle("ms-a", parent=base, firstLineIndent=0, spaceAfter=0)
    # standard manuscript format: name, then contact, top left
    story.append(RLParagraph(pdfkit.markup((Run(book.author),)), corner))
    lines = 1
    for line in (book.contact.splitlines() if book.contact else []):
        if line.strip():
            story.append(RLParagraph(pdfkit.markup((Run(line.strip()),)), corner))
            lines += 1
    story.append(Spacer(1, GRID * max(1, 8 - lines + 1)))
    story.append(RLParagraph(pdfkit.markup((Run(book.title.upper()),)), centre))
    if book.subtitle:
        story.append(plain(book.subtitle, centre))
    if book.author:
        story += [Spacer(1, GRID), plain("by", centre), plain(book.author, centre)]
    story += [Spacer(1, GRID * 2), plain(_rounded_words(book.words), centre)]
    if book.copyright:
        story += [Spacer(1, GRID * 3), plain(book.copyright, centre)]
    story.append(PageBreak())

    fresh = True
    for part in book.parts:
        if part.title is not None and not part.front:
            if not fresh:
                story.append(PageBreak())
            story += [Spacer(1, GRID * 9)]
            if part.label:
                story.append(plain(part.label.upper(), centre, NumberedParagraph))
            story.append(plain(part.title.upper(), centre, NumberedParagraph))
            story.append(PageBreak())
            fresh = True
        for chapter in part.chapters:
            if not fresh:
                story.append(PageBreak())
            fresh = False
            shown = chapter.title
            if shown or chapter.label:
                story.append(Spacer(1, GRID * 9))
                if chapter.label and shown:
                    story.append(plain(chapter.label.upper(), centre, NumberedParagraph))
                story.append(plain((shown or chapter.label).upper(), centre, NumberedParagraph))
                story.append(Spacer(1, GRID))
            for block in chapter.blocks:
                if isinstance(block, Break):
                    story.append(plain("#", centre, NumberedParagraph))
                else:
                    story.append(NumberedParagraph(pdfkit.markup(block.runs), first))

    doc = Doc(str(path), pagesize=(width, height), title=book.title, author=book.author,
              subject=book.subtitle, creator="chisel", initialFontName=face.regular, initialFontSize=SIZE,
              leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin)
    frame = Frame(margin, margin, width - 2 * margin, frame_h, id="f", leftPadding=0,
                  rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPageEnd=head)])
    doc.build(story)
    return doc.page


LAYOUT = Layout(
    name="manuscript", label="Manuscript review",
    description="Double-spaced with line numbers on every page, for printing and red-pen review.",
    page_sizes=("letter",), fonts=("liberation-serif", "liberation-mono", "noto-serif"),
    toc=False, continuous=True, numbering=True, render=render)
