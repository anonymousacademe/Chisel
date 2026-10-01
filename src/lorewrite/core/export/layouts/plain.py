"""Plain proof layout: A4, sans serif, 1.5 line spacing, left aligned, a new
page per chapter. A deliberately simple third layout for proofreading on
screen or paper (and the proof that the layout mechanism takes more than two)."""

from __future__ import annotations

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph as RLParagraph, Spacer,
)

from .. import pdfkit
from ..manuscript import Book, Break, ExportOptions, Run
from . import Layout

SIZE = 10.5


def render(book: Book, opts: ExportOptions, path) -> int:
    face = pdfkit.register_font(opts.font)
    width, height = pdfkit.PAGE_SIZES[opts.page_size]
    margin = 2.3 * cm
    body = ParagraphStyle("pp", fontName=face.regular, fontSize=SIZE, leading=SIZE * 1.5,
                          spaceAfter=SIZE * 0.6, allowWidows=0, allowOrphans=0)
    h1 = ParagraphStyle("pp-h1", parent=body, fontName=face.bold, fontSize=17, leading=21,
                        spaceAfter=14, keepWithNext=1)
    h0 = ParagraphStyle("pp-h0", parent=h1, fontSize=22, leading=27, spaceBefore=60)
    label = ParagraphStyle("pp-l", parent=body, textColor="#666666", spaceAfter=2)
    brk = ParagraphStyle("pp-b", parent=body, alignment=1)

    def foot(canv, doc):
        canv.saveState()
        canv.setFont(face.regular, 8.5)
        canv.setFillGray(0.4)
        canv.drawString(margin, 1.3 * cm, book.title)
        canv.drawRightString(width - margin, 1.3 * cm, str(doc.page))
        canv.restoreState()

    def para(text, style):
        return RLParagraph(pdfkit.markup((Run(text),)), style)

    story: list = [Spacer(1, 4 * cm), para(book.title, ParagraphStyle(
        "pp-t", parent=h0, fontSize=30, leading=36, spaceBefore=0))]
    if book.author:
        story.append(para(book.author, body))
    story += [para(f"{book.words:,} words in {book.scenes} scenes", label), PageBreak()]
    fresh = True
    for part in book.parts:
        if part.title is not None and not part.front:
            if not fresh:
                story.append(PageBreak())
            if part.label:
                story.append(para(part.label, label))
            story += [para(part.title, h0), PageBreak()]
            fresh = True
        for chapter in part.chapters:
            if not fresh:
                story.append(PageBreak())
            fresh = False
            if chapter.label and chapter.title:
                story.append(para(chapter.label, label))
            if chapter.title or chapter.label:
                story.append(para(chapter.title or chapter.label, h1))
            for block in chapter.blocks:
                story.append(RLParagraph("* * *", brk) if isinstance(block, Break)
                             else RLParagraph(pdfkit.markup(block.runs), body))
    doc = BaseDocTemplate(str(path), pagesize=(width, height), title=book.title,
                          author=book.author, creator="lorewrite",
                          initialFontName=face.regular, initialFontSize=SIZE)
    frame = Frame(margin, 2 * cm, width - 2 * margin, height - 2 * cm - margin, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPageEnd=foot)])
    doc.build(story)
    return doc.page


LAYOUT = Layout(
    name="plain", label="Plain proof",
    description="A4, sans serif, 1.5 spacing: a simple copy for proofreading.",
    page_sizes=("a4", "letter"), fonts=("liberation-sans",),
    toc=False, continuous=True, numbering=True, render=render)
