#!/usr/bin/env python3
"""Build docs/user-guide/lorewrite-users-guide.pdf.

    python3 docs/user-guide/build_guide.py            # use captured screens
    python3 docs/user-guide/build_guide.py --capture  # re-capture screens first

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
    s = re.sub(r"//(.+?)//", r"<i>\1</i>", s)
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
        self.add(self._P(f"<b>{T(lead)}</b>", ST["body_tight"]))
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
        self.st["refs"][key] = num
        img = fig_image(shot)
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
    pts_w = (x1 - x0) * PT_PER_COL
    px_w = min(im.width, round(pts_w * 4))     # ~288 dpi is plenty
    im = im.resize((px_w, round(im.height * px_w / im.width)), Image.LANCZOS)
    im.save(dst, optimize=True)
    pts_h = pts_w * im.height / im.width
    return RLImage(str(dst), width=pts_w, height=pts_h)


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
        c.drawRightString(w, h - 4, "Second Edition")
        c.setStrokeColor(INK)
        c.setLineWidth(3)
        c.line(0, h - 22, w, h - 22)
        c.setLineWidth(0.6)
        c.line(0, h - 27, w, h - 27)
        # title block
        c.setFillColor(INK)
        c.setFont("Sans-Bold", 46)
        c.drawString(0, h * 0.60, "Lorewrite")
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
        c.drawString(0, 58, "A terminal fiction-writing application")
        c.drawString(0, 45, "Plain text · Wiki-style links · AI that suggests, "
                            "never edits")
        c.setFont("Sans-Bold", 9)
        c.setFillColor(INK)
        c.drawRightString(w, 58, "Lorewrite Publications")
        c.setFont("Sans", 9)
        c.setFillColor(GREY)
        c.drawRightString(w, 45, "September 2026")


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
    s.p("**Second Edition (September 2026)**", style="notice")
    s.p("This edition replaces and makes obsolete the First Edition, "
        "LW00-0001-0.", style="notice")
    s.p("This edition applies to Version 0.2.0 of Lorewrite, including the "
        "AI writing features (style guide, drafting, pending AI text), and to all "
        "subsequent releases and modifications until otherwise indicated in "
        "new editions. Make sure you are using the correct edition for the "
        "level of the product. The version number is shown in the title bar "
        "of the main window and at the top of the launch screen.",
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
        "example that is supplied with Lorewrite. The results shown "
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
    s.p("This book describes Lorewrite, a program for writing fiction in a "
        "terminal window. It explains what Lorewrite does, how to install "
        "and start it, how to write scenes, how to keep track of your "
        "characters and places, how to use its optional AI assistance, and "
        "where every key, menu entry and setting is. It is both a guide, "
        "which you can read from the front, and a reference, which you can "
        "look things up in.")
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
        "appendixes and the index are for looking things up.")
    s.bullets([
        "**Chapter 1, Introducing Lorewrite**, explains the ideas the "
        "program is built on: projects, scenes, entities, mentions, links "
        "and backlinks, and the rule that AI only suggests.",
        "**Chapter 2, Installing and Starting**, tells you how to install "
        "Lorewrite, start it, open or create a project, and what happens "
        "the first time you run it.",
        "**Chapter 3, Writing Scenes**, covers the editor, saving, the "
        "status bar, writer mode, and creating, renaming, reordering and "
        "deleting scenes.",
        "**Chapter 4, Characters, Places and Mentions**, explains how to "
        "make notes for your characters and places and how Lorewrite "
        "recognizes them in your text.",
        "**Chapter 5, AI Assistance**, describes how to set up an AI "
        "service and the three features that keep your story consistent: "
        "finding aliases, continuity checks and story-bible updates, "
        "with what they cost and send.",
        "**Chapter 6, Writing with AI**, describes the features that "
        "write: the style guide, drafting at the cursor, expanding "
        "placeholders, rewriting a selection, and reviewing pending AI "
        "text.",
        "**Chapter 7, Settings Reference**, lists every setting, where it "
        "is stored, and its default.",
        "**Chapter 8, Command and Key Reference**, lists every key and "
        "every entry in the command palette.",
        "**Appendix A, File Formats**, describes the files Lorewrite reads "
        "and writes.",
        "**Appendix B, Messages and Problem Solving**, lists the messages "
        "the program shows and what to do about them.",
        "**Appendix C, Tutorial**, walks through the sample project.",
        "The **Glossary** defines the terms used in this book, and the "
        "**Index** helps you find things.",
    ])
    s.h2("Typographic Conventions")
    s.p("This book uses the following conventions.")
    s.table(None, None, ["Convention", "Meaning", "Example"], [
        ["Monospace type", "Keys you press, text you type, file and folder "
         "names, and text shown exactly as it appears on the screen.",
         "`ctrl+j`, `project.toml`"],
        ["**Bold type**", "Names of buttons, dialogs and screens.",
         "Press **Save**."],
        ["//Italic type//", "A term being defined, a title, or a value you "
         "replace with your own.", "//scene//, //PATH//"],
        ["`ctrl+j`", "Press and hold the first key, then press the second. "
         "Keys are written the way Lorewrite writes them on its own help "
         "screen.", "`ctrl+s` saves"],
        ["`alt+left`", "The Alt key together with the left arrow key. "
         "`alt+right` is the right arrow.", ""],
        ["**Note:**", "Information that is useful but not essential.", ""],
        ["**Attention:**", "Something that can lose work or surprise you if "
         "you overlook it.", ""],
    ], [0.20, 0.55, 0.25])
    s.p("Screens are shown as figures with a ruled border. Procedures are "
        "numbered lists; do the steps in order. Tables and figures are "
        "numbered by chapter, so //Figure 3-1// is the first figure in "
        "Chapter 3. Page numbers also carry the chapter: page //4-2// is "
        "the second page of Chapter 4, and //B-1// is the first page of "
        "Appendix B.")
    s.h2("Names and Terms")
    s.p("The program is called Lorewrite; its command is `lorewrite`. "
        "A //project// is one book: a folder of plain files. The Glossary "
        "at the back defines the other terms.")

    # ------------------------------------------------------------ changes
    s.front("Summary of Changes")
    s.p("This Second Edition (LW00-0001-1) covers the same Version 0.2.0 "
        "of Lorewrite as the First Edition, now including the AI writing "
        "features. The changes from the First Edition are listed below; "
        "each is described in the chapter shown. Chapters 6 and 7 of the "
        "First Edition (Settings Reference, Command and Key Reference) are "
        "now Chapters 7 and 8.")
    s.table(None, None, ["Change", "Where described"], [
        ["**New chapter, Writing with AI.** Learn a style guide from your "
         "own prose (`style.md`); press `ctrl+g` to draft at the cursor, "
         "expand a `{{expand: ...}}` placeholder, or rewrite a selection; "
         "review the result as a pending AI draft and accept (`f7`) or "
         "reject (`f8`) it. Pending text is stored in the scene file "
         "between `<!--ai-->` comments, with replaced originals in "
         "`.drafts/`.", "Chapter 6"],
        ["**`ctrl+l` is now Find aliases.** It no longer inserts "
         "`[[brackets]]` into your scene. Accepted suggestions become "
         "aliases in your notes; the scene is never edited.",
         "Chapter 5"],
        ["**Story-bible updates add only.** The AI proposes new facts, "
         "each shown in full and accepted one by one; existing canon is "
         "never removed or rewritten. The old whole-section replacement, "
         "and the warning about it, are gone.", "Chapter 5"],
        ["**AI cost is shown** in the status bar (for the session) and in "
         "each AI notification.", "Chapters 3 and 5"],
        ["**Continuity report:** `enter` now jumps to the line and closes "
         "the report. A new palette action, //Restore waived continuity "
         "issues (this scene)//, brings waived issues back.",
         "Chapter 5"],
        ["**Writing model.** A third model setting for drafting, rewrites "
         "and the style guide, with a picker that lists the whole "
         "catalog; the Settings screen is more compact.",
         "Chapters 5 and 7"],
        ["**New keys:** `ctrl+g` (AI write), `f7` and `f8` (accept and "
         "reject a draft), `f1` (help, also from the editor). "
         "Select-all moved from `f7` to `f5`.", "Chapter 8"],
        ["**Pending AI text is ignored** by word counts, continuity "
         "checks, the story bible, the alias finder and backlinks.",
         "Chapters 3, 4 and 6"],
        ["**Tour** has a fifth page on AI writing. The launch-screen key "
         "hint now wraps instead of being cut off.", "Chapter 2"],
        ["**Appendixes:** `style.md`, `style.md.bak`, `.drafts/`, the "
         "`<!--ai-->` marker format, `writing_model`, and the scene field "
         "of `waivers.json` are described in Appendix A; every new "
         "message is in Appendix B; the tutorial (Appendix C) now "
         "uses the bundled Residual example and adds AI writing steps.",
         "Appendixes A, B, C"],
    ], [0.78, 0.22])

    # ============================================================ CH 1
    s.chapter("1", "Introducing Lorewrite",
              "What Lorewrite is for, and the handful of ideas that "
              "everything else in this book builds on.")
    s.p("Lorewrite is a program for writing novels and other long fiction "
        "at a keyboard, inside a terminal window. You write your scenes in "
        "a plain editor. As you go, you tell Lorewrite about the people, "
        "places, things and organizations in your story, and it helps you "
        "keep them straight: it shows you where each one appears, lets you "
        "jump to the notes you keep on each, and, if you choose, uses an AI "
        "service to look for slips in continuity.",
        idx=["Lorewrite|purpose"])
    s.p("It is deliberately modest. It does not format your book, publish "
        "it, or write it for you. It keeps your files plain, your notes "
        "close, and your story consistent.")

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
        "when you move one.")
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
        "You do not have to type anything special; see Chapter 4.")
    s.h3("Links and backlinks", idx=["link", "backlink"])
    s.p("You may also mark a name explicitly by wrapping it in double "
        "square brackets, like `[[Rook Tanaka]]`. This is a //link//. Links "
        "were how earlier versions of Lorewrite worked; they are now "
        "optional, but they still work and are useful in a few cases "
        "described in Chapter 4.")
    s.p("The other side of a link is a //backlink//. When the cursor is on "
        "a name, Lorewrite shows the note for that entity and lists every "
        "line in your book that mentions it, so that you can jump straight "
        "to any of them.")
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
        "exactly as described in Chapters 2 to 4 and makes no network "
        "connections while you write.")
    s.attention("Accepting a proposal does change your files: accepted "
                "aliases and canon facts are written into your notes, and "
                "an accepted draft becomes part of your scene. The review "
                "screens and the accept and reject keys are where you stay "
                "in control. Chapters 5 and 6 describe what each one "
                "will do.")

    s.h2("What You Need")
    s.bullets([
        "A computer with Python 3.11 or later and a terminal window "
        "(Chapter 2).",
        "For the AI features only: an OpenRouter account and an API key, "
        "and a network connection when you use them (Chapters 5 and 6).",
        "Nothing else. Lorewrite runs in a terminal of at least about "
        "100 columns by 30 rows; larger is more comfortable.",
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
    s.attention("`--new` creates the project files directly in the folder "
                "named by `--project`, or in the current folder. Run it "
                "from an empty folder, not from a folder that already "
                "holds other files you care about.")

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
        ["s", "Open the Settings screen (Chapter 7)."],
        ["q", "Quit Lorewrite. (If you reached the launch screen with "
         "//Return to main menu//, `q` instead returns to the project you "
         "were in.)"],
    ], [0.20, 0.80], mono_cols=(0,))
    s.h3("Opening a folder", idx=["opening a project"])
    s.p("Press `o`. A box titled //Project folder:// asks for a path. "
        "Type it (a leading `~` stands for your home folder) and press "
        "`enter`. If the folder does not contain a `project.toml` file, "
        "Lorewrite says //No lorewrite project in// followed by the path.")

    s.h2("Creating a New Project", idx=["new project", "creating a project"])
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
    s.p("The tour is shown once. Lorewrite records that you have seen it in "
        "its settings file (`tour_seen`). To see it again, open "
        "`settings.json` in the state folder (see below) and change "
        "`\"tour_seen\": true` to `false`.")

    s.h2("Where Lorewrite Keeps Its Own Settings",
         idx=["state folder", "settings.json", "recent.json"])
    s.p("Apart from your projects, Lorewrite keeps two small files in "
        "`~/.local/state/lorewrite`: `recent.json` (the list on the launch "
        "screen) and `settings.json` (whether you have seen the tour, and "
        "your chosen AI models). They can be deleted safely; Lorewrite "
        "recreates them. If you set the environment variable "
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
    s.p("Omarchy can also add a launcher for a program to its application "
        "menu or top bar. The design notes for Lorewrite describe using "
        "Omarchy's `omarchy tui install` command with a command line such "
        "as `lorewrite --project <path>`, and a top-bar button that runs "
        "`omarchy launch or focus tui --app-id=lorewrite` so that a "
        "running Lorewrite is brought to the front instead of a second copy "
        "being started. Those are features of Omarchy, not of Lorewrite; "
        "see the Omarchy documentation for the exact steps on your "
        "system.")

    s.h2("Leaving Lorewrite", idx=["quitting", "ctrl+q"])
    s.p("Press `ctrl+q`. Lorewrite saves the scene you are working on as "
        "it closes, so there is nothing to save first.")

    # ============================================================ CH 3
    s.chapter("3", "Writing Scenes",
              "The editor, saving, the status bar, writer mode, and "
              "everything you can do with scenes.")
    s.h2("The Main Window", idx=["main window"])
    s.p(f"After you open a project, the main window appears "
        f"({R('fig_main')}). It has five areas, listed in {R('t_areas')}.")
    s.figure("fig_main", "main", "The main window")
    s.table("t_areas", "Areas of the main window",
            ["Area", "What it shows"], [
        ["Title bar", "The program name and version, and the title of the "
         "project."],
        ["Sidebar (left)", "A filter box, the list of scenes, and the list "
         "of entities with their kinds."],
        ["Editor (center)", "The open scene or note, with line numbers."],
        ["Entity panel (right)", "The note for the name under the cursor, "
         "and a list of backlinks. See Chapter 4."],
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
        "numbers (which you can turn off; see Chapter 6), and colors "
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
        ["f6, f5", "Select the current line; select everything. (`f7` and `f8` accept and reject AI drafts; see Chapter 6.)"],
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
    s.attention("Lorewrite writes the contents of its editor over the file "
                "on disk. If you change the scene you have open using "
                "another program while Lorewrite is running, your change "
                "is lost the next time Lorewrite saves. Quit Lorewrite, or "
                "switch to a different scene, before editing that file "
                "elsewhere.")

    s.h2("The Status Bar", idx=["status bar", "word count"])
    s.p("The line above the footer describes the open file. Its fields, "
        "separated by vertical bars, are listed in "
        f"{R('t_status')}.")
    s.table("t_status", "Fields of the status bar",
            ["Field", "Meaning"], [
        ["`manuscript/02-capsule-7-19.md`",
         "The open file, relative to the project folder."],
        ["`● modified`", "You have typed since the last save."],
        ["`saved 23:10`", "The time of the last save. Until you have saved "
         "something in the session it reads simply `saved`."],
        ["`391 words (1502 project)`",
         "Words in the open file, and words in all scenes together. Words "
         "are runs of characters separated by spaces or line breaks. The "
         "project total is refreshed each time a file is saved. Text in "
         "pending AI drafts (Chapter 6) is not counted."],
        ["`Ln 11, Col 42`", "The line and column of the cursor."],
        ["A link hint", "When the cursor is on a name, the name and what "
         "`ctrl+j` will do: //to open// its note, or //no note, ctrl+j "
         "to create// one. Inside a pending AI draft, the hint //AI draft "
         "— f7 accept · f8 reject// comes first."],
        ["`AI $0.0153`", "The cost of the AI calls made since you started "
         "Lorewrite, as reported by OpenRouter. It appears after the "
         "first AI call that reports a cost and is not shown before."],
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

    s.h2("Moving Between Scenes", idx=["scene|navigating", "alt+left", "alt+right"])
    s.p("Press `alt+right` for the next scene and `alt+left` for the "
        "previous one. A brief message shows the title of the scene you "
        "have moved to. At the first or last scene, the message //No more "
        "scenes this way// appears. If you are looking at an entity note "
        "when you press either key, Lorewrite takes you back to the first "
        "scene. You can also click a scene in the sidebar, or use the "
        "command palette (Chapter 7) to open a scene by title.")

    s.h2("Creating a Scene", idx=["scene|creating", "new scene", "ctrl+n"])
    s.proc("To create a scene:", [
        "Press `ctrl+n`. A box asks //New scene title://.",
        "Type a title and press `enter`. (`esc` cancels.)",
    ])
    s.figure("fig_newscene", "newscene", "Creating a scene")
    s.p("Lorewrite makes a new file at the end of the manuscript, named "
        "with the next number and a version of the title, for example "
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
    s.p("Scenes are ordered by the number at the start of the file name. To "
        "move the open scene, choose **Action · Move current scene up** or "
        "**Action · Move current scene down** from the command palette. "
        "Lorewrite swaps the numbers of the scene and its neighbor, so "
        "both files are renamed. A message says //Moved to// and the new "
        "file name. At the top or bottom of the book it says //Scene is "
        "already at the edge//.")
    s.p("If the scene has pending AI drafts (Chapter 6), the file that "
        "holds their originals moves along with it.")
    s.attention("Moving a scene renames files. If your project is under "
                "version control, the change appears as two renames. A "
                "scene whose file name does not start with a number (a "
                "file you added yourself) cannot be moved; in that case "
                "Lorewrite also says //Scene is already at the edge//. "
                "Rename such files yourself, following the pattern "
                "`NN-name.md`.")

    s.h2("Deleting a Scene", idx=["scene|deleting"])
    s.proc("To delete the open scene:", [
        "Choose **Action · Delete current scene** from the command "
        "palette.",
        f"Read the confirmation ({R('fig_delete')}). Press `y` or click "
        "**Delete** to go ahead; press `n` or `esc`, or click **Cancel**, "
        "to keep the scene.",
    ])
    s.figure("fig_delete", "deleteconfirm", "Confirming the deletion of a "
             "scene")
    s.attention("Deleting a scene removes its file from the disk at once. "
                "It is not moved to a trash folder. Lorewrite has no undo "
                "for this; if you keep your project under version control "
                "or in a backed-up folder, you can recover the file from "
                "there.")
    s.p("Afterward, Lorewrite opens the first remaining scene and says "
        "//Deleted// followed by the title. The scene's file of pending-draft "
        "originals, if it has one (Chapter 6), is deleted with it.")

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

    # ============================================================ CH 4
    s.chapter("4", "Characters, Places and Mentions",
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
        "managed by the story-bible feature described in Chapter 5, and "
        "you can ignore it until then.")
    s.h3("Adding aliases", idx=["alias|adding"])
    s.p("Open the note (put the cursor on the name and press `ctrl+j`, or "
        "click it in the sidebar) and edit the `aliases:` line. Separate "
        "the aliases with commas. If an alias contains a colon, put it in "
        "quotation marks. When the note is saved (a moment after you "
        "stop typing), Lorewrite reloads its list of names, recolors your "
        "scenes and updates the backlinks. Lorewrite can also suggest "
        "aliases for you; see //Find Aliases// in Chapter 5.")
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
        "brackets to your text: not even the AI features do (Chapters 5 "
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
        "Names inside pending AI drafts (Chapter 6) are not counted. It "
        "shows the file, the line number and the beginning of the line, "
        "like `manuscript/03-the-stairwell.md:22`. Backlinks count "
        "mentions and links, by name or by any alias. Select one and press "
        "`enter` (or click it) to open that scene with the cursor on the "
        "line.")
    s.note("The panel changes only when the cursor is on a name. When you "
           "move to plain text it keeps showing the last entity you looked "
           "at.")

    s.h2("Rebuilding the Index", idx=["index (cache)|rebuilding", "f9", "rebuild index"])
    s.p("Backlinks come from the index, a cache kept in the project's "
        "`.lorewrite` folder. Lorewrite updates it as you work. If you "
        "add, edit or delete note files with another program, or if a "
        "backlink list looks out of date, press `f9`. Lorewrite saves the "
        "open file, rebuilds the index from every scene and note, reloads "
        "the notes, and says //Index rebuilt//. It is always safe to "
        "press `f9`.")

    s.h2("Renaming or Deleting an Entity", idx=["entity|deleting", "entity|renaming"])
    s.p("Lorewrite has no command for deleting a note. To remove an "
        "entity, delete its file (in `entities/characters`, "
        "`entities/places` and so on) with your file manager or a shell, "
        "then press `f9`. Its mentions stop being colored. To rename one, "
        "edit the `name:` line and, if you still use the old name, add it "
        "to `aliases`. The file's own name is unchanged by either edit, "
        "which is harmless.")

    # ============================================================ CH 5
    s.chapter("5", "AI Assistance",
              "Setting up an AI service, and the three features that help "
              "you keep your story consistent. All are proposals you "
              "confirm.")
    s.h2("Overview", idx=["AI|overview"])
    s.p("Lorewrite can use an AI service, called OpenRouter, to help with "
        "your story. This chapter describes how to set it up and the three "
        f"features summarized in {R('t_ai')}, which check and record "
        "consistency. The features that write prose are in Chapter 6. "
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
    s.p("There are three models in all, because the jobs differ. Finding "
        "names is easy and can be done by a small, cheap model (the "
        "//fast// model). Judging whether a scene contradicts your notes "
        "takes a more capable one (the //strong// model). Writing prose "
        "is a third kind of job, with its own //writing// model "
        "(Chapter 6).")
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
        "further help (Chapter 4).")
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
    s.p("Text in pending AI drafts (Chapter 6) is ignored, so the line "
        "numbers in the review are always the real line numbers of your "
        "scene.")

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
    s.p("Pending AI drafts (Chapter 6) are removed from the scene before "
        "it is checked: unaccepted AI text is not part of your story yet.")
    s.idx("Jev")
    s.note("If the optional helper program Jev is installed on your "
           "computer (as `~/.config/jev/jev.py`), Lorewrite first asks it "
           "a quick question about each entity, so that the more expensive "
           "model is asked only about entities the scene might "
           "contradict. If Jev is not installed, or fails, every entity is "
           "checked. You can ignore this if you have never installed it.")

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
    s.note("Facts in the review are wrapped, so a long fact is shown in "
           "full. Pending AI drafts (Chapter 6) are removed from the scene "
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
        "features send other text; see Chapter 6. Pending AI drafts are "
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
    s.chapter("6", "Writing with AI",
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
        "the fast and strong models of Chapter 5. It is a separate "
        "choice because writing is a different kind of job: what matters "
        "is the quality of the prose and the price per word, and what "
        "comes back is ordinary text, not the strict structured answer "
        "that finding aliases or checking continuity need. So any model "
        "will do, and the picker for this model lists the whole catalog. "
        "The writing model is also the one that learns your style guide. "
        "Its built-in default is `anthropic/claude-sonnet-4.5`; set "
        "your own with **Choose…** in Settings (Chapter 7) or with "
        "`writing_model` in the `[ai]` section of `project.toml` "
        "(Appendix A). You need an API key first (Chapter 5).")

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
        "`.drafts/03-the-stairwell.md.json` for the scene "
        "`03-the-stairwell.md`. It maps each id to the original words:")
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
        "its scene (Chapter 3).")
    s.h3("Accept and reject", idx=["accept draft", "reject draft", "f7", "f8"])
    s.p(f"Put the cursor inside a draft, or at either edge of it, and use "
        f"the keys in {R('t_draftkeys')}. If the cursor is not in a draft "
        "Lorewrite says //No AI draft under the cursor//.")
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
    s.p("Like the features of Chapter 5, these send text to OpenRouter, "
        "and to the company that runs the writing model, when you start "
        "them, and to no one otherwise. Learning a style guide sends about "
        "six thousand words of your prose, as numbered paragraphs with "
        "their scene file names. `ctrl+g` sends your style guide, about "
        "a thousand words of the scene around the cursor, the notes of the "
        "characters and places the scene mentions, and your instruction; "
        "for a rewrite, it also sends the selected passage. Each call's "
        "cost appears in the message that follows it and in the status "
        "bar (Chapter 5).")

    s.h2("Walkthrough: Writing in the Residual Project",
         idx=["tutorial|writing"])
    s.p("This walkthrough uses the Residual example that is supplied with "
        "Lorewrite (Appendix C says how to open a copy of it). You need "
        "an API key set up (Chapter 5). The figures in this chapter were "
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

    # ============================================================ CH 7
    s.chapter("7", "Settings Reference",
              "Every setting, where it is kept, and what it does.")
    s.h2("The Settings Screen", idx=["Settings screen"])
    s.p(f"Open the Settings screen ({R('fig_settings')}) from the command "
        "palette (**Action · Settings**), or by pressing `s` on the launch "
        "screen. It has the fields listed in "
        f"{R('t_settings')}.")
    s.figure("fig_settings", "settings", "The Settings screen with a "
             "project open, showing the three model rows")
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
         "by learning the style guide (Chapter 6). Empty means the "
         "default.", "`settings.json`"],
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
        ["Save", "Stores the models and, if a project is open, the editor "
         "settings, and closes the screen. A message says //Settings "
         "saved//.", ""],
    ], [0.24, 0.52, 0.24])
    s.p("The screen is compact: the boxes are one line tall so that all "
        "three model rows, the editor settings and the buttons fit in a "
        "window about 40 rows high. **Save** applies every field at once; the padding and line "
        "numbers change immediately. Pressing `esc` closes the screen and "
        "discards changes to the boxes. (The key buttons act at once and "
        "are not undone by `esc`.) From the launch screen, with no "
        "project open, only the AI settings are shown.")
    s.figure("fig_settings2", "settings_nokey_launch",
             "The Settings screen when no project is open (from the launch "
             "screen): only the AI settings appear")
    s.h2("Settings Files", idx=["project.toml|settings", "settings.json"])
    s.p("Settings live in three places, according to what they affect.")
    s.table("t_where", "Where settings are stored",
            ["Location", "Holds", "Affects"], [
        ["`project.toml` in the project", "Title, author, `[editor]` "
         "and `[ai]` sections.", "That project only."],
        ["`~/.local/state/lorewrite/settings.json`", "`tour_seen`, "
         "`fast_model`, `strong_model`, `writing_model`.", "All projects."],
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
    s.chapter("8", "Command and Key Reference",
              "Every key, every command-palette entry, and the keys of "
              "every dialog.")
    s.h2("Keys in the Main Window", idx=["keys|main window",
                                         "key bindings", "question mark", "terminal limits"])
    s.table("t_keys", "Keys in the main window",
            ["Key", "Action", "See"], [
        ["ctrl+n", "New scene.", "Chapter 3"],
        ["alt+left, alt+right", "Previous scene, next scene.", "Chapter 3"],
        ["ctrl+p", "Open the command palette.", "This chapter"],
        ["ctrl+j", "Open the note for the name under the cursor; with a "
         "name selected, or on a link with no note, create the note.",
         "Chapter 4"],
        ["ctrl+l", "AI: find other names your prose uses for your "
         "characters and places, and add them as aliases (never edits "
         "the scene).", "Chapter 5"],
        ["ctrl+g", "AI write: draft at the cursor (prompt window), expand "
         "the `{{expand: ...}}` placeholder under the cursor, or rewrite "
         "the selection. Also submits the prompt window.", "Chapter 6"],
        ["f7", "Accept the AI draft under the cursor.", "Chapter 6"],
        ["f8", "Reject the AI draft under the cursor.", "Chapter 6"],
        ["f5", "Select all text in the editor. (It was `f7` before "
         "AI drafts.)", "Chapter 3"],
        ["ctrl+s", "Save now.", "Chapter 3"],
        ["ctrl+b", "Hide or show the sidebar.", "Chapter 3"],
        ["f11", "Writer mode.", "Chapter 3"],
        ["f9", "Rebuild the index from disk.", "Chapter 4"],
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
        "`f11`. `f7` is used for accepting AI drafts, which is why select-all "
        "is on `f5`. The keys inside dialogs are listed in "
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
        ["Action ·", "Runs a command; see the next table.",
         "`Action · New scene`"],
    ], [0.16, 0.44, 0.40])
    s.p("Among the scenes and before the entities, the palette also lists "
        "a few general commands supplied by the terminal toolkit "
        "Lorewrite is built on: //Keys// (help for the focused widget), "
        "//Maximize//, //Quit//, //Screenshot// and //Theme// (change "
        "the color theme). They are not part of Lorewrite and are not "
        "described further here.")
    s.table("t_actions", "Palette actions",
            ["Entry", "What it does", "Key"], [
        ["New scene", "Create a new manuscript scene.", "ctrl+n"],
        ["Next scene", "Open the next scene.", "alt+right"],
        ["Previous scene", "Open the previous scene.", "alt+left"],
        ["Rename current scene", "Change the title of the open scene.",
         ""],
        ["Move current scene up", "Swap with the scene above (renumbers "
         "files).", ""],
        ["Move current scene down", "Swap with the scene below (renumbers "
         "files).", ""],
        ["Delete current scene", "Delete the open scene, after "
         "confirmation.", ""],
        ["Writer mode", "Hide everything but the editor.", "f11"],
        ["New character", "Create a character note.", ""],
        ["New place", "Create a place note.", ""],
        ["Find aliases in this scene", "AI: find other ways the prose "
         "refers to your entities, and add them as aliases.", "ctrl+l"],
        ["Check scene for continuity issues", "AI: flag contradictions "
         "with the story bible.", ""],
        ["Restore waived continuity issues (this scene)", "Un-waive this "
         "scene's continuity flags so the next check reports them.", ""],
        ["Update story bible from scene", "AI: propose new canon facts "
         "for notes from this scene.", ""],
        ["AI: learn style guide from manuscript", "Describe your voice "
         "from your own prose; review before saving `style.md`.", ""],
        ["Open style guide", "Edit `style.md`, the style guide the AI "
         "writing features follow.", ""],
        ["AI write at cursor / expand / rewrite selection", "Draft "
         "prose (prompt window), expand a `{{expand: ...}}` placeholder, "
         "or rewrite the selection.", "ctrl+g"],
        ["Accept all AI drafts in this scene", "Keep every pending AI "
         "draft as normal text.", "f7 (one)"],
        ["Reject all AI drafts in this scene", "Restore the original "
         "text for every pending AI draft.", "f8 (one)"],
        ["Set OpenRouter API key", "Store the key for AI features in the "
         "system keyring.", ""],
        ["Settings", "API key, models and editor preferences.", ""],
        ["Return to main menu", "Save, and go back to the launch screen "
         "to switch projects.", ""],
        ["Rebuild index", "Rebuild the link and entity index from disk.",
         "f9"],
    ], [0.36, 0.46, 0.18], mono_cols=(2,))
    s.p("Each is shown in the palette with the prefix //Action ·//. "
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

    # ============================================================ APP A
    s.chapter("A", "File Formats",
              "What Lorewrite reads and writes on disk.")
    s.h2("Project Layout", idx=["project|layout", "manuscript folder", "entities folder"])
    s.code("""\
