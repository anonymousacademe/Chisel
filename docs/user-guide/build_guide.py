#!/usr/bin/env python3
"""Build docs/user-guide/lorewrite-users-guide.pdf.

    python3 docs/user-guide/build_guide.py            # use captured screens
    python3 docs/user-guide/build_guide.py --capture  # re-capture screens first
                                                      # (terminal: Textual Pilot; desktop: headless Chromium)

Uses the system python3 (ReportLab + Pillow). Screens are captured headlessly
with the project venv (Textual Pilot) by build/capture.py, against a COPY of
the demo project and canned AI results; nothing touches the network.

Two-plus-pass build: pass 1 collects page labels for the contents, index and
cross-references; later passes typeset them until the layout is stable.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "build"))

from PIL import Image  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    CondPageBreak, Flowable, FrameBreak, KeepTogether, NextPageTemplate,
    PageBreak, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus import Image as RLImage  # noqa: E402

sys.path.insert(0, str(HERE / "build" / "chapters"))
import ch_aids, ch_export, ch_history, ch_inspiration, ch_notes, ch_organize  # noqa: E402
NEW_CHAPTERS = [ch_organize, ch_history, ch_notes, ch_aids, ch_inspiration, ch_export]


def palette_rows():
    """The palette's Action entries, read from the program's own table
    (src/lorewrite/tui/commands.py) so the book cannot drift from it."""
    import ast
    src = (HERE.parents[1] / "src" / "lorewrite" / "tui" / "commands.py").read_text()
    actions, category = None, {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "ACTIONS":
                actions = ast.literal_eval(node.value)
            elif node.targets[0].id == "CATEGORY":
                category = ast.literal_eval(node.value)
    keys = {"New scene": "ctrl+n", "Next scene": "alt+right",
            "Previous scene": "alt+left", "Writer mode": "f11",
            "Find aliases in this scene": "ctrl+l",
            "AI write at cursor / expand / rewrite selection": "ctrl+g",
            "Accept all AI drafts in this scene": "f7 (one)",
            "Reject all AI drafts in this scene": "f8 (one)",
            "Toggle spell check": "f6 fixes", "Rebuild index": "f9"}
    rows = []
    for title, method, help_text in actions:
        entry = f"{category[method]} · {title}" if method in category else title
        rows.append([entry, help_text.replace(" (ctrl+l)", "").replace(" (ctrl+g)", "")
                     .replace(" (f11)", "").replace(" (alt+right)", "")
                     .replace(" (alt+left)", ""), keys.get(title, "")])
    return rows


def extra(attr, key=None):
    """Rows the new chapter modules add to a shared table (Appendix B, palette, problems)."""
    rows = []
    for m in NEW_CHAPTERS:
        v = getattr(m, attr)
        rows += v[key] if key else v
    return rows


import guidelib as gl  # noqa: E402
from guidelib import (  # noqa: E402
    GREY, HAIR, INK, LIGHT, ST, TEXT_W, GuideDoc, Marker, Railroad, Rule,
    Ruled, TocLine, IdxP,
)

OUT = HERE / "lorewrite-users-guide.pdf"
SHOTS = HERE / "build" / "shots"
FIGS = HERE / "build" / "fig"
VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# inline markup:  `mono`   **bold**   //italic//
# ---------------------------------------------------------------------------


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def T(s: str) -> str:
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r'<font name="Mono" size="9.4">\1</font>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![:\w])//(.+?)(?<!:)//", r"<i>\1</i>", s)
    return s


class Story:
    """Collects flowables and tracks chapter/figure/table numbering."""

    def __init__(self, st):
        self.st = st
        self.f: list = []
        self.prefix = ""
        self.fig_n = 0
        self.tbl_n = 0
        self.first_in_chapter = True
        self.pending = []

    def _P(self, text, style, toc=None, **kw):
        para = IdxP(text, style, idx=self.pending, toc=toc, **kw)
        self.pending = []
        return para

    def add(self, *fl):
        self.f.extend(fl)

    # -- structure
    def front(self, title, toc=True, new_page=True):
        if new_page:
            self.add(PageBreak())
        self.add(Marker("front", title=title, toc=toc),
                 Paragraph(T(title), ST["h1"]), Rule(1.2, INK, 2, 10))

    def chapter(self, prefix, title, kicker=None, mode="body", numbered=True,
                new_page=True):
        self.prefix = prefix
        self.fig_n = 0
        self.tbl_n = 0
        num = ""
        if numbered:
            kind = "Chapter" if prefix.isdigit() else "Appendix"
            num = f"{kind} {prefix}."
        if new_page:
            self.add(NextPageTemplate("plain"), PageBreak())
        self.add(Marker("chapter", prefix=prefix, title=title, num=num,
                        mode=mode))
        self.add(Spacer(1, 26))
        if numbered:
            self.add(Paragraph(f"{kind} {prefix}", ST["h1_kicker"]))
        self.add(Paragraph(T(title), ST["h1"]), Rule(1.4, INK, 2, 12))
        if kicker:
            self.add(Paragraph(T(kicker), ST["lead"]))

    def h2(self, title, idx=()):
        for t in idx:
            self.idx(t)
        self.add(CondPageBreak(90),
                 self._P(T(title), ST["h2"], toc=title))

    def h3(self, title, idx=()):
        for t in idx:
            self.idx(t)
        self.add(self._P(T(title), ST["h3"]))

    def idx(self, term):
        term, _, sub = term.partition("|")
        self.pending.append((term.strip(), sub.strip() or None))

    # -- text
    def p(self, text, idx=(), style="body"):
        for t in idx:
            self.idx(t)
        self.add(self._P(T(text), ST[style]))

    def bullets(self, items, idx=()):
        for t in idx:
            self.idx(t)
        for it in items:
            self.add(Paragraph(T(it), ST["bullet"], bulletText="•"))
        self.add(Spacer(1, 4))

    def proc(self, lead, steps, idx=()):
        for t in idx:
            self.idx(t)
        self.add(self._P(f"<b>{T(lead)}</b>", ST["body_tight_k"]))
        for i, s in enumerate(steps, 1):
            self.add(Paragraph(T(s), ST["step"], bulletText=f"{i}."))
        self.add(Spacer(1, 5))

    def note(self, text, idx=()):
        for t in idx:
            self.idx(t)
        self.add(self._P(f"<b>Note:</b>&nbsp; {T(text)}", ST["note"]))

    def attention(self, text, idx=()):
        for t in idx:
            self.idx(t)
        para = self._P(f"<b>Attention:</b>&nbsp; {T(text)}", ST["cell"])
        tb = Table([[para]], colWidths=[TEXT_W - 22])
        tb.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.9, INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        tb.hAlign = "RIGHT"
        self.add(tb, Spacer(1, 9))

    def code(self, text, width_chars=78):
        lines = text.rstrip("\n").split("\n")
        for ln in lines:
            assert len(ln) <= width_chars, f"code line too long ({len(ln)}): {ln}"
        from reportlab.platypus import Preformatted
        pre = Preformatted("\n".join(lines), ST["code"])
        tb = Table([[pre]], colWidths=[TEXT_W - 22])
        tb.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 0.6, GREY),
            ("LINEBELOW", (0, -1), (-1, -1), 0.6, GREY),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        tb.hAlign = "RIGHT"
        self.add(tb, Spacer(1, 8))

    # -- tables & figures
    def _num(self, kind):
        if kind == "Figure":
            self.fig_n += 1
            return f"Figure {self.prefix}-{self.fig_n}"
        self.tbl_n += 1
        return f"Table {self.prefix}-{self.tbl_n}"

    def table(self, key, caption, header, rows, widths, mono_cols=(),
              keep=False):
        num = self._num("Table") if caption else None
        if key and num:
            assert key not in self.st["refs"], f"duplicate reference key {key}"
            self.st["refs"][key] = num
        head = [Paragraph(T(h), ST["cellh"]) for h in header]
        body = []
        for r in rows:
            cells = []
            for i, c in enumerate(r):
                if i in mono_cols and c and "`" not in c:
                    c = f"`{c}`"
                cells.append(Paragraph(T(c), ST["cell"]))
            body.append(cells)
        tb = Table([head] + body, colWidths=[w * TEXT_W for w in widths],
                   repeatRows=1)
        tb.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1.1, INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
            ("LINEBELOW", (0, -1), (-1, -1), 1.1, INK),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, HAIR),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
        ]))
        out = []
        if caption:
            cap_style = "tcaption" if len(rows) <= 12 else "tcaption_nk"
            out.append(Paragraph(f"{num}. {T(caption)}", ST[cap_style]))
        out.append(tb)
        out.append(Spacer(1, 10))
        if keep:
            self.add(KeepTogether(out))
        else:
            self.add(*out)

    def figure(self, key, shot, caption, width=None):
        num = self._num("Figure")
        assert key not in self.st["refs"], f"duplicate reference key {key}"
        self.st["refs"][key] = num
        img = fig_image(shot)
        box = Ruled(img, pad=5)
        cap = Paragraph(f"{num}. {T(caption)}", ST["caption"])
        self.add(KeepTogether([Spacer(1, 4), box, cap]))

    def gfigure(self, key, shot, caption, width=None, scale=None, crop=None):
        """A figure of the desktop application (a grayscale screenshot)."""
        num = self._num("Figure")
        assert key not in self.st["refs"], f"duplicate reference key {key}"
        self.st["refs"][key] = num
        img = gui_image(shot, width=width, scale=scale, crop=crop)
        box = Ruled(img, pad=5)
        cap = Paragraph(f"{num}. {T(caption)}", ST["caption"])
        self.add(KeepTogether([Spacer(1, 4), box, cap]))

    def figure_flow(self, key, flow, caption):
        num = self._num("Figure")
        self.st["refs"][key] = num
        cap = Paragraph(f"{num}. {T(caption)}", ST["caption"])
        self.add(KeepTogether([Spacer(1, 4), Ruled(flow, pad=8, fit=True), cap]))

    def ref(self, key):
        return self.st["prev_refs"].get(key, "??")


ST["body_tight_k"] = ST["body_tight"].clone("body_tight_k", keepWithNext=1)
PT_PER_COL = 4.75           # every screen is drawn at the same scale
CROP_OVERRIDES = {
    "palette": [0, 0, 100, 19], "palette_search": [0, 0, 100, 19],
    "filter": [0, 0, 30, 13],             # just the sidebar
    "afterlink": [27, 0, 64, 24],         # just the editor
    "entitynote": [27, 0, 64, 26],
    "main_scene1": [27, 0, 64, 21],
    "expand_marker": [27, 0, 64, 18],
    "expand_draft": [27, 0, 64, 31],
    "rewrite_draft": [27, 0, 64, 31],
    "styleguide": [27, 0, 64, 31],
    "aliasnote": [27, 0, 64, 20],
    "spell_underline": [27, 0, 64, 24],
    "tui_statusbar": [0, 29, 124, 32],
}


def fig_image(shot: str, width=None):
    """Crop terminal window chrome (and, for dialogs, everything but the
    dialog), convert to grayscale, embed at a constant points-per-column."""
    import json
    FIGS.mkdir(parents=True, exist_ok=True)
    dst = FIGS / f"{shot}.png"
    src = SHOTS / f"{shot}.png"
    meta = json.loads((SHOTS / "crops.json").read_text())[shot]
    cols, rows = meta["cols"], meta["rows"]
    box = CROP_OVERRIDES.get(shot)
    if box is None and meta["box"]:      # undo the 1-cell margin from capture
        b = meta["box"]
        box = [b[0] + 1, b[1] + 1, b[2] - 1, b[3] - 1]
    box = box or [0, 0, cols, rows]
    im = Image.open(src).convert("L")
    w, h = im.size
    im = im.crop((3, 68, w - 3, h - 3))      # terminal window chrome
    cw = im.width / cols
    rh = im.height / rows
    x0, y0, x1, y1 = box
    im = im.crop((round(x0 * cw), round(y0 * rh), round(x1 * cw),
                  round(y1 * rh)))
    pts_w = min((x1 - x0) * PT_PER_COL, 418)   # a wide screen is shrunk to the page
    px_w = min(im.width, round(pts_w * 4))     # ~288 dpi is plenty
    im = im.resize((px_w, round(im.height * px_w / im.width)), Image.LANCZOS)
    im.save(dst, optimize=True)
    pts_h = pts_w * im.height / im.width
    return RLImage(str(dst), width=pts_w, height=pts_h)


GUISHOTS = HERE / "build" / "guishots"
PT_PER_CSS_PX = 0.52      # desktop figures: one CSS pixel of the window, in points
MAX_FIG_W = 418


def gui_image(shot: str, width=None, scale=None, crop=None):
    """A desktop-application screenshot (captured at 2x) as a grayscale
    figure. Without *width* it is drawn at a constant scale, so type is the
    same size in every figure; wide shots are limited to the page."""
    from PIL import ImageOps
    FIGS.mkdir(parents=True, exist_ok=True)
    src = GUISHOTS / f"{shot}.png"
    if not src.exists():
        src = HERE / "build" / "exportshots" / f"{shot}.png"
    dst = FIGS / f"g_{shot}.png"
    im = Image.open(src).convert("L")
    if crop:        # (left, right[, top, bottom]) as fractions of the size
        t, b = (crop[2], crop[3]) if len(crop) == 4 else (0, 1)
        im = im.crop((round(crop[0] * im.width), round(t * im.height),
                      round(crop[1] * im.width), round(b * im.height)))
    im = ImageOps.autocontrast(im, cutoff=0.5)
    css_w = im.width / 2
    pts_w = width if width else min(MAX_FIG_W, css_w * (scale or PT_PER_CSS_PX))
    px_w = min(im.width, round(pts_w * 4))
    im = im.resize((px_w, round(im.height * px_w / im.width)), Image.LANCZOS)
    im.save(dst, optimize=True)
    return RLImage(str(dst), width=pts_w, height=pts_w * im.height / im.width)


class Cover(Flowable):
    def wrap(self, aw, ah):
        self.aw, self.ah = aw, ah
        return aw, ah - 2

    def draw(self):
        c = self.canv
        w, h = self.aw, self.ah
        c.setFillColor(INK)
        c.setStrokeColor(INK)
        # document number, top left
        c.setFont("Sans", 9)
        c.setFillColor(GREY)
        c.drawString(0, h - 4, gl.DOC_NUMBER)
        c.setFont("Sans-Bold", 9)
        c.drawRightString(w, h - 4, "Fifth Edition")
        c.setStrokeColor(INK)
        c.setLineWidth(3)
        c.line(0, h - 22, w, h - 22)
        c.setLineWidth(0.6)
        c.line(0, h - 27, w, h - 27)
        # title block
        c.setFillColor(INK)
        c.setFont("Sans-Bold", 46)
        c.drawString(0, h * 0.60, "Chisel")
        c.setFont("Sans", 20)
        c.drawString(0, h * 0.60 - 34, "User's Guide and Reference")
        c.setLineWidth(1.4)
        c.line(0, h * 0.60 - 50, 150, h * 0.60 - 50)
        c.setFont("Sans", 14)
        c.setFillColor(GREY)
        c.drawString(0, h * 0.60 - 78, f"Version 0.2")
        # bottom
        c.setFillColor(INK)
        c.setLineWidth(0.6)
        c.line(0, 74, w, 74)
        c.setFont("Sans", 9)
        c.setFillColor(GREY)
        c.drawString(0, 58, "A fiction-writing application: terminal and desktop")
        c.drawString(0, 45, "Plain text · Wiki-style links · AI that suggests, "
                            "never edits")
        c.setFont("Sans-Bold", 9)
        c.setFillColor(INK)
        c.drawRightString(w, 58, "Lorewrite Publications")
        c.setFont("Sans", 9)
        c.setFillColor(GREY)
        c.drawRightString(w, 45, "October 2026")


# ---------------------------------------------------------------------------
# content
# ---------------------------------------------------------------------------


def build_story(st) -> list:
    s = Story(st)
    R = s.ref

    # ------------------------------------------------------------ cover
    s.add(Cover(), NextPageTemplate("plain"))

    # ------------------------------------------------------------ notice
    s.front("Edition Notice", toc=False)
    s.p("**Fifth Edition (October 2026)**", style="notice")
    s.p("This edition replaces and makes obsolete the Fourth Edition, "
        "LW00-0001-3.", style="notice")
    s.p("This edition applies to Version 0.2.0 of Lorewrite, including the "
        "terminal application (`lorewrite`), the desktop application "
        "(`lorewrite-gui`, whose window is titled Chisel), and the "
        "features added to both since the Third Edition: parts, the "
        "Trash and scene details; snapshots, drafts and git sync; "
        "collections, comments, research notes and saved assistant "
        "conversations; session stats, focus sprints and Brainstorm; "
        "export of the book to PDF, Word, EPUB and other formats; and AI "
        "inspiration images. It "
        "applies to all subsequent releases and modifications until "
        "otherwise indicated in new editions. Make sure you are using the "
        "correct edition for the level of the product. The version number "
        "is shown in the title bar of the terminal application's main "
        "window and at the top of its launch screen.",
        style="notice")
    s.p("This book was written for Version 0.2.0, when the program was "
        "called Lorewrite. The program is now called //Chisel//: where the "
        "text says Lorewrite, read Chisel. Commands, folder names and "
        "settings are unchanged (`lorewrite`, `lorewrite-gui`). In the "
        "desktop application, //Unplaced Scenes// is now called //Parked "
        "scenes// (the terminal application and the `_unplaced` folder keep "
        "the old name). Later releases also added: the //About// chip, "
        "which tells the assistant which open item you are asking about; "
        "pictures linked to any item and picture upload; the //What was "
        "sent// report under every AI result; relevance filtering and a "
        "size check before an AI request is sent; and optional story time "
        "(`when:` in scene details, `born:` in a character note). See "
        "CHANGELOG.md in the repository for the full list; a later edition "
        "will describe them in the chapters.",
        style="notice")
    s.p("Changes are made periodically to the information herein. Where this "
        "book and the program disagree, the program is right; please report "
        "the difference so that the next edition can correct it.",
        style="notice")
    s.add(Paragraph("Document Number", ST["notice_h"]))
    s.p(f"{gl.DOC_NUMBER}. The number is a label for this book only.",
        style="notice")
    s.add(Paragraph("Notices", ST["notice_h"]))
    s.p("The example story used in the figures, //Residual//, is fiction; "
        "any resemblance of its characters, companies or places to real ones "
        "is coincidental. All screens in this book were captured from "
        "Version 0.2.0 running against a sample project, the Residual "
        "example that is supplied with Lorewrite. Screens of the terminal "
        "application come from a terminal; screens of the desktop "
        "application come from its interface in a headless browser, "
        "against the same code and the same sample project. The desktop "
        "screens are printed in shades of gray; the application itself is "
        "in color and dark. The results shown "
        "for the AI features were prepared in advance for the sample and "
        "were not obtained from any AI service.", style="notice")
    s.p("Product and company names that appear in this book, such as "
        "OpenRouter and Omarchy, belong to their owners and are mentioned "
        "only to say what Lorewrite works with.", style="notice")
    s.add(Paragraph("Your Comments Are Welcome", ST["notice_h"]))
    s.p("If you find an error in this book, or a place where it fails to "
        "explain something, please tell the maintainers of the project. "
        "Quote the document number and the page label printed at the foot "
        "of the page, for example //3-4//.", style="notice")

    # ------------------------------------------------------------ contents
    s.add(PageBreak(), Marker("front", title="Contents", toc=False),
          Paragraph("Contents", ST["h1"]), Rule(1.2, INK, 2, 10))
    for lvl, text, label, num in st["prev_toc"]:
        s.add(TocLine(lvl, text, label, num))
    if not st["prev_toc"]:
        s.add(Paragraph("(contents are filled in on the second pass)",
                        ST["body"]))

    # ------------------------------------------------------------ about
    s.front("About This Book")
    s.p("This book describes Lorewrite, a program for writing fiction. It "
        "comes in two forms that work on the same files: a //terminal "
        "application//, started with `lorewrite`, and a //desktop "
        "application//, started with `lorewrite-gui`, whose window is "
        "titled Chisel. The book explains what Lorewrite does, how to "
        "install and start it, how to write and organize scenes, how to "
        "keep track of your characters and places, how to keep a history "
        "of your work, how to check your spelling, how to use its optional "
        "AI assistance, and where every key, menu entry and setting is. It "
        "is both a guide, which you can read from the front, and a "
        "reference, which you can look things up in.")
    s.h2("Who Should Read This Book")
    s.p("This book is for people who write stories, not for programmers. "
        "You do not need to know how Lorewrite works inside. You should be "
        "comfortable opening a terminal window and typing a command, and "
        "you should know what a folder and a file are. Everything else is "
        "explained where it first matters. A small amount of technical "
        "material (installation, file formats) is kept in Chapter 2 and in "
        "the appendixes so that it stays out of your way.")
    s.h2("How This Book Is Organized")
    s.p("The chapters are meant to be read in order the first time. The "
        "appendixes and the index are for looking things up. Where a "
        "feature exists in both applications, its chapter describes both: "
        "the keys of the terminal application and the controls of the "
        "desktop application, side by side.")
    s.bullets([
        "**Chapter 1, Introducing Lorewrite**, explains the ideas the "
        "program is built on: projects, scenes, entities, mentions, links "
        "and backlinks, and the rule that AI only suggests.",
        "**Chapter 2, Installing and Starting**, tells you how to install "
        "Lorewrite, start either application, open or create a project, "
        "and what happens the first time you run it.",
        "**Chapter 3, The Desktop Application**, tours the window of "
        "`lorewrite-gui`: the binder, the editor, the assistant, the status "
        "bar and the dialogs.",
        "**Chapter 4, Writing Scenes**, covers the editor, saving, the "
        "status bar, writer mode, and creating, renaming, reordering and "
        "deleting scenes.",
        "**Chapter 5, Organizing the Manuscript**, covers parts and front "
        "matter, unplaced scenes, the Trash, scene details, chapter labels, "
        "dragging scenes into order, and collections.",
        "**Chapter 6, Characters, Places and Mentions**, explains how to "
        "make notes for your characters and places and how Lorewrite "
        "recognizes them in your text.",
        "**Chapter 7, Spelling**, describes the spell checker, what it "
        "never flags, and the two dictionaries you can teach it.",
        "**Chapter 8, History and Versions**, describes snapshots, the "
        "draft counter, and the optional git sync.",
        "**Chapter 9, Notes, Comments and Research**, describes comments "
        "on passages, research notes, and the assistant's saved "
        "conversations.",
        "**Chapter 10, AI Assistance**, describes how to set up an AI "
        "service and the three features that keep your story consistent: "
        "finding aliases, continuity checks and story-bible updates, "
        "with what they cost and send.",
        "**Chapter 11, Writing with AI**, describes the features that "
        "write: the style guide, drafting at the cursor, expanding "
        "placeholders, rewriting a selection, and reviewing pending AI "
        "text.",
        "**Chapter 12, Writing Aids**, describes your session stats, the "
        "streak and daily target, focus sprints and Brainstorm.",
        "**Chapter 13, Inspiration Images**, describes the reference "
        "pictures you can have made from a description of a scene.",
        "**Chapter 14, Exporting Your Book**, describes how to turn the "
        "manuscript into a typeset PDF, a Word file, an EPUB and other "
        "formats.",
        "**Chapter 15, Settings Reference**, lists every setting, where it "
        "is stored, and its default.",
        "**Chapter 16, Command and Key Reference**, lists every key and "
        "every entry in the command palette and the desktop application's "
        "menus.",
        "**Appendix A, File Formats**, shows what is in your project folder "
        "and describes every file Lorewrite reads and writes.",
        "**Appendix B, Messages and Problem Solving**, lists the messages "
        "the programs show and what to do about them.",
        "**Appendix C, Tutorial**, walks through the sample project, in "
        "the terminal application and in the desktop application.",
        "The **Glossary** defines the terms used in this book, and the "
        "**Index** helps you find things.",
    ])
    s.h2("Typographic Conventions")
    s.p("This book uses the following conventions.")
    s.table(None, None, ["Convention", "Meaning", "Example"], [
        ["Monospace type", "Keys you press, text you type, file and folder "
         "names, and text shown exactly as it appears on the screen.",
         "`ctrl+j`, `project.toml`"],
        ["**Bold type**", "Names of buttons, dialogs, menu items and "
         "screens.", "Press **Save**."],
        ["//Italic type//", "A term being defined, a title, or a value you "
         "replace with your own.", "//scene//, //PATH//"],
        ["`ctrl+j`", "Press and hold the first key, then press the second. "
         "Keys are written the way Lorewrite writes them on its own help "
         "screen.", "`ctrl+s` saves"],
        ["`alt+left`", "The Alt key together with the left arrow key. "
         "`alt+right` is the right arrow.", ""],
        ["**Action · Name**", "A command in the terminal application's "
         "command palette (`ctrl+p`). Some entries begin **Scene ·** "
         "(**Chapter ·** when the manuscript's unit is chapters) or "
         "**Research ·**.", "**Action · New scene**"],
        ["**Menu \u203a Item**", "An entry of a menu in the desktop "
         "application, reached from the button named first.",
         "**AI menu \u203a Find aliases**"],
        ["**Note:**", "Information that is useful but not essential.", ""],
        ["**Attention:**", "Something that can lose work or surprise you if "
         "you overlook it.", ""],
    ], [0.20, 0.55, 0.25])
    s.p("Screens are shown as figures with a ruled border. Procedures are "
        "numbered lists; do the steps in order. Tables and figures are "
        "numbered by chapter, so //Figure 4-1// is the first figure in "
        "Chapter 4. Page numbers also carry the chapter: page //6-2// is "
        "the second page of Chapter 6, and //B-1// is the first page of "
        "Appendix B. In figures of the terminal application the colors "
        "depend on your theme; figures of the desktop application are "
        "printed in shades of gray.")
    s.h2("Names and Terms")
    s.p("The program is called Chisel (this edition calls it Lorewrite "
        "in most places; see the Edition Notice); its commands are "
        "`lorewrite` (terminal) and `lorewrite-gui` (desktop). The desktop "
        "window and its assistant call themselves //Chisel//; it is the "
        "same program. A //project// is one book: a folder of plain files. The "
        "Glossary at the back defines the other terms.")

    # ------------------------------------------------------------ changes
    s.front("Summary of Changes")
    s.p("This Fifth Edition (LW00-0001-4) covers Version 0.2.0 of "
        "Lorewrite as it is now on its main line. Two features have been "
        "added to both applications since the Fourth Edition: export of "
        "the book, and AI inspiration images. The changes are listed "
        "below, with the chapter that describes each. Chapter 13 "
        "(Inspiration Images) and Chapter 14 (Exporting Your Book) are "
        "new, and the Fourth Edition's Chapters 13 and 14 (Settings "
        "Reference, Command and Key Reference) are now Chapters 15 and "
        "16. The corrections of the Fourth Edition's second printing are "
        "included.")
    s.table(None, None, ["Change", "Where described"], [
        ["**Export.** The book can be written to `exports/` as a PDF "
         "(Book, Manuscript review or Plain proof layout), a Word file, "
         "an EPUB, one Markdown file or LaTeX source, from the desktop "
         "dialog or the terminal form. Unplaced scenes, the Trash, notes, "
         "comments and scene details are left out; unaccepted AI drafts "
         "are left out unless you ask. Files are never overwritten.",
         "Chapter 14"],
        ["**Inspiration images.** Describe a place (or let the AI describe "
         "the scene you are in) and have a reference picture made, "
         "about $0.03 each, kept in `inspiration/`, pinned to a scene, "
         "shown in a gallery and a large view, and never put into your "
         "prose. A new //Inspiration// tab in the desktop assistant; "
         "palette actions in the terminal.", "Chapter 13"],
        ["**Settings.** A fourth model, the //image model//, and an "
         "//image style// line; the remembered export options in "
         "`[export]` of `project.toml`.", "Chapter 15, Appendix A"],
        ["**Trash.** Inspiration pictures go to the Trash like scenes and "
         "research notes.", "Chapters 5 and 13"],
        ["**Files and folders.** `exports/`, `inspiration/` with a "
         ".md sidecar for each picture, `[export]` and the image model "
         "setting.", "Appendix A"],
        ["**New palette entries, messages and problems; a tutorial "
         "section** that exports the Residual book and makes a picture.",
         "Chapter 16, Appendix B, Appendix C"],
        ["**Corrected after the polish pass** (carried over from the "
         "Fourth Edition's second printing): the restore toast, the "
         "terminal Compare title, one form for word changes, the part "
         "commands, //Call them chapters//, `ctrl+t` for saved "
         "conversations, unplaced scenes and the continuity check.",
         "Chapters 5, 8, 9, 12, 16"],
    ], [0.78, 0.22])

    # ============================================================ CH 1
    s.chapter("1", "Introducing Lorewrite",
              "What Lorewrite is for, and the handful of ideas that "
              "everything else in this book builds on.")
    s.p("Lorewrite is a program for writing novels and other long fiction "
        "at a keyboard. You can use it in a terminal window or in a desktop "
        "window; both work on the same files, so you can switch between "
        "them at will. You write your scenes in a plain editor. As you go, you tell Lorewrite about the people, "
        "places, things and organizations in your story, and it helps you "
        "keep them straight: it shows you where each one appears, lets you "
        "jump to the notes you keep on each, and, if you choose, uses an AI "
        "service to look for slips in continuity.",
        idx=["Lorewrite|purpose"])
    s.p("It is deliberately modest. It does not format your book or "
        "publish it, and it writes only when you ask. It keeps your files "
        "plain, your notes close, and your story consistent.")
    s.h3("Two applications, one project", idx=["terminal application",
                                              "desktop application"])
    s.p("The //terminal application// (`lorewrite`) runs inside a terminal "
        "window and is driven by keys and a command palette. The //desktop "
        "application// (`lorewrite-gui`) is an ordinary window with a "
        "binder of scenes and notes on the left, a page-like editor in the "
        "middle and an assistant panel on the right; it is driven by the "
        "mouse and by keys. Neither one needs the other. Both read and "
        "write the same Markdown files, so a scene you were typing in one "
        "can be opened in the other. If you leave one running while you "
        "edit in the other, each notices changes made behind its back "
        "(Chapters 3 and 4). Chapter 3 describes the desktop window; every "
        "other chapter says what to press in the terminal application and "
        "what to click in the desktop one.")

    s.h2("The Ideas Behind Lorewrite")
    s.h3("Your book is a folder of plain files", idx=["project", "plain text"])
    s.p("A Lorewrite //project// is a folder. Inside it, each //scene// is "
        "an ordinary Markdown text file, and each note on a character or "
        "place is another. There is no hidden database that holds your "
        "writing. You can open the same files in any other editor, copy "
        "them to a memory stick, keep them under version control, or read "
        "them in ten years' time. If Lorewrite disappeared tomorrow, your "
        "book would still be there.")
    s.p("Markdown is a way of marking up plain text with a few simple "
        "conventions. In Lorewrite you need only one: a line that begins "
        "with `# ` (a number sign and a space) is a heading, and the first "
        "such line in a scene is the scene's title.", idx=["Markdown"])
    s.figure_flow("fig_parts", _parts_diagram(),
                  "The parts of a Lorewrite project")
    s.h3("Scenes", idx=["scene"])
    s.p("A //scene// is one file in the project's `manuscript` folder. "
        "Scenes are played in the order of their file names, which start "
        "with a number: `01-rain-on-the-spur.md`, `02-capsule-7-19.md`, and "
        "so on. Lorewrite numbers new scenes for you and renumbers them "
        "when you move one. You can gather scenes into //parts// (a folder "
        "each), keep scenes you have written but not placed in the book "
        "aside, and set details such as the point of view and a word "
        "target on each scene; Chapter 5 describes all of this.")
    s.h3("Entities and notes",
         idx=["entity", "note (entity)", "character", "place", "object",
              "faction"])
    s.p("An //entity// is anything in your story that you want to keep "
        "track of by name. Lorewrite knows four kinds, listed in "
        f"{R('t_types')}. Each entity has a //note//: a small file with a "
        "few lines at the top (its name, its kind and its aliases) and, "
        "below them, whatever you want to write about it.")
    s.table("t_types", "Kinds of entity", ["Kind", "Typical use", "Folder"],
            [["character", "People, creatures, AIs.", "entities/characters"],
             ["place", "Cities, buildings, rooms, regions.",
              "entities/places"],
             ["object", "A sword, a letter, a data shard.",
              "entities/objects"],
             ["faction", "A company, a family, a guild.",
              "entities/factions"]],
            [0.17, 0.53, 0.30], mono_cols=(0, 2))
    s.h3("Aliases and mentions", idx=["alias", "mention"])
    s.p("People are not always called by the same name. Rook Tanaka is "
        "//Rook// to his friends and //Tanaka// to the police. Each note "
        "can list //aliases//, other ways your text refers to the same "
        "entity. Whenever the name or an alias appears in a scene, "
        "Lorewrite recognizes it as a //mention// and colors it so that you "
        "can see, at a glance, that the program knows who or what you mean. "
        "You do not have to type anything special; see Chapter 6.")
    s.h3("Links and backlinks", idx=["link", "backlink"])
    s.p("You may also mark a name explicitly by wrapping it in double "
        "square brackets, like `[[Rook Tanaka]]`. This is a //link//. Links "
        "were how earlier versions of Lorewrite worked; they are now "
        "optional, but they still work and are useful in a few cases "
        "described in Chapter 6.")
    s.p("The other side of a link is a //backlink//. When the cursor is on "
        "a name, Lorewrite shows the note for that entity and lists every "
        "line in your book that mentions it, so that you can jump straight "
        "to any of them.")
    s.h3("History and notes live beside your work",
         idx=["snapshot", "comment", "research note"])
    s.p("Everything else Lorewrite keeps for you is plain files in the same "
        "folder, so it travels with the book. Snapshots of your scenes "
        "(Chapter 8), comments you attach to passages and conversations "
        "with the assistant (Chapter 9) each have a folder of their own, "
        "and your research notes are ordinary Markdown files you may edit "
        "anywhere. Deleting a scene moves it to a Trash folder first. The "
        "only exceptions are your personal numbers (Chapter 12) and your "
        "personal dictionary, which belong to you rather than to a book "
        "and live in Lorewrite's own state folder. Appendix A has a map "
        "of everything in a project folder.")
    s.h3("The index is a cache", idx=["index (cache)", "cache"])
    s.p("To find mentions quickly, Lorewrite keeps a small search index in "
        "a hidden folder inside the project. The index can always be "
        "thrown away and rebuilt from your files (press `f9`). Your files "
        "are the truth; the index is only a convenience.")
    s.h3("AI suggests; you decide", idx=["AI", "suggest-and-confirm"])
    s.p("Lorewrite has optional features that use an AI service. Three "
        "help you keep the story consistent: finding other names your "
        "prose uses for your characters and places, checking a scene "
        "against your notes for contradictions, and proposing new facts "
        "for your notes. Others write: learning your style, drafting new "
        "prose, expanding a placeholder and rewriting a passage. The rule "
        "for all of them is the same: //the AI never changes your prose "
        "on its own//. Its proposals are shown for review, and nothing is "
        "changed until you accept them. Text the AI writes goes into your "
        "scene as a clearly marked //pending draft// that stays marked "
        "until you accept it, and rejecting it puts back exactly what was "
        "there. If you never set up an AI service, Lorewrite works "
        "exactly as described in Chapters 2 to 9 and makes no network "
        "connections while you write.")
    s.attention("Accepting a proposal does change your files: accepted "
                "aliases and canon facts are written into your notes, and "
                "an accepted draft becomes part of your scene. The review "
                "screens and the accept and reject keys are where you stay "
                "in control. Chapters 10 and 11 describe what each one "
                "will do.")

    s.h2("What You Need")
    s.bullets([
        "A computer with Python 3.11 or later and a terminal window "
        "(Chapter 2). For the desktop application, also the WebKitGTK "
        "libraries it draws with (Chapter 2).",
        "For the optional git sync only: git, installed on your computer "
        "(Chapter 8).",
        "For the AI features only: an OpenRouter account and an API key, "
        "and a network connection when you use them (Chapters 10 and 11).",
        "Nothing else. The terminal application runs in a terminal of at "
        "least about 100 columns by 30 rows; larger is more comfortable. "
        "The desktop window asks for 1600 by 1000 pixels and is not "
        "smaller than 1280 by 760.",
    ])

    # ============================================================ CH 2
    s.chapter("2", "Installing and Starting",
              "How to install Lorewrite, start it, and open or create a "
              "project.")
    s.h2("Installing Lorewrite", idx=["installing", "Python"])
    s.p("Lorewrite is a Python program. It needs Python 3.11 or later. It "
        "uses four supporting packages, which the installer fetches for "
        "you: Textual (the terminal interface), PyYAML (for the header of "
        "note files), the OpenAI client library (used to talk to "
        "OpenRouter), and Keyring (to keep your API key safe).")
    s.proc("To install Lorewrite:", [
        "Open a terminal and change to the folder where you keep programs.",
        "Fetch the source: `git clone <repo-url> lorewrite`, where "
        "//repo-url// is the address you were given.",
        "Change into the new folder: `cd lorewrite`.",
        "Create a private Python environment: `python3 -m venv .venv`.",
        "Install: `.venv/bin/pip install -e \".[dev]\"`.",
    ], idx=["virtual environment"])
    s.note("The `[dev]` part also installs the tools used to test the "
           "program. You can leave it out (`.venv/bin/pip install -e .`) "
           "if you only want to write.")
    s.p("The installer places a command named `lorewrite` in "
        "`.venv/bin`. You can run it by its full path, add `.venv/bin` to "
        "your PATH, or make a shell alias.")
    s.h3("Installing the desktop application", idx=["lorewrite-gui command",
                                                   "pywebview"])
    s.p("The desktop application (`lorewrite-gui`) needs a little more: "
        "pywebview, which puts a web page in a native window, and the "
        "WebKitGTK and PyGObject libraries that pywebview draws with, which "
        "come from your operating system, not from Python. Its page is "
        "built once with Node.js (version 20 or later).")
    s.proc("To install the desktop application:", [
        "In the Lorewrite folder, create an environment that can see the "
        "system libraries: `python3 -m venv --system-site-packages "
        ".venv-gui`.",
        "Install: `.venv-gui/bin/pip install -e \".[dev,gui]\"`.",
        "Build the window's pages: `cd gui`, then `npm install`, then "
        "`npm run build`.",
        "Start it with `.venv-gui/bin/lorewrite-gui`.",
    ])
    s.note("If you start `lorewrite-gui` before building the pages, it "
           "stops with //the UI is not built// and tells you to run "
           "`npm install && npm run build` in `gui`. If pywebview is "
           "missing it says so and names the install command.")
    s.p("On the computer this edition was prepared on, both commands are "
        "linked into `~/.local/bin`, so `lorewrite` and `lorewrite-gui` "
        "start by name from any folder. On yours, do the same with `ln -s`, "
        "or put the environment's `bin` folder on your PATH.")

    s.h2("Starting Lorewrite", idx=["lorewrite command", "command line"])
    s.p(f"Start Lorewrite by typing the command name. {R('fig_syntax')} "
        "shows its syntax. Read the diagram from left to right, following "
        "the line. Items on the main line are required; items below the "
        "line are optional. Words in bold type are typed exactly as "
        "shown; words in italic type stand for something you supply.")
    s.figure_flow("fig_syntax", Railroad([
        "lorewrite",
        ("opt", ["--project", ("var", "PATH")]),
        ("opt", ["--new", ("var", "TITLE")]),
    ]), "Syntax of the lorewrite command")
    s.table("t_opts", "Options of the lorewrite command",
            ["Option", "Effect"], [
        ["--project PATH",
         "Open the project in the folder //PATH//. If //PATH// is not a "
         "project (it has no `project.toml`), Lorewrite ignores it and "
         "shows the launch screen."],
        ["--new TITLE",
         "Create a new project called //TITLE// and open it. The project is "
         "made in the folder given by `--project`, or in the current "
         "folder if `--project` is not given."],
        ["-h, --help", "Print a summary of the options and stop."],
    ], [0.24, 0.76], mono_cols=(0,))
    s.p("With no options, Lorewrite shows the launch screen.")
    s.attention("In the terminal application, `--new` creates the project "
                "files directly in the folder named by `--project`, or in "
                "the current folder. Run it from an empty folder, not from "
                "a folder that already holds other files you care about.")
    s.p(f"The desktop application is started the same way, with its own "
        f"command ({R('fig_syntax2')}, {R('t_opts2')}).")
    s.figure_flow("fig_syntax2", Railroad([
        "lorewrite-gui",
        ("opt", ["--project", ("var", "PATH")]),
        ("opt", ["--new", ("var", "TITLE")]),
    ]), "Syntax of the lorewrite-gui command")
    s.table("t_opts2", "Options of the lorewrite-gui command",
            ["Option", "Effect"], [
        ["--project PATH",
         "Open the project in the folder //PATH// at once. If it is not a "
         "project, the launch screen shows."],
        ["--new TITLE",
         "Create a new project called //TITLE// and open it. The folder is "
         "`~/novels/` followed by the title in lowercase with hyphens "
         "(for example `~/novels/the-salt-road`), or the folder given by "
         "`--project`. If the folder cannot be made, the command stops "
         "with the reason."],
        ["--dev URL", "For developers: load the window's pages from a "
         "development server instead of the built ones."],
        ["-h, --help", "Print a summary of the options and stop."],
    ], [0.24, 0.76], mono_cols=(0,))
    s.p("Whichever command you use, the application finds the same list of "
        "recent projects and the same settings (see “Where Lorewrite Keeps "
        "Its Own Settings” below).")

    s.h2("The Launch Screen", idx=["launch screen", "recent projects"])
    s.p(f"When you start Lorewrite without a project, the launch screen "
        f"({R('fig_launch')}) appears. It lists the projects you opened "
        "most recently, the newest first, up to ten. The first one is "
        "already highlighted, so pressing `enter` resumes your last book.")
    s.figure("fig_launch", "launch", "The launch screen")
    s.p("Only projects that still exist are listed. If you choose one "
        "that has since been moved or deleted, Lorewrite removes it from "
        "the list and says that the folder is no longer a project. If you "
        "have not opened anything yet, the list reads //(none yet — press n "
        "to start a novel)//.")
    s.p("The last two lines of the launch screen list its keys; "
        f"{R('t_launchkeys')} lists them with what they do.")
    s.table("t_launchkeys", "Keys on the launch screen",
            ["Key", "Action"], [
        ["up, down", "Move through the list of recent projects."],
        ["enter", "Resume the highlighted project."],
        ["o", "Open a folder: type the path of a project."],
        ["n", "Start a new project."],
        ["s", "Open the Settings screen (Chapter 15)."],
        ["q", "Quit Lorewrite. (If you reached the launch screen with "
         "//Return to main menu//, `q` instead returns to the project you "
         "were in.)"],
    ], [0.20, 0.80], mono_cols=(0,))
    s.h3("Opening a folder", idx=["opening a project"])
    s.p("Press `o`. A box titled //Project folder:// asks for a path. "
        "Type it (a leading `~` stands for your home folder) and press "
        "`enter`. If the folder does not contain a `project.toml` file, "
        "Lorewrite says //No lorewrite project in// followed by the path.")
    s.h3("The launch screen of the desktop application",
         idx=["launch screen|desktop"])
    s.p(f"The desktop application shows its launch screen "
        f"({R('fig_glaunch')}) when it is started without a project. It is "
        "a single card with three sections.")
    s.gfigure("fig_glaunch", "launch", "The launch screen of the desktop "
              "application", width=300)
    s.bullets([
        "**Recent projects.** One button for each of the projects you "
        "opened lately, with its folder under the title. Click one to open "
        "it. A project whose folder has gone is shown with //(missing)// "
        "after its path and cannot be clicked.",
        "**New project.** Type a title. The folder line below fills in "
        "with `~/novels/` and the title in lowercase with hyphens "
        f"({R('fig_glaunch2')}); you may change it. Press `enter` or click "
        "**Create**. If the folder is already a project it is opened, not "
        "overwritten.",
        "**Open an existing project.** Type or paste a folder, or click "
        "**Browse** to choose one, then click **Open project**.",
    ])
    s.gfigure("fig_glaunch2", "launch_new", "Typing a title fills in the "
              "folder", width=300)
    s.p("A message in red under the card says what went wrong if the "
        "project cannot be opened or created, for example //a project "
        "needs a title//.")

    s.h2("Creating a New Project", idx=["new project", "creating a project"])
    s.p("In the desktop application, use the **New project** section "
        "described above. The steps below are for the terminal "
        "application.")
    s.proc("To create a project from the launch screen:", [
        "Press `n`. The **New project** box appears "
        f"({R('fig_newproj')}).",
        "Type a title, for example //The Salt Road//. As you type, the "
        "//Folder// line below fills in with a suggested place: a folder "
        "named after the title inside `novels` in your home folder.",
        "Press `enter` to move to the //Folder// line. Change it if you "
        "want the project somewhere else.",
        "Press `enter` again. Lorewrite creates the project and opens it.",
    ])
    s.figure("fig_newproj", "newproject", "Creating a new project")
    s.p("Both the title and the folder are required; if one is empty, "
        "Lorewrite says //Title and folder are both required//. If the "
        "folder you name is already a Lorewrite project, it is opened "
        "instead of being overwritten. If the folder cannot be created, "
        "you see //Could not create project:// and the reason.")
    s.add(CondPageBreak(150))
    s.p("A new project contains the following. Nothing is ever placed "
        "outside the project folder except the small state files "
        "described under “Where Lorewrite Keeps Its Own Settings.”",
        idx=["project|files created"])
    s.code("""\
