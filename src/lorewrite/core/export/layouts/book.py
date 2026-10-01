"""Book layout: a typeset trade paperback.

Title page, optional contents, part title pages, every scene (chapter) on a new
page, classic look: justified text, first paragraph of a chapter not indented
and the rest indented, running heads (book title on left pages, chapter title
on right pages), page numbers in the foot, mirrored margins."""

from __future__ import annotations

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, HRFlowable, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph as RLParagraph, Spacer, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from .. import pdfkit
from ..manuscript import Break, Book, ExportOptions
from . import Layout

BODY = 11
LEADING = 14
ORNAMENT = "*&nbsp;&nbsp;*&nbsp;&nbsp;*"


class Mark(Flowable):
    """Zero-size flowable that tells the document something about the page it
    lands on (read in ``BookDoc.afterFlowable``)."""

    def __init__(self, kind: str, text: str = "") -> None:
        super().__init__()
        self.kind, self.text = kind, text

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        pass


class BookDoc(BaseDocTemplate):
    def __init__(self, path, book: Book, opts: ExportOptions, face: pdfkit.Face, **kw):
        super().__init__(path, **kw)
        self.book, self.opts, self.face = book, opts, face
        self.chapter_title = ""
        self.flags: dict[int, set[str]] = {}
        self._key = 0

    def handle_documentBegin(self):  # every multiBuild pass starts afresh
        self._key = 0
        self.chapter_title = ""
        self.flags = {}
        super().handle_documentBegin()

    # chapters and parts announce themselves; headings feed the contents
    def afterFlowable(self, flowable):
        if isinstance(flowable, Mark):
            page = self.flags.setdefault(self.page, set())
            if flowable.kind == "chapter":
                self.chapter_title = flowable.text
                page.add("nohead")
            else:
                page.add(flowable.kind)
        entry = getattr(flowable, "_toc", None)
        if entry:
            level, text = entry
            self._key += 1
            key = f"toc{self._key}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level, 0)
            self.notify("TOCEntry", (level, text, self.page, key))


def _styles(face: pdfkit.Face, opts: ExportOptions) -> dict[str, ParagraphStyle]:
    lang = pdfkit.hyphenation_lang()
    body = ParagraphStyle(
        "body", fontName=face.regular, fontSize=BODY, leading=LEADING,
        alignment=TA_JUSTIFY, firstLineIndent=1.4 * BODY, allowWidows=0, allowOrphans=0,
        hyphenationLang=lang or "", embeddedHyphenation=1 if lang else 0, uriWasteReduce=0.3,
        splitLongWords=1)
    centre = dict(alignment=TA_CENTER, firstLineIndent=0)
    return {
        "body": body,
        "first": ParagraphStyle("first", parent=body, firstLineIndent=0),
        "break": ParagraphStyle("break", parent=body, spaceBefore=LEADING * 0.8,
                                spaceAfter=LEADING * 0.8, **centre),
        "label": ParagraphStyle("label", parent=body, fontSize=9, leading=12,
                                textTransform="uppercase", spaceAfter=6, **centre),
        "title": ParagraphStyle("title", parent=body, fontName=face.regular, fontSize=20,
                                leading=25, spaceAfter=10, keepWithNext=1, **centre),
        "part_label": ParagraphStyle("part_label", parent=body, fontSize=11, leading=14,
                                     textTransform="uppercase", spaceAfter=10, **centre),
        "part_title": ParagraphStyle("part_title", parent=body, fontSize=26, leading=32, **centre),
        "book_title": ParagraphStyle("book_title", parent=body, fontSize=30, leading=36,
                                     spaceAfter=18, **centre),
        "author": ParagraphStyle("author", parent=body, fontSize=15, leading=20, **centre),
        "small": ParagraphStyle("small", parent=body, fontSize=8.5, leading=11, **centre),
        "contents": ParagraphStyle("contents", parent=body, fontSize=18, leading=24,
                                   spaceAfter=18, **centre),
        "toc0": ParagraphStyle("toc0", parent=body, fontName=face.bold, fontSize=BODY,
                               leading=LEADING + 2, spaceBefore=6, firstLineIndent=0,
                               alignment=0),
        "toc1": ParagraphStyle("toc1", parent=body, leftIndent=14, firstLineIndent=0,
                               leading=LEADING + 1, alignment=0),
    }


def _tagged(par: RLParagraph, level: int, text: str) -> RLParagraph:
    par._toc = (level, text)  # read by BookDoc.afterFlowable
    return par


