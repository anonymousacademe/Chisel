"""Screenplay layout (script mode): US Letter, Courier-metric 12 pt (Liberation Mono), 55 lines a page,
the standard element positions (scene headings and action at the left margin, dialogue 1.0 in in, cues
2.2 in in, transitions at the right), a title page, and the page number at the top right from page 2.

The pages come from ``core.fountain.paginate`` (the same layout the editor's page estimate uses), so what is
drawn here is what the author was told. Dual dialogue prints one speaker after the other, and "(MORE)" /
"(CONT'D)" are not added: both are listed as later work in docs/dev/plan-script-mode.md."""

from __future__ import annotations

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from ... import fountain
from .. import pdfkit
from ..manuscript import Book, ExportOptions
from ..script import script_text
from . import Layout

SIZE = 12
LEADING = 12                 # six lines to the inch
LEFT = 1.5 * inch
TOP = 1.0 * inch


def _draw_row(canv: Canvas, face: pdfkit.Face, row: fountain.Row, y: float) -> None:
    x = LEFT + row.indent * pdfmetrics.stringWidth("0", face.regular, SIZE)   # monospaced: one width
    for seg in row.segs:
        font = (face.bold_italic if seg.bold and seg.italic else face.bold if seg.bold
                else face.italic if seg.italic else face.regular)
        canv.setFont(font, SIZE)
        canv.drawString(x, y, seg.text)
        width = pdfmetrics.stringWidth(seg.text, font, SIZE)
        if seg.underline:
            canv.setLineWidth(0.6)
            canv.line(x, y - 1.6, x + width, y - 1.6)
        x += width


def _centered(canv: Canvas, face: pdfkit.Face, text: str, y: float, width: float, *, underline: bool = False) -> None:
    canv.setFont(face.regular, SIZE)
    w = pdfmetrics.stringWidth(text, face.regular, SIZE)
    x = (width - w) / 2
    canv.drawString(x, y, text)
    if underline:
        canv.setLineWidth(0.6)
        canv.line(x, y - 1.6, x + w, y - 1.6)


def _title_page(canv: Canvas, face: pdfkit.Face, book: Book, width: float, height: float) -> None:
    y = height - 3.6 * inch
    title = fountain.plain(book.title).upper()
    for line in fountain._wrap([fountain.Seg(title)], 40):
        _centered(canv, face, "".join(s.text for s in line), y, width, underline=False)
        y -= LEADING
    if book.subtitle:
        y -= LEADING
        _centered(canv, face, book.subtitle, y, width)
        y -= LEADING
    if book.author:
        y -= 2 * LEADING
        _centered(canv, face, "Written by", y, width)
        y -= 2 * LEADING
        _centered(canv, face, book.author, y, width)
    y = 1.25 * inch
    lines = [ln.strip() for ln in book.contact.splitlines() if ln.strip()]
    if book.copyright.strip():
        lines += ([""] if lines else []) + [book.copyright.strip()]
    y += LEADING * (len(lines) - 1)
    canv.setFont(face.regular, SIZE)
    for ln in lines:
        canv.drawString(LEFT, y, ln)
        y -= LEADING


def render(book: Book, opts: ExportOptions, path) -> int:
    face = pdfkit.register_font(opts.font)
    width, height = LETTER
    pages = fountain.paginate(fountain.blocks(script_text(book)))
    canv = Canvas(str(path), pagesize=LETTER)
    canv.setTitle(book.title)
    canv.setAuthor(book.author)
    canv.setCreator("chisel")
    count = 0
    if book.title.strip():
        _title_page(canv, face, book, width, height)
        canv.showPage()
        count += 1
    for number, rows in enumerate(pages, start=1):
        for r, row in enumerate(rows):
            if row is not None:
                _draw_row(canv, face, row, height - TOP - SIZE * 0.8 - r * LEADING)
        if number > 1:
            canv.setFont(face.regular, SIZE)
            canv.drawRightString(width - 1.0 * inch, height - 0.5 * inch - SIZE * 0.8, f"{number}.")
        canv.showPage()
        count += 1
    canv.save()
    return count


LAYOUT = Layout(
    name="screenplay", label="Screenplay",
    description="Standard screenplay format: Courier 12 pt, 55 lines a page, numbered pages. Scripts only.",
    page_sizes=("letter",), fonts=("liberation-mono",),
    toc=False, continuous=False, numbering=False, render=render)