the-salt-road/
  project.toml            title = "The Salt Road", author = ""
  .gitignore              contains: .lorewrite/
  manuscript/
    01-opening.md         a short sample scene with a few tips
  entities/               empty folders, one for each kind of note
    characters/  places/  objects/  factions/""")
    s.p("You can create the same thing from the command line with "
        "`lorewrite --new \"The Salt Road\" --project ~/novels/the-salt-road`.")

    s.h2("The First-Run Tour", idx=["tour", "first run"])
    s.p(f"The first time you open a project, a five-page tour appears "
        f"({R('fig_tour')}). Each page explains one idea: that a project "
        "is just files, how writing and saving work, how links work, what "
        "the optional AI writing help does, and how to find things. Press `space`, `enter` or `right` to go to the "
        "next page, `left` to go back, and `esc` to close it at any time. "
        "Pressing `space` on the last page also closes it.")
    s.figure("fig_tour", "tour4", "The first-run tour (page 4 of 5)")
    s.p("The tour belongs to the terminal application; the desktop "
        "application has none. It is shown once. Lorewrite records that you have seen it in "
        "its settings file (`tour_seen`). To see it again, open "
        "`settings.json` in the state folder (see below) and change "
        "`\"tour_seen\": true` to `false`.")

    s.h2("Where Lorewrite Keeps Its Own Settings",
         idx=["state folder", "settings.json", "recent.json"])
    s.p("Apart from your projects, Lorewrite keeps small files in "
        "`~/.local/state/lorewrite`: `recent.json` (the list on the launch "
        "screen), `settings.json` (whether you have seen the tour, your "
        "chosen AI models, whether spelling is underlined, and the desktop "
        "window's text size, your daily word target and whether a snapshot is "
        "taken the first time a scene is edited each day), `stats/` (your "
        "writing numbers, Chapter 12) and, once you have made one, "
        "`dictionary.txt` "
        "(your personal dictionary; Chapter 7). The first two can be "
        "deleted safely; Lorewrite recreates them. Both applications read "
        "and write the same files. If you set the environment variable "
        "`LOREWRITE_STATE_DIR` to a folder, Lorewrite keeps them there "
        "instead. This is handy for trying the program without disturbing "
        "your real settings.")

    s.h2("Omarchy: Theme and Launcher", idx=["Omarchy", "theme"])
    s.p("Lorewrite was designed for the Omarchy Linux desktop, but it runs "
        "anywhere Python and a terminal do. On Omarchy it takes its colors "
        "from your current system theme, so it matches the rest of your "
        "desktop. It reads the name of the current theme and that theme's "
        "color file (a copy in your own `~/.config/omarchy/themes` folder "
        "takes precedence over the stock theme), and uses them for the "
        "interface, for the colors of links and mentions, and for the "
        "orange used for links that have no note. The theme is read when "
        "Lorewrite starts; to pick up a new theme, quit and start it again. "
        "Off Omarchy, Lorewrite uses the terminal toolkit's own built-in "
        "theme, and everything else is unchanged.")
    s.p("The desktop application does not read the Omarchy theme; it has "
        "one dark appearance of its own.")
    s.p("On Omarchy, both applications can be started from the desktop "
        "rather than from a terminal. On the computer this edition was "
        "prepared on, the application menu has an entry named //Chisel// "
        "that starts the desktop application (or, if its window is already "
        "open, brings that window to the front instead of opening a second "
        "copy), and the top-bar pencil button does the same on a left "
        "click; a right click starts the terminal application. These "
        "launchers are set up through Omarchy, not by Lorewrite; see the "
        "Omarchy documentation for the steps on your system. The entry is "
        "an ordinary desktop file that runs `lorewrite-gui`.",
        idx=["launcher"])

    s.h2("Leaving Lorewrite", idx=["quitting", "ctrl+q"])
    s.p("In the terminal application, press `ctrl+q`. Lorewrite saves the "
        "scene you are working on as it closes, so there is nothing to save "
        "first.")
    s.p("In the desktop application, click the red dot at the left of the "
        "title bar, or close the window with your window manager. The "
        "application saves a moment after you stop typing and whenever the "
        "window loses focus, so closing it does not lose work; if you want "
        "to be sure, press `ctrl+s` first and wait for the title bar to say "
        "//Saved//.")

    # ============================================================ CH 3 (desktop)
    s.chapter("3", "The Desktop Application",
              "A tour of the window of lorewrite-gui: where everything is, "
              "and what each control does.")
    s.p("The desktop application is the same Lorewrite seen through a "
        "window. It shows the project you opened, lets you write in a "
        "page-like editor, and puts the notes and the AI assistant beside "
        "the page. Nothing in it changes the rules of Chapter 1: your "
        "scenes and notes are the same plain Markdown files, and every AI "
        "result is a proposal you accept or reject. This chapter is a tour "
        "of the window. The chapters after it say how to do each task, in "
        "the terminal application and in this one.", idx=["desktop application|window"])

    s.h2("The Window", idx=["window (desktop)"])
    s.p(f"{R('fig_gmain')} shows the window with the Residual project "
        f"open on its first scene. {R('t_gareas')} names its areas.")
    s.gfigure("fig_gmain", "main", "The desktop window: the Residual project "
              "at its first scene, with front matter and two parts", width=418)
    s.table("t_gareas", "Areas of the desktop window",
            ["Area", "What it holds"], [
        ["Title bar (top)", "Window buttons, the project and scene, the "
         "//Draft N// badge, whether the file is saved, and three buttons: "
         "quick switcher, assistant panel, and a menu."],
        ["Activity rail (far left)", "Four views (Binder, Search, Assistant, "
         "Library) and, below, History and Settings."],
        ["Binder (left)", "The tree of your parts, scenes, notes, research "
         "notes, unplaced scenes and Trash, with a button to make a new "
         "scene, a menu of scene and part commands, and your collections."],
        ["Editor (center)", "A toolbar, the three views of the manuscript, "
         "and the page you write on. Under it, a strip with the scene's "
         "details."],
        ["Assistant (right)", "Four tabs: Assistant, Context, Notes and Inspiration. "
         "The AI features, the style card, the conversation and the notes "
         "and comments live here."],
        ["Status bar (bottom)", "The draft, the latest snapshot, the git "
         "state, your sprint, streak and words today, project words, AI "
         "cost, misspellings, the cursor position and the text size."],
    ], [0.27, 0.73])
    s.p("The window asks for 1600 by 1000 pixels and will not shrink below "
        "1280 by 760. It has no frame of its own: the title bar is part of "
        "the page, and you move the window by dragging it. Where the "
        "window appears, and how it can be resized, is up to your window "
        "manager.")

    s.h2("The Title Bar and the Rail", idx=["title bar (desktop)",
                                            "activity rail"])
    s.gfigure("fig_gtitle", "titlebar", "The right half of the title bar",
              crop=(0.38, 1.0), width=418)
    s.p("On a Mac, three colored dots at the left close, minimize and maximize "
        "the window; on Windows and Linux the same three buttons are at the "
        "far right. "
        "Next come the project's title and, after a slash, the open file "
        "(for a scene, //Scene 01 · Rain on the Spur//). The //Draft 2// "
        "badge says which draft of the book this is; click it to start "
        "the next draft (Chapter 8). At the right, a label says whether "
        "your work is safe:")
    s.table("t_gsave", "The save label in the title bar",
            ["Label", "Meaning"], [
        ["Saved", "The open file on disk matches the page."],
        ["Unsaved", "You have typed since the last save. The window saves "
         "by itself 1.5 seconds after you stop."],
        ["Saving…", "A save is under way."],
        ["Changed on disk", "Another program changed the file; see "
         "“Saving and Conflicts” below."],
        ["Save failed", "The file could not be written. A message says "
         "why."],
    ], [0.25, 0.75])
    s.p("The three buttons after the label are the //quick switcher// (the "
        "magnifying glass, `ctrl+k`), the //assistant panel// toggle, and "
        "the **More** (three dots) menu, whose entries are **Switch "
        "project…**, **Export…** (Chapter 14), **Rebuild the link index**, **Call scenes “chapters”** "
        "(or **Call chapters “scenes”**) and **Settings…**. **Switch "
        "project…** saves your work and returns to the launch screen. "
        "**Rebuild the link index** is the desktop's `f9` (Chapter 6). "
        "The chapters entry changes only the wording of labels "
        "(Chapter 5).")
    s.p("The rail, at the far left, chooses what the left column shows. "
        "From the top: **Binder** (your manuscript and notes); **Search** "
        "(the binder with a filter box above it); **Assistant** (opens or "
        "closes the right panel); and **Library** (only the notes, the "
        "style guide and the dictionary). At the bottom are **History** "
        "(the snapshots of the open scene, Chapter 8), **Settings**, and a "
        "round badge with your initials, taken from the `author` line of "
        "`project.toml`.")

    s.h2("The Binder", idx=["binder"])
    s.gfigure("fig_gbinder", "binder", "The binder, with the Front Matter "
              "part opened", width=150)
    s.p(f"The binder ({R('fig_gbinder')}) lists the whole project as a "
        "tree. Click the little arrow beside a folder to open or close it; "
        "click a scene or note to open it in the editor, and use the "
        "arrow keys and `enter` to move through it from the keyboard. "
        "Beside each scene is its word count (without pending AI text or "
        "scene details), and beside the project the total of the book, "
        "written like //1.5k//. The rows are, from the top:")
    s.bullets([
        "**Front Matter**, shown dimmed, and each **part** (for example "
        "//The Recall//) with its scenes. Scenes that belong to no part "
        "are listed under **Manuscript**. Parts, front matter and how "
        "scenes are numbered are the subject of Chapter 5.",
        "**Characters** holds the notes whose kind is //character//; "
        "**World Bible** holds places, objects and factions, with the kind "
        "beside each name.",
        "**Style Guide** opens `style.md`. Before the file exists it is "
        "marked //new//; opening it creates it with the six headings of "
        "Chapter 11. **Dictionary** opens your project dictionary "
        "`dictionary.txt` (Chapter 7), creating it with a short comment if "
        "need be. Both open as plain text, without a title block.",
        "**Research** holds your reference notes (Chapter 9); **Unplaced "
        "Scenes** holds scenes you kept out of the book; **Trash** holds "
        "what you deleted (Chapter 5). Each shows a count.",
    ])
    s.p("Below the tree is the list of your **collections** with a count "
        "for each and an **Edit** link (Chapter 5). The **New scene** "
        "button at the top of the binder (a page with a plus) asks for a "
        "title and makes a scene, like `ctrl+n`. The three-dots button "
        "opens the //scene and part options// menu, which has the commands "
        "for scenes, parts, research notes and the Trash; Chapters 5, 8 "
        "and 9 describe them, and Chapter 16 lists them all.")
    s.p("The **Search** view puts a //Filter binder…// box above the tree; "
        "typing narrows it to titles that contain what you typed. The "
        "**Library** view shows only characters, world notes, the style "
        "guide and the dictionary; in it, the first button reads **New "
        "note** and asks for a name and a kind (character, place, object "
        "or faction), so that objects and factions, which the terminal "
        "application cannot create directly, can be made here.")

    s.h2("The Editor", idx=["editor (desktop)", "live preview"])
    s.p("The editor is the middle of the window. At the top is a toolbar; "
        "below it a thin line with the path (//The Recall › Scene 01//), "
        "the scene's status tag and its word count (with the target, if "
        "you set one); then the page; and at the foot the //inspector//, "
        "a strip with the scene's status, POV and place, purpose, "
        "collections and the words and minutes of this session. The tag, "
        "the target and the strip are where you edit the scene's details "
        "(Chapter 5).")
    s.gfigure("fig_gtoolbar", "toolbar", "The editor toolbar", width=418)
    s.table("t_gtoolbar", "The editor toolbar",
            ["Control", "What it does"], [
        ["Manuscript, Corkboard, Outline", "Three views of the scenes; see "
         "below."],
        ["Undo, Redo", "Step back and forward through your edits. "
         "(`ctrl+z` and `ctrl+y` also work.)"],
        ["Bold, Italic", "Wrap the selection in `**` or `*`, which is how "
         "Markdown marks them; on text already wrapped they take the marks "
         "off again. With nothing selected, they insert a pair of marks "
         "and put the cursor between them."],
        ["Link", "Make a note from the selection: the desktop's `ctrl+j` "
         "(Chapter 6)."],
        ["Add to dictionary", "Add the selected word or phrase to the "
         "project dictionary (Chapter 7). Dimmed until something is "
         "selected."],
        ["Comment", "Attach a comment to the selected passage "
         "(Chapter 9). Dimmed until something is selected."],
        ["Focus mode", "Hide the binder, the assistant and the bars, as "
         "`f11` does."],
    ], [0.34, 0.66])
    s.p("The page is a column of text set in a book face, headed by a "
        "small label (//SCENE 01//), the scene's title and a line naming "
        "the notes it mentions. The title is the first `# ` heading of the "
        "file; you edit it in the text like any other line. What you see "
        "is a //live preview// of the Markdown file:")
    s.bullets([
        "Mentions are in color, as in the terminal application. Names "
        "that are wrapped in `[[double brackets]]` are shown without the "
        "brackets, unless the cursor is inside the link, when they "
        "appear so that you can edit them.",
        "The `<!--ai-->` markers that surround pending AI text are hidden. "
        "The pending text is shown in color and italics, and followed by "
        "small **Accept** and **Reject** buttons (Chapter 11).",
        "`{{expand: ...}}` placeholders are shown as a rounded tag.",
        "Misspelled words have a wavy red underline (Chapter 7).",
        "A passage with an open comment has a faint highlight and a "
        "marker in the margin (Chapter 9).",
        "The scene's details (its frontmatter) are hidden; you edit them "
        "with the inspector (Chapter 5).",
        "Hard-wrapped lines (a scene typed in an editor that broke lines "
        "at 70 columns) are shown as flowing paragraphs. This is only a "
        "display; the file is not changed, and you can turn it off in "
        "Settings.",
    ])
    s.p("Rest the pointer on a colored name for a moment and a //hover "
        "card// shows its kind and the beginning of its note "
        f"({R('fig_ghover')}). Hold `ctrl` and click the name to open the "
        "note in the **Notes** tab of the assistant. Put the cursor on a "
        "name and press `ctrl+j` to do the same from the keyboard; with a "
        "name selected, or on a link that has no note, `ctrl+j` makes the "
        "note (Chapter 6).")
    s.gfigure("fig_ghover", "hovercard", "A hover card over a mention",
              width=300)
    s.h3("Corkboard and Outline", idx=["corkboard", "outline"])
    s.p("The **Corkboard** view shows each scene as a card with its "
        "number, title, the opening of its text, its status and POV, and "
        "its word count; the cards are grouped under the headings of your "
        "parts, with front matter first and unplaced scenes last. Click "
        "a card to open the scene. The **Outline** view lists the same "
        "groups as rows with their word counts, and under each scene any "
        "headings (lines beginning with `#`) that follow its title. In "
        "both views you can drag a scene to a new place; you are asked to "
        "confirm and can undo the move (Chapter 5).")
    s.gfigure("fig_gcork", "corkboard", "The corkboard view", width=300)

    s.h2("The Assistant", idx=["assistant panel"])
    s.p("The panel at the right is called Chisel and carries a green "
        "//Project aware// tag, meaning that it reads your notes. Close "
        "it with the button at its top right or with the title bar's "
        "panel button. The clock button opens your saved conversations "
        "(Chapter 9); the three dots open the //AI menu//, which starts "
        "with **New chat** and **Conversation history…** and has every "
        "other AI command (Chapters 10 and 11). The panel's "
        "four tabs are listed in " + R("t_gtabs") + ".")
    s.gfigure("fig_gassist", "assistant", "The Assistant tab", width=215)
    s.table("t_gtabs", "Tabs of the assistant panel",
            ["Tab", "What it holds"], [
        ["Assistant", "Quick actions, the //Your style// card, continuity "
         "cards, the conversation, and the list of notes the scene "
         "mentions."],
        ["Context", "Only that list, //Retrieved context//: the notes "
         "the open scene mentions, how many times, and how many lines "
         "of the project mention each. Click one to read it."],
        ["Notes", "The note under the cursor (or the one you opened), with "
         "its aliases and backlinks (Chapter 6), and below it the "
         "comments on the open scene (Chapter 9)."],
        ["Inspiration", "Reference pictures made from a description of a "
         "place; the picture pinned to the open scene, and a gallery "
         "(Chapter 13)."],
    ], [0.20, 0.80])
    s.p("The //Quick actions// are four buttons: **Brainstorm** asks for "
        "ideas to get unstuck (Chapter 12), **Rewrite** rewrites the "
        "selected passage (Chapter 11), **Continuity** checks the scene "
        "(Chapter 10), and **Research** switches the question box to "
        "answer from your research notes (Chapter 9). `ctrl+j` outside the "
        "editor moves the cursor to the question box at the foot of the "
        "panel.")
    s.p("Below the quick actions is the //Your style// card (Chapter 11), "
        "then any continuity cards, then the conversation, then the "
        "retrieved context. At the foot, the question box lets you ask "
        "about the scene; the paperclip beside it attaches scenes, notes, "
        "research notes or comments to the question (Chapter 9), and the "
        "small tag beside the paperclip switches between **Current scene** "
        "and **Project**, which decides how much of your book the "
        "assistant reads for that question. Answers appear in the panel "
        "only. They never change your text unless you choose **Insert as "
        "a draft at the cursor** under an answer, which puts it in the "
        "scene as a pending draft you must accept (Chapter 11). Without "
        "an API key the AI parts of the panel are off and say so.")

    s.h2("The Status Bar", idx=["status bar (desktop)"])
    s.p("The status bar has two ends. The left end holds the draft, the "
        "latest snapshot and the git state (Chapter 8); the right end "
        f"({R('fig_gstatus')}) holds your writing numbers and the "
        "cursor.")
    s.gfigure("fig_gstatus", "statusbar", "The right half of the status "
              "bar", crop=(0.42, 1.0), width=418)
    s.table("t_gstatus", "Items of the desktop status bar",
            ["Item", "Meaning"], [
        ["Draft 2", "Which draft of the book this is. Click it to start "
         "the next draft (Chapter 8)."],
        ["Snapshot 1 min ago", "How long ago the open scene was last "
         "snapshotted, or //No snapshot//. Click it for the history "
         "(Chapter 8)."],
        ["1 change, Ahead 2, Synced", "The git state of the project, "
         "shown only when git is installed. Click it for the menu "
         "(Chapter 8)."],
        ["Sprint", "Start a focus sprint; while one runs it reads "
         "//24:05 · +120//, the time left and the words written. Click "
         "to stop it (Chapter 12)."],
        ["Streak 8", "Days in a row that met your daily word target. "
         "Click it for the stats (Chapter 12)."],
        ["+240 / 500 words today", "Words you wrote today across "
         "sessions, against your daily target. Click it for the stats."],
        ["1,502 project words", "Words in the book: all scenes except "
         "front matter and unplaced scenes."],
        ["AI $0.0269", "What the AI calls of this session cost, as "
         "reported by OpenRouter."],
        ["3 spelling", "Misspelled words in the open scene. Click it to "
         "jump to the next one. Shown only for scenes."],
        ["Ln 11, Col 42", "The cursor's line and column."],
        ["100%", "Text size. Click it to step through 90%, 100%, 110% and "
         "125%."],
    ], [0.30, 0.70])

    s.h2("Dialogs and the Quick Switcher", idx=["quick switcher", "ctrl+k"])
    s.p("Dialogs appear over the window and close with `esc`, with "
        "**Cancel**, or by clicking outside them. The //quick switcher// "
        f"({R('fig_gswitch')}), opened with `ctrl+k` or the magnifying "
        "glass, is a search box over every scene and note. Type a few "
        "letters of a title, a name or an alias; use `up` and `down` and "
        "`enter` to open the highlighted row.")
    s.gfigure("fig_gswitch", "switcher", "The quick switcher, searching "
              "for //sal//", width=300)
    s.p("Other dialogs are described where their task is: new scene and "
        "rename (Chapter 4), new note (Chapter 6), the spelling popover "
        "(Chapter 7), the review of alias and story-bible suggestions and "
        "the style guide (Chapters 10 and 11), the prompt for drafting "
        "(Chapter 11) and Settings (Chapter 15).")

    s.h2("Saving and Conflicts", idx=["autosave|desktop", "conflict banner"])
    s.p("The window saves the open file 1.5 seconds after you stop typing, "
        "when the window loses focus, when you open another file, and on "
        "`ctrl+s`. Because the terminal application may be open on the "
        "same project, every save carries the time the file had when it "
        "was opened, and a save is refused if the file on disk has changed "
        "since. A refused save never overwrites anything. Instead the "
        f"title bar reads //Changed on disk// and a banner ({R('fig_gconf')}) "
        "appears above the page.")
    s.gfigure("fig_gconf", "conflict", "The conflict banner", width=418)
    s.p("Click **Reload from disk** to take the other program's version and "
        "lose what you typed since, or **Keep my version** to write yours "
        "over it. When you return to the window after being away and the "
        "file has changed on disk, with nothing unsaved of yours, the "
        "window simply reloads it and says //Reloaded: the file changed on "
        "disk.//")

    s.h2("What Is Still Planned", idx=["planned features"])
    s.p("An earlier edition of this book listed parts of the window that "
        "were drawn dimmed and did nothing, with the tooltip //Not in "
        "Chisel yet//. All of them now work: the draft badge, "
        "snapshots, sync, streak, the parts of the binder, collections, "
        "comments, the details strip and the status tag, the word target, "
        "Brainstorm, Research, conversation history and attaching. No "
        "control in the desktop window is a placeholder. Export "
        "(Chapter 14) and inspiration images (Chapter 13) are built, too.")
    s.p("What the program does not do yet:")
    s.bullets([
        "**Dragging scenes** works in the desktop application only; the "
        "terminal application moves scenes with palette commands.",
        "**Attaching material to a chat** works in the desktop "
        "application only.",
        "**Keys.** The terminal application reaches the session stats, "
        "focus sprints and Brainstorm only through the command palette; "
        "they have no key of their own.",
    ])

    s.h2("Keys in the Desktop Window", idx=["keys|desktop"])
    s.p(f"The desktop window has few keys of its own ({R('t_gkeys')}); "
        "the full list for both applications is in Chapter 16.")
    s.table("t_gkeys", "Keys of the desktop window",
            ["Key", "Action"], [
        ["ctrl+k", "Quick switcher."],
        ["ctrl+n", "New scene."],
        ["ctrl+s", "Save now."],
        ["f11", "Focus mode."],
        ["ctrl+j", "In the editor: open the note under the cursor, or make "
         "one for the selected name. Elsewhere: go to the assistant's "
         "question box."],
        ["ctrl+g", "AI: draft at the cursor, expand the placeholder, or "
         "rewrite the selection."],
        ["f7, f8", "Accept or reject the AI draft under the cursor."],
        ["ctrl+.", "Spelling popover for the word at the cursor, or the "
         "selected phrase."],
        ["ctrl+click", "Open the note under the pointer."],
        ["esc", "Close a dialog or menu."],
    ], [0.22, 0.78], mono_cols=(0,))

    # ============================================================ CH 3
    s.chapter("4", "Writing Scenes",
              "The editor, saving, the status bar, writer mode, and "
              "everything you can do with scenes.")
    s.p("This chapter describes the terminal application and says, for "
        "each task, what to do in the desktop application instead; the "
        "desktop window itself is described in Chapter 3. "
        f"{R('t_scenetasks')}, at the end of the chapter, puts the two "
        "side by side.")
    s.h2("The Main Window", idx=["main window"])
    s.p(f"After you open a project in the terminal application, the main "
        f"window appears ({R('fig_main')}). It has five areas, listed in "
        f"{R('t_areas')}.")
    s.figure("fig_main", "main", "The main window")
    s.table("t_areas", "Areas of the main window",
            ["Area", "What it shows"], [
        ["Title bar", "The program name and version, and the title of the "
         "project."],
        ["Sidebar (left)", "A filter box, the list of scenes, and the list "
         "of entities with their kinds."],
        ["Editor (center)", "The open scene or note, with line numbers."],
        ["Entity panel (right)", "The note for the name under the cursor, "
         "and a list of backlinks. See Chapter 6."],
        ["Status bar", "Details of the open file. See "
         "//The Status Bar// below."],
        ["Footer", "The most useful keys. What fits depends on the width "
         "of your window."],
    ], [0.25, 0.75])
    s.p("Click an item in the sidebar to open it. Lorewrite opens your "
        "first scene automatically when a project loads.")

    s.h2("Typing and Markdown", idx=["editor", "Markdown|headings"])
    s.p("The editor is an ordinary text editor with a few conveniences. "
        "It wraps long lines to the width of the window, shows line "
        "numbers (which you can turn off; see Chapter 15), and colors "
        "Markdown as you type: headings, //italic// text between single "
        "asterisks, and **bold** text between double asterisks.")
    s.p("Begin each scene with a heading line, for example "
        "`# Capsule 7-19`. That line becomes the scene's title in the "
        "sidebar and in the command palette. A scene with no heading is "
        "listed by its file name instead.")
    s.p(f"The usual editing keys work; {R('t_editkeys')} lists them.")
    s.table("t_editkeys", "Editing keys",
            ["Key", "Action"], [
        ["arrows, home, end", "Move the cursor. `ctrl+a` and `ctrl+e` "
         "also go to the start and end of the line."],
        ["ctrl+left, ctrl+right", "Move by a word."],
        ["pageup, pagedown", "Move by a screenful."],
        ["shift + any movement key", "Select text."],
        ["f5", "Select everything. (`f6` fixes the next misspelled word, "
         "Chapter 7; `f7` and `f8` accept and reject AI drafts, "
         "Chapter 11.)"],
        ["ctrl+c, ctrl+x, ctrl+v", "Copy, cut and paste."],
        ["ctrl+z, ctrl+y", "Undo and redo."],
        ["backspace, delete", "Delete a character. `ctrl+w` deletes the "
         "word to the left; `ctrl+u` deletes to the start of the line; "
         "`ctrl+k` deletes to the end of the line; `ctrl+shift+k` deletes "
         "the whole line."],
    ], [0.34, 0.66], mono_cols=())
    s.note("These keys are provided by the terminal toolkit that Lorewrite "
           "is built on, so a few may differ in other versions of it.")

    s.h2("Saving Your Work", idx=["saving", "autosave", "ctrl+s"])
    s.p("You never have to save. Lorewrite saves the open file "
        "automatically (//autosave//) shortly after you stop typing (a little over half a "
        "second), whenever you open another scene or note, and when you "
        "quit. To save at once, press `ctrl+s`; a brief message says "
        "//Saved//. Files are written safely: Lorewrite writes a temporary "
        "copy and then swaps it into place, so a power failure cannot leave "
        "a half-written scene.")
    s.p("The desktop application saves 1.5 seconds after you stop typing, "
        "when its window loses focus, and on `ctrl+s`, and shows the "
        "state in the title bar (Chapter 3).")
    s.attention("The terminal application writes the contents of its "
                "editor over the file on disk. If you change the scene you "
                "have open using another program while Lorewrite is "
                "running, your change is lost the next time Lorewrite "
                "saves. Quit Lorewrite, or switch to a different scene, "
                "before editing that file elsewhere. The desktop "
                "application is more careful: it refuses to overwrite a "
                "file that changed on disk and offers you the choice "
                "(Chapter 3), so it is safe to leave open beside the "
                "terminal one; but the terminal application does not do "
                "the same, so the last one to save a file wins.")

    s.h2("The Status Bar", idx=["status bar", "word count"])
    s.p("The line above the footer describes the open file. Its fields, "
        "separated by vertical bars, are listed in "
        f"{R('t_status')}.")
    s.table("t_status", "Fields of the status bar",
            ["Field", "Meaning"], [
        ["`manuscript/02-capsule-7-19.md`",
         "The open file, relative to the project folder."],
        ["`Draft 2`", "Which draft of the book this is (Chapter 8)."],
        ["`3 changes`, `Ahead 2`, `Synced`", "The git state of the project, "
         "shown only when it is under git (Chapter 8)."],
        ["`SPRINT 24:05 (+120)`", "A focus sprint is running: time left "
         "and the words written in it (Chapter 12)."],
        ["`● modified`", "You have typed since the last save."],
        ["`saved 23:10`", "The time of the last save. Until you have saved "
         "something in the session it reads simply `saved`."],
        ["`391 words (1502 project)`",
         "Words in the open file, and words in all scenes together. Words "
         "are runs of characters separated by spaces or line breaks. The "
         "project total is refreshed each time a file is saved. It counts "
         "the book: front matter and unplaced scenes (Chapter 5), scene "
         "details and text in pending AI drafts (Chapter 11) are not "
         "counted."],
        ["`+240 / 500 today`, `streak 8`", "Words you wrote today against "
         "your daily target, and the days in a row that met it "
         "(Chapter 12). The streak is shown only when it is above zero."],
        ["`Ln 11, Col 42`", "The line and column of the cursor."],
        ["A link hint", "When the cursor is on a name, the name and what "
         "`ctrl+j` will do: //to open// its note, or //no note, ctrl+j "
         "to create// one. Inside a pending AI draft, the hint //AI draft "
         "— f7 accept · f8 reject// comes first."],
        ["`AI $0.0153`", "The cost of the AI calls made since you started "
         "Lorewrite, as reported by OpenRouter. It appears after the "
         "first AI call that reports a cost and is not shown before."],
        ["`Snapshot 12 min ago`", "How long ago the open scene was last "
         "snapshotted; absent if it never was (Chapter 8)."],
    ], [0.36, 0.64])
    s.p("With no file open, the status bar says //no file open — ctrl+p to "
        "open a scene//.")

    s.h2("Writer Mode and the Sidebar", idx=["writer mode", "sidebar", "f11"])
    s.p(f"Press `f11` for //writer mode// ({R('fig_writer')}). The sidebar, "
        "the entity panel, the title bar and the footer disappear, and the "
        "editor is padded from the sides so lines are shorter and easier to "
        "read. Only the status bar remains. Press `f11` again to return.")
    s.figure("fig_writer", "writer", "Writer mode")
    s.p("To hide only the sidebar, press `ctrl+b`; press it again to bring "
        "it back. The entity panel has no separate key; it is hidden in "
        "writer mode only.", idx=["ctrl+b"])
    s.p("In the desktop application the same idea is called //focus "
        "mode//: press `f11` or click the focus button at the right of the "
        "editor toolbar. The binder, the assistant and the bars go away "
        "and only the page remains; press `f11` again to come back.")
    s.gfigure("fig_gfocus", "focus", "Focus mode in the desktop "
              "application", width=300)

    s.h2("Moving Between Scenes", idx=["scene|navigating", "alt+left", "alt+right"])
    s.p("Press `alt+right` for the next scene and `alt+left` for the "
        "previous one. A brief message shows the title of the scene you "
        "have moved to. At the first or last scene, the message //No more "
        "scenes this way// appears. The keys follow the order of the book, "
        "so they carry you from the last scene of one part into the first "
        "of the next (front matter comes first, and unplaced scenes are "
        "skipped; Chapter 5). If you are looking at an entity note "
        "when you press either key, Lorewrite takes you back to the first "
        "scene. You can also click a scene in the sidebar, or use the "
        "command palette (Chapter 16) to open a scene by title.")

    s.h2("Creating a Scene", idx=["scene|creating", "new scene", "ctrl+n"])
    s.proc("To create a scene:", [
        "Press `ctrl+n`. A box asks //New scene title://.",
        "Type a title and press `enter`. (`esc` cancels.)",
    ])
    s.figure("fig_newscene", "newscene", "Creating a scene")
    s.p("Lorewrite makes a new file at the end of the part you are working "
        "in (or at the end of the last part, or of the manuscript folder, "
        "if the project has no parts or the open file is not a scene), "
        "named with the next number and a version of the title, for example "
        "`05-neon-lullaby.md`. It contains just the heading `# Neon "
        "Lullaby` and a blank line, and opens ready for you to type.")

    s.h2("Renaming a Scene", idx=["scene|renaming"])
    s.proc("To rename the open scene:", [
        "Press `ctrl+p` to open the command palette, type //rename//, and "
        "choose **Action · Rename current scene**.",
        "Edit the title in the box and press `enter`.",
    ])
    s.p("This changes the scene's title, its first heading line, and "
        "nothing else. The file keeps its old name on disk; that name only "
        "matters for ordering. The rename is refused with //Open a scene "
        "first// if you are looking at an entity note.")

    s.h2("Reordering Scenes", idx=["scene|reordering", "moving a scene"])
    s.p("Scenes are ordered by the number at the start of the file name, "
        "within their part. To "
        "move the open scene, choose **Action · Move current scene up** or "
        "**Action · Move current scene down** from the command palette. "
        "Lorewrite swaps the numbers of the scene and its neighbor in the "
        "same part, so "
        "both files are renamed. A message says //Moved to// and the new "
        "file name. At the top or bottom of the part it says //Already at "
        "the edge of its part//. To send a scene to another part, see "
        "Chapter 5.")
    s.p("If the scene has pending AI drafts (Chapter 11), the file that "
        "holds their originals moves along with it.")
    s.attention("Moving a scene renames files. If your project is under "
                "version control, the change appears as two renames. A "
                "scene whose file name does not start with a number (a "
                "file you added yourself) cannot be moved; in that case "
                "Lorewrite also says it is at the edge. "
                "Rename such files yourself, following the pattern "
                "`NN-name.md`.")

    s.h2("Deleting a Scene", idx=["scene|deleting"])
    s.proc("To delete the open scene:", [
        "Choose **Action · Delete current scene** from the command "
        "palette.",
        f"Read the confirmation ({R('fig_delete')}). Press `y` or click "
        "**Move to Trash** to go ahead; press `n` or `esc`, or click "
        "**Cancel**, to keep the scene.",
    ])
    s.figure("fig_delete", "deleteconfirm", "Confirming that a scene "
             "goes to the Trash")
    s.p("Deleting a scene does not destroy it. The file is moved into the "
        "project's `.trash` folder together with its drafts, snapshots "
        "and comments, and **Action · Open Trash** brings it back, or "
        "deletes it for good, after a confirmation (Chapter 5). Afterward, "
        "Lorewrite opens the first scene of the book and says //Moved "
        "'Title' to the Trash//.")
    s.attention("Only the Trash view deletes a scene for good, and it "
                "asks first. An emptied Trash cannot be recovered; if your "
                "project is under version control or in a backed-up folder "
                "you can still get a file back from there.")

    s.h2("Finding a Scene or Note: the Sidebar Filter",
         idx=["filter", "sidebar|filter"])
    s.p(f"The box at the top of the sidebar ({R('fig_filter')}) filters "
        "both lists as you type. It matches any part of a title or name, "
        "ignoring capital letters; for entities the kind in square "
        "brackets counts too, so typing //place// lists your places. "
        "Clear the box to see everything again.")
    s.figure("fig_filter", "filter", "Filtering the sidebar")
    s.p("The lists are empty at first; they say //ctrl+n — your first "
        "scene// and //select a name, then ctrl+j// to point you to the "
        "next step.")
    s.p("In the desktop application, click **Search** on the rail for a "
        "filter box above the binder, or press `ctrl+k` for the quick "
        "switcher, which searches every scene and note at once "
        "(Chapter 3).")

    s.h2("Scene Tasks at a Glance")
    s.table("t_scenetasks", "Scene tasks in the two applications",
            ["Task", "Terminal application", "Desktop application"], [
        ["New scene", "`ctrl+n`, type a title, `enter`.", "`ctrl+n`, or the "
         "**New scene** button of the binder; type a title and click "
         "**Create** (or press `enter`)."],
        ["Open a scene", "Click it in the sidebar; `alt+left` and "
         "`alt+right` for the previous and next.", "Click it in the "
         "binder, a corkboard card or an outline row; or `ctrl+k`."],
        ["Rename", "**Action · Rename current scene**.", "Binder menu "
         "(three dots) \u203a **Rename scene…**."],
        ["Move", "**Action · Move current scene up**, **down**.",
         "Binder menu \u203a **Move up**, **Move down**."],
        ["Delete (to the Trash)", "**Action · Delete current scene**, then "
         "`y`.", "Binder menu \u203a **Delete scene…**, then **Move to "
         "Trash**."],
        ["Move to another part", "**Action · Move scene to part**.",
         "Binder menu \u203a **Move scene to part…**, or drag a card "
         "(Chapter 5)."],
        ["Save now", "`ctrl+s`.", "`ctrl+s`."],
        ["Hide everything but the page", "`f11` (writer mode).",
         "`f11` (focus mode)."],
        ["Undo", "`ctrl+z`.", "`ctrl+z`, or the Undo button."],
    ], [0.20, 0.38, 0.42])
    s.p("Deleting a scene moves it to the Trash in both applications; "
        "the desktop confirmation names the file it is about to move.")

    ch_organize.build(s, R)

    # ============================================================ CH 4
    s.chapter("6", "Characters, Places and Mentions",
              "How to tell Lorewrite about the people and places in your "
              "story, and how it recognizes them in your writing.")
    s.h2("Making a Note", idx=["note (entity)|creating", "ctrl+j"])
    s.p("The quickest way to introduce a character or place is to write "
        "its name in a scene, select it, and press `ctrl+j`.")
    s.proc("To make a note for a name:", [
        f"In a scene, select the name with the mouse or with `shift` and "
        f"the arrow keys ({R('fig_selected')}). Select one line only.",
        "Press `ctrl+j`. Lorewrite asks what kind of note to make: "
        f"**Character** or **Place** ({R('fig_type')}).",
        "Choose one. Lorewrite creates the note, using exactly the text "
        "you selected as its name, and opens it for you to write in.",
    ])
    s.figure("fig_selected", "selected_name",
             "A name selected, ready for ctrl+j")
    s.figure("fig_type", "typeprompt", "Choosing the kind of a new note")
    s.p("From then on, every mention of that name in your scenes is "
        "colored, and its backlinks are counted. You make each note once.")
    s.p("You can also create a note without selecting anything: open the "
        "command palette and choose **Action · New character** or "
        "**Action · New place**, then type the name. If a note with that "
        "name already exists, it is opened and not overwritten.")
    s.p("Objects and factions have no button. Create the note as a "
        "character, then change the `type:` line at the top of the note to "
        "`object` or `faction`, then press `f9`; the kind shown in the sidebar "
        "changes then. Any other value is treated as //character//.")
    s.note("When you press `ctrl+j` with nothing selected and the cursor "
           "is not on a name, Lorewrite says //Select a name and press "
           "ctrl+j to make a note for it//. A selection that spans more "
           "than one line is ignored.")
    s.h3("In the desktop application", idx=["note (entity)|desktop"])
    s.p("Select the name in the page and press `ctrl+j`, or click the "
        "**Link** button of the editor toolbar. A **New note** box asks "
        "for the name (filled in with your selection) and a kind: "
        "**character**, **place**, **object** or **faction**. Click "
        "**Create**. The note is made and shown in the **Notes** tab of "
        "the assistant, and every mention of the name is colored. If the "
        "selection already names a note, that note is shown instead. You "
        "can also make a note from the **Library** view of the binder with "
        "its **New note** button, which opens the new note in the editor. "
        "Because all four kinds can be chosen here, there is no need to "
        "edit the `type:` line by hand for objects and factions.")

    s.h2("Anatomy of a Note", idx=["frontmatter", "note (entity)|format"])
    s.p(f"A note ({R('fig_note')}) is a text file in one of the folders "
        "under `entities`. It has two parts. The first, between two lines "
        "of three hyphens, is the //frontmatter//: three fields that "
        "Lorewrite reads. The second, below it, is free text of your own.")
    s.figure("fig_note", "entitynote", "An entity note open in the editor")
    s.table("t_front", "Frontmatter fields of a note",
            ["Field", "Meaning"], [
        ["name", "The entity's proper name. Shown in the sidebar and used "
         "for matching."],
        ["type", "`character`, `place`, `object` or `faction`."],
        ["aliases", "Other names, as a list in square brackets: "
         "`[Kuroda, Inspector Kuroda, the inspector]`."],
    ], [0.20, 0.80], mono_cols=(0,))
    s.p(f"Everything below the frontmatter is yours. The note shown in "
        f"{R('fig_note')} also has a section headed `## Canon (auto)`; that is "
        "managed by the story-bible feature described in Chapter 10, and "
        "you can ignore it until then.")
    s.h3("Adding aliases", idx=["alias|adding"])
    s.p("Open the note (put the cursor on the name and press `ctrl+j`, or "
        "click it in the sidebar) and edit the `aliases:` line. Separate "
        "the aliases with commas. If an alias contains a colon, put it in "
        "quotation marks. When the note is saved (a moment after you "
        "stop typing), Lorewrite reloads its list of names, recolors your "
        "scenes and updates the backlinks. Lorewrite can also suggest "
        "aliases for you; see //Find Aliases// in Chapter 10.")
    s.p("In the desktop application you can also add an alias without "
        "opening the file: in the **Notes** tab, type it into the //Add "
        "alias// box under the name and press `enter`. The colors and the "
        "backlinks update at once.")
    s.attention("The `name` field controls what is recognized. If you "
                "change the name of an entity, its old name stops being "
                "recognized in your scenes unless you add it to the "
                "aliases. Lorewrite does not change the file's name or "
                "rewrite your scenes.")

    s.h2("How Mentions Are Recognized", idx=["mention|matching rules"])
    s.p("Lorewrite looks for the name and every alias of every note in "
        "your scenes. It follows a few simple rules, listed in "
        f"{R('t_rules')}, so that it finds what you mean without "
        "finding what you do not.")
    s.table("t_rules", "How names are matched",
            ["Rule", "Example"], [
        ["**Whole words only.** A name must not be part of a longer word.",
         "The alias `Rook` matches //Rook climbed// but not //Rookery//."],
        ["**Capitals matter, with one exception.** A name matches as you "
         "spelled it in the note. Its first letter may also be a capital "
         "so that names starting a sentence still match.",
         "The alias `the inspector` matches //the inspector// and //The "
         "inspector//, but not //THE INSPECTOR//. A name `Will` does not "
         "match the word //will//."],
        ["**The longest name wins.** When two names overlap in the "
         "text, the longer one is used.",
         "With the names `the Hollow` and `Hollow Market`, the text //the "
         "Hollow Market// is one mention of //Hollow Market//."],
        ["**Possessives are fine.** An apostrophe ends a word.",
         "`Sallow` matches in //Sallow's eyes//. (If a note is named "
         "`Sallow's Shard`, the longer name wins for that phrase.)"],
        ["**Names must be at least two characters long.**", ""],
        ["**Plurals and other forms are not guessed.** List them as "
         "aliases if you use them.",
         "Add `the Kurodas` if you write it."],
        ["**Text already in [[brackets]] is left alone.** It is a link, "
         "not a mention.", ""],
        ["**Only scenes are scanned.** Names in your notes are not "
         "colored, though [[links]] in notes still work.", ""],
    ], [0.55, 0.45])

    s.h2("What Mentions and Links Look Like",
         idx=["color", "orange link", "mention|appearance"])
    s.p(f"{R('fig_links')} shows a scene with all the kinds of "
        f"highlighting. {R('t_look')} says what each one means. The "
        "figures in this book are printed in shades of gray; on your "
        "screen, the colors depend on your theme, but resolved names are "
        "usually cyan or blue and names with no note are orange.")
    s.table("t_look", "How names look in the editor",
            ["What you see", "What it means"], [
        ["A name in a color, no underline", "A mention: a name or alias "
         "of a note, written without brackets."],
        ["A colored, bold, underlined name inside faded brackets",
         "A `[[link]]` to a note that exists."],
        ["An orange, bold, underlined name inside faded brackets",
         "A `[[link]]` with no note yet. Put the cursor on it and press "
         "`ctrl+j` to create the note."],
        ["Faded brackets", "The `[[` and `]]` themselves, dimmed so they "
         "do not distract."],
    ], [0.45, 0.55])
    s.figure("fig_links", "main_scene1", "Mentions and links in a scene. The author has typed [[Lin]] and "
             "[[Kuroda]] with brackets; Lin has no note yet, so it is "
             "shown in the orange style")
    s.p("Plain text that is not a name is left as it is; a word that "
        "merely //looks// like a name, but has no note, is not colored "
        "unless you put it in brackets.")

    s.h2("Links with Brackets", idx=["link|syntax", "[[ ]]"])
    s.p("You never need brackets for a name that has a note. They are "
        "still useful in two cases: to mark a name that has no note yet "
        "(it turns orange, reminding you to create one), and to show "
        "different words from the name, as in "
        f"`[[Rook Tanaka|Rook]]`, which is drawn as //Rook// but points at "
        f"Rook Tanaka. {R('fig_linksyntax')} shows the syntax.")
    s.figure_flow("fig_linksyntax", Railroad([
        "[[", ("var", "name"), ("opt", ["|", ("var", "display text")]), "]]",
    ]), "Syntax of a link")
    s.p("The //name// may be an entity's name or one of its aliases; "
        "capital letters do not matter here. Lorewrite never adds "
        "brackets to your text: not even the AI features do (Chapters 10 "
        "and 6).")

    s.h2("Opening a Note from Your Text", idx=["ctrl+j|opening a note"])
    s.p("Put the cursor anywhere in a name and press `ctrl+j`. Lorewrite "
        "opens that name's note in the editor. The status bar tells you "
        "beforehand: //Rook Tanaka — ctrl+j to open//. Your scene is "
        "saved first. To return, click the scene in the sidebar, or press "
        "`alt+left` or `alt+right`.")

    s.h2("The Entity Panel and Backlinks",
         idx=["entity panel", "backlink|list"])
    s.p("When the cursor is on a name (see the right side of "
        f"{R('fig_main')}), the entity panel shows its note: the entity's "
        "name and kind as a heading, then the text of the note. For a "
        "name that has no note, it says //no note yet//. Below the note is "
        "the //Backlinks// list.")
    s.p("Each backlink is one line of your book that names the entity. "
        "Names inside pending AI drafts (Chapter 11) are not counted. It "
        "shows the file, the line number and the beginning of the line, "
        "like `manuscript/03-the-stairwell.md:22`. Backlinks count "
        "mentions and links, by name or by any alias. Select one and press "
        "`enter` (or click it) to open that scene with the cursor on the "
        "line.")
    s.note("The panel changes only when the cursor is on a name. When you "
           "move to plain text it keeps showing the last entity you looked "
           "at.")
    s.p("In the desktop application the same information is in the "
        f"**Notes** tab of the assistant ({R('fig_gnotes')}). It is shown "
        "when you press `ctrl+j` on a name, `ctrl`-click a name, click a "
        "note in the binder's Library view, or click a note in the "
        "**Context** tab. The tab shows the name and kind, the aliases as small tags "
        "with the //Add alias// box, the text of the note, a button **Open "
        "in editor**, and the //Backlinks// list: each entry names the "
        "scene and the line, and shows the line; click it to open the "
        "scene at that line. For a name in `[[brackets]]` that has no note, "
        "the tab offers **Create note**.")
    s.gfigure("fig_gnotes", "assistant_notes", "The Notes tab for Rook "
              "Tanaka: aliases, the note and its backlinks", width=215)

    s.h2("Rebuilding the Index", idx=["index (cache)|rebuilding", "f9", "rebuild index"])
    s.p("Backlinks come from the index, a cache kept in the project's "
        "`.lorewrite` folder. Lorewrite updates it as you work. If you "
        "add, edit or delete note files with another program, or if a "
        "backlink list looks out of date, press `f9`. Lorewrite saves the "
        "open file, rebuilds the index from every scene and note, reloads "
        "the notes, and says //Index rebuilt//. It is always safe to "
        "press `f9`. In the desktop application use **More \u203a Rebuild the link "
        "index**; it says //Index rebuilt from the files.//")

    s.h2("Renaming or Deleting an Entity", idx=["entity|deleting", "entity|renaming"])
    s.p("Lorewrite has no command for deleting a note. To remove an "
        "entity, delete its file (in `entities/characters`, "
        "`entities/places` and so on) with your file manager or a shell, "
        "then press `f9`. Its mentions stop being colored. To rename one, "
        "edit the `name:` line and, if you still use the old name, add it "
        "to `aliases`. The file's own name is unchanged by either edit, "
        "which is harmless.")

    # ============================================================ CH 6 (spelling)
    s.chapter("7", "Spelling",
              "Underlined misspellings, how to fix them, and how to teach "
              "Lorewrite the words of your world.")
    s.p("Lorewrite checks the spelling of your scenes as you write, in both "
        "applications, and underlines the words it does not know. It "
        "checks //spelling only//; it does not look at grammar, style or "
        "punctuation. It works entirely on your computer, with a built-in "
        "English word list (American spelling), and sends nothing "
        "anywhere. Its list does not know your invented words, so the "
        "chapter spends most of its time on how to tell it which of them "
        "are right.", idx=["spell check", "spelling"])
    s.p("Spell check applies to //scenes// only. Entity notes, the style "
        "guide and the dictionary files are not underlined. You can turn "
        "the underlining off (see “Turning It Off” below).")

    s.h2("What Gets Underlined", idx=["misspelling"])
    s.p("In the terminal application a misspelled word is underlined in "
        f"red ({R('fig_spellu')}); in the desktop application it has a "
        "wavy red underline. The check runs a moment after you stop "
        "typing (0.6 seconds in the terminal), so the marks catch up "
        "with a fast typist rather than flickering under them.")
    s.figure("fig_spellu", "spell_underline", "A misspelled word, underlined "
             "in the terminal application (here //maglev//, a word of the "
             "story's world)")
    s.p("A word is //not// underlined if any of these is true. They are the "
        "things Lorewrite assumes you meant.")
    s.table("t_nospell", "What is never flagged",
            ["Kind of text", "Notes"], [
        ["Names and aliases of your notes", "Every word of every entity "
         "name and alias, and each whole name. A character called "
         "//Kessler-Voss// is never flagged, nor is the alias //the "
         "Hollow//."],
        ["Your dictionaries", "Every word and phrase in the project "
         "dictionary and in your personal dictionary (below)."],
        ["Words you chose to ignore", "Ignored words, for the rest of the "
         "session (below)."],
        ["Possessives and contractions", "//Rook's// is checked as "
         "//Rook//; //don't//, //he'd//, //they're// and similar are "
         "accepted. Straight and curly apostrophes are the same."],
        ["Hyphenated words", "Each part is checked, so //noodle-stall// "
         "passes when //noodle// and //stall// do, or when the whole "
         "compound is a known word."],
        ["Acronyms", "Words in capitals of five letters or fewer, such as "
         "//NYPD// or //K-V//."],
        ["Words with digits, single letters, and words in other "
         "alphabets", "Skipped."],
        ["Markup and machinery", "The title block of a note, code in "
         "back-quotes or in fenced blocks, web and e-mail addresses, "
         "`<!--` comments (which includes the markers of AI drafts and the "
         "provenance line of `style.md`), `{{expand: ...}}` placeholders, "
         "and the name inside a `[[link]]` (the words you show after a "
         "`|` are still checked)."],
    ], [0.34, 0.66])
    s.p("Capital letters count in one direction. A word that is in the "
        "dictionary in lower case is accepted in any capitalization, but "
        "a name you added with a capital letter is accepted only with "
        "one: after adding //Kowloon//, the lower-case //kowloon// is "
        "still underlined. Text inside a pending AI draft //is// checked "
        "(Chapter 11), because you are about to decide whether to keep it.")

    s.h2("Fixing a Word in the Terminal Application", idx=["f6", "spell check|terminal"])
    s.p(f"Press `f6`. Lorewrite moves the cursor to the end of the next "
        "misspelled word after the cursor (starting again at the top "
        "after the last one) and opens a small window "
        f"({R('fig_spellfix')}) with the word and up to five suggestions "
        "ranked by how common they are, in the capitalization of the word "
        "you typed. Press the key for what you want to do:")
    s.figure("fig_spellfix", "spell_fix", "The f6 window: one suggestion "
             "for //unnattractive//", )
    s.table("t_spellkeys", "Keys in the f6 window",
            ["Key", "Action"], [
        ["1 to 5, enter", "Replace the word with that suggestion. `enter` "
         "takes the first. The replacement is an ordinary edit, so "
         "`ctrl+z` undoes it."],
        ["a", "Add the word to the project dictionary."],
        ["p", "Add the word to your personal dictionary."],
        ["i", "Ignore the word until you quit Lorewrite."],
        ["esc", "Close the window and change nothing."],
    ], [0.22, 0.78], mono_cols=(0,))
    s.p("If there is nothing to fix, Lorewrite says //No misspellings//; "
        "in a note or the style guide it says //Spell check applies to "
        "scenes//. Press `f6` again for the next word. The three palette "
        f"actions of {R('t_spellact')} work on dictionaries from the "
        "keyboard.")
    s.table("t_spellact", "Palette actions for spelling",
            ["Entry", "What it does"], [
        ["Toggle spell check", "Turn the underlining on or off (the same "
         "setting as in Settings). A message says //Spell check on// or "
         "//Spell check off//."],
        ["Add selection to dictionary", "Add the selected word or phrase "
         "to the project dictionary; the selection may span several "
         "words. If nothing is selected it says //Select a word or phrase "
         "first//."],
        ["Open project dictionary", "Open `dictionary.txt` in the editor "
         "(creating it with a short comment if need be), to edit by "
         "hand."],
    ], [0.34, 0.66])

    s.h2("Fixing a Word in the Desktop Application", idx=["spell check|desktop"])
    s.p("Click a misspelled word, or right-click it, or put the cursor in "
        f"it and press `ctrl+.`. A popover ({R('fig_gspell')}) lists "
        "suggestions; click one to replace the word. As in the terminal "
        "application the replacement is an ordinary, undoable edit. Below "
        "the suggestions are three commands.")
    s.gfigure("fig_gspell", "spell_popover", "The spelling popover for "
              "//maglev//. Suggestions for invented words are poor; the "
              "dictionary commands are what you want", width=250)
    s.bullets([
        "**Add to dictionary** adds the word to the project dictionary.",
        "**Add to my dictionary (all projects)** adds it to your personal "
        "dictionary.",
        "**Ignore** hides the underline on that word until you quit the "
        "application. It is not saved anywhere.",
    ])
    s.p("To add a //phrase//, select two or more words and press `ctrl+.` "
        "(or right-click inside the selection, or click the "
        f"**Add to dictionary** button of the toolbar). The popover "
        f"({R('fig_gphrase')}) then offers the two dictionaries and no "
        "suggestions. A message confirms it: //Added “sweet rot” to the "
        "project dictionary.//, or //“sweet rot” is already in the "
        "dictionary.//")
    s.gfigure("fig_gphrase", "spell_phrase", "A phrase selected: the "
              "popover offers to add it to a dictionary", width=250)
    s.p("The status bar shows how many misspellings the open scene has "
        "(//3 spelling//); click it to jump to and select the next one. "
        "When there are none it reads //0 spelling// and "
        "dims. A message says //No misspelled words.// if you jump with "
        "none left. "
        "The count is not shown for notes, the style guide or the "
        "dictionary.")

    s.h2("The Two Dictionaries", idx=["dictionary", "dictionary.txt",
                                      "personal dictionary",
                                      "project dictionary"])
    s.p("What you teach Lorewrite goes into one of two plain text files. "
        "They have the same format and the same effect; they differ only "
        "in how far they reach.")
    s.table("t_dicts", "The two dictionaries",
            ["Dictionary", "File", "Applies to"], [
        ["Project dictionary", "`dictionary.txt` in the project folder, "
         "beside `project.toml`.", "That project only. It travels with "
         "the project when you copy or back it up, and is kept by version "
         "control."],
        ["Personal dictionary", "`dictionary.txt` in Lorewrite's state "
         "folder (`~/.local/state/lorewrite`, or the folder named by "
         "`LOREWRITE_STATE_DIR`).", "Every project you open on this "
         "computer."],
    ], [0.22, 0.46, 0.32])
    s.p("Put a word of your world (a place, an invented material, a "
        "shared slang) in the project dictionary; put a word that is yours "
        "wherever you write (a name you often use, a spelling you prefer) "
        "in the personal one. The format is one word or phrase per line. "
        "Blank lines and lines that begin with `#` are ignored. A file "
        "that Lorewrite creates begins with a comment that says so:")
    s.code("""\