def _story(book: Book, opts: ExportOptions, st: dict, frame_h: float, face: pdfkit.Face) -> list:
    smart = True
    story: list = []
    toc_wanted = opts.toc and any(not p.front and p.chapters for p in book.parts)

    story += [Mark("nochrome"), Spacer(1, frame_h * 0.28),
              RLParagraph(pdfkit.markup(_runs(book.title), smart), st["book_title"])]
    if book.author:
        story.append(RLParagraph(pdfkit.markup(_runs(book.author), smart), st["author"]))
    story.append(NextPageTemplate(["verso", "recto"]))
    story.append(PageBreak())

    if toc_wanted:
        toc = TableOfContents(dotsMinLevel=0)
        toc.levelStyles = [st["toc0"], st["toc1"]]
        toc.tableStyle = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("FONTNAME", (0, 0), (-1, -1), face.regular)])
        story += [Mark("nohead"), Spacer(1, frame_h * 0.08),
                  RLParagraph("Contents", st["contents"]), toc, PageBreak()]

    first_unit = True
    for part in book.parts:
        part_page = part.title is not None and not part.front
        if part_page:
            if not first_unit:
                story.append(PageBreak())
            heading = [Mark("nohead"), Spacer(1, frame_h * 0.30)]
            if part.label:
                heading.append(RLParagraph(pdfkit.markup(_runs(part.label)), st["part_label"]))
            heading.append(_tagged(RLParagraph(pdfkit.markup(_runs(part.title), smart),
                                               st["part_title"]), 0, _plain(part, smart)))
            story += heading
            first_unit = False
        for chapter in part.chapters:
            if not first_unit:
                story.append(PageBreak())
            first_unit = False
            story += _chapter(chapter, part, opts, st, frame_h, smart, part_page)
    return story


def _plain(part, smart: bool) -> str:
    text = (part.label + ": " if part.label else "") + (part.title or "")
    return pdfkit.smarten(text) if smart else text


def _runs(text: str):
    from ..manuscript import Run
    return (Run(text),)


def _chapter(chapter, part, opts, st, frame_h, smart, in_part) -> list:
    out: list = []
    shown = chapter.title or chapter.label
    if shown:
        out += [Mark("chapter", pdfkit.smarten(shown)), Spacer(1, frame_h * 0.16)]
        if chapter.label and chapter.title:
            out.append(RLParagraph(pdfkit.markup(_runs(chapter.label)), st["label"]))
        heading = RLParagraph(pdfkit.markup(_runs(shown), smart), st["title"])
        if not part.front:  # front matter is not listed in the contents
            toc_text = f"{chapter.label}. {chapter.title}" if chapter.label and chapter.title else shown
            heading = _tagged(heading, 1 if in_part else 0, pdfkit.smarten(toc_text))
        out += [heading, HRFlowable(width="14%", thickness=0.6, spaceBefore=2, spaceAfter=22,
                                    color="#555555", hAlign="CENTER")]
    else:
        out.append(Mark("nohead"))
    first = True
    for block in chapter.blocks:
        if isinstance(block, Break):
            out.append(RLParagraph(ORNAMENT, st["break"]))
            first = True
            continue
        out.append(RLParagraph(pdfkit.markup(block.runs, smart),
                               st["first"] if first else st["body"]))
        first = False
    return out


def render(book: Book, opts: ExportOptions, path) -> int:
    face = pdfkit.register_font(opts.font)
    width, height = pdfkit.PAGE_SIZES[opts.page_size]
    big = opts.page_size == "letter"
    top, bottom = (0.9 if big else 0.8) * inch, (1.0 if big else 0.9) * inch
    inner, outer = (1.0 if big else 0.9) * inch, (0.8 if big else 0.7) * inch
    st = _styles(face, opts)
    title = pdfkit.smarten(book.title)

    def frame(left: float, right: float, name: str) -> Frame:
        return Frame(left, bottom, width - left - right, height - top - bottom,
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=name)

    def chrome(canv, doc, side: str) -> None:
        flags = doc.flags.get(doc.page, set())
        if "nochrome" in flags:
            if opts.copyright:
                canv.saveState()
                canv.setFont(face.regular, 8.5)
                canv.drawCentredString(width / 2, bottom, pdfkit.smarten(opts.copyright))
                canv.restoreState()
            return
        canv.saveState()
        canv.setFont(face.italic, 8.5)
        canv.setFillGray(0.25)
        if "nohead" not in flags:
            head = title if side == "verso" else (doc.chapter_title or title)
            y = height - top + 0.32 * inch
            if side == "verso":
                canv.drawString(outer, y, pdfkit.smarten(head))
            else:
                canv.drawRightString(width - outer, y, pdfkit.smarten(head))
        canv.setFont(face.regular, 9)
        canv.drawCentredString(
            (outer + (width - inner)) / 2 if side == "verso" else (inner + (width - outer)) / 2,
            bottom - 0.42 * inch, str(doc.page))
        canv.restoreState()

    doc = BookDoc(str(path), book, opts, face, pagesize=(width, height),
                  title=book.title, author=book.author, creator="lorewrite",
                  initialFontName=face.regular, initialFontSize=BODY)
    # verso (left-hand, even) pages have the wide margin on the right
    full = Frame(outer, bottom, width - 2 * outer, height - top - bottom, id="full",
                 leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[full], onPageEnd=lambda c, d: chrome(c, d, "recto")),
        PageTemplate(id="verso", frames=[frame(outer, inner, "v")],
                     onPageEnd=lambda c, d: chrome(c, d, "verso")),
        PageTemplate(id="recto", frames=[frame(inner, outer, "r")],
                     onPageEnd=lambda c, d: chrome(c, d, "recto")),
    ])
    story = _story(book, opts, st, height - top - bottom, face)
    doc.multiBuild(story)
    return doc.page


LAYOUT = Layout(
    name="book", label="Book",
    description="A typeset trade paperback: title page, contents, chapters on new pages, running heads.",
    page_sizes=("trade", "a5", "letter"), fonts=("noto-serif", "liberation-serif"),
    toc=True, continuous=True, numbering=True, render=render)
