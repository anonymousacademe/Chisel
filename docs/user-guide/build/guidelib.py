"""Typesetting engine for the Lorewrite User's Guide (ReportLab platypus).

A small "manual" toolkit: chapter-page numbering (3-4), roman front matter,
running headers, callouts, captioned tables and figures, a railroad (syntax)
diagram flowable, a table of contents and a back-of-book index. Content lives
in build_guide.py; this file knows nothing about Lorewrite.
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, Image, KeepTogether, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    CondPageBreak, FrameBreak,
)

FONT_DIR = Path("/usr/share/fonts/liberation")
for name, fn in {
    "Body": "LiberationSerif-Regular.ttf",
    "Body-Bold": "LiberationSerif-Bold.ttf",
    "Body-Italic": "LiberationSerif-Italic.ttf",
    "Body-BoldItalic": "LiberationSerif-BoldItalic.ttf",
    "Sans": "LiberationSans-Regular.ttf",
    "Sans-Bold": "LiberationSans-Bold.ttf",
    "Sans-Italic": "LiberationSans-Italic.ttf",
    "Sans-BoldItalic": "LiberationSans-BoldItalic.ttf",
    "Mono": "LiberationMono-Regular.ttf",
    "Mono-Bold": "LiberationMono-Bold.ttf",
    "Mono-Italic": "LiberationMono-Italic.ttf",
    "Mono-BoldItalic": "LiberationMono-BoldItalic.ttf",
}.items():
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / fn)))
for fam in ("Body", "Sans", "Mono"):
    pdfmetrics.registerFontFamily(
        fam, normal=fam, bold=fam + "-Bold", italic=fam + "-Italic",
        boldItalic=fam + "-BoldItalic")

PAGE_W, PAGE_H = letter
LM = RM = 1.25 * inch
TM = 1.15 * inch
BM = 1.0 * inch
TEXT_W = PAGE_W - LM - RM  # 432 pt
INK = colors.HexColor("#111111")
GREY = colors.HexColor("#555555")
LIGHT = colors.HexColor("#999999")
HAIR = colors.HexColor("#BBBBBB")

BOOK_TITLE = "Lorewrite User's Guide and Reference"
DOC_NUMBER = "LW00-0001-2"


def S(name, **kw):
    base = dict(fontName="Body", fontSize=10.5, leading=13.6, textColor=INK,
                alignment=TA_LEFT, spaceAfter=6)
    base.update(kw)
    return ParagraphStyle(name, **base)


ST = {
    "body": S("body"),
    "body_tight": S("body_tight", spaceAfter=3),
    "h1": S("h1", fontName="Sans-Bold", fontSize=23, leading=27, spaceAfter=4),
    "h1_kicker": S("h1_kicker", fontName="Sans", fontSize=11, leading=14,
                   textColor=GREY, spaceAfter=2),
    "h2": S("h2", fontName="Sans-Bold", fontSize=13.5, leading=16.5,
            spaceBefore=16, spaceAfter=6, keepWithNext=1),
    "h3": S("h3", fontName="Sans-Bold", fontSize=10.5, leading=13,
            spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "lead": S("lead", fontSize=11.5, leading=15, spaceAfter=10),
    "caption": S("caption", fontName="Sans-Bold", fontSize=8.8, leading=11,
                 spaceBefore=4, spaceAfter=10),
    "tcaption": S("tcaption", fontName="Sans-Bold", fontSize=8.8, leading=11,
                  spaceBefore=8, spaceAfter=4, keepWithNext=1),
    "tcaption_nk": S("tcaption_nk", fontName="Sans-Bold", fontSize=8.8,
                     leading=11, spaceBefore=8, spaceAfter=4),
    "cell": S("cell", fontSize=9, leading=11.2, spaceAfter=0),
    "cellh": S("cellh", fontName="Sans-Bold", fontSize=8.4, leading=10.5,
               spaceAfter=0),
    "code": S("code", fontName="Mono", fontSize=8.4, leading=10.4,
              spaceAfter=0),
    "note": S("note", leftIndent=22, spaceAfter=8),
    "step": S("step", leftIndent=24, firstLineIndent=0, bulletIndent=4,
              spaceAfter=4, bulletFontName="Body-Bold"),
    "bullet": S("bullet", leftIndent=20, bulletIndent=6, spaceAfter=3),
    "gloss_t": S("gloss_t", fontName="Sans-Bold", fontSize=10, leading=12.5,
                 spaceBefore=3, spaceAfter=1, keepWithNext=1),
    "gloss_d": S("gloss_d", fontSize=10, leading=12.3, leftIndent=16, spaceAfter=1),
    "idx": S("idx", fontSize=8.6, leading=10.1, leftIndent=12, firstLineIndent=-12,
             spaceAfter=0),
    "idx_sub": S("idx_sub", fontSize=8.6, leading=10.1, leftIndent=24,
                 firstLineIndent=-10, spaceAfter=0),
    "idx_letter": S("idx_letter", fontName="Sans-Bold", fontSize=11,
                    leading=13, spaceBefore=8, spaceAfter=2, keepWithNext=1),
    "cover_small": S("cover_small", fontName="Sans", fontSize=9, leading=12,
                     textColor=GREY),
    "notice": S("notice", fontSize=9.5, leading=12.4, spaceAfter=7),
    "notice_h": S("notice_h", fontName="Sans-Bold", fontSize=9.5, leading=12,
                  spaceBefore=6, spaceAfter=3),
}


def roman(n: int) -> str:
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


# -- flowables ----------------------------------------------------------------


class Marker(Flowable):
    """Zero-size flowable carrying data for afterFlowable()."""

    def __init__(self, kind, **data):
        super().__init__()
        self.kind = kind
        self.data = data
        self.width = self.height = 0

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        pass


HOOK = None  # the GuideDoc currently building (set by GuideDoc.__init__)


class IdxP(Paragraph):
    """Paragraph that records index terms / a contents entry when it is
    actually drawn, so page labels are exact even when text moves pages."""

    def __init__(self, text, style, *a, idx=(), toc=None, **kw):
        super().__init__(text, style, *a, **kw)
        self.idx = list(idx)
        self.toc = toc

    def split(self, aw, ah):
        parts = super().split(aw, ah)
        if len(parts) == 2:
            for p in parts:
                p.idx, p.toc = [], None
            parts[0].idx, parts[0].toc = self.idx, self.toc
        return parts

    def draw(self):
        super().draw()
        if HOOK is not None and (self.idx or self.toc):
            HOOK.record(self.idx, self.toc)
            self.idx, self.toc = [], None


class TocLine(Flowable):
    """Contents line: text, dotted leader, page label."""

    def __init__(self, level, text, label, num=""):
        super().__init__()
        self.level, self.text, self.label, self.num = level, text, label, num

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, {0: 15, 1: 12.2, 2: 12.2}[self.level] + (3 if self.level == 0 else 0)

    def draw(self):
        c = self.canv
        lvl = self.level
        font, size = ("Sans-Bold", 10) if lvl == 0 else ("Body", 10)
        x = {0: 0, 1: 30, 2: 30}[lvl]
        y = 2
        label_w = stringWidth(self.label, "Body", 10)
        c.setFont(font, size)
        c.setFillColor(INK)
        text = self.text
        if self.num:
            c.drawString(0, y, self.num)
            x = 70
        c.drawString(x, y, text)
        tw = stringWidth(text, font, size)
        c.setFont("Body", 10)
        c.drawRightString(self.aw, y, self.label)
        dots_x0 = x + tw + 6
        dots_x1 = self.aw - label_w - 6
        dot_w = stringWidth(". ", "Body", 10)
        if dots_x1 > dots_x0 + dot_w:
            n = int((dots_x1 - dots_x0) / dot_w)
            c.setFillColor(GREY)
            c.drawString(dots_x1 - n * dot_w, y, ". " * n)


class Rule(Flowable):
    def __init__(self, thick=0.7, color=INK, space_before=0, space_after=0):
        super().__init__()
        self.t, self.color = thick, color
        self.sb, self.sa = space_before, space_after

    def wrap(self, aw, ah):
        self.aw = aw
        return aw, self.t + self.sb + self.sa

    def draw(self):
        c = self.canv
        c.setStrokeColor(self.color)
        c.setLineWidth(self.t)
        c.line(0, self.sa, self.aw, self.sa)


class Railroad(Flowable):
    """Syntax (railroad) diagram in the classic IBM style.

    items: list of str (keyword, bold mono), ('var', str) (italic),
    ('opt', [items]) (optional: drawn on a lower track, main line bypasses)
    """

    FS = 10
    PAD = 10
    ROW = 26

    def __init__(self, items, label=None):
        super().__init__()
        self.items = items
        self.label = label

    def _w(self, it):
        if isinstance(it, str):
            return stringWidth(it, "Mono-Bold", self.FS)
        kind, val = it
        if kind == "var":
            return stringWidth(val, "Mono-Italic", self.FS)
        if kind == "opt":
            return sum(self._w(i) + self.PAD for i in val) + 2 * self.PAD
        raise ValueError(kind)

    def wrap(self, aw, ah):
        self.aw = aw
        self.h = self.ROW * 2 + 14
        return aw, self.h

    def _text(self, c, it, x, y):
        if isinstance(it, str):
            c.setFont("Mono-Bold", self.FS)
            c.drawString(x, y - 3.5, it)
        else:
            c.setFont("Mono-Italic", self.FS)
            c.drawString(x, y - 3.5, it[1])

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setFillColor(INK)
        c.setLineWidth(0.9)
        y = self.h - 18            # main track
        y2 = y - self.ROW          # optional track
        x = 0
        # start arrows  >>--
        for dx in (0, 7):
            p = c.beginPath()
            p.moveTo(x + dx, y + 3.5)
            p.lineTo(x + dx + 6, y)
            p.lineTo(x + dx, y - 3.5)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
        x += 20
        c.line(x - 6, y, x + self.PAD, y)
        x += self.PAD
        for it in self.items:
            if isinstance(it, tuple) and it[0] == "opt":
                inner = it[1]
                w = self._w(it)
                # main track bypass
                c.line(x, y, x + w, y)
                # drop / rise
                c.line(x + 4, y, x + 4, y2)
                c.line(x + w - 4, y2, x + w - 4, y)
                ix = x + 4
                c.line(ix, y2, ix + self.PAD, y2)
                ix += self.PAD
                for sub in inner:
                    sw = self._w(sub)
                    self._text(c, sub, ix + 2, y2)
                    ix += sw + 4
                    c.line(ix, y2, ix + self.PAD - 4, y2)
                    ix += self.PAD - 4
                c.line(ix, y2, x + w - 4, y2)
                # tiny arrowhead on the return
                x += w
                c.line(x, y, x + self.PAD, y)
                x += self.PAD
            else:
                w = self._w(it)
                self._text(c, it, x, y)
                x += w
                c.line(x, y, x + self.PAD, y)
                x += self.PAD
        # end marker  --><
        c.line(x, y, x + 8, y)
        p = c.beginPath()
        p.moveTo(x + 8, y + 3.5)
        p.lineTo(x + 14, y)
        p.lineTo(x + 8, y - 3.5)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        p = c.beginPath()
        p.moveTo(x + 22, y + 3.5)
        p.lineTo(x + 16, y)
        p.lineTo(x + 22, y - 3.5)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.setLineWidth(1.2)
        c.line(x + 23.5, y + 4, x + 23.5, y - 4)


class Ruled(Flowable):
    """Wraps a flowable in a thin ruled box with padding (for figures).

    The box may be wider than the text frame (wide screens overhang the
    margins symmetrically); the frame is told the frame width only.
    """

    def __init__(self, inner, pad=6, lw=0.7, fit=False):
        super().__init__()
        self.inner, self.pad, self.lw, self.fit = inner, pad, lw, fit

    def wrap(self, aw, ah):
        iw, ih = self.inner.wrap(aw - 2 * self.pad if self.fit else 10 ** 6, ah)
        if self.fit:
            iw = aw - 2 * self.pad
        self.iw, self.ih = iw, ih
        self.aw = aw
        self.bw = iw + 2 * self.pad
        self.height = ih + 2 * self.pad
        return aw, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(self.lw)
        x0 = (self.aw - self.bw) / 2
        c.rect(x0, 0, self.bw, self.height, stroke=1, fill=0)
        self.inner.drawOn(c, x0 + self.pad, self.pad)


# -- document ------------------------------------------------------------------


class GuideDoc(BaseDocTemplate):
    def __init__(self, path, state, **kw):
        super().__init__(path, pagesize=letter, leftMargin=LM, rightMargin=RM,
                         topMargin=TM, bottomMargin=BM,
                         title="Lorewrite User's Guide and Reference",
                         author="Lorewrite Publications",
                         subject="Version 0.2.0", **kw)
        global HOOK
        HOOK = self
        self.st = state           # shared across passes
        self.mode = "cover"       # cover | front | body | back
        self.chap_prefix = ""
        self.chap_title = ""
        self.chap_start = 1
        self.seen_toc = []
        self.seen_idx = []
        body = Frame(LM, BM, TEXT_W, PAGE_H - TM - BM, id="body",
                     leftPadding=0, rightPadding=0, topPadding=0,
                     bottomPadding=0)
        gap = 22
        cw = (TEXT_W - gap) / 2
        col1 = Frame(LM, BM, cw, PAGE_H - TM - BM, id="c1", leftPadding=0,
                     rightPadding=0, topPadding=0, bottomPadding=0)
        col2 = Frame(LM + cw + gap, BM, cw, PAGE_H - TM - BM, id="c2",
                     leftPadding=0, rightPadding=0, topPadding=0,
                     bottomPadding=0)
        cover = Frame(LM, BM, TEXT_W, PAGE_H - TM - BM, id="cover")
        top_h = 1.55 * inch
        col_h = PAGE_H - TM - BM - top_h
        top = Frame(LM, BM + col_h, TEXT_W, top_h, id="idxtop", leftPadding=0,
                    rightPadding=0, topPadding=0, bottomPadding=0)
        f1 = Frame(LM, BM, cw, col_h, id="f1", leftPadding=0, rightPadding=0,
                   topPadding=0, bottomPadding=0)
        f2 = Frame(LM + cw + gap, BM, cw, col_h, id="f2", leftPadding=0,
                   rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate("cover", [cover], onPage=self.draw_cover),
            PageTemplate("plain", [body], onPageEnd=self.draw_chrome),
            PageTemplate("twocol", [col1, col2], onPageEnd=self.draw_chrome),
            PageTemplate("idxfirst", [top, f1, f2], onPageEnd=self.draw_chrome),
        ])

    # label of the current page
    def page_label(self):
        p = self.page
        if self.mode in ("front", "cover"):
            return roman(p)
        return f"{self.chap_prefix}-{p - self.chap_start + 1}"

    def record(self, idx, toc):
        label = self.page_label()
        for term, sub in idx:
            self.seen_idx.append((term, sub, label))
        if toc:
            self.seen_toc.append((1, toc, label, ""))

    def afterFlowable(self, fl):
        if not isinstance(fl, Marker):
            return
        k, d = fl.kind, fl.data
        if k == "chapter":
            self.mode = d.get("mode", "body")
            self.chap_prefix = d["prefix"]
            self.chap_title = d["title"]
            self.chap_start = self.page
            self.seen_toc.append((0, d["title"], self.page_label(),
                                  d.get("num", "")))
        elif k == "front":
            self.mode = "front"
            self.chap_title = d["title"]
            if d.get("toc", True):
                self.seen_toc.append((0, d["title"], self.page_label(), ""))
        elif k == "label":
            self.st["labels"][d["key"]] = self.page_label()

    def draw_cover(self, c, doc):
        pass

    def draw_chrome(self, c, doc):
        if self.mode == "cover":
            return
        p = self.page
        right_hand = p % 2 == 1
        label = self.page_label()
        c.saveState()
        c.setStrokeColor(INK)
        c.setLineWidth(0.5)
        # header
        y = PAGE_H - 0.72 * inch
        c.setFont("Sans", 8.2)
        c.setFillColor(GREY)
        chap = self.chap_title
        if self.chap_prefix and self.mode == "body" and self.chap_prefix.isdigit():
            chap = f"Chapter {self.chap_prefix}. {chap}"
        elif self.chap_prefix and self.mode == "body" and len(self.chap_prefix) == 1 \
                and self.chap_prefix.isalpha() and self.chap_prefix not in "GX":
            chap = f"Appendix {self.chap_prefix}. {chap}"
        if right_hand:
            c.drawString(LM, y, BOOK_TITLE)
            c.drawRightString(PAGE_W - RM, y, chap)
        else:
            c.drawString(LM, y, chap)
            c.drawRightString(PAGE_W - RM, y, BOOK_TITLE)
        c.line(LM, y - 5, PAGE_W - RM, y - 5)
        # footer
        fy = 0.62 * inch
        c.line(LM, fy + 14, PAGE_W - RM, fy + 14)
        c.setFont("Sans-Bold", 9.5)
        c.setFillColor(INK)
        c.setFont("Sans", 7.5)
        c.setFillColor(GREY)
        if right_hand:
            c.drawString(LM, fy, DOC_NUMBER)
            c.setFont("Sans-Bold", 9.5)
            c.setFillColor(INK)
            c.drawRightString(PAGE_W - RM, fy, label)
        else:
            c.setFont("Sans-Bold", 9.5)
            c.setFillColor(INK)
            c.drawString(LM, fy, label)
            c.setFont("Sans", 7.5)
            c.setFillColor(GREY)
            c.drawRightString(PAGE_W - RM, fy, DOC_NUMBER)
        c.restoreState()