# One word or phrase per line; these are never flagged as misspelled.
# Lines starting with # and blank lines are ignored.
maglev
Kowloon
sweet rot""")
    s.p("A line with a space in it is a //phrase//. It accepts the words "
        "inside every occurrence of that phrase, in any capitalization and "
        "with any spacing, even if one of them would be underlined on its "
        "own. Adding a term never duplicates a line that is already "
        "there. To remove a word, delete its line in a text editor. In the "
        "desktop application the binder's **Dictionary** row opens the "
        "project file; in the terminal application, **Action · Open "
        "project dictionary** does. The personal dictionary has no "
        "button; open it with any editor.")
    s.attention("`dictionary.txt` is your data, not a cache: it is not in "
                "the `.lorewrite` folder and the `.gitignore` of a new "
                "project does not list it. It is not a scene and not a "
                "note, so it never appears in the sidebar's scene list, the "
                "word counts or the index.")

    s.h2("Turning It Off", idx=["spell check|turning off"])
    s.p("In the terminal application, tick or untick //Underline "
        "misspellings// in Settings (Chapter 15), or choose **Action · "
        "Toggle spell check**. In the desktop application, use the same "
        "box in the Settings dialog. The setting, `spellcheck`, is kept in "
        "`settings.json` and is shared: turning it off in one application "
        "turns it off in the other. With it off, `f6` still opens the fix "
        "window in the terminal application.")

    s.h2("Limits")
    s.bullets([
        "**English only**, with American spelling: //colour// and "
        "//favourite// are underlined, //color// and //favorite// are not. Words in other alphabets are skipped; accented "
        "Latin letters are checked after removing the accents.",
        "**Suggestions come from a list of common words.** They are good "
        "for typing slips (//recieve//, //unnattractive//) and poor for "
        "invented words, which have no right answer to find. For those, "
        "use the dictionary commands rather than a suggestion.",
        "**It cannot tell a correct wrong word from a right one:** "
        "//their// for //there// is a spelling-correct word and is not "
        "flagged.",
        "**Names keep their capitals.** A name taken from a note, or added "
        "with a capital letter, is accepted only with that capital: "
        "//kuroda// is underlined even though //Kuroda// is not. A "
        "lower-case entry accepts any capitalization.",
    ])

    ch_history.build(s, R)
    ch_notes.build(s, R)

    # ============================================================ CH 5
    s.chapter("10", "AI Assistance",
              "Setting up an AI service, and the three features that help "
              "you keep your story consistent. All are proposals you "
              "confirm.")
    s.h2("Overview", idx=["AI|overview"])
    s.p("Lorewrite can use an AI service, called OpenRouter, to help with "
        "your story. This chapter describes how to set it up and the three "
        f"features summarized in {R('t_ai')}, which check and record "
        "consistency. The features that write prose are in Chapter 11. "
        "None of them is needed to write. None runs unless you start it. "
        "And none changes anything until you have reviewed its proposals "
        "and pressed `enter`.")
    s.table("t_ai", "The consistency features",
            ["Feature", "How to start it", "Model used", "What it proposes"],
            [["Find aliases", "`ctrl+l`, or **Action · Find aliases in "
              "this scene**", "Fast", "Other names your prose uses for "
              "your characters and places, to add to their notes as "
              "aliases. Never edits the scene."],
             ["Continuity check", "**Action · Check scene for continuity "
              "issues**", "Strong", "Places where the scene contradicts "
              "your notes."],
             ["Story-bible update", "**Action · Update story bible from "
              "scene**", "Strong", "New facts to add to the //Canon// "
              "section of your notes. Only adds."]],
            [0.19, 0.31, 0.11, 0.39])
    s.p(f"In the desktop application the same features are started from "
        f"the assistant panel ({R('t_aigui')}).")
    s.table("t_aigui", "Starting the consistency features in the two "
            "applications",
            ["Feature", "Terminal application", "Desktop application"], [
        ["Find aliases", "`ctrl+l`", "AI menu (the three dots at the top "
         "of the assistant) \u203a **Find aliases**"],
        ["Continuity check", "**Action · Check scene for continuity "
         "issues**", "**Continuity** quick action"],
        ["Waive an issue", "`space` in the report", "**Dismiss** on its "
         "card"],
        ["Restore waived issues", "**Action · Restore waived continuity "
         "issues (this scene)**", "AI menu \u203a **Restore waived issues**"],
        ["Story-bible update", "**Action · Update story bible from "
         "scene**", "AI menu \u203a **Update story bible**"],
    ], [0.22, 0.38, 0.40])
    s.p("There are three models in all, because the jobs differ. Finding "
        "names is easy and can be done by a small, cheap model (the "
        "//fast// model). Judging whether a scene contradicts your notes "
        "takes a more capable one (the //strong// model). Writing prose "
        "is a third kind of job, with its own //writing// model "
        "(Chapter 11).")
    s.attention("When you start an AI feature, text from your scene "
                "leaves your computer. See //Costs and Privacy// at the "
                "end of this chapter before you use it on anything "
                "confidential.")

    s.h2("Setting Up Your API Key", idx=["API key", "OpenRouter", "keyring", "OPENROUTER_API_KEY"])
    s.p("OpenRouter is a service that gives access to many AI models with "
        "one account. You need your own account and an //API key// (a long "
        "secret string) from openrouter.ai. You pay OpenRouter directly for "
        "what you use; Lorewrite does not.")
    s.p("Lorewrite finds your key in this order: first the environment "
        "variable `OPENROUTER_API_KEY`, then your operating system's "
        "keyring (a secure store for passwords). To store a key in the "
        "keyring from within Lorewrite:")
    s.proc("To store your API key:", [
        "Press `ctrl+p` and choose **Action · Set OpenRouter API key** "
        "(or open **Settings** and press **Set API key…**).",
        f"Paste the key into the box ({R('fig_keyprompt')}) with `ctrl+v` "
        "and press `enter`. The characters are hidden as dots.",
        "Lorewrite says //API key stored in the system keyring//.",
    ])
    s.figure("fig_keyprompt", "keyprompt", "Entering the API key")
    s.idx("clipboard")
    s.p("`ctrl+v` reads your system clipboard (using `wl-paste`, `xclip` or "
        "`xsel`, whichever is installed). The terminal's own paste "
        "command, usually `ctrl+shift+v`, works too. If the keyring is "
        "not available on your system, Lorewrite says //Keyring "
        "unavailable// and the reason, and tells you to set "
        "`OPENROUTER_API_KEY` in the environment instead.")
    s.p("The Settings screen shows whether a key is found: //API key: set "
        "(…a1b2)// shows the last four characters, and //API key: not set — "
        "AI features won't work// means none was found. **Clear API key** "
        "removes the key from the keyring; it cannot remove an environment "
        "variable.")
    s.note("If `OPENROUTER_API_KEY` is set, it is used even when a "
           "different key is stored in the keyring.")
    s.p("In the desktop application, open Settings (the gear at the foot of "
        "the rail) and use the first section, //AI (OpenRouter)//. It says "
        "whether a key is set and where it comes from: //from the "
        "OPENROUTER_API_KEY environment variable// or //stored in the "
        "system keyring//. Paste a key into the box and click **Save "
        "key**; **Clear** removes the keyring's key. Without a key the AI "
        "controls of the assistant are dimmed, and trying one opens "
        "Settings with the message //Add your OpenRouter API key first. "
        "AI features are off until then.//")

    s.h2("Choosing Models", idx=["model", "fast model", "strong model",
                                 "writing model", "model picker",
                                 "OpenRouter|models"])
    s.p("Lorewrite starts with ready-made choices: "
        "`google/gemini-2.5-flash` for the fast model, "
        "`anthropic/claude-sonnet-4.5` for the strong model, and the same "
        "`anthropic/claude-sonnet-4.5` for the writing model. You can "
        "change any of them in **Settings**, either by typing an "
        "OpenRouter model name into the box or by pressing **Choose…** "
        f"beside it. Choose… opens the model picker ({R('fig_picker')}).")
    s.figure("fig_picker", "modelpicker_fast", "The model picker for the "
             "fast model, filtered by the word //gemini//")
    s.p("Lorewrite asks OpenRouter for its current list of models (this "
        "needs a network connection but no key). Type to narrow the list; "
        "each row gives the model's name, its identifier, its price per "
        "million words of input and of output, and how much text it can "
        "consider at once. Use `up` and `down` to move, `enter` to choose, "
        "and `esc` to cancel. For the fast and strong models the list "
        "contains only models that can return answers in the strict "
        "format those features need. For the writing model, which "
        "produces ordinary text, the picker lists the whole catalog "
        f"({R('fig_picker2')}). If the list cannot be loaded, the picker "
        "says //Couldn't load models// and the reason; type a model name "
        "into Settings instead.")
    s.figure("fig_picker2", "modelpicker_writing", "The model picker for "
             "the writing model lists every model, here filtered by "
             "//llama//")
    s.p("A model can be set for every project in Settings, or for one "
        "project by adding an `[ai]` section to that project's "
        f"`project.toml` (see {R('t_models')} and Appendix A).")
    s.p("In the desktop Settings dialog the three rows are //Fast "
        "model//, //Strong model// and //Writing model//, each with a "
        "**Choose…** button that opens a searchable list of the same "
        "catalog under the row (Chapter 15). An empty box means the "
        "default, which is shown in the box in gray; a project that "
        "overrides a model in `project.toml` says so under the row.")
    s.table("t_models", "Which model is used",
            ["Priority", "Source", "Where"], [
        ["1 (highest)", "The project", "`fast_model`, `strong_model` or "
         "`writing_model` in the `[ai]` section of `project.toml`"],
        ["2", "Your settings", "Settings screen; stored in `settings.json`"],
        ["3", "Built-in default", "`google/gemini-2.5-flash` (fast); "
         "`anthropic/claude-sonnet-4.5` (strong and writing)"],
    ], [0.17, 0.25, 0.58])

    s.h2("Find Aliases", idx=["find aliases", "ctrl+l"])
    s.p("Recognizing names you have listed needs no AI. What the AI adds "
        "is finding //other// ways your prose refers to your characters "
        "and places: a description such as //the old smith// for a "
        "character named Borin. It reads the scene and proposes each one "
        "as a new //alias// for that entity's note. Once an alias is in "
        "the note, it is recognized everywhere, in every scene, without "
        "further help (Chapter 6).")
    s.attention("Find aliases never changes your scene. In earlier "
                "versions `ctrl+l` wrapped words in `[[brackets]]`; it "
                "does not any more. Accepting a suggestion only adds "
                "an alias to an entity's note.")
    s.proc("To find aliases:", [
        "Open a scene, and press `ctrl+l`. Lorewrite says //Looking for "
        "aliases…//.",
        f"When the proposals arrive, a review appears ({R('fig_aliasrev')}). "
        "Each line shows the words, the entity they refer to, and the "
        "line number and surrounding text. All are ticked to begin with.",
        "Press `up` and `down` to move, and `space` to tick or untick the "
        "highlighted line. Press `a` to tick them all again.",
        "Press `enter` to add the ticked aliases to the notes, or `esc` "
        "to cancel and change nothing. Lorewrite says //Added N "
        "alias(es) to entity notes//.",
    ])
    s.figure("fig_aliasrev", "aliasreview", "Reviewing alias suggestions. "
             "The scene text is not changed")
    s.p("Lorewrite checks each proposal against your text before showing "
        "it, and drops any that do not match the words actually on the "
        "page, that name an entity you do not have, that are pronouns, "
        "shorter than two or longer than forty characters, already a name "
        "or alias, inside a link, or repeated. If nothing is left, it says "
        "//No new aliases found//. A capitalized first word such as "
        "//The// in //The flyers// is stored in lower case "
        f"(//the flyers//), so that the alias also matches in the middle "
        f"of a sentence. {R('fig_aliasnote')} shows the result in the note "
        "for Kessler-Voss.")
    s.figure("fig_aliasnote", "aliasnote", "The note for Kessler-Voss after "
             "accepting //The flyers//: the alias is added to the list")
    s.p("Text in pending AI drafts (Chapter 11) is ignored, so the line "
        "numbers in the review are always the real line numbers of your "
        "scene.")
    s.h3("In the desktop application")
    s.p("Open a scene, open the AI menu and choose **Find aliases**. When "
        f"the answer arrives a dialog titled **Possible aliases** opens "
        f"({R('fig_galias')}). Each suggestion is a box with the words "
        "highlighted in their sentence and, below, the entity they would "
        "become an alias of. //None// are ticked to begin with: tick the "
        "ones you want, or click **Select all**, then click **Add //N// "
        "aliases**. The scene is not changed. If there is nothing to "
        "suggest, a message says //No new aliases found// with the cost.")
    s.gfigure("fig_galias", "aliasreview", "The Possible aliases dialog. "
              "Ticks are yours to give; the scene is never edited",
              width=330)

    s.h2("Continuity Checking", idx=["continuity", "Contextual Tracker",
                                     "contradiction"])
    s.p("A long story accumulates facts: eye colors, injuries, who has "
        "what, who knows what. Continuity checking (the //Contextual "
        "Tracker//, in the design notes for the program) compares the scene you "
        "are working on with the facts recorded in your notes and reports "
        "anything that contradicts them.")
    s.h3("What it compares", idx=["canon"])
    s.p("For each entity, Lorewrite uses its //canon//. If the note has a "
        "`## Canon (auto)` section (see “Updating the Story Bible” below), "
        "that section is the canon. Otherwise the beginning of the note "
        "(up to 1,500 characters) is used. The scene is then compared with "
        "each entity's canon. The kinds of contradiction reported are "
        f"listed in {R('t_ctypes')}.")
    s.table("t_ctypes", "Kinds of continuity issue",
            ["Type", "Meaning"], [
        ["physical_attribute", "A physical trait changed: eye color, "
         "height, an injury, which arm is a prosthetic."],
        ["timeline", "Events or travel times that cannot fit together."],
        ["character_knowledge", "A character knows something they should "
         "not know yet."],
        ["object_custody", "An object is in the wrong place or hands."],
        ["present_absent", "A character is present where they were "
         "established to be absent, or the reverse."],
        ["spelling_drift", "A name is spelled differently from earlier."],
    ], [0.30, 0.70], mono_cols=(0,))
    s.p("Each issue also has a severity, shown as a mark at the start of "
        "the line: `!` for an error, `?` for a warning and `-` for a note.")
    s.proc("To check a scene:", [
        "Open the scene. Press `ctrl+p` and choose **Action · Check scene "
        "for continuity issues**. Lorewrite says //Checking continuity…//.",
        f"If problems are found, the report appears ({R('fig_cont')}). If "
        "not, you see //No continuity issues found//.",
        "Read each entry. It gives the kind of issue, the entity, the "
        "line of the scene, the exact words that conflict, and a suggested "
        "fix (which is only a suggestion; Lorewrite never changes your "
        "text).",
        "Press `enter` to jump to the line (the report closes), `space` to "
        "waive an issue, and `esc` when you are done.",
    ])
    s.figure("fig_cont", "continuity",
             "A continuity report: Sallow's eyes were established as grey")
    s.p("Pressing `enter` closes the report and opens the scene with the "
        "cursor on the line in question. To go through the list without "
        "leaving it, use `up`, `down` and `space`, and press `esc` when you "
        "are done.")
    s.h3("Waiving an issue", idx=["waiver", "waivers.json", "waive"])
    s.p(f"Sometimes an apparent contradiction is deliberate: a character "
        "lies, or a narrator is unreliable. Press `space` to //waive// the "
        f"issue ({R('fig_waived')}); the entry is marked //(waived)// and "
        "Lorewrite will not report that issue again. Pressing `space` "
        "again in the same report takes the waiver back. Waivers are "
        "saved at once, in the project's `.lorewrite/waivers.json` file, "
        "and identify an issue by its kind, the entity and the "
        "conflicting words, together with the scene it was waived in. "
        "Once you close the report, a waived issue no longer appears in "
        "later checks. To bring a scene's waived issues back, open the "
        "scene and choose **Action · Restore waived continuity issues "
        "(this scene)** from the command palette; Lorewrite says how many "
        "it restored, and the next check reports them again. Waivers made "
        "with an earlier version of Lorewrite did not record a scene and "
        "cannot be restored this way; to reinstate one, edit "
        "`.lorewrite/waivers.json` and remove its code from the list.")
    s.figure("fig_waived", "continuity_waived", "A waived issue")
    s.p("Pending AI drafts (Chapter 11) are removed from the scene before "
        "it is checked: unaccepted AI text is not part of your story yet.")
    s.h3("In the desktop application")
    s.p("Click **Continuity** in the quick actions. A message says how "
        "many possible conflicts were found, with the cost, and one card "
        f"per conflict appears in the Assistant tab ({R('fig_gcont')}). A "
        "card gives the kind of issue and the entity, the words of the "
        "scene that conflict, in quotation marks, and a suggested fix, "
        "which is only a suggestion. **Review passage** scrolls the scene "
        "to the line (it is the desktop's `enter`); **Dismiss** is the "
        "desktop's waive: the issue will not be reported again, and a "
        "message says so. **Restore waived issues** in the AI menu brings "
        "back the open scene's waived issues, as in the terminal "
        "application. If you dismiss by mistake, restore and check again.")
    s.gfigure("fig_gcont", "continuity_card", "A continuity card in the "
              "assistant panel", width=240)
    s.idx("Jev")
    s.note("If the optional helper program Jev is installed on your "
           "computer (as `~/.config/jev/jev.py`), Lorewrite first asks it "
           "a quick question about each entity, so that the more expensive "
           "model is asked only about entities the scene might "
           "contradict. If Jev is not installed, or fails, or answers in a "
           "way Lorewrite cannot read, every entity is checked. In earlier "
           "versions this screening did not take effect even when Jev was "
           "installed; now it does. You can ignore this if you have never "
           "installed Jev.")

    s.h2("Updating the Story Bible", idx=["story bible", "canon|section",
                                          "Canon (auto)"])
    s.p("The canon that continuity checking relies on has to come from "
        "somewhere. You can write it yourself, or you can ask Lorewrite "
        "to propose new facts from a scene you have just written. The "
        "update only //adds//: Lorewrite sends the AI each entity's "
        "existing canon and asks for facts that are new, and nothing "
        "already in the canon is ever changed or removed.")
    s.proc("To update the story bible from a scene:", [
        "Open the scene. Press `ctrl+p` and choose **Action · Update story "
        "bible from scene**. Lorewrite says //Reading the scene for new "
        "canon…//.",
        f"A review appears ({R('fig_bible')}). For each entity it shows, "
        "in order, the entity's name, its existing canon (dimmed), the "
        "reason the AI gives, and then each proposed new fact on a line "
        "of its own. If the scene establishes nothing new, you see //No "
        "new canon found in this scene//.",
        "Use `up` and `down` to move between facts, `space` to tick or "
        "untick the highlighted fact, `a` to tick all, `enter` to apply "
        "and `esc` to cancel. You accept facts one by one.",
        "Lorewrite says //Added canon to N entity note(s)//.",
    ])
    s.figure("fig_bible", "bible", "Reviewing proposed canon: each new fact "
             "is shown in full and accepted on its own")
    s.p("Each accepted fact is added as a line beginning with a hyphen at "
        "the end of the `## Canon (auto)` section of the entity's note. "
        "Lorewrite creates the section at the end of the note if it is not "
        "there. A fact that is already in the section (ignoring capitals "
        "and a final full stop) is skipped. Nothing outside that section "
        "is ever touched, so your own writing in the note is safe, and "
        "running the update on later scenes never removes a fact from "
        "earlier ones.")
    s.p("In the desktop application choose **Update story bible** in the AI "
        f"menu. The **Update the story bible** dialog ({R('fig_gcanon')}) "
        "lists, for each entity, the reason the AI gives and its proposed "
        "new facts, each with its own box; open //Existing canon// to "
        "see what is already there. Tick the facts you want (**Select "
        "all** ticks them all), then click **Add //N// facts**. The "
        "message says //Added canon to N notes.//")
    s.gfigure("fig_gcanon", "canonreview", "The story-bible dialog: new "
              "facts, ticked one by one", width=330)
    s.note("Facts in the review are wrapped, so a long fact is shown in "
           "full. Pending AI drafts (Chapter 11) are removed from the scene "
           "before it is read, so text the AI wrote but you have not "
           "accepted does not become canon.")

    s.h2("Costs and Privacy", idx=["privacy", "cost"])
    s.p("Lorewrite asks OpenRouter to report what each request cost. "
        "You see it in two places: the status bar shows the total for "
        "this session after the first call that reports a cost, as //AI "
        "$0.0153//, and the message that follows each AI call ends with "
        "that call's cost, for example //No new aliases found (AI "
        "$0.0008)// or //AI draft ready — f7 accept · f8 reject (AI "
        "$0.0042)//. The total starts again from nothing each time you "
        "start Lorewrite. If the provider does not report a cost, nothing "
        "is shown.")
    s.p("If an AI service does not answer, Lorewrite gives up after 180 "
        "seconds (three minutes) and tells you the request failed, and "
        "tries one more time before that if the connection drops; earlier "
        "it could wait for many minutes with nothing on the screen. You "
        "can then start the feature again.")
    s.bullets([
        "**Nothing is sent unless you ask.** Lorewrite contacts an AI "
        "service only when you start one of the AI features, and "
        "contacts OpenRouter's public model list only when you open the "
        "model picker.",
        "**What is sent.** For finding aliases: the text of the open "
        "scene, and each entity's name, kind and aliases. For the "
        "continuity check: the scene and the canon of the entities "
        "being checked. For a story-bible update: the scene, and each "
        "entity's name, kind, aliases and existing canon. The writing "
        "features send other text; see Chapter 11. Pending AI drafts are "
        "never sent as part of your scene. OpenRouter passes the text to "
        "the company that runs the model you chose; read their terms.",
        "**What it costs.** OpenRouter charges your account for the amount "
        "of text processed. The model picker shows each model's prices. "
        "The fast default is much cheaper than the strong one; long "
        "scenes cost more.",
        "**Your key.** It is stored in your system keyring, or wherever "
        "you keep your environment variable. It is not written to your "
        "project or to Lorewrite's settings file.",
    ])
    s.p("If a request fails, Lorewrite shows the reason in a message, for "
        "example //Alias search failed//, //Continuity check failed//, "
        "//Story-bible update failed//, //Style guide failed// or //AI "
        "writing failed//, followed by the error. Appendix B lists them.")

    # ============================================================ CH 6
    s.chapter("11", "Writing with AI",
              "Teach Lorewrite your style, then have it draft, expand and "
              "rewrite prose. Everything it writes is a draft you accept "
              "or reject.")
    s.h2("How AI Writing Works", idx=["AI writing", "writing model"])
    s.p("Lorewrite can write for you in three ways, all started with "
        "`ctrl+g`: it can draft new prose at the cursor, expand a short "
        "placeholder that you leave in the text, or rewrite a passage "
        "that you select. To write like //you//, it follows a //style "
        "guide// that it learns from your own scenes.")
    s.p("The rule is the same as everywhere else in Lorewrite: the AI "
        "never changes your prose on its own. What it writes is put into "
        "your scene as a //pending draft//, shown in color, and it stays "
        "a draft until you press `f7` to accept it or `f8` to reject it. "
        "Rejecting puts back exactly what was there before.")
    s.h3("The writing model")
    s.p("Writing uses its own model, the //writing model//, separate from "
        "the fast and strong models of Chapter 10. It is a separate "
        "choice because writing is a different kind of job: what matters "
        "is the quality of the prose and the price per word, and what "
        "comes back is ordinary text, not the strict structured answer "
        "that finding aliases or checking continuity need. So any model "
        "will do, and the picker for this model lists the whole catalog. "
        "The writing model is also the one that learns your style guide. "
        "Its built-in default is `anthropic/claude-sonnet-4.5`; set "
        "your own with **Choose…** in Settings (Chapter 15) or with "
        "`writing_model` in the `[ai]` section of `project.toml` "
        "(Appendix A). You need an API key first (Chapter 10).")

    s.p("Most of this chapter describes the terminal application's keys. "
        "The desktop application does the same things with buttons and "
        f"menus; {R('t_wgui')} lists where.")
    s.table("t_wgui", "Writing with AI in the two applications",
            ["Task", "Terminal application", "Desktop application"], [
        ["Learn a style guide", "**Action · AI: learn style guide from "
         "manuscript**", "**Learn my style** (or **Relearn my style**) on "
         "the //Your style// card; or AI menu \u203a **Learn style guide**"],
        ["Open the style guide", "**Action · Open style guide**",
         "**Style Guide** in the binder, or **Open guide** on the card"],
        ["Draft at the cursor", "`ctrl+g` with nothing selected",
         "`ctrl+g`, or AI menu \u203a **Draft at the cursor…**"],
        ["Expand a placeholder", "`ctrl+g` inside `{{expand: ...}}`",
         "`ctrl+g` inside the placeholder"],
        ["Rewrite a selection", "`ctrl+g` with text selected",
         "`ctrl+g`, or the **Rewrite** quick action"],
        ["Accept, reject one draft", "`f7`, `f8`", "`f7`, `f8`, or the "
         "**Accept** and **Reject** buttons beside the draft"],
        ["Accept, reject all", "**Action · Accept all AI drafts in this "
         "scene**, **Reject all ...**", "AI menu \u203a **Accept all "
         "drafts**, **Reject all drafts**"],
        ["Ask a question", "(not available)", "The question box of the "
         "assistant; **Insert as a draft** under an answer"],
    ], [0.22, 0.38, 0.40])
    s.h2("The Style Guide", idx=["style guide", "style.md"])
    s.p("The style guide is a plain Markdown file named `style.md` in the "
        "project folder, beside `project.toml`. It describes how you write, "
        f"in the six sections listed in {R('t_style')}. It is yours: you "
        "can read it, edit it, and keep it under version control like "
        "your scenes. Lorewrite sends the whole file with every writing "
        "request.")
    s.table("t_style", "Sections of style.md",
            ["Section", "What it holds"], [
        ["Voice", "Point of view, tense, how close the narration is, "
         "register."],
        ["Rhythm & syntax", "Sentence length, paragraphing, pacing."],
        ["Diction", "Word choice, imagery, recurring vocabulary."],
        ["Dialogue", "Tags, punctuation, how characters sound."],
        ["Avoid", "Things you never do."],
        ["Exemplars", "Two or three paragraphs quoted word for word from "
         "your manuscript, each followed by the name of its scene file."],
    ], [0.27, 0.73])
    s.h3("Learning a style guide from your manuscript",
         idx=["style guide|learning"])
    s.p("You do not have to write the guide yourself. Lorewrite can "
        "read your scenes and describe your habits.")
    s.proc("To learn a style guide:", [
        "Write at least a few scenes. Open the command palette with "
        "`ctrl+p` and choose **Action · AI: learn style guide from "
        "manuscript**. Lorewrite saves the open file and says //Learning "
        "your style from N paragraphs…//. If there is nothing to learn "
        "from, it says //Nothing to learn from yet — write some scenes "
        "first//.",
        f"When the answer arrives, a review shows the proposed file "
        f"({R('fig_stylerev')}). Scroll it with `up` and `down`. Nothing "
        "has been written yet.",
        "Press `enter` to save it as `style.md`, or `esc` to discard it. "
        "Lorewrite says //Saved style.md//.",
    ], idx=["learn style guide"])
    s.figure("fig_stylerev", "stylereview", "Reviewing a proposed style "
             "guide before it is saved")
    s.p("Lorewrite gives the AI about six thousand words of your prose to "
        "read, taken from paragraphs spread through every scene. "
        "Headings, paragraphs shorter than 25 words and pending AI drafts "
        "are left out, so the guide describes //your// writing. The AI "
        "describes your voice, rhythm, diction and dialogue and names "
        "the paragraphs that show them best; Lorewrite itself copies "
        "those paragraphs into the Exemplars section word for word, "
        "so the AI never writes your examples for you.")
    s.idx("style.md.bak")
    s.note("If you already have a `style.md`, the review says so, and "
           "saving replaces it after copying the old file to `style.md.bak`. "
           "Only one backup is kept: the next time you learn a guide, the "
           "backup is overwritten with the guide you had before it.")
    s.h3("Opening and editing the guide", idx=["style guide|editing"])
    s.p("Choose **Action · Open style guide** from the command palette. "
        "The guide opens in the editor "
        f"({R('fig_styleguide')}) like a note, and autosaves like "
        "one. If there is no `style.md` yet, Lorewrite first creates one "
        "with the six headings and a hint under each. Edit it freely: add "
        "rules the AI could not know, delete ones that are wrong, or "
        "replace an exemplar with a paragraph you prefer. To return to "
        "your scene, click it in the sidebar or press `alt+left` or "
        "`alt+right`.")
    s.figure("fig_styleguide", "styleguide", "The style guide open in the "
             "editor, like any note")
    s.h3("The Your style card in the desktop application",
         idx=["Your style card", "Learn my style"])
    s.p("At the top of the Assistant tab, under the quick actions, the "
        f"//Your style// card ({R('fig_gstyle1')}) does in one click what "
        "the palette does in two steps. What it says depends on the "
        "state of your project:")
    s.table("t_stylecard", "What the Your style card says",
            ["State", "The card says", "Buttons"], [
        ["No style guide, fewer than 300 words in your scenes",
         "//Write a few hundred words first; then Chisel can learn "
         "your voice from them.//", "**Learn my style**, dimmed"],
        ["No style guide, 300 words or more",
         "//Chisel writes in a generic voice until it learns yours "
         "from your scenes.// The card is outlined to catch your eye.",
         "**Learn my style**"],
        ["A guide you wrote or edited by hand, with no provenance line",
         "//You have a style guide. Relearn it from your scenes, or edit "
         "it by hand.//", "**Relearn my style**, **Open guide**"],
        ["A guide learned by Lorewrite", "//Learned// and the date, //from// "
         "the number of words it was shown, //of your prose.//",
         "**Relearn my style**, **Open guide**"],
        ["The same, when the manuscript has since grown by half and by "
         "at least 1,000 words", "The line above, then //Your manuscript "
         "has grown to// the new total //since; relearn to keep up.// A tag "
         "//Out of date// appears and the card is outlined again.",
         "the same"],
    ], [0.30, 0.46, 0.24])
    s.gfigure("fig_gstyle1", "stylecard_before", "The Your style card "
              "before a guide exists", width=230)
    s.p("Click **Learn my style**. Lorewrite saves the open scene, reads "
        "your scenes as described above, and says //Learning your "
        "style…//. When the answer arrives a dialog titled **Style guide "
        f"learned from your prose** ({R('fig_gstylerev')}) shows the "
        "proposed file in a box that you can //edit//. Nothing is saved "
        "yet. If there is a style guide already the dialog says that "
        "saving replaces it and that a copy is kept as `style.md.bak`. "
        "Click **Save style guide** to write `style.md`, or **Cancel**.")
    s.gfigure("fig_gstylerev", "stylereview", "The learned guide, "
              "editable before it is saved. Its second line is the "
              "provenance line", width=330)
    s.gfigure("fig_gstyle2", "stylecard_after", "The card after "
              "learning: when, and from how much prose", width=230)
    s.p("The second line of the proposal, `<!-- learned 2026-10-01 from "
        "1,099 sampled words; manuscript 1,502 words in 4 scenes -->`, is "
        "the //provenance line//. It is an HTML comment, so Markdown "
        "programs hide it, and it is how the card knows the date, how "
        "much of your prose the AI saw, and how large the manuscript was "
        "(it is compared with the manuscript now to decide when the guide "
        "is out of date). You may delete it, or write a guide by hand "
        "without one; the card then simply cannot say when the guide was "
        "learned and never calls it out of date. The terminal application "
        "writes the same line.")
    s.note("You can use `ctrl+g` without a style guide; the AI then "
           "writes in a general style. The first time you do, Lorewrite "
           "shows the tip //learn a style guide first// once for that "
           "session.")

    s.h2("Writing with ctrl+g", idx=["ctrl+g", "drafting"])
    s.p("`ctrl+g` does one of three things, chosen by where the cursor "
        f"is, as {R('t_modes')} shows. It works in scenes only; in a "
        "note or the style guide it says //Open a scene first//.")
    s.table("t_modes", "The three modes of ctrl+g",
            ["If...", "Mode", "What happens"], [
        ["Text is selected", "Rewrite", "A prompt window opens with the "
         "instruction //Rewrite this in my style.//, which you may edit. "
         "The selection is replaced by the rewrite."],
        ["The cursor is in a `{{expand: ...}}` placeholder", "Expand",
         "No window: the words in the placeholder are the instruction. "
         "The placeholder is replaced by the new prose."],
        ["Otherwise", "Draft", "A prompt window asks what to write. The "
         "result is inserted at the cursor."],
    ], [0.30, 0.14, 0.56])
    s.p("The selection is tested first, so a selection that includes a "
        "placeholder is a rewrite. The AI is given the whole style "
        "guide, about five hundred words of your scene before and "
        "after the cursor, and the notes (or canon) of the characters "
        "and places the scene mentions (up to 1,200 characters each and "
        "6,000 in all). Pending AI drafts are removed from that text. "
        "While it works Lorewrite says //Drafting… (model name)//, and "
        "you can keep writing. The reply is cleaned of code fences, "
        "labels such as //Here's the paragraph:// and quotation marks "
        "around the whole text, and an empty reply is an error.")
    s.h3("Your own prose as examples", idx=["voice samples"])
    s.p("A style guide describes your voice in words. To help the AI match "
        "it, every `ctrl+g` request now also carries about two thousand "
        "words of your own writing as examples. Lorewrite picks whole "
        "paragraphs from your //other// scenes (from the rest of the "
        "scene itself only if it is your only scene), preferring "
        "paragraphs that involve the same characters and places as the "
        "scene you are writing and that have about the same share of "
        "dialogue. Text in pending AI drafts is never used: it is not "
        "yours. The AI is told to imitate your rhythm, paragraph shape, "
        "word choice and punctuation, and never to reuse your events, "
        "images or sentences.")
    s.attention("The examples make every drafting, expanding and "
                "rewriting request larger by roughly two thousand words, "
                "which OpenRouter charges for like any other input. The "
                "cost still appears in the status bar and after each "
                "call (Chapter 10). The examples leave your computer along "
                "with the rest of the request, like the style guide does.")
    s.h3("Draft at the cursor", idx=["draft at cursor"])
    s.proc("To draft new prose:", [
        "Put the cursor where the new text should go: at the end of the "
        "scene, or between two paragraphs. Press `ctrl+g`.",
        f"The prompt window opens ({R('fig_promptdraft')}). Type what you "
        "want, for example //One paragraph: the company flyer's "
        "searchlight finds the window. Rook goes still. Dread, not "
        "panic.// Enter starts a new line in this window; it does not "
        "submit.",
        "Press `ctrl+g` again to submit, or `esc` to cancel. An empty "
        "instruction does nothing.",
        f"After a moment the draft appears at the cursor "
        f"({R('fig_draft')}) and Lorewrite says //AI draft ready — f7 "
        "accept · f8 reject//, followed by the cost.",
    ])
    s.figure("fig_promptdraft", "prompt_draft", "The prompt window for a "
             "draft. The same key that opened it submits it")
    s.figure("fig_draft", "draft", "A pending AI draft at the end of a "
             "scene: colored italics, with the marker comments faded")
    s.p(f"In the desktop application `ctrl+g` opens a box with one line "
        f"({R('fig_ggen')}). Type what you want and press `enter` or click "
        "**Generate**; the box is not multi-line. The draft appears at the "
        f"cursor ({R('fig_gdraft')}) in color and italics, with small "
        "**Accept** and **Reject** buttons after it, and a message says "
        "//AI draft ready: F7 accept, F8 reject// and the cost. The "
        "`<!--ai-->` comments around it are hidden. If you have no style "
        "guide, a second message says //Tip: learn a style guide first "
        "(AI menu, Learn style guide).//")
    s.gfigure("fig_ggen", "generate_dialog", "The desktop prompt for "
              "a draft", width=300)
    s.gfigure("fig_gdraft", "draft", "A pending draft in the desktop "
              "application, with its Accept and Reject buttons", width=300)
    s.p("If the cursor follows a word with no space, Lorewrite puts a "
        "space at the start of the draft so the sentences do not run "
        "together; the space is part of the draft, so rejecting it "
        "leaves your text exactly as it was.")
    s.h3("Expand a placeholder", idx=["expand marker", "placeholder"])
    s.p("A placeholder is a note to yourself, written into the scene "
        "where prose should go later: //{{expand: the lobby of the "
        "Meridian at 3 a.m., wet and humming}}//. Type it like any "
        "other text: two opening braces, the word //expand//, a colon, "
        "your instruction, and two closing braces. The instruction "
        "cannot itself contain braces. Lorewrite fades placeholders so "
        "you can see them.")
    s.proc("To expand a placeholder:", [
        f"Put the cursor anywhere in the placeholder "
        f"({R('fig_expand')}). The edges count.",
        "Press `ctrl+g`. There is no prompt window: the placeholder's "
        "own words are the instruction. If they are empty, Lorewrite "
        "says //Empty {{expand: }} marker — say what to write//.",
        f"The placeholder is replaced by a pending draft "
        f"({R('fig_expanddraft')}). Press `f7` to keep the prose, or "
        "`f8` to get the placeholder back exactly as you wrote it.",
    ])
    s.figure("fig_expand", "expand_marker", "A placeholder in a scene, "
             "faded, with the cursor inside it")
    s.figure("fig_expanddraft", "expand_draft", "The placeholder replaced "
             "by a pending draft. The marker comment now carries a short "
             "id")
    s.h3("Rewrite a selection", idx=["rewrite selection"])
    s.proc("To rewrite a passage:", [
        "Select the passage that feels wrong, with the mouse or with "
        "`shift` and the arrow keys.",
        f"Press `ctrl+g`. The prompt window opens with //Rewrite this in "
        f"my style.// already filled in ({R('fig_promptrewrite')}). Keep "
        "it, or change it, for example to //Shorter, and colder.//",
        "Press `ctrl+g` to submit. The passage is replaced by a pending "
        f"draft ({R('fig_rewrite')}). Press `f7` to keep the rewrite, or "
        "`f8` to restore your original, word for word.",
    ])
    s.figure("fig_promptrewrite", "prompt_rewrite", "The prompt window "
             "for a rewrite, prefilled")
    s.figure("fig_rewrite", "rewrite_draft", "A rewrite, pending. Your "
             "original is safe and comes back on `f8`")
    s.p("In the desktop application, select the passage and press "
        f"`ctrl+g` or click **Rewrite** in the quick actions. The box "
        f"titled **Rewrite the selection** ({R('fig_grew')}) is filled "
        "in with //Rewrite this in my style.// and selected, so typing "
        "replaces it. If you choose **Rewrite** with nothing selected, a "
        "message says //Select a passage in the text first, then choose "
        "Rewrite.//  To expand a placeholder, put the cursor in it "
        "(click it) and press `ctrl+g`: the desktop also uses the "
        "placeholder's words as the instruction, and says //Empty "
        "{{expand: }} marker: say what to write.// if there are none.")
    s.gfigure("fig_grew", "rewrite_dialog", "The desktop prompt for a "
              "rewrite", width=300)
    s.gfigure("fig_grewd", "rewrite_draft", "A pending rewrite; Reject "
              "restores the original sentence", width=300)
    s.p("If you switch to another scene while the AI is working, the "
        "draft is thrown away: Lorewrite says //Scene changed while "
        "drafting — draft discarded//. The same happens to a rewrite or "
        "expansion if the words it was to replace have changed or cannot "
        "be found uniquely: //The text changed while drafting — draft "
        "discarded//. The cost of the call is still counted.")

    s.h2("Pending AI Text", idx=["pending draft", "AI draft"])
    s.h3("How it looks")
    s.p("Pending text is shown in italics, in a color that Lorewrite "
        "chooses to stand out from your prose, your links and the orange "
        "of links with no note, and on a slightly tinted background. The "
        "marker comments around it are faded. On Omarchy the color is "
        "picked from your theme; elsewhere it is green. In the gray "
        "figures of this book a draft shows as italic text on a dark "
        "tint. While the cursor is inside a draft, the status bar says "
        "//AI draft — f7 accept · f8 reject//.")
    s.p("In the desktop application a pending draft is colored the same "
        "way, and the buttons **Accept** and **Reject** after it do what "
        "`f7` and `f8` do. The cost of each call is in the status bar "
        f"({R('fig_gcost')}).")
    s.gfigure("fig_gcost", "draftbar", "A draft with its buttons", width=300)
    s.h3("Where it is stored", idx=[".drafts folder", "marker (AI)"])
    s.p("A pending draft is part of the scene file. It sits between two "
        "HTML comments, which most Markdown programs, such as Obsidian, "
        "do not display. A draft that is only inserted looks like this:")
    s.code("""\