my-novel/
  project.toml               title, author, [editor], [ai]
  .gitignore                 excludes .lorewrite/
  style.md                   your style guide (optional; you or the AI)
  style.md.bak               the guide before the last replacement
  manuscript/                scenes: 01-opening.md, 02-tavern.md, ...
  entities/                  entity notes, one folder for each kind
    characters/  places/  objects/  factions/
  .drafts/                   originals behind pending AI drafts
    02-tavern.md.json        one file per scene that has such drafts
  .lorewrite/                cache; safe to delete
    index.sqlite             the backlink index
    waivers.json             waived continuity issues""")
    s.p("Lorewrite only reads `manuscript/*.md` for scenes and "
        "`entities/*/*.md` for notes (the note's folder name does not "
        "matter; its `type:` line does), plus `style.md` and the `.drafts` "
        "folder described below. Everything else in the project "
        "folder is ignored, so you may keep research files beside them.")
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
writing_model = "anthropic/claude-sonnet-4.5\"""")
    s.table("t_toml", "Keys of project.toml",
            ["Key", "Meaning", "Default"], [
        ["title", "The project's title, shown in the title bar and on the "
         "launch screen.", "Untitled if missing"],
        ["author", "Your name. Not used by the program yet.", "empty"],
        ["[editor] padding", "Side padding of the editor, 0 to 8.", "0"],
        ["[editor] line_numbers", "`true` or `false`.", "true"],
        ["[ai] fast_model", "Model for Find aliases, for this "
         "project.", "your setting, else the built-in"],
        ["[ai] strong_model", "Model for continuity checks and "
         "story-bible updates, for this project.", "same"],
        ["[ai] writing_model", "Model for `ctrl+g` and for learning the "
         "style guide, for this project.", "same"],
    ], [0.27, 0.48, 0.25], mono_cols=(0,))
    s.p("When you press **Save** in Settings, Lorewrite rewrites only the "
        "`[editor]` section and leaves the rest of the file as it was.")
    s.h2("Scene Files", idx=["scene|file format"])
    s.p("A scene is a Markdown file named `NN-slug.md`, where //NN// is a "
        "two-digit number and //slug// is the title in lowercase with "
        "hyphens. The order of the scenes is the alphabetical order of "
        "the file names. The title is the first line that begins `# `; if "
        "there is none, the file name is used. Nothing else is required.")
    s.code("""\
# Capsule 7-19

The Meridian stacked its sleepers forty high under the spur, a
honeycomb of fiberglass coffins lit the color of weak tea.

Rook climbed the ladder and looked in.""")
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
        "created by //learn style guide// (Chapter 6) or, with the "
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
        "space.) When a new guide replaces an old one, the old file is "
        "first copied to `style.md.bak`, next to it. Both files are "
        "written safely, with a temporary copy swapped into place.")
    s.h2("Pending AI Text: the Marker and .drafts",
         idx=["marker (AI)|format", ".drafts folder|format"])
    s.p("A pending AI draft (Chapter 6) is stored in the scene file "
        "itself, between two HTML comments:")
    s.code("""\
<!--ai-->text the AI wrote<!--/ai-->
<!--ai id="k3f9q2"-->text that replaced something<!--/ai-->""")
    s.p("The first form is an insertion. The second replaced text (a "
        "selection that was rewritten, or an expanded placeholder). Its "
        "//id// is six lower-case letters and digits, unique in the "
        "project. The replaced text is stored in "
        "`.drafts/<scene file name>.json`, for example "
        "`.drafts/02-tavern.md.json`, as a JSON object from ids to "
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
        "an id has no entry, reject refuses (Chapter 6). A body that "
        "contains `<!--` has it changed to `<!-` when written, so a "
        "draft cannot contain a marker of its own. Markers that are "
        "nested, or missing one half, are not drafts; they are ordinary "
        "text. Moving a scene (which renames its file) carries its `.drafts` "
        "file along, and deleting a scene deletes it.")
    s.h2("The .lorewrite Folder", idx=[".lorewrite folder"])
    s.p("`index.sqlite` is the backlink index (see Chapter 4); it is "
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
  settings.json    {"tour_seen": true, "fast_model": null, ...}""")

    # ============================================================ APP B
    s.chapter("B", "Messages and Problem Solving",
              "The messages Lorewrite shows, in the words it uses, and "
              "what to do about them.")
    s.h2("Messages", idx=["messages"])
    s.p("Lorewrite reports what it has done with brief messages at the "
        "bottom right of the window. They fade after a few seconds. "
        "Warnings and errors are colored differently. Text in italic "
        "type below stands for something that varies.")
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
        ["Tip: learn a style guide first (ctrl+p → learn style)", "Shown "
         "once per session the first time you use `ctrl+g` with no "
         "`style.md`."],
        ["API key stored in the system keyring", "The key was saved."],
        ["Settings saved", "You pressed **Save** in Settings."],
        ["Renamed to '//title//'", "A scene was renamed."],
        ["Moved to //file name//", "A scene was reordered."],
        ["Deleted '//title//'", "A scene was deleted."],
        ["(a scene title)", "Shown briefly when you move to another "
         "scene with `alt+left` or `alt+right`."],
    ], [0.42, 0.58])
    s.table("t_msgs_warn", "Warnings",
            ["Message", "Cause and action"], [
        ["Open a scene first", "The command needs an open scene. Rename, "
         "move, delete and `ctrl+g` work only on scenes, not on entity "
         "notes or the style guide; open a scene from the sidebar."],
        ["No scenes yet — ctrl+n to create one", "The project has no "
         "scenes. Press `ctrl+n`."],
        ["No more scenes this way", "You are at the first or last scene."],
        ["Scene is already at the edge", "The scene cannot move further "
         "in that direction, or its file name has no leading number "
         "(rename the file to `NN-name.md`)."],
        ["No entities yet — create some notes first", "Find aliases and "
         "the story-bible update need at least one note. See Chapter 4."],
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
         "have no entry in `.drafts`; see Chapter 6."],
        ["No entities yet — nothing to check against", "The continuity "
         "check needs at least one note."],
        ["Select a name and press ctrl+j to make a note for it",
         "`ctrl+j` was pressed with nothing selected and the cursor not "
         "on a name."],
    ], [0.42, 0.58])
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
         "`.drafts`. Nothing was changed. See Chapter 6."],
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
         "(Chapter 5); you do not need to use the technical name in the "
         "message."],
    ], [0.42, 0.58])
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
         "the `.drafts` folder is gone (Chapter 6). Accept the draft and "
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
         "with another program (Chapter 3). Recover the file from a "
         "backup or version control."],
        ["The screen is garbled after a crash.", "Type `reset` in the "
         "terminal. Your files are safe; Lorewrite saves as you work."],
        ["I cannot remember a key.", "Press `f1` for the help screen (it works "
         "while you type), or `ctrl+p` and type what you want to do."],
        ["I want to see the tour again.", "Set `tour_seen` to `false` "
         "in `settings.json` (Chapter 2)."],
    ], [0.36, 0.64])

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
        "Open the copy: `lorewrite --project /tmp/residual`.",
    ], idx=["Residual example", "examples folder"])
    s.attention("Always open a //copy//. Lorewrite saves as you work, and "
                "the AI features write notes, `style.md` and `.drafts/` "
                "into the project, so the original would no longer be "
                "the clean example. If you start a second run, delete "
                "`/tmp/residual` and copy it again. The steps that use AI "
                "need an API key (Chapter 5).")
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
        "(Chapter 4).",
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

    # ============================================================ GLOSSARY
    s.chapter("G", "Glossary", mode="back", numbered=False)
    for term, d in sorted(GLOSSARY, key=lambda g: g[0].lower()):
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
  |     +-- 01-opening.md
  |     +-- 02-tavern.md
  |
  +-- style.md                       your style guide (optional)
  |
  +-- entities/                      notes on your story's things
  |     +-- characters/
  |     |     +-- elara-vance.md     name, type, aliases + free text
  |     +-- places/
  |     |     +-- thornwick.md
  |     +-- objects/   factions/     (the same idea)
  |
  +-- .drafts/                       originals behind pending AI drafts
  |
  +-- .lorewrite/                    cache, rebuilt at any time"""
    for ln in txt.split("\n"):
        assert len(ln) <= 78
    return Preformatted(txt, ST["code"])


GLOSSARY = [
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
     "project: recent projects, open, new, settings."),
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
    pages = build()
    print(f"wrote {OUT} ({pages} pages)")