Rook put the clove out on the counter.<!--ai--> He did not look back at
the koi holo.<!--/ai-->""")
    s.p("A draft that replaced something (a rewrite or an expanded "
        "placeholder) also carries a short //id//, six lower-case letters "
        "and digits:")
    s.code("""\
<!--ai id="k3f9q2"-->The shard sat in Rook's pocket, cold and exact.<!--/ai-->""")
    s.p("The text that was replaced is kept in a small file named for the "
        "scene, in a folder called `.drafts` at the top of the project: "
        "`.drafts/manuscript__03-the-stairwell.md.json` for the scene "
        "`manuscript/03-the-stairwell.md` (in a project with parts the "
        "part's folder is in the name too). It maps each id to the "
        "original words:")
    s.code("""\
{
  "k3f9q2": "The shard sat in Rook's pocket like a coin from another country."
}""")
    s.p("Nothing is hidden in the prose beyond the short marker. The "
        "`.drafts` folder is part of your project, not a cache: do not "
        "delete it while drafts are pending, and keep it with the project "
        "when you copy or back it up. The `.gitignore` made for a new "
        "project does not list it, so version control keeps it. Lorewrite "
        "deletes each entry when you accept or reject the draft, removes "
        "the file when it is empty, and moves or deletes it together with "
        "its scene (Chapter 4).")
    s.h3("Accept and reject", idx=["accept draft", "reject draft", "f7", "f8"])
    s.p(f"Put the cursor inside a draft, or at either edge of it, and use "
        f"the keys in {R('t_draftkeys')}. If the cursor is not in a draft "
        "Lorewrite says //No AI draft under the cursor//.")
    s.p("In the desktop application, **AI menu \u203a Accept all drafts** and "
        "**Reject all drafts** apply to every draft in the open scene, and "
        "an answer in the assistant's conversation can be put into the "
        "scene as a draft with its **Insert as a draft at the cursor** "
        "button (the icon of a cursor in a text box); the message is "
        "//Inserted as an AI draft: F7 accept, F8 reject.// If a reject "
        "cannot find an original, the message is //N draft(s) left: the "
        "original text is missing. Accept it or edit by hand.//")
    s.table("t_draftkeys", "Keys for pending AI drafts",
            ["Key or command", "Effect", "Message"], [
        ["f7", "Accept the draft under the cursor: the markers go and the "
         "words are ordinary text.", "AI draft accepted"],
        ["f8", "Reject the draft under the cursor: what it replaced is put "
         "back, or, for an insertion, the draft is removed.",
         "AI draft rejected"],
        ["**Action · Accept all AI drafts in this scene**", "Accept every "
         "draft in the open scene.", "N AI draft(s) accepted"],
        ["**Action · Reject all AI drafts in this scene**", "Reject every "
         "draft in the open scene.", "N AI draft(s) rejected"],
    ], [0.33, 0.45, 0.22], mono_cols=(0,))
    s.p("Both keys work while you are typing in the editor. (`f7` used to "
        "select all text; that is now `f5`.) Accepting and rejecting are "
        "edits like any other, so `ctrl+z` undoes them. If a scene has no "
        "drafts, the //all// commands say //No AI drafts in this scene//.")
    s.attention("Reject refuses to act if the original text of a draft is "
                "missing, for example because the `.drafts` file was "
                "deleted or edited. Lorewrite will not delete your prose "
                "because a lookup failed. It says //Original text for this "
                "draft is missing — accept it or edit by hand//, and "
                "changes nothing. You can still accept the draft. With "
                "//Reject all//, drafts whose original is present are "
                "rejected and the rest are left, with a message saying "
                "how many.")
    s.note("If you delete part of a marker by hand, the damaged marker is "
           "treated as ordinary text: the draft is no longer pending, and "
           "the leftover `<!--ai-->` pieces stay in your scene until you "
           "delete them. Accept or reject a draft with `f7` or `f8` "
           "rather than by deleting its markers.")
    s.h3("What pending text is kept out of", idx=["pending draft|excluded"])
    s.p("Unaccepted AI text is not your story yet, so the rest of "
        "Lorewrite ignores it:")
    s.bullets([
        "**Word counts** in the status bar, for the scene and the "
        "project.",
        "**Continuity checks** and **story-bible updates**: the scene is "
        "sent to the AI as if every draft had been rejected.",
        "**Find aliases**: drafts are blanked out, and line numbers stay "
        "true.",
        "**Backlinks and the index**: names inside a draft are not "
        "counted, and the lines still point at the right places.",
        "**Style learning**: drafts are not part of the sample of your "
        "prose.",
        "**The context for later writing**: a new draft is written "
        "without seeing earlier pending ones.",
    ])
    s.p("Once you accept a draft, all of these treat it as ordinary text.")

    s.h2("What the Writing Features Send", idx=["privacy|writing"])
    s.p("Like the features of Chapter 10, these send text to OpenRouter, "
        "and to the company that runs the writing model, when you start "
        "them, and to no one otherwise. Learning a style guide sends about "
        "six thousand words of your prose, as numbered paragraphs with "
        "their scene file names. `ctrl+g` sends your style guide, about "
        "a thousand words of the scene around the cursor, the notes of the "
        "characters and places the scene mentions, and your instruction; "
        "about two thousand words of your other scenes as examples of "
        "your voice (see “Your own prose as examples” in Chapter 11); "
        "for a rewrite, it also sends the selected passage. The desktop "
        "assistant's question box sends your question, the style guide, "
        "the notes, and the text of the open scene or, in //Project// "
        "scope, the titles of all scenes and the canon of every note, "
        "plus the last few turns of the conversation. Each call's "
        "cost appears in the message that follows it and in the status "
        "bar (Chapter 10).")

    s.h2("Walkthrough: Writing in the Residual Project",
         idx=["tutorial|writing"])
    s.p("This walkthrough uses the Residual example that is supplied with "
        "Lorewrite (Appendix C says how to open a copy of it). You need "
        "an API key set up (Chapter 10). The figures in this chapter were "
        "made with it, so what you see should look much like them, though "
        "the AI's words will differ.")
    s.proc("Teach Lorewrite your style:", [
        "Open the project. Press `ctrl+p`, type //learn//, and choose "
        "**Action · AI: learn style guide from manuscript**.",
        f"Read the proposed guide ({R('fig_stylerev')}). Scroll to the "
        "Exemplars at the end and check that they are paragraphs of your "
        "own. Press `enter` to save.",
        "Choose **Action · Open style guide**, and add one rule of your "
        "own under **Avoid**. Go back to your scenes.",
    ])
    s.proc("Draft a paragraph:", [
        "Open the last scene, //Ghost in the Ice//, and put the cursor at "
        "the end. Press `ctrl+g`.",
        "Type the instruction of "
        f"{R('fig_promptdraft')} and press `ctrl+g` again.",
        f"Read the draft ({R('fig_draft')}). Look at the word count in "
        "the status bar: it does not include the draft. Press `f7` to "
        "accept it. The count now includes it.",
    ])
    s.proc("Expand a placeholder:", [
        "Open //Capsule 7-19//. Above the line //Rook climbed the "
        "ladder and looked in.// type a line reading "
        "`{{expand: the lobby of the Meridian at 3 a.m., wet and "
        "humming}}`.",
        "Put the cursor inside it and press `ctrl+g`. Read the draft. "
        "Press `f8` to reject it and see that the placeholder is back.",
    ])
    s.proc("Rewrite a sentence:", [
        "Open //The Stairwell//. Select the sentence //The shard sat in "
        "Rook's pocket like a coin from another country.//",
        "Press `ctrl+g`, then `ctrl+g` again to accept the suggested "
        "instruction. When the rewrite appears, open the `.drafts` folder "
        "in a file manager and look at the small file inside. Press `f8` "
        "and see that the folder disappears and your sentence is back.",
    ])

    ch_aids.build(s, R)
    ch_inspiration.build(s, R)
    ch_export.build(s, R)

    # ============================================================ CH 7
    s.chapter("15", "Settings Reference",
              "Every setting, where it is kept, and what it does.")
    s.h2("The Settings Screen", idx=["Settings screen"])
    s.p(f"Open the Settings screen ({R('fig_settings')}) from the command "
        "palette (**Action · Settings**), or by pressing `s` on the launch "
        "screen. It has the fields listed in "
        f"{R('t_settings')}.")
    s.figure("fig_settings", "settings_v4", "The Settings screen with a "
             "project open, showing the model rows, the Spelling box, the "
             "writing goal and the History box")
    s.table("t_settings", "Fields of the Settings screen",
            ["Field", "Effect", "Stored in"], [
        ["API key status", "Shows whether a key is found, and its last "
         "four characters.", "(not stored)"],
        ["Set API key…", "Asks for a key and stores it in the system "
         "keyring.", "Keyring"],
        ["Clear API key", "Removes the key from the keyring.", "Keyring"],
        ["Fast model (linking)", "Model used by Find aliases. Empty "
         "means the default.", "`settings.json`"],
        ["Strong model (continuity)", "Model used by continuity checks "
         "and story-bible updates. Empty means the default.",
         "`settings.json`"],
        ["Writing model (drafting & rewrites)", "Model used by `ctrl+g` and "
         "by learning the style guide (Chapter 11). Empty means the "
         "default.", "`settings.json`"],
        ["Image model (inspiration pictures, about $0.03 each)", "Model "
         "that draws the pictures of Chapter 13. Empty means "
         "`google/gemini-3.1-flash-lite-image`. Its picker lists only "
         "models that produce images.", "`settings.json` (`image_model`)"],
        ["Image style (added to every picture description; empty = off)",
         "A phrase added to every description before the picture is "
         "drawn. Empty turns it off; untouched, it keeps the built-in "
         "default.", "`settings.json` (`image_style`)"],
        ["Choose…", "Opens the model picker to fill in the box beside "
         "it. The picker for the writing model lists the whole catalog; "
         "the others list only models with structured output.",
         "(not stored)"],
        ["Side padding (0–8)", "Blank space, in characters, at each side "
         "of the editor. Whole numbers from 0 to 8; other values are "
         "brought into that range. Shown only when a project is open.",
         "`project.toml`"],
        ["Line numbers", "Show line numbers in the editor. Shown only "
         "when a project is open.", "`project.toml`"],
        ["Underline misspellings", "Underline misspelled words in scenes "
         "(Chapter 7). Ticked by default. Shown only when a project is "
         "open.", "`settings.json`"],
        ["Daily word target (0 = off)", "How many words you aim to write "
         "each day; 0 turns the target off. A whole number from 0 to "
         "100,000. It decides what counts toward your streak (Chapter 12). "
         "A bad entry gives //The daily target must be a number from 0 to "
         "100,000//.", "`settings.json`"],
        ["Snapshot a scene the first time it is edited each day", "A safety "
         "net: before the first change you save to a scene on a given day, "
         "its earlier text is kept as a snapshot (Chapter 8). Ticked by "
         "default.", "`settings.json`"],
        ["Save", "Stores the models, the spelling box, the goal and "
         "the snapshot box and, if a project is "
         "open, the editor settings, and closes the screen. A message says "
         "//Settings saved//.", ""],
    ], [0.24, 0.52, 0.24])
    s.p("The screen is compact: the boxes are one line tall so that all "
        "three model rows, the editor settings, the Spelling box and the "
        "buttons fit in a window about 48 rows high. **Save** applies every field at once; the padding and line "
        "numbers change immediately. Pressing `esc` closes the screen and "
        "discards changes to the boxes. (The key buttons act at once and "
        "are not undone by `esc`.) From the launch screen, with no "
        "project open, the editor settings (side padding and line numbers) are left out; the rest is shown.")
    s.figure("fig_settings2", "settings_nokey_launch",
             "The Settings screen when no project is open (from the launch "
             "screen): the editor settings are left out")
    s.h2("The Settings Dialog of the Desktop Application",
         idx=["Settings dialog"])
    s.p(f"Open the Settings dialog ({R('fig_gsettings')}) with the gear at "
        "the foot of the activity rail, with **More \u203a Settings…** in the "
        "title bar, or by trying an AI feature before you have a key. It "
        f"has sections for the key, the models, the editor (with the "
        f"spelling box), your writing goals and history ({R('t_gsettings')}). **Save** applies "
        "everything at once and closes the dialog; **Cancel** or `esc` "
        "discards your changes to the boxes. (**Save key** and **Clear** "
        "act at once.)")
    s.gfigure("fig_gsettings", "settings", "The desktop Settings dialog",
              width=330)
    s.table("t_gsettings", "Fields of the desktop Settings dialog",
            ["Field", "Effect", "Stored in"], [
        ["API key box, **Save key**, **Clear**", "Store or remove the "
         "OpenRouter key. The line above says whether a key is set and "
         "where it comes from.", "Keyring"],
        ["Fast, Strong, Writing and Image model; Image style", "As in the terminal "
         "application. The default is shown in gray in an empty box; "
         "**Choose…** opens a list under the row.", "`settings.json`"],
        ["Text size (90%, 100%, 110%, 125%)", "The size of the page text. "
         "The status bar's percentage steps through the same values.",
         "`settings.json` (`gui_zoom`)"],
        ["Show hard-wrapped lines as flowing paragraphs", "Display only; "
         "files are never changed. Ticked by default.",
         "`settings.json` (`gui_reflow`)"],
        ["Underline misspellings", "Spell check on or off (Chapter 7). "
         "Shared with the terminal application.",
         "`settings.json` (`spellcheck`)"],
        ["Daily word target", "Words per day you aim for; 0 turns the "
         "target off. A whole number from 0 to 100,000; otherwise the "
         "message is //The daily target must be a whole number from 0 to "
         "100,000.// Shared with the terminal application (Chapter 12).",
         "`settings.json` (`daily_target`)"],
        ["Snapshot a scene the first time it is edited each day", "The "
         "automatic daily snapshot of Chapter 8. Shared with the terminal "
         "application. Ticked by default.",
         "`settings.json` (`auto_snapshot`)"],
    ], [0.30, 0.46, 0.24])
    s.gfigure("fig_gpicker", "settings_picker", "The list opened by "
              "**Choose…** on the writing model, filtered by //llama//. "
              "Each row gives the model's name, its identifier and its "
              "prices", width=330)
    s.p("The list is fetched from OpenRouter when you open it (this needs "
        "a network connection but no key), shows up to 80 matches, and "
        "narrows as you type; every word you type must appear in the "
        "model's name or identifier. Click a row to put its identifier in "
        "the box. For the fast and strong models it lists only models "
        "that can return strict structured answers; for the writing "
        "model it lists everything. If it cannot be loaded it says //Could "
        "not load the model list// and the reason; you can still type a "
        "model identifier. The desktop editor settings are not per "
        "project: unlike the terminal application's side padding and line "
        "numbers, they apply to every project.")

    s.h2("Settings Files", idx=["project.toml|settings", "settings.json"])
    s.p("Settings live in three places, according to what they affect.")
    s.table("t_where", "Where settings are stored",
            ["Location", "Holds", "Affects"], [
        ["`project.toml` in the project", "Title, author, and the `[editor]`, "
         "`[ai]`, `[manuscript]` and `[collections]` sections.",
         "That project only."],
        ["`~/.local/state/lorewrite/settings.json`", "`tour_seen`, "
         "`fast_model`, `strong_model`, `writing_model`, `spellcheck`, "
         "`daily_target`, `auto_snapshot`, `gui_zoom`, `gui_reflow`.",
         "All projects."],
        ["`~/.local/state/lorewrite/stats/<id>.json`", "Your writing "
         "numbers for one project (Chapter 12).", "That project, on this "
         "computer."],
        ["`~/.local/state/lorewrite/dictionary.txt`", "Your personal "
         "dictionary (Chapter 7).", "All projects."],
        ["System keyring", "Your OpenRouter API key.", "All projects."],
    ], [0.36, 0.38, 0.26])
    s.table("t_env", "Environment variables",
            ["Variable", "Effect"], [
        ["OPENROUTER_API_KEY", "The API key. Takes precedence over the "
         "keyring."],
        ["LOREWRITE_STATE_DIR", "Folder for `recent.json` and "
         "`settings.json`, instead of `~/.local/state/lorewrite`."],
    ], [0.30, 0.70], mono_cols=(0,))
    s.p("All of the settings in `project.toml` are described in "
        "Appendix A.")

    # ============================================================ CH 8
    s.chapter("16", "Command and Key Reference",
              "Every key, every command-palette entry, and the keys of "
              "every dialog.")
    s.h2("Keys in the Main Window", idx=["keys|main window",
                                         "key bindings", "question mark", "terminal limits"])
    s.p("This section is for the terminal application; the desktop "
        f"application's keys are in {R('t_gkeys2')}, further on.")
    s.table("t_keys", "Keys in the main window of the terminal application",
            ["Key", "Action", "See"], [
        ["ctrl+n", "New scene.", "Chapter 4"],
        ["alt+left, alt+right", "Previous scene, next scene.", "Chapter 4"],
        ["ctrl+p", "Open the command palette.", "This chapter"],
        ["ctrl+j", "Open the note for the name under the cursor; with a "
         "name selected, or on a link with no note, create the note.",
         "Chapter 6"],
        ["ctrl+l", "AI: find other names your prose uses for your "
         "characters and places, and add them as aliases (never edits "
         "the scene).", "Chapter 10"],
        ["ctrl+g", "AI write: draft at the cursor (prompt window), expand "
         "the `{{expand: ...}}` placeholder under the cursor, or rewrite "
         "the selection. Also submits the prompt window.", "Chapter 11"],
        ["f7", "Accept the AI draft under the cursor.", "Chapter 11"],
        ["f8", "Reject the AI draft under the cursor.", "Chapter 11"],
        ["f6", "Spell check: go to the next misspelled word and open the "
         "fix window.", "Chapter 7"],
        ["f5", "Select all text in the editor. (It was `f7` before "
         "AI drafts.)", "Chapter 4"],
        ["ctrl+s", "Save now.", "Chapter 4"],
        ["ctrl+b", "Hide or show the sidebar.", "Chapter 4"],
        ["f11", "Writer mode.", "Chapter 4"],
        ["f9", "Rebuild the index from disk.", "Chapter 6"],
        ["f1", "Show the help screen. Works everywhere, including while "
         "you type in the editor.", "This chapter"],
        ["?", "Also shows the help screen, but only when the focus is not "
         "in the editor; in the editor it types a question mark.",
         "This chapter"],
        ["ctrl+q", "Quit.", "Chapter 2"],
    ], [0.28, 0.54, 0.18], mono_cols=(0,))
    s.note("`esc`, `f1` or `?` closes the help screen again.")
    s.p("Two keys that people often try do not work in terminals. "
        "`ctrl+[` is the same key as `esc`, and `ctrl+enter` is not "
        "delivered to programs by most terminals. That is why scenes are "
        "flipped with `alt+left` and `alt+right`, and writer mode is on "
        "`f11`. `f7` is used for accepting AI drafts and `f6` for fixing "
        "spelling, which is why select-all is on `f5`. The keys inside dialogs are listed in "
        f"{R('t_dialogkeys')}.")

    s.h2("The Command Palette", idx=["command palette", "ctrl+p", "palette|actions"])
    s.p(f"Press `ctrl+p` to open the palette ({R('fig_palette')}). It "
        "lists everything you can do, each with a short explanation. Type "
        f"to narrow the list ({R('fig_palette2')}); the letters you type "
        "need not be together. Use `up` and `down` to move, `enter` to "
        "choose, and `esc` to close.")
    s.figure("fig_palette", "palette", "The command palette")
    s.figure("fig_palette2", "palette_ai", "Searching the palette for "
             "//ai//: the AI commands, with their explanations")
    s.p("Every entry starts with a category word, so that you can type it "
        f"to narrow the list. The categories are in {R('t_cats')}.")
    s.table("t_cats", "Categories in the command palette",
            ["Category", "Choosing it", "Example"], [
        ["Scene ·", "Opens that scene.", "`Scene · Capsule 7-19`"],
        ["Entity ·", "Opens that note. Names and aliases are searched.",
         "`Entity · Dace Kuroda (character)`"],
        ["Link ·", "Types the entity's name into your text at the "
         "cursor.", "`Link · Wren`"],
        ["Research ·", "Opens that research note (Chapter 9).",
         "`Research · Capsule hotels`"],
        ["Action ·", "Runs a command; see the next table. A few commands "
         "about the open scene carry the category //Scene · // instead "
         "(//Chapter · // when the manuscript's unit is chapters).",
         "`Action · New scene`"],
    ], [0.16, 0.44, 0.40])
    s.p("Among the scenes and before the entities, the palette also lists "
        "a few general commands supplied by the terminal toolkit "
        "Lorewrite is built on: //Keys// (help for the focused widget), "
        "//Maximize//, //Quit//, //Screenshot// and //Theme// (change "
        "the color theme). They are not part of Lorewrite and are not "
        "described further here.")
    s.add(CondPageBreak(160))
    s.table("t_actions", "Palette actions",
            ["Entry", "What it does", "Key"], palette_rows(),
            [0.33, 0.49, 0.18], mono_cols=(2,))
    s.p("Each is shown in the palette with the prefix //Action ·// unless "
        "the table names another category. When the manuscript's unit is "
        "//chapter// (Chapter 5) the words //scene// and //Scene// in the "
        "palette become //chapter// and //Chapter//; the table gives the "
        "scene wording. The git entries appear only when they apply: "
        "**Commit changes** for a project that is in a repository, "
        "**Push** when it also has a remote, **Initialize git for this "
        "project** when it is not in one yet. "
        "//Return to main menu// saves your work and shows the launch "
        "screen; choose another project, or press `q` to stay where you "
        "were.")

    s.h2("Keys in Dialogs and Reviews", idx=["keys|dialogs", "review screens"])
    s.table("t_dialogkeys", "Keys in dialogs and review screens",
            ["Screen", "Keys"], [
        ["Text prompts (new scene, rename, new note, project folder)",
         "Type, then `enter` to accept. `esc` cancels."],
        ["Confirmation (delete a scene)",
         "`y` or the confirm button accepts. `n`, `esc` or **Cancel** "
         "declines."],
        ["Kind of a new note", "Click **Character** or **Place**; `esc` "
         "cancels."],
        ["Alias review (`ctrl+l`)", "`space` tick or untick; `a` tick "
         "all; `enter` apply; `esc` cancel."],
        ["Continuity report", "`space` waive or reinstate; `enter` jump "
         "to the line and close the report; `esc` close."],
        ["Story-bible review", "`space` tick or untick a fact; `a` tick "
         "all; `enter` apply; `esc` cancel."],
        ["Scene details form", "`tab` next field; right arrow accepts a "
         "suggested name; `enter` or `ctrl+s` saves; `esc` cancels "
         "(Chapter 5)."],
        ["Trash", "`enter` or `r` restore; `d` delete forever; `e` empty "
         "the Trash; `esc` close (Chapter 5)."],
        ["Collections", "`space` or `enter` tick; `n` new; `r` rename; `c` "
         "next colour; `d` delete; `esc` close (Chapter 5)."],
        ["Snapshots", "`enter` or `c` compare; `r` restore; `d` delete; "
         "`n` new snapshot; `a` snapshot all; `esc` close (Chapter 8)."],
        ["Compare", "`r` restore this snapshot; `esc` back to the list "
         "(Chapter 8)."],
        ["Comments", "`enter` jump to it; `r` resolve or reopen; `e` edit; "
         "`d` delete; `esc` close (Chapter 9)."],
        ["Assistant window", "`enter` send; `ctrl+r` chat or research "
         "mode; `ctrl+o` open a cited note; `ctrl+s` save the answer to "
         "notes; `ctrl+t` saved conversations; `ctrl+n` new chat; `esc` "
         "close (Chapter 9)."],
        ["Saved conversations", "`enter` open; `r` rename; `d` delete; "
         "`n` new chat; `esc` back (Chapter 9)."],
        ["Brainstorm", "`enter` or `d` draft from the idea; `s` save it to "
         "notes; `esc` close (Chapter 12)."],
        ["Session stats", "`esc` or `enter` close (Chapter 12)."],
        ["Choice lists (sprint length, which part)", "`up`, `down`, "
         "`enter` choose; `esc` cancel."],
        ["Spelling window (`f6`)", "`1` to `5` or `enter` replace; `a` add "
         "to the project dictionary; `p` add to your dictionary; `i` "
         "ignore; `esc` cancel."],
        ["Prompt window (`ctrl+g`)", "Type the instruction; `enter` "
         "starts a new line; `ctrl+g` submit; `esc` cancel."],
        ["Style guide review", "`up`, `down` scroll; `enter` save "
         "`style.md`; `esc` discard."],
        ["Settings", "Type in a field, then press **Save**. `esc` closes "
         "without saving the boxes."],
        ["Model picker", "Type to filter; `up`, `down`, `pageup`, "
         "`pagedown` move; `enter` choose; `esc` cancel."],
        ["API key box", "`ctrl+v` paste, `enter` store, `esc` cancel."],
        ["First-run tour", "`space`, `enter`, `right` next; `left` back; "
         "`esc` close."],
        ["Help screen", "`esc`, `f1` or `?` close."],
        ["Launch screen", "See " + R("t_launchkeys") + "."],
    ], [0.40, 0.60])

    s.h2("The Help Screen", idx=["help screen"])
    s.p("The help screen, opened with `f1` (or with `?` when the focus is "
        f"outside the editor), is shown in {R('fig_help')}. It lists the "
        "keys, what the palette adds, and how names and links work; "
        "`esc`, `f1` or `?` closes it.")
    s.figure("fig_help", "help", "The help screen")
    s.p(f"The keys it names are the ones in {R('t_keys')}. The screen is "
        "100 columns wide, or as wide as your window if that is "
        "narrower, and scrolls if your window is too short to show all of "
        "it.")

    s.h2("Keys of the Desktop Application", idx=["keys|desktop reference"])
    s.p("The desktop window shares the names of most terminal keys. "
        f"{R('t_gkeys2')} is complete; where a key does something "
        "different elsewhere in the window, both uses are given.")
    s.table("t_gkeys2", "Keys of the desktop application",
            ["Key", "Action", "See"], [
        ["ctrl+k", "Quick switcher over every scene and note.", "Chapter 3"],
        ["ctrl+n", "New scene.", "Chapter 4"],
        ["ctrl+s", "Save now.", "Chapter 4"],
        ["f11", "Focus mode.", "Chapter 4"],
        ["ctrl+j", "In the editor: open the note under the cursor, or "
         "make one for the selected name. Anywhere else: put the cursor "
         "in the assistant's question box.", "Chapter 6"],
        ["ctrl+click", "Open the note under the pointer in the Notes tab.",
         "Chapter 6"],
        ["ctrl+g", "AI: draft at the cursor, expand the placeholder under "
         "it, or rewrite the selection.", "Chapter 11"],
        ["f7, f8", "Accept, reject the AI draft under the cursor.",
         "Chapter 11"],
        ["ctrl+.", "Spelling popover for the word under the cursor, or "
         "for the selected phrase.", "Chapter 7"],
        ["ctrl+z, ctrl+y", "Undo, redo.", "Chapter 3"],
        ["enter (quick switcher)", "Open the highlighted row; `up` and "
         "`down` move, `esc` closes.", "Chapter 3"],
        ["enter (question box)", "Send the question; `shift+enter` starts "
         "a new line.", "Chapter 3"],
        ["esc", "Close a dialog, menu or popover.", "Chapter 3"],
    ], [0.24, 0.58, 0.18], mono_cols=(0,))
    s.note("The terminal application's `ctrl+p`, `ctrl+l`, `ctrl+b`, "
           "`alt+left`, `alt+right`, `f1`, `f5`, `f6` and `f9` have no key "
           "in the desktop window; the buttons and menus below take their "
           "place.")
    s.h2("Menus of the Desktop Application", idx=["menus (desktop)"])
    s.table("t_gmenus", "Menus and what is in them",
            ["Menu (how to open it)", "Entries"], [
        ["Scene and part options (three dots at the top of the binder)",
         "**New scene**, **New part…**, **Rename scene…**, **Move up**, "
         "**Move down**, **Move scene to part…**, **Move to Unplaced "
         "Scenes** (**Place in the book…** for an unplaced scene), "
         "**Collections…**, **History (snapshots)…**, **Delete scene…**; "
         "then, under //parts//: **Rename part…**, **Move part up**, "
         "**Move part down**, **Delete empty part…**; under //research//: "
         "**New research note…**, **New research note from a link…**, "
         "**Move this research note to the Trash…**; **Open Trash…**; and "
         "**Export…**. "
         "Scene entries are dimmed when no scene is open, part entries "
         "when no part is in focus. With the unit set to chapters, "
         "//scene// reads //chapter//."],
        ["More (three dots in the title bar)", "**Switch project…**, "
         "**Export…**, **Rebuild the link index**, **Call scenes “chapters”** (or "
         "**Call chapters “scenes”**), **Settings…**."],
        ["AI menu (three dots at the top of the assistant)", "**New chat**, "
         "**Conversation history…**, **Draft at the cursor…**, **Find "
         "aliases**, **Update story bible**, **Learn style guide**, "
         "**Accept all drafts**, **Reject all drafts**, **Restore waived "
         "issues**."],
        ["Draft badge (title bar or status bar)", "**Start draft N…** "
         "(Chapter 8)."],
        ["Git state (status bar)", "**Initialize git for this project…**; "
         "or **Commit N changes…**, **Push N commits to the remote…**, "
         "**Refresh** (Chapter 8)."],
        ["Spelling popover (click a misspelled word, or `ctrl+.`)",
         "Suggestions; **Add to dictionary**; **Add to my dictionary (all "
         "projects)**; **Ignore**. For a selected phrase, only the two "
         "dictionary entries."],
    ], [0.34, 0.66])
    s.gfigure("fig_gmenu", "aimenu", "The AI menu", width=200)

    # ============================================================ APP A
    s.chapter("A", "File Formats",
              "What Lorewrite reads and writes on disk.")
    s.h2("What Is in My Project Folder", idx=["project|layout",
                                              "manuscript folder",
                                              "entities folder",
                                              "project folder map"])
    s.p("A project is one folder. Everything in it is plain text that you "
        "can read and edit; the listing below shows all of it, and "
        f"{R('t_projmap')} says who writes each part and whether you may "
        "edit it by hand. The folder below is the Residual example after "
        "some use.")
    s.code("""\
residual/
  project.toml          title, author and the [editor] [ai] [manuscript]
  .gitignore            hides .lorewrite/ (and nothing else)
  style.md, style.md.bak  your style guide, and the one before the last
  dictionary.txt        words this project never flags
  manuscript/
    00-front-matter/    a part named front-matter: not counted in the book
      _part.md            its title
      01-title-page.md
    01-the-recall/      a part: a folder of scenes
      _part.md            "# The Recall" and notes on the part
      01-rain-on-the-spur.md
      02-capsule-7-19.md  (starts with scene details between --- lines)
    02-ghost-frequency/
    _unplaced/          scenes written but kept out of the book
      01-the-night-market.md
  entities/             characters/ places/ objects/ factions/  (the notes)
  research/             reference notes: capsule-hotels.md, assistant-notes.md
  .drafts/              what pending AI drafts replaced, one file per scene
  .snapshots/           history: one folder per scene, one file per snapshot
  .comments/            your comments on passages, one file per scene
  .trash/               deleted scenes and research notes
  .assistant/chats/     saved conversations with the assistant
  exports/              the book as PDF, DOCX, EPUB, Markdown, LaTeX
  inspiration/          reference pictures, each with a .md sidecar
  .lorewrite/           cache: index.sqlite, waivers.json (safe to delete)""")
    s.table("t_projmap", "What is in the project folder",
            ["Path", "What it holds", "Written by", "Edit by hand?"], [
        ["`project.toml`", "Title, author and settings of this project.",
         "Lorewrite and you", "Yes"],
        ["`manuscript/`", "Your scenes, directly or in parts.",
         "You", "Yes"],
        ["`manuscript/NN-name/`", "A part; `_part.md` inside holds its "
         "title.", "Lorewrite (New part)", "Title and notes, yes"],
        ["`manuscript/_unplaced/`", "Scenes kept out of the book.",
         "Lorewrite (Move to Unplaced)", "Yes"],
        ["`entities/`", "Notes on characters, places, objects and "
         "factions.", "You and Lorewrite", "Yes"],
        ["`research/`", "Reference notes, plain Markdown, any "
         "subfolders.", "You and Lorewrite", "Yes"],
        ["`style.md`, `dictionary.txt`", "Your style guide; the words "
         "spell check accepts.", "You and Lorewrite", "Yes"],
        ["`.drafts/`", "The original text behind each pending AI draft.",
         "Lorewrite", "No"],
        ["`.snapshots/`", "Verbatim copies of scenes (history).",
         "Lorewrite", "No; delete in the History screen"],
        ["`.comments/`", "Your comments on passages.", "Lorewrite",
         "Possible, not needed"],
        ["`.trash/`", "Deleted scenes and research notes.", "Lorewrite",
         "No; use the Trash screen"],
        ["`.assistant/chats/`", "Saved conversations.", "Lorewrite",
         "No"],
        ["`exports/`", "Files written by Export (Chapter 14); never "
         "overwritten.", "Lorewrite", "They are yours; delete freely"],
        ["`inspiration/`", "Inspiration pictures and their notes "
         "(Chapter 13).", "Lorewrite and you", "Notes in the .md files, "
         "yes"],
        ["`.lorewrite/`", "The link index and waived continuity issues.",
         "Lorewrite", "No; safe to delete"],
    ], [0.27, 0.37, 0.18, 0.18])
    s.p("Lorewrite reads scenes from `manuscript/` (directly in it, in a "
        "part folder directly under it, and in `_unplaced/`; only one "
        "level of folders counts), notes from `entities/*/*.md` (the "
        "note's folder name does not matter; its `type:` line does), "
        "research notes from `research/`, plus `style.md`, "
        "`dictionary.txt` and the folders above. Everything else in the "
        "project folder is ignored, so you may keep other files beside "
        "them. Only `.lorewrite/` is hidden from git by the `.gitignore` "
        "of a new project; everything else is yours and is committed.")
    s.p("Not in the folder, because they are about you rather than the "
        "book, are your personal dictionary, your settings and your "
        "writing numbers, which live in Lorewrite's state folder "
        "(see “Lorewrite's State Files” below).")
    s.h2("project.toml", idx=["project.toml", "TOML"])
    s.p("A small file in TOML format. Lorewrite writes `title` and "
        f"`author` when it creates the project; the other keys are "
        f"optional ({R('t_toml')}).")
    s.code("""\
title = "Residual"
author = ""

[editor]
padding = 2
line_numbers = true

[ai]
fast_model = "google/gemini-2.5-flash"
strong_model = "anthropic/claude-sonnet-4.5"
writing_model = "anthropic/claude-sonnet-4.5"
image_model = "google/gemini-3.1-flash-lite-image"

[manuscript]
unit = "scene"
draft = 2

[export]
format = "pdf"
layout = "book"
page_size = "trade"

[collections]
"Needs continuity pass" = "amber"
"Rook's arc" = "violet\"""")
    s.table("t_toml", "Keys of project.toml",
            ["Key", "Meaning", "Default"], [
        ["title", "The project's title, shown in the title bar and on the "
         "launch screen.", "Untitled if missing"],
        ["author", "Your name. The desktop application shows its initials "
         "in the badge at the foot of the rail.", "empty"],
        ["[editor] padding", "Side padding of the terminal editor, 0 to "
         "8. (The desktop application does not use it.)", "0"],
        ["[editor] line_numbers", "`true` or `false`. Terminal "
         "application only.", "true"],
        ["[ai] fast_model", "Model for Find aliases, for this "
         "project.", "your setting, else the built-in"],
        ["[ai] strong_model", "Model for continuity checks and "
         "story-bible updates, for this project.", "same"],
        ["[ai] writing_model", "Model for `ctrl+g` and for learning the "
         "style guide, for this project.", "same"],
        ["[ai] image_model", "Model for inspiration pictures (Chapter 13), "
         "for this project.", "same"],
        ["[export]", "The options last used in the Export dialog or "
         "form: format, layout, page_size, font, numbering, toc, "
         "include_front_matter, include_drafts, continuous, copyright "
         "(Chapter 14). Written by Lorewrite after each export; you may "
         "edit it.", "the defaults of the dialog"],
        ["[manuscript] unit", "`\"scene\"` or `\"chapter\"`: what the "
         "program calls the units of the book. Wording only (Chapter 5).",
         "scene"],
        ["[manuscript] draft", "Which draft of the book this is; **Start "
         "new draft** raises it by one (Chapter 8).", "1"],
        ["[collections]", "One line for each collection: its name, then "
         "its colour: violet, amber, green, red or gray (Chapter 5). Which "
         "scenes belong to it is kept in the scenes themselves.",
         "none"],
    ], [0.27, 0.48, 0.25], mono_cols=(0,))
    s.p("When you press **Save** in Settings, Lorewrite rewrites only the "
        "`[editor]` section and leaves the rest of the file as it was; "
        "the draft, the unit and the collections are written by the "
        "commands that change them. Everything else you put in the file "
        "is kept.")
    s.h2("Scene Files", idx=["scene|file format"])
    s.p("A scene is a Markdown file named `NN-slug.md`, where //NN// is a "
        "number of at least two digits and //slug// is the title in "
        "lowercase with hyphens. The order of the scenes within a folder is "
        "the order of the numbers (`2-` comes before `10-`). The title is "
        "the first line that begins `# `, after the scene details if there "
        "are any; if there is none, the file name is used. Nothing else "
        "is required.")
    s.code("""\
# Capsule 7-19

The Meridian stacked its sleepers forty high under the spur, a
honeycomb of fiberglass coffins lit the color of weak tea.

Rook climbed the ladder and looked in.""")
    s.h2("Parts, Unplaced Scenes and Front Matter",
         idx=["part|folder", "_part.md", "_unplaced folder",
              "front matter"])
    s.p("A //part// is a folder directly under `manuscript/`. Its name "
        "begins with a number, like a scene's: `01-the-recall`. The "
        "optional file `_part.md` in it holds the part's title as its "
        "first `# ` line, and anything you want to write about the part "
        "below that; without it the title is the folder's name with the "
        "hyphens turned into spaces. **New part** makes the folder with "
        "the next free number and writes `# Title` into `_part.md`. "
        "Renaming a part rewrites that heading only; the folder keeps its "
        "name.")
    s.code("""\
manuscript/
  00-front-matter/        slug front-matter: shown first, not in the count
    _part.md              # Front Matter
    01-title-page.md
  01-the-recall/
    _part.md              # The Recall
    01-rain-on-the-spur.md
    02-capsule-7-19.md
  _unplaced/              not a part: scenes kept out of the book
    01-the-night-market.md""")
    s.p("A part whose folder name, without its number, is "
        "`front-matter` is the front matter: it comes first, is shown "
        "dimmed, and its words are not counted as the book. There is no "
        "button for it; make a part called //Front Matter// and move it to "
        "the top, or name the folder yourself. Scenes may also sit "
        "directly in `manuscript/`; they are read before the parts. "
        "Names that begin with `_` or `.` are never scenes or parts, and "
        "only one level of folders is understood. Moving a scene into a "
        "folder renumbers that folder so the order is what you asked for "
        "(`01-`, `02-`, ...); the folder it left keeps its numbers, "
        "leaving a gap, which is harmless. The numbers shown in the desktop "
        "application (//SCENE 03//) are the positions in the whole book "
        "once it has parts, not the file numbers.")
    s.h2("Scene Details: Frontmatter", idx=["frontmatter|scene details",
                                            "scene details|format"])
    s.p("The details of a scene (Chapter 5) are the scene's own YAML "
        "frontmatter: a block between two lines of three hyphens at the "
        "very top of the file, before the `# ` title. It is written only "
        "when you set a field, and removed again when none is left, so a "
        "scene you never gave details has none.")
    s.code("""\
---
pov: Rook Tanaka
place: The Meridian
purpose: Rook finds the body and the shard
status: revising
target: 600
collections: [Needs continuity pass]
---
# Capsule 7-19""")
    s.table("t_scenekeys", "Keys of the scene details",
            ["Key", "Meaning"], [
        ["pov", "The point-of-view character. A name that is one of your "
         "notes counts as a mention."],
        ["place", "Where the scene happens. A name that is one of your "
         "notes counts as a mention."],
        ["purpose", "What the scene is for, in a line."],
        ["status", "Free text. Suggested: idea, draft, revising, done."],
        ["target", "A number of words."],
        ["collections", "The collections the scene belongs to, in square "
         "brackets, separated by commas."],
    ], [0.20, 0.80], mono_cols=(0,))
    s.p("Keys that Lorewrite does not know (an Obsidian `tags:` line, for "
        "instance) are kept when it rewrites the block. A block is "
        "frontmatter only if it is a YAML mapping: a scene that begins "
        "with a horizontal rule of three hyphens is left alone. The block "
        "is not prose: it is not counted as words, not spell-checked, not "
        "scanned for names (except //pov// and //place//), not used as "
        "evidence by the continuity check, and not sampled for your "
        "style. The AI is told the details in one line "
        "(//SCENE DETAILS//) instead of being shown the raw block.")
    s.h2("Entity Notes", idx=["entity|file format", "YAML"])
    s.p("An entity note is a Markdown file with a YAML header. The file "
        "name is the entity's name in lowercase with hyphens, for example "
        "`dace-kuroda.md`.")
    s.code("""\
---
name: Dace Kuroda
type: character
aliases: [Kuroda, Inspector Kuroda, the inspector]
---

Arcology Police homicide. Tired, decent within limits, owes Rook a
favor and resents it.

## Canon (auto)

- Left arm is an old chrome prosthetic; right arm is flesh.
- Voice like gravel. Works nights.""")
    s.p("If the header is missing or damaged, Lorewrite still opens the "
        "note, using the file name as the name and //character// as the "
        "type. The section headed `## Canon (auto)` runs to the next "
        "heading that begins with `## `, or to the end of the note. "
        "Lorewrite only adds lines to the end of that section when you "
        "accept story-bible facts; it never removes or rewrites what is "
        "there.")
    s.h2("The Style Guide: style.md", idx=["style.md|format"])
    s.p("`style.md` is a plain Markdown file at the top of the project, "
        "created by //learn style guide// (Chapter 11) or, with the "
        "headings and a hint under each, by //Open style guide//. It is "
        "yours to edit. Lorewrite reads it whole and sends it with every "
        "writing request; a file that is empty or only blanks counts as "
        "no guide. The sections are the headings below; the Exemplars are "
        "block quotes, each ending with the scene file it came from.")
    s.code("""\
# Style guide

## Voice

- Close third person, past tense, anchored in Rook's senses.

## Rhythm & syntax
## Diction
## Dialogue
## Avoid

## Exemplars

> Rook climbed the ladder and looked in. Imogen Sallow lay on her back
> with her knees drawn up, because the capsule was too short for her.
>
> — 02-capsule-7-19.md""")
    s.p("(The middle headings are shown without their bullets here to save "
        "space.) A guide that Lorewrite learned has one more line, directly "
        "under the title: the //provenance line//, for example "
        "`<!-- learned 2026-10-01 from 1,099 sampled words; manuscript "
        "1,502 words in 4 scenes -->`. It is an HTML comment that records the date, the number of words of "
        "your prose the AI was shown, and the size of the manuscript then, "
        "in words and scenes. The desktop application reads it to say "
        "when the guide was learned and when it has become out of date "
        "(Chapter 11). Delete it if you do not want that; nothing else "
        "depends on it. When a new guide replaces an old one, the old file is "
        "first copied to `style.md.bak`, next to it. Both files are "
        "written safely, with a temporary copy swapped into place.")
    s.h2("Pending AI Text: the Marker and .drafts",
         idx=["marker (AI)|format", ".drafts folder|format"])
    s.p("A pending AI draft (Chapter 11) is stored in the scene file "
        "itself, between two HTML comments:")
    s.code("""\
<!--ai-->text the AI wrote<!--/ai-->
<!--ai id="k3f9q2"-->text that replaced something<!--/ai-->""")
    s.p("The first form is an insertion. The second replaced text (a "
        "selection that was rewritten, or an expanded placeholder). Its "
        "//id// is six lower-case letters and digits, unique in the "
        "project. The replaced text is stored in a file named for the "
        "scene's path in the project, with each `/` written as `__`: "
        "`.drafts/manuscript__01-the-recall__02-tavern.md.json` for "
        "`manuscript/01-the-recall/02-tavern.md`. (Older projects kept "
        "these under the file name alone; Lorewrite renames them when it "
        "opens the project.) The file is a JSON object from ids to "
        "original text:")
    s.code("""\
{
  "k3f9q2": "The text the draft replaced, exactly as it was."
}""")
    s.p("The file is written safely, and it is deleted when it would be "
        "empty (and the `.drafts` folder with it, if nothing else is in "
        "it). It belongs to the project, not to the cache: it is not "
        "under `.lorewrite`, and the `.gitignore` of a new project does "
        "not list it. Accepting a draft removes the markers and the "
        "entry; rejecting restores the original and removes the entry. If "
        "an id has no entry, reject refuses (Chapter 11). A body that "
        "contains `<!--` has it changed to `<!-` when written, so a "
        "draft cannot contain a marker of its own. Markers that are "
        "nested, or missing one half, are not drafts; they are ordinary "
        "text. Moving a scene (which renames its file) carries its `.drafts` "
        "file along, and deleting a scene deletes it.")
    s.h2("The Trash: .trash", idx=[".trash folder"])
    s.p("Deleting a scene moves its file to `.trash/` under a name made of "
        "the time, then the scene's path with `/` written as `__`: "
        "`.trash/20261001-102200-manuscript__01-the-recall__03-a.md`. "
        "(If that name is taken, a `-2` follows the time.) What belongs "
        "to the scene travels with it, beside it, as "
        "`...md.drafts.json`, `...md.comments.json` and a folder "
        "`...md.snapshots/`. A research note goes the same way, as "
        "`.trash/20261001-102200-research__tides__almanac.md`. The folder "
        "is created by the first deletion and removed when it is empty "
        "again. **Restore** puts a scene back at the end of its original "
        "part (or in `_unplaced/` if that part is gone) under the next "
        "free number, and a research note at its original path (or in "
        "`research/`). **Delete forever** and **Empty Trash** remove the "
        "files. Only names of this form are listed; anything else you "
        "drop into `.trash/` is invisible to the Trash screen, and "
        "**Empty Trash** removes the whole folder.")
    s.h2("History: .snapshots", idx=[".snapshots folder"])
    s.p("Each scene with snapshots has a folder in `.snapshots/` named by "
        "the same rule as its draft file (the path with `/` written as "
        "`__`). In it, each snapshot is a copy of the scene file, "
        "frontmatter included, named by the time and an optional label:")
    s.code("""\
.snapshots/manuscript__01-the-recall__02-capsule-7-19.md/
  20260929-093231--before the rewrite.md
  20260930-113231.md
  20261001-123231--end-of-draft-1.md
  20261001-123231--end-of-draft-1.json   the draft originals, if any""")
    s.p("The labels the program gives are //auto// (the first-edit-of-the-"
        "day snapshot), //before-restore//, //before-accept-all//, "
        "//before-reject-all// and //end-of-draft-N//. A name taken in the "
        "same second gets a `-2`. A `.json` file with the same name holds "
        "the scene's pending-draft originals at that moment, and comes "
        "back with a restore. Nothing is ever pruned: the folder grows "
        "until you delete snapshots in the History screen. A scene's "
        "snapshot folder follows it when the scene is renamed or moved, "
        "and goes to the Trash with it.")
    s.h2("Comments: .comments", idx=[".comments folder"])
    s.p("Comments on a scene are one JSON file, `.comments/` followed by "
        "the scene's path with `/` written as `__`, a list of comments. A "
        "comment holds the quoted words, up to forty characters around "
        "them, your note and whether it is resolved:")
    s.code("""\
[
  {
    "id": "d86d64f2",
    "quote": "Rook climbed the ladder and looked in.",
    "prefix": "ager about who would pay for the tape.\\n\\n",
    "suffix": "\\n\\nImogen Sallow lay on her back with her",
    "body": "Check how many tiers up this is.",
    "created": "2026-10-01T12:32:31",
    "resolved": false
  }
]""")
    s.p("Lorewrite finds the passage again by its words and what "
        "surrounds them, not by its position, so the comment survives "
        "edits around it. If the words are gone it is //detached//: still "
        "in the file and still listed, never deleted. The file is removed "
        "when its last comment is.")
    s.h2("Research Notes and Saved Conversations",
         idx=["research folder|format", ".assistant folder"])
    s.p("`research/` holds ordinary Markdown files, in any subfolders; "
        "files and folders that begin with a dot are ignored. A note's "
        "title is its first `# ` line, or else its file name. **Save to "
        "notes** appends to `research/assistant-notes.md`, which is "
        "created on first use:")
    s.code("""\
# Assistant notes

Answers saved from the assistant, newest last.

## 2026-10-01 - How can I make the stairwell scene more tense?

**Prompt:** How can I make the stairwell scene more tense?

Three options: ...""")
    s.p("A note made from a web link holds a title built from the address "
        "and the address itself; the page is not fetched:")
    s.code("""\
# example.com - capsule hotel etiquette

https://www.example.com/articles/capsule-hotel-etiquette.html""")
    s.p("Conversations are `.assistant/chats/<id>.json`, where the "
        "identifier is a `c` and ten hexadecimal digits. A chat holds its "
        "title (the first question, cut at 60 characters), when it was "
        "made and last changed, whether it was about the scene or the "
        "project, what was attached, and the messages in order; answers "
        "from the research question carry the notes they cited and "
        "Brainstorm answers their ideas. At most 400 messages are kept, and "
        "failed answers are not saved. The files hold no key and no "
        "settings.")
    s.h2("The Dictionaries: dictionary.txt", idx=["dictionary.txt|format",
                                                  "personal dictionary|format"])
    s.p("Two files of the same plain format hold the words that spell check "
        "never flags (Chapter 7). The project dictionary is "
        "`dictionary.txt` at the top of the project; the personal "
        "dictionary is `dictionary.txt` in Lorewrite's state folder. Each "
        "is UTF-8 text with one word or phrase per line; blank lines and "
        "lines that begin with `#` are ignored. A word with a capital "
        "letter is accepted only capitalized; a lower-case word is "
        "accepted in any capitalization; a line with a space is a phrase. "
        "Lorewrite appends new terms to the end, keeps your comments, and "
        "writes the file safely (a temporary copy swapped into place). "
        "Neither file is a scene, a note or part of the index.")
    s.code("""\
# One word or phrase per line; these are never flagged as misspelled.
# Lines starting with # and blank lines are ignored.
hundered
maglev spur""")
    s.h2("The .lorewrite Folder", idx=[".lorewrite folder"])
    s.p("`index.sqlite` is the backlink index (see Chapter 6); it is "
        "rebuilt when the project opens and by `f9`. `waivers.json` "
        "records waived continuity issues as a list of short codes, with, "
        "in the `scenes` object, the scene each was waived in (used by "
        "//Restore waived continuity issues//):")
    s.code("""\
{
  "waived": [
    "3f9a1c5e07b2d846"
  ],
  "scenes": {
    "3f9a1c5e07b2d846": "manuscript/02-capsule-7-19.md"
  }
}""")
    s.p("The `.gitignore` file made for a new project lists this whole "
        "folder so that version control ignores it. That includes "
        "`waivers.json`; copy it yourself, or edit `.gitignore`, if you "
        "want your waivers kept with the book.")
    s.h2("Lorewrite's State Files", idx=["state folder|files"])
    s.code("""\
~/.local/state/lorewrite/
  recent.json      recent projects: path, title, time opened (max 10)
  settings.json    {"tour_seen": true, "fast_model": null, "spellcheck": true,
                    "daily_target": 500, "auto_snapshot": true,
                    "gui_zoom": 100, "gui_reflow": true, ...}
  dictionary.txt   your personal dictionary (created when first used)
  stats/           your writing numbers, one file for each project""")
    s.p("Your writing numbers are personal, not part of the book, so they "
        "are kept here and not in the project. The file is named by the "
        "first sixteen characters of a hash of the project folder's full "
        "path, which means that moving or renaming the folder starts a "
        "fresh file. It records, for each day, the words you wrote net of "
        "cuts, the words of AI drafts you accepted, the seconds you were "
        "active, the sessions, and your focus sprints:")
    s.code("""\
{"version": 1, "project": "/home/writer/novels/residual", "days": {
 "2026-10-01": {"words": 420, "ai_words": 60, "seconds": 3100, "sessions": 2,
  "sprints": [{"at": "2026-10-01T09:30:00", "minutes": 25, "elapsed": 1500,
               "words": 310, "completed": true}]}}}""")
    s.p("When both applications are open on one project, each adds only "
        "what it counted itself, so neither overwrites the other's "
        "numbers.")

    # ============================================================ APP B
    s.chapter("B", "Messages and Problem Solving",
              "The messages Lorewrite shows, in the words it uses, and "
              "what to do about them.")
    s.h2("Messages", idx=["messages"])
    s.p("Lorewrite reports what it has done with brief messages at the "
        "bottom right of the window. They fade after a few seconds. "
        "Warnings and errors are colored differently. Text in italic "
        "type below stands for something that varies. The first three "
        "tables are for the terminal application; the messages of the "
        f"desktop application are in {R('t_msgs_gui')}, further on.")
    s.table("t_msgs_info", "Information messages",
            ["Message", "Meaning"], [
        ["Saved", "You pressed `ctrl+s` and the file was saved."],
        ["Index rebuilt", "`f9` finished."],
        ["Looking for aliases…", "An alias request is under way."],
        ["Checking continuity…", "A continuity check is under way."],
        ["Reading the scene for new canon…", "A story-bible request is "
         "under way."],
        ["Learning your style from //N// paragraphs…", "A style guide "
         "request is under way."],
        ["Drafting… (//model//)", "A `ctrl+g` request is under way with the "
         "named writing model."],
        ["No new aliases found", "The AI found nothing to propose."],
        ["Found //N// possible alias(es)", "Shown, with the cost, just "
         "before the alias review opens."],
        ["No continuity issues found", "Nothing contradicts your notes "
         "(or every issue was waived earlier)."],
        ["No new canon found in this scene", "The scene establishes "
         "nothing new about your entities."],
        ["Added //N// alias(es) to entity notes", "You applied alias "
         "suggestions."],
        ["Canon proposals ready", "Shown, with the cost, just before the "
         "story-bible review opens."],
        ["Continuity check done", "Shown, with the cost, just before the "
         "continuity report opens."],
        ["Added canon to //N// entity note(s)", "You applied story-bible "
         "facts."],
        ["Style guide ready", "Shown, with the cost, before the style "
         "guide review opens."],
        ["Saved style.md", "You accepted a proposed style guide."],
        ["AI draft ready — f7 accept · f8 reject", "A draft was inserted "
         "into the scene."],
        ["AI draft accepted", "You pressed `f7` on a draft."],
        ["AI draft rejected", "You pressed `f8` on a draft."],
        ["//N// AI draft(s) accepted", "//Accept all AI drafts in this "
         "scene// finished."],
        ["//N// AI draft(s) rejected", "//Reject all AI drafts in this "
         "scene// finished."],
        ["No AI drafts in this scene", "An accept-all or reject-all "
         "command found nothing pending."],
        ["Restored //N// waived continuity issue(s) — they will be "
         "reported again by the next check", "You chose //Restore waived "
         "continuity issues//."],
        ["No waived continuity issues recorded for this scene", "There "
         "was nothing to restore for the open scene."],
        ["Spell check on, Spell check off", "You chose **Toggle spell "
         "check**."],
        ["Added \"//word//\" to the project dictionary", "You pressed `a` in "
         "the `f6` window, or chose **Add selection to dictionary** (the "
         "latter also says it for a phrase)."],
        ["Added \"//word//\" to your dictionary", "You pressed `p` in the "
         "`f6` window."],
        ["\"//word//\" is already in the dictionary", "**Add selection to "
         "dictionary** found the term in the project dictionary."],
        ["Tip: learn a style guide first (ctrl+p → learn style)", "Shown "
         "once per session the first time you use `ctrl+g` with no "
         "`style.md`."],
        ["API key stored in the system keyring", "The key was saved."],
        ["Settings saved", "You pressed **Save** in Settings."],
        ["Renamed to '//title//'", "A scene was renamed."],
        ["Moved to //file name//", "A scene was reordered."],
        ["Moved '//title//' to the Trash", "A scene was deleted to the "
         "Trash (Chapter 5)."],
        ["(a scene title)", "Shown briefly when you move to another "
         "scene with `alt+left` or `alt+right`."],
    ] + extra('MSG_TUI','info'), [0.42, 0.58])
    s.table("t_msgs_warn", "Warnings",
            ["Message", "Cause and action"], [
        ["Open a scene first", "The command needs an open scene. Rename, "
         "move, delete and `ctrl+g` work only on scenes, not on entity "
         "notes or the style guide; open a scene from the sidebar."],
        ["No scenes yet — ctrl+n to create one", "The project has no "
         "scenes. Press `ctrl+n`."],
        ["No more scenes this way", "You are at the first or last scene."],
        ["Already at the edge of its part", "The scene cannot move further "
         "in that direction within its part, or its file name has no "
         "leading number (rename the file to `NN-name.md`)."],
        ["No entities yet — create some notes first", "Find aliases and "
         "the story-bible update need at least one note. See Chapter 6."],
        ["No AI draft under the cursor", "`f7` or `f8` was pressed with "
         "the cursor outside any pending draft."],
        ["Empty {{expand: }} marker — say what to write", "The "
         "placeholder under the cursor has no instruction."],
        ["Nothing to learn from yet — write some scenes first", "The "
         "style guide needs paragraphs of at least 25 words in your "
         "scenes."],
        ["Open a project first", "A project command was used with no "
         "project open."],
        ["Scene changed while drafting — draft discarded", "You moved to "
         "another scene before the AI finished. The call is still "
         "charged."],
        ["The text changed while drafting — draft discarded", "The words "
         "to be replaced were edited, or appear more than once, so the "
         "draft could not be placed safely."],
        ["//N// AI draft(s) rejected; //M// left because the original "
         "text is missing — accept them or edit by hand", "Some drafts "
         "have no entry in `.drafts`; see Chapter 11."],
        ["No entities yet — nothing to check against", "The continuity "
         "check needs at least one note."],
        ["No misspellings", "`f6` found nothing to fix in this scene."],
        ["Spell check applies to scenes", "`f6` was pressed in a note, the "
         "style guide or the dictionary."],
        ["Select a word or phrase first", "**Add selection to dictionary** "
         "was chosen with nothing selected."],
        ["Select a name and press ctrl+j to make a note for it",
         "`ctrl+j` was pressed with nothing selected and the cursor not "
         "on a name."],
    ] + extra('MSG_TUI','warn'), [0.42, 0.58])
    s.table("t_msgs_err", "Errors",
            ["Message", "Cause and action"], [
        ["Alias search failed: //reason//", "The request to the AI "
         "service failed. Common reasons: no API key, no network, an "
         "invalid model name. See the problems below."],
        ["AI writing failed: //reason//", "Same, for `ctrl+g`. A reply "
         "with no text is also reported this way (//the model returned no "
         "text//)."],
        ["Style guide failed: //reason//", "Same, for learning a style "
         "guide. //the model's reply wasn't a usable style guide// means "
         "the reply could not be read; try again or choose another "
         "writing model."],
        ["Original text for this draft is missing — accept it or edit by "
         "hand", "`f8` was pressed on a draft whose original is not in "
         "`.drafts`. Nothing was changed. See Chapter 11."],
        ["Continuity check failed: //reason//", "Same, for the continuity "
         "check."],
        ["Story-bible update failed: //reason//", "Same, for the "
         "story-bible update."],
        ["Keyring unavailable (//reason//). Set the OPENROUTER_API_KEY "
         "environment variable instead.", "Your system has no usable "
         "keyring. Set the variable before starting Lorewrite. (The "
         "Settings screen words it slightly differently: //Set "
         "OPENROUTER_API_KEY in the environment instead.//)"],
        ["Couldn't load models (//reason//). Type a model id in Settings "
         "instead.", "The model picker could not reach OpenRouter. Check "
         "your network, or type a model name yourself."],
        ["No lorewrite project in //path//", "The folder has no "
         "`project.toml`. Choose the project's own folder."],
        ["//path// is no longer a project", "A recent project was moved or "
         "deleted; it is removed from the list."],
        ["Title and folder are both required", "Fill in both lines of the "
         "**New project** box."],
        ["Could not create project: //reason//", "The folder could not be "
         "made, often for lack of permission."],
        ["No OpenRouter API key. Set OPENROUTER_API_KEY or store one via "
         "lorewrite.ai.client.set_api_key().",
         "Shown after //failed:// when no key is found. Store a key "
         "(Chapter 10); you do not need to use the technical name in the "
         "message."],
    ] + extra('MSG_TUI','err'), [0.42, 0.58])
    s.table("t_msgs_gui", "Messages of the desktop application",
            ["Message", "Meaning and action"], [
        ["Saved", "You pressed `ctrl+s` and the file was saved."],
        ["Save failed: //reason//", "A save could not be written. Your "
         "text is still in the window; fix the cause (a full disk, a "
         "read-only folder) and press `ctrl+s`."],
        ["Resolve the save conflict first (reload or keep your version).",
         "You tried to open another file while the banner of Chapter 3 is "
         "showing. Click **Reload from disk** or **Keep my version**."],
        ["Could not save the current document first.", "The window "
         "refused to leave the open file because it could not save it; "
         "the cause is usually shown beside it."],
        ["Reloaded: the file changed on disk.", "You came back to the "
         "window, the file had changed, and you had nothing unsaved, so "
         "it was reloaded."],
        ["Kept your version. / Could not save your version.", "The result "
         "of **Keep my version**."],
        ["Index rebuilt from the files.", "**Rebuild the link index** "
         "finished."],
        ["Settings saved.", "You clicked **Save** in Settings."],
        ["API key stored in the system keyring.", "**Save key** worked. "
         "If the keyring is not available the message explains and tells "
         "you to set `OPENROUTER_API_KEY`."],
        ["Add your OpenRouter API key first. AI features are off until "
         "then.", "An AI control was used with no key; Settings opens."],
        ["Wait for the current AI request to finish.", "Only one AI "
         "request runs at a time."],
        ["Open a scene first.", "The command works on scenes, not on "
         "notes, the style guide or the dictionary."],
        ["//N// possible conflict(s) / No continuity issues found",
         "Result of **Continuity**, followed by \"(//N// waived)\" and "
         "the cost when they apply."],
        ["Dismissed. It will not be reported again (Restore waived issues "
         "brings it back).", "You clicked **Dismiss** on a card."],
        ["Restored //N// waived issue(s); the next check reports them "
         "again. / No waived issues are recorded for this scene.",
         "The result of **Restore waived issues**."],
        ["Could not locate that passage; the quote on the card is what the "
         "assistant flagged.", "**Review passage** could not find the "
         "words, usually because you have edited them."],
        ["No new aliases found / Added //N// alias(es) to your notes.",
         "Results of **Find aliases**."],
        ["No new canon found in this scene / Added canon to //N// "
         "note(s).", "Results of **Update story bible**."],
        ["Saved style.md", "You clicked **Save style guide**."],
        ["AI draft ready: F7 accept, F8 reject", "A draft was inserted; the "
         "cost follows. Also: //Inserted as an AI draft: F7 accept, F8 "
         "reject.// after **Insert as a draft**."],
        ["Tip: learn a style guide first (AI menu, Learn style guide).",
         "You drafted with no `style.md`."],
        ["AI draft accepted. / AI draft rejected. / //N// AI drafts "
         "accepted. / //N// AI drafts rejected.", "The results of F7, F8 "
         "and of the all-drafts commands."],
        ["No AI draft under the cursor. / No AI drafts in this scene.",
         "There was nothing pending where you pressed."],
        ["//N// draft(s) left: the original text is missing. Accept it or "
         "edit by hand.", "A reject was refused for lack of the original "
         "in `.drafts` (Chapter 11)."],
        ["Scene changed while drafting; draft discarded. / The text "
         "changed while drafting; draft discarded.", "You moved or edited "
         "the words the draft was for before the AI finished. The call is "
         "still charged."],
        ["Empty {{expand: }} marker: say what to write.", "The "
         "placeholder has no instruction."],
        ["Select a passage in the text first, then choose Rewrite.",
         "**Rewrite** needs a selection."],
        ["Select a name in the text (or put the cursor on a [[link]]) "
         "first.", "`ctrl+j` was pressed with nothing to open or make."],
        ["“//name//” already has a note.", "You asked to make a note that "
         "exists; it was opened."],
        ["Added “//word//” to the project dictionary. / ... to your "
         "dictionary. / “//word//” is already in the dictionary.",
         "Results of the spelling commands (Chapter 7)."],
        ["No misspelled words.", "You jumped to the next misspelling and "
         "there is none."],
        ["Moved “//title//” to the Trash.", "A scene was deleted to the "
         "Trash. Also: //Moved the research note “title” to the Trash.//"],
    ] + extra('MSG_GUI'), [0.46, 0.54])
    s.add(CondPageBreak(330))
    s.h2("Problem Solving", idx=["problem solving", "troubleshooting"])
    s.p("Use this table for troubleshooting the everyday problems. "
        "Messages that Lorewrite itself shows are explained above.")
    s.table("t_problems", "Common problems",
            ["Problem", "What to try"], [
        ["A name I wrote is not colored.", "Check that its note exists "
         "and that the name or an alias matches your spelling exactly, "
         "including capital letters (" + R("t_rules") + "). Press `f9`. Names inside "
         "an entity note are never colored."],
        ["A name is orange.", "It is in `[[brackets]]` and has no note. "
         "Put the cursor on it and press `ctrl+j` to make one."],
        ["Backlinks are missing or old.", "Press `f9` to rebuild the "
         "index."],
        ["`?` does not open help.", "In the editor `?` types a question "
         "mark. Press `f1`, which works everywhere."],
        ["`f7` no longer selects all.", "It accepts an AI draft now. "
         "Select all is `f5`."],
        ["A reject says the original is missing.", "The draft's entry in "
         "the `.drafts` folder is gone (Chapter 11). Accept the draft and "
         "edit it by hand, or restore the `.drafts` file from a backup."],
        ["`ctrl+g` does nothing in a note.", "It works in scenes only. "
         "Open a scene."],
        ["Drafts are hard to see in my theme.", "Lorewrite picks the color "
         "from your Omarchy theme. The text is also italic, on a tint, "
         "with `<!--ai-->` markers at each end; the status bar says "
         "//AI draft// when the cursor is inside one."],
        ["`alt+left` and `alt+right` do nothing.", "Some terminals send "
         "the Alt key differently. Use the palette entries **Next scene** "
         "and **Previous scene** instead, or click in the sidebar."],
        ["AI features say the key is missing.", "Open Settings and check "
         "the //API key// line. Set the key, or set "
         "`OPENROUTER_API_KEY` before starting Lorewrite."],
        ["The model picker is empty or lacks a model.", "For the fast and "
         "strong models it lists only models that can return the strict "
         "format those features need; the writing model's picker lists "
         "everything. Clear the filter box. If it says it could not load "
         "models, check your network."],
        ["An AI request fails with a model error.", "Check the model "
         "name in Settings and in the project's `project.toml` "
         "(a project setting overrides yours)."],
        ["My edits to a file were lost.", "You edited the open scene "
         "with another program (Chapter 4). Recover the file from a "
         "backup or version control."],
        ["The screen is garbled after a crash.", "Type `reset` in the "
         "terminal. Your files are safe; Lorewrite saves as you work."],
        ["A word of my story's world is underlined.", "Add it to a "
         "dictionary (Chapter 7): `a` or `p` in the `f6` window, or **Add "
         "to dictionary** in the popover of the desktop application. "
         "Names of your notes are never flagged; add an alias or a note "
         "instead if it is a character or place."],
        ["Nothing is underlined.", "Spell check applies to scenes only, "
         "and may be off: tick //Underline misspellings// in Settings, "
         "or use **Action · Toggle spell check**. In a new scene the "
         "marks appear a moment after you stop typing."],
        ["Suggestions for a word are useless.", "Suggestions come from a "
         "list of common English words and cannot guess invented ones. Add "
         "the word to a dictionary instead."],
        ["The desktop application does not start.", "It says why on the "
         "terminal: //the UI is not built// (run `npm install && npm run "
         "build` in `gui`) or //pywebview is not installed// (install "
         "with `pip install -e \".[gui]\"`). It also needs the WebKitGTK "
         "libraries of your system (Chapter 2)."],
        ["The desktop window says //Changed on disk//.", "The terminal "
         "application, or another program, saved the same file. Choose "
         "**Reload from disk** or **Keep my version** in the banner "
         "(Chapter 3)."],
        ["An AI request seems stuck.", "Requests give up after 180 "
         "seconds with an error. Start the feature again, or check your "
         "network."],
        ["I cannot remember a key.", "Press `f1` for the help screen (it works "
         "while you type), or `ctrl+p` and type what you want to do."],
        ["I want to see the tour again.", "Set `tour_seen` to `false` "
         "in `settings.json` (Chapter 2)."],
    ] + extra('PROBLEMS'), [0.36, 0.64])

    # ============================================================ APP C
    s.chapter("C", "Tutorial: The Residual Project",
              "A guided tour of the features using a small sample "
              "project, a cyberpunk mystery.")
    s.p("This tutorial follows the example project //Residual//, which "
        "is supplied with Lorewrite in its `examples` folder and is the "
        "project used for the figures in this book. It has four scenes "
        "and eight notes. The scenes follow Rook Tanaka, a data-forensics "
        "freelancer, and Wren, the AI construct that rides in his neural "
        "jack, as they are called to a dead body in a capsule hotel. "
        f"{R('t_residual')} lists the cast.")
    s.proc("To open a working copy of the example:", [
        "In the terminal, change to the Lorewrite folder you installed "
        "from (Chapter 2).",
        "Copy the example: `cp -r examples/residual /tmp/residual`.",
        "Open the copy: `lorewrite --project /tmp/residual` for the "
        "terminal application, or `lorewrite-gui --project /tmp/residual` "
        "for the desktop application.",
    ], idx=["Residual example", "examples folder"])
    s.p("Steps 1 to 8 use the terminal application. “The Same Story in "
        "the Desktop Application” at the end of this appendix repeats "
        "the tour in the desktop window.")
    s.attention("Always open a //copy//. Lorewrite saves as you work, and "
                "the AI features write notes, `style.md` and `.drafts/` "
                "into the project, so the original would no longer be "
                "the clean example. If you start a second run, delete "
                "`/tmp/residual` and copy it again. The steps that use AI "
                "need an API key (Chapter 10).")
    s.table("t_residual", "The cast of the Residual project",
            ["Name", "Kind", "Aliases"], [
        ["Rook Tanaka", "character", "Rook, Tanaka"],
        ["Wren", "character", "the construct"],
        ["Dace Kuroda", "character", "Kuroda, Inspector Kuroda, the "
         "inspector"],
        ["Imogen Sallow", "character", "Sallow, Dr. Sallow, the architect"],
        ["Kessler-Voss", "faction", "K-V, the company"],
        ["Sallow's Shard", "object", "the shard"],
        ["Hollow Market", "place", "the Hollow, the market"],
        ["The Meridian", "place", "the Meridian, Meridian"],
    ], [0.30, 0.20, 0.50])
    s.h2("Step 1. Open the Project")
    s.proc("Look at the project you opened:", [
        f"Lorewrite adds the project to the list on the launch screen "
        f"({R('fig_launch')}), so next time you can start with `lorewrite` "
        "alone and press `enter`.",
        "The main window opens on the first scene, //Rain on the "
        "Spur//. Look at the sidebar: four scenes and eight entities.",
        "Read the first paragraphs. Names such as //Hollow Market//, "
        "//Rook// and //Kessler-Voss// are colored, though they are "
        "written without brackets. That is mention recognition "
        "(Chapter 6).",
    ])
    s.h2("Step 2. Look Around a Name")
    s.proc("Inspect a character:", [
        "Press `alt+right` to open //Capsule 7-19//.",
        "In the paragraph that begins //Imogen Sallow lay on her back//, "
        "click on //Dr. Sallow//. The status bar says //Dr. Sallow — "
        "ctrl+j to open//.",
        f"Look at the entity panel ({R('fig_main')}). It shows the note "
        "for Imogen Sallow. Below it, the backlinks list every line in "
        "the scenes that names her, whether as //Imogen Sallow//, "
        "//Sallow//, //Dr. Sallow// or //the architect//.",
        "Move the cursor into the backlinks list and press `enter` on "
        "one. Lorewrite opens that scene at that line.",
    ])
    s.h2("Step 3. Make a Note")
    s.proc("Turn a name into an entity:", [
        "Open //Rain on the Spur// again. The bar's owner, //Lin//, has no "
        "note. Select the word //Lin// in the sentence //It's "
        f"unattractive in a man who owes Lin four hundred// ({R('fig_selected')}).",
        f"Press `ctrl+j`. Choose **Character** ({R('fig_type')}).",
        "Lorewrite creates `entities/characters/lin.md` and opens it. "
        "Type a line about Lin.",
        "Return to the scene (click it in the sidebar). //Lin// is now "
        "colored wherever it occurs, in every scene.",
    ])
    s.h2("Step 4. Find Aliases")
    s.proc("Use the AI to find other names for your characters:", [
        "Open //The Stairwell// and press `ctrl+l`.",
        f"Read the review ({R('fig_aliasrev')}). Suppose it proposes "
        "//dead woman// for Imogen Sallow and //The flyers// for "
        "Kessler-Voss. Leave both ticked and press `enter`.",
        "Look at the scene: it is exactly as it was. Open the note for "
        f"Kessler-Voss ({R('fig_aliasnote')}): //the flyers// is now one "
        "of its aliases, and is colored in every scene.",
    ])
    s.h2("Step 5. Check Continuity")
    s.p("The example was written with two slips planted in it, so that "
        "there is something to find. The note for Imogen Sallow says she "
        "has grey eyes, but //Capsule 7-19// says //Her green eyes were "
        "open//. The note for Dace Kuroda says his //left// arm is the "
        "chrome one, but //The Stairwell// says the fingers of his "
        "//right// hand, //the chrome one//.")
    s.proc("Find the first slip:", [
        "Open //Capsule 7-19//, press `ctrl+p` and choose **Action · Check "
        "scene for continuity issues**.",
        f"The report ({R('fig_cont')}) names the issue, the line, the "
        "words, and a suggested fix.",
        "Press `enter` to jump to the line (the report closes). Decide: "
        "change //green// to //grey// in the scene. Nothing is changed for "
        "you.",
        "Run the check again; the issue is gone. If the eyes had been "
        "meant as a lie, you would have pressed `space` instead, to "
        f"waive it ({R('fig_waived')}); //Restore waived continuity "
        "issues (this scene)// would bring it back.",
    ])
    s.p("Repeat for //The Stairwell//, where the chrome arm is the "
        "second slip.")
    s.h2("Step 6. Update the Story Bible")
    s.proc("Record what a scene establishes:", [
        "In //Capsule 7-19//, choose **Action · Update story bible from "
        "scene**.",
        f"In the review ({R('fig_bible')}), untick any fact you do not "
        "want, and press `enter`.",
        "Open the note for Wren. The accepted facts have been added to "
        "the end of its **Canon (auto)** section; every older fact is "
        "still there above them.",
    ])
    s.h2("Step 7. Teach Lorewrite Your Style")
    s.proc("Learn a style guide from the four scenes:", [
        "Press `ctrl+p` and choose **Action · AI: learn style guide from "
        "manuscript**.",
        f"Read the proposal ({R('fig_stylerev')}) and press `enter` to "
        "save it. Open it with **Action · Open style guide** "
        f"({R('fig_styleguide')}) and change a line.",
    ])
    s.h2("Step 8. Write with ctrl+g")
    s.proc("Draft, expand and rewrite, and review each result:", [
        f"Open //Ghost in the Ice//, put the cursor at the end and press "
        f"`ctrl+g`. Ask for a paragraph ({R('fig_promptdraft')}), "
        f"submit with `ctrl+g`, and read the draft ({R('fig_draft')}). "
        "Press `f7` to accept it.",
        f"In //Capsule 7-19//, type a placeholder such as "
        "`{{expand: the lobby of the Meridian at 3 a.m.}}` on a line of "
        f"its own, put the cursor in it and press `ctrl+g` "
        f"({R('fig_expanddraft')}). Press `f8` to reject the result and "
        "get the placeholder back.",
        f"In //The Stairwell//, select a sentence and press `ctrl+g` "
        f"twice ({R('fig_rewrite')}). Press `f8` to restore your "
        "sentence, or `f7` to keep the rewrite.",
        "Watch the status bar: the word count leaves out pending drafts, "
        "and the AI total grows with each call.",
    ])
    s.p("To finish, try writer mode with `f11`, add a scene with `ctrl+n`, and "
        "move it with **Action · Move current scene up**. When you are "
        "done, press `ctrl+q`. Your work has already been saved.")
    s.h2("The Same Story in the Desktop Application")
    s.p("Quit the terminal application, delete `/tmp/residual`, copy the "
        "example again (a fresh copy shows the same results as the "
        "figures), and start `lorewrite-gui --project /tmp/residual`. "
        f"The window opens as in {R('fig_gmain')}. The steps that use AI "
        "need an API key (Chapter 10).")
    s.proc("Look around:", [
        "In the binder, open //Manuscript// if it is closed. Click //02 "
        "Capsule 7-19//. The title bar reads //Scene 02 · Capsule 7-19//.",
        "Rest the pointer on //Dr. Sallow// until a card appears, then "
        f"`ctrl`-click it. The **Notes** tab ({R('fig_gnotes')}) shows "
        "Imogen Sallow's note, her aliases, and every line that mentions "
        "her; click a backlink to open that scene at that line.",
        "Press `ctrl+k`, type //sal//, and press `enter` on //Sallow's "
        "Shard//. The note opens in the editor.",
    ])
    s.proc("Make a note:", [
        "Open //Rain on the Spur//. Select the word //Lin// in the sentence "
        "that mentions //Lin's counter// and press `ctrl+j`.",
        "In the **New note** box leave the kind as **character** and click "
        "**Create**. //Lin// is now colored in every scene, and the "
        "**Notes** tab shows the new note.",
    ])
    s.proc("Check spelling:", [
        "In //Rain on the Spur//, look at the status bar: it reads //3 "
        "spelling//. Click //maglev// (underlined in the first "
        f"paragraph). In the popover ({R('fig_gspell')}) choose **Add to "
        "dictionary**. The underline goes and the count drops to 2.",
        "Open **Dictionary** in the binder: `dictionary.txt` now lists "
        "//maglev//.",
    ])
    s.proc("Find aliases and check continuity:", [
        "Open //The Stairwell//, open the AI menu and choose **Find "
        f"aliases**. In the dialog ({R('fig_galias')}) click **Select "
        "all**, then **Add 2 aliases**. The scene is unchanged.",
        "Open //Capsule 7-19// and click **Continuity**. The card "
        f"({R('fig_gcont')}) says Imogen Sallow's green eyes conflict "
        "with her note. Click **Review passage**, change //green// to "
        "//grey// in the page, and click **Continuity** again.",
        "Choose **Update story bible** in the AI menu, click **Select "
        f"all** and **Add 2 facts** ({R('fig_gcanon')}). Open Wren's note "
        "in the **Library** to see them under //Canon (auto)//.",
    ])
    s.proc("Teach it your style and write:", [
        f"On the //Your style// card ({R('fig_gstyle1')}) click **Learn my "
        f"style**, read the proposal ({R('fig_gstylerev')}) and click "
        "**Save style guide**. The card now says when it was learned "
        f"({R('fig_gstyle2')}).",
        "Open //Ghost in the Ice//, put the cursor at the end of the last "
        f"paragraph and press `ctrl+g` ({R('fig_ggen')}). Type an "
        "instruction and press `enter`. Read the draft, then click "
        "**Accept**. The word count in the binder grows by its length.",
        "In //Capsule 7-19// type "
        "`{{expand: the lobby of the Meridian at 3 a.m.}}` on a line of "
        "its own, click inside the tag and press `ctrl+g`. Click "
        "**Reject**: the tag comes back as you wrote it.",
        "In //The Stairwell//, select //The shard sat in Rook's pocket "
        f"like a coin from another country.// and press `ctrl+g` "
        f"({R('fig_grew')}), then `enter`. Press `f8`: your sentence "
        "returns.",
    ])

    s.h2("Export the Book and Make a Picture")
    s.p("Start from the Parts section below or from a fresh copy; this "
        "section needs no AI for the export and an API key for the "
        "picture.")
    s.proc("Export the Residual book:", [
        "Terminal application: press `ctrl+p` and choose **Action · "
        "Export manuscript**. Leave //PDF//, //Book// and //Trade// as "
        "they are and press `ctrl+s`. A notice says //Exported to "
        "exports/residual-book-...pdf//. Desktop application: open the "
        "**More** menu and choose **Export…**, check the summary line "
        "at the top of the dialog, and click **Export**, then **Open "
        "file** in the **Export finished** dialog.",
        "Open the PDF. The cover, contents and a first chapter look "
        f"like the pages of {R('pdf_book_title')} and its neighbors. "
        "Export again with the **Manuscript review** layout and compare: "
        "double-spaced, with line numbers.",
        "Look in the project folder: `exports/` holds both files, and "
        "`project.toml` now has an `[export]` section remembering your "
        "choices.",
    ])
    s.proc("Make an inspiration picture:", [
        "Set your OpenRouter key (Chapter 10). Open //Capsule 7-19//.",
        "Desktop application: open the **Inspiration** tab of the "
        "assistant and click **Describe this scene**. Read the "
        "description, change a phrase, and click **Generate**. Terminal "
        "application: **Action · Inspiration image…**, then `ctrl+d` to "
        "describe and `ctrl+g` to generate (Chapter 13).",
        "The picture appears pinned to the scene. Click it for the large "
        "view. Check the cost in the status bar. Your scene text has not "
        "changed.",
    ])

    s.h2("Parts, a Snapshot and a Sprint")
    s.p("This last section uses a fresh copy of the example (delete "
        "`/tmp/residual` and copy it again). It shows the newest features "
        "on the four scenes: dividing the book into parts, keeping a "
        "snapshot you can come back to, and timing a sprint.")
    s.proc("Divide the book into two parts (terminal application):", [
        "Open the project. Press `ctrl+p` and choose **Action · New part**. "
        "Type //The Recall// and press `enter`. Make a second part, "
        "//Ghost Frequency//.",
        "Open //Rain on the Spur// and choose **Action · Move scene to "
        "part**. In the list, choose //The Recall//. Do the same for "
        "//Capsule 7-19//. Send //The Stairwell// and //Ghost in the Ice// "
        "to //Ghost Frequency//.",
        "Look at the sidebar: part headers in capitals now group the "
        "scenes. Press `alt+right` from //Capsule 7-19//; it carries you "
        "into the next part.",
        "Look in the project folder: `manuscript/01-the-recall/`, "
        "`manuscript/02-ghost-frequency/`, and a `_part.md` in each. The "
        "scenes were renumbered inside their new parts.",
    ])
    s.proc("The same, in the desktop application:", [
        "Open the binder's options menu (the three dots) and choose **New "
        "part…**; type //The Recall// and click **Create**. Make //Ghost "
        "Frequency// the same way.",
        "Click the corkboard. Drag the //Rain on the Spur// card onto the "
        "//The Recall// heading, or open a scene and choose **Move scene "
        "to part…** in the options menu. When asked, click **Move**; the "
        "toast has an **Undo** button.",
        "Open the corkboard again: the cards are grouped by part.",
    ])
    s.proc("Keep a snapshot:", [
        "Open //Capsule 7-19//. Choose **Scene · Snapshot scene**, type "
        "//before the rewrite// and press `enter`. In the desktop "
        "application click the clock (**History**) in the rail, type the "
        "label and click **Snapshot this scene**.",
        "Delete the sentence //Rook climbed the ladder and looked in.// "
        "from the scene.",
        "Open the history: **Scene · Snapshots** in the terminal "
        f"application ({R('fig_snaps')}), or the **History** button in the "
        f"desktop one ({R('fig_ghist')}). Compare the snapshot with the "
        "scene: the sentence shows as removed. Restore the snapshot. The "
        "sentence is back, and the text you had just before is kept as "
        "//before a restore//, so you can undo the restore, too.",
    ])
    s.proc("Time a sprint:", [
        "Choose **Action · Focus sprint**, then //15 minutes//, then keep "
        "the screen as it is. In the desktop application click **Sprint** "
        "in the status bar and **Start sprint**.",
        "Write a paragraph. The countdown in the status bar shows the "
        "time left and the words you have added.",
        "Stop the sprint (run the command again, or click the countdown). "
        "A notice says how many words you wrote. Open **Action · Session "
        "stats** (or click //words today// in the desktop status bar): "
        "today's numbers and the sprint are in it.",
    ])

    # ============================================================ GLOSSARY
    s.chapter("G", "Glossary", mode="back", numbered=False)
    seen_terms = set()
    for term, d in sorted(GLOSSARY, key=lambda g: g[0].lower()):
        if term.lower() in seen_terms:      # a term defined by two chapters: first wins
            continue
        seen_terms.add(term.lower())
        s.add(Paragraph(T(term), ST["gloss_t"]),
              Paragraph(T(d), ST["gloss_d"]))

    # ============================================================ INDEX
    s.add(NextPageTemplate(["idxfirst", "twocol"]), PageBreak())
    s.chapter("X", "Index", mode="back", numbered=False, new_page=False)
    s.add(FrameBreak())
    entries = {}
    for term, sub, label in st["prev_idx"]:
        entries.setdefault(term, {}).setdefault(sub, [])
        if label not in entries[term][sub]:
            entries[term][sub].append(label)
    letter = None
    for term in sorted(entries, key=lambda t: t.lower().lstrip("[.")):
        first = term.lstrip("[.")[:1].upper()
        first = first if first.isalpha() else "Symbols"
        if first != letter:
            letter = first
            s.add(Paragraph(letter, ST["idx_letter"]))
        subs = entries[term]
        top = subs.get(None, [])
        line = f"{esc(term)}" + (", " + ", ".join(top) if top else "")
        s.add(Paragraph(line, ST["idx"]))
        for sub in sorted(k for k in subs if k):
            s.add(Paragraph(f"{esc(sub)}, {', '.join(subs[sub])}",
                            ST["idx_sub"]))
    assert not s.pending, f"index terms with no paragraph: {s.pending}"
    return s.f


def _parts_diagram():
    from reportlab.platypus import Preformatted
    txt = """\
  my-novel/                          a project is a folder
  |
  +-- project.toml                   title and settings
  |
  +-- manuscript/                    your scenes, in order
  |     +-- 01-opening.md              a scene outside any part
  |     +-- 01-the-recall/             a part is a folder of scenes
  |     |     +-- _part.md             its title and notes
  |     |     +-- 01-rain.md
  |     +-- _unplaced/                 written, but not in the book
  |
  +-- entities/                      notes on your story's things
  |     +-- characters/  places/  objects/  factions/
  |
  +-- research/                      reference notes, plain Markdown
  +-- style.md  dictionary.txt       your style guide, your word list
  |
  +-- .trash/  .snapshots/          deleted scenes; history
  +-- .comments/  .drafts/           comments; AI draft originals
  +-- .assistant/chats/              saved conversations
  +-- .lorewrite/                    cache, rebuilt at any time"""
    for ln in txt.split("\n"):
        assert len(ln) <= 78
    return Preformatted(txt, ST["code"])


GLOSSARY = [
    ("assistant (desktop)", "The panel at the right of the desktop window, "
     "with the tabs Assistant, Context and Notes; it holds the AI features, "
     "the Your style card and the notes."),
    ("binder", "The tree at the left of the desktop window that lists the "
     "scenes and notes of the project."),
    ("conflict banner", "The bar the desktop application shows when a file "
     "changed on disk while you were editing it; it offers Reload from "
     "disk or Keep my version."),
    ("corkboard", "A view of the desktop editor that shows each scene as a "
     "card."),
    ("desktop application", "`lorewrite-gui`: the windowed form of "
     "Lorewrite. Its window is titled Chisel."),
    ("dictionary", "A plain text file of words and phrases that spell check "
     "never flags. There is one for each project (`dictionary.txt`) and one "
     "personal one."),
    ("focus mode", "The desktop's name for writer mode: `f11` hides "
     "everything but the page."),
    ("hover card", "The small card that appears when you rest the pointer "
     "on a mention in the desktop editor."),
    ("misspelling", "A word that spell check does not know and underlines."),
    ("outline", "A view of the desktop editor that lists the scenes with "
     "their headings."),
    ("phrase (dictionary)", "A dictionary entry of two or more words; it "
     "accepts the words inside every occurrence of the phrase."),
    ("provenance line", "The comment under the title of a learned "
     "`style.md` that records when it was learned and from how much "
     "prose."),
    ("quick switcher", "The search box opened by `ctrl+k` in the desktop "
     "application, which opens any scene or note."),
    ("spell check", "Underlining of misspelled words in scenes; spelling "
     "only, never grammar."),
    ("terminal application", "`lorewrite`: the form of Lorewrite that runs "
     "in a terminal window."),
    ("voice samples", "About two thousand words of your own paragraphs "
     "that `ctrl+g` sends as examples of your style."),
    ("Your style card", "The card at the top of the desktop assistant that "
     "learns, relearns and opens the style guide and says when it is out "
     "of date."),
    ("alias finder", "The AI feature, started with `ctrl+l`, that finds "
     "other ways your prose refers to your characters and places and "
     "offers them as aliases. It never edits the scene."),
    ("alias", "Another name that a note lists for its entity, such as "
     "//the inspector// for Dace Kuroda. Every alias is recognized as a "
     "mention."),
    ("API key", "A secret string that identifies your OpenRouter account. "
     "Lorewrite keeps it in your system keyring, or reads it from the "
     "OPENROUTER_API_KEY environment variable."),
    ("autosave", "Lorewrite's saving of the open file a moment after you "
     "stop typing."),
    ("backlink", "A line of your book that mentions an entity, listed in "
     "the entity panel when the cursor is on that entity's name."),
    ("cache", "Information Lorewrite can rebuild from your files. The "
     "search index in `.lorewrite` is a cache."),
    ("AI draft", "See //pending draft//."),
    ("canon", "The established facts about an entity, kept in the "
     "`## Canon (auto)` section of its note (or, failing that, the "
     "beginning of the note). Continuity checks compare scenes with it."),
    ("command palette", "The searchable list of commands, scenes, "
     "entities and links that opens with `ctrl+p`."),
    ("continuity check", "An AI review of the open scene against your "
     "notes that reports contradictions."),
    ("entity", "A character, place, object or faction that has a note."),
    ("entity panel", "The panel at the right of the main window that shows "
     "the note and backlinks for the name under the cursor."),
    ("fast model", "The AI model used by Find aliases."),
    ("frontmatter", "The few lines between two rows of hyphens at the top "
     "of a note that give its name, kind and aliases."),
    ("index", "The cache of where each entity is mentioned, stored in "
     "`.lorewrite/index.sqlite`. Rebuilt with `f9`."),
    ("launch screen", "The screen shown when Lorewrite starts without a "
     "project: recent projects, open, new (and, in the terminal "
     "application, settings)."),
    ("link", "A name wrapped in double square brackets, "
     "`[[like this]]`. Also called a wiki-link."),
    ("Markdown", "A way of writing formatted text with plain characters, "
     "for example `# ` before a heading."),
    ("mention", "A place in a scene where the name or an alias of an "
     "entity appears, with or without brackets."),
    ("note", "The file that describes one entity."),
    ("OpenRouter", "The service through which Lorewrite reaches AI "
     "models."),
    ("project", "A folder containing a `project.toml` file, your scenes "
     "and your notes: one book."),
    ("scene", "One Markdown file in the `manuscript` folder."),
    ("pending draft", "Text written by the AI and inserted into a scene "
     "between `<!--ai-->` comments. It is shown in color and stays "
     "pending until you accept it with `f7` or reject it with `f8`."),
    ("prompt window", "The small box opened by `ctrl+g` for typing an "
     "instruction to the AI. `ctrl+g` submits it and `esc` cancels."),
    ("sidecar (.drafts)", "The file in the `.drafts` folder that keeps the "
     "original text behind each pending draft that replaced something."),
    ("expand marker", "A placeholder of the form `{{expand: what to "
     "write}}` that `ctrl+g` replaces with a pending draft."),
    ("strong model", "The AI model used for continuity checks and "
     "story-bible updates."),
    ("story bible", "The collected notes on everything in your story."),
    ("style guide", "The file `style.md` at the top of the project, "
     "describing how you write. The AI follows it when it writes."),
    ("suggest-and-confirm", "The rule that AI features only propose "
     "changes, and nothing is changed until you accept."),
    ("writing model", "The AI model used by `ctrl+g` and for learning the "
     "style guide; chosen separately from the fast and strong models."),
    ("waive", "To mark a continuity issue as intentional so that it is "
     "not reported again."),
    ("writer mode", "The view, opened with `f11`, that hides everything "
     "but the editor and status bar."),
]


for _m in NEW_CHAPTERS:
    GLOSSARY.extend(_m.GLOSSARY)


# ---------------------------------------------------------------------------
# build driver
# ---------------------------------------------------------------------------


def build():
    st = {"prev_toc": [], "prev_idx": [], "prev_refs": {}, "refs": {},
          "labels": {}}
    prev_sig = None
    for n in range(1, 7):
        st["refs"] = {}
        st["labels"] = {}
        story = build_story(st)
        doc = GuideDoc(str(OUT), st)
        doc.build(story)
        sig = (doc.seen_toc, doc.seen_idx, dict(st["refs"]), doc.page)
        print(f"pass {n}: {doc.page} pages, {len(doc.seen_toc)} toc, "
              f"{len(doc.seen_idx)} idx")
        st["prev_toc"] = doc.seen_toc
        st["prev_idx"] = doc.seen_idx
        st["prev_refs"] = dict(st["refs"])
        if sig == prev_sig:
            break
        prev_sig = sig
    import json
    (HERE / "build" / "state.json").write_text(json.dumps(
        {"toc": doc.seen_toc, "idx": doc.seen_idx}), encoding="utf-8")
    return doc.page


if __name__ == "__main__":
    if "--capture" in sys.argv:
        import os
        subprocess.run([str(HERE.parents[1] / ".venv/bin/python"),
                        str(HERE / "build" / "capture.py")], check=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONPATH": str(HERE.parents[1] / "src")})
        # the desktop application's figures: headless Chromium against the
        # headless backend with canned AI (needs Node and chromium; no window
        # opens on the desktop)
        subprocess.run([str(HERE.parents[1] / ".venv-gui/bin/python"),
                        str(HERE / "build" / "gui_capture.py")], check=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    pages = build()
    print(f"wrote {OUT} ({pages} pages)")
