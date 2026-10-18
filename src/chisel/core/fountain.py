"""Script mode: Fountain (https://fountain.io) inside Chisel's Markdown scenes.

A script project's scenes are ordinary ``.md`` files; the body is Fountain. This module is the one place
that knows the format (the GUI and the exporters never re-implement it):

* ``parse`` classifies every line (scene heading, action, character, dialogue, ...) with code-point offsets,
  for the editor's formatting and for word / mention awareness;
* ``blocks`` groups those lines into screenplay elements; ``layout`` wraps and ``paginate`` pages them at the
  standard positions (Courier 12, 55 lines), which the PDF layout draws and the page estimate counts;
* ``import_text`` splits a ``.fountain`` file into parts and scenes; ``export_text`` is its inverse.

Differences from plain Fountain, all because the files are Markdown and Chisel owns some syntax:

* ``[[Name]]`` is a Chisel link, not a Fountain note. Notes are written ``<!-- note -->`` in a scene and
  become ``[[note]]`` on export (and back on import). Links are flattened to their text on export.
* The first ``# Title`` line of a scene is Chisel's scene title, not a Fountain section.
* A scene's YAML details and pending AI drafts are handled by the callers (``scenemeta`` / ``drafts``).

Pure Python; no Textual, no ReportLab.
"""

from __future__ import annotations

import re
import textwrap
from bisect import bisect_right
from dataclasses import dataclass, field

# -- line kinds ----------------------------------------------------------------------------------

BLANK = "blank"
TITLE = "title"                     # Chisel's "# Scene title" line
SCENE_HEADING = "scene_heading"
ACTION = "action"
CHARACTER = "character"
DIALOGUE = "dialogue"
PARENTHETICAL = "parenthetical"
TRANSITION = "transition"
CENTERED = "centered"
LYRICS = "lyrics"
SECTION = "section"
SYNOPSIS = "synopsis"
PAGE_BREAK = "page_break"
NOTE = "note"                       # <!-- ... --> (a Fountain note in Chisel's spelling)
BONEYARD = "boneyard"               # /* ... */

KINDS = (BLANK, TITLE, SCENE_HEADING, ACTION, CHARACTER, DIALOGUE, PARENTHETICAL, TRANSITION, CENTERED,
         LYRICS, SECTION, SYNOPSIS, PAGE_BREAK, NOTE, BONEYARD)
# lines that print nothing (the author's notes to self and the outline)
SILENT = (BLANK, TITLE, SECTION, SYNOPSIS, NOTE, BONEYARD)
# lines the spell checker and the name scanner should skip: they are not prose
NOT_PROSE = (SCENE_HEADING, TRANSITION, CHARACTER, SECTION, SYNOPSIS, NOTE, BONEYARD, PAGE_BREAK)

_SCENE_RE = re.compile(r"^(?:INT|EXT|EST|INT\./EXT|INT/EXT|I/E)[. ]", re.IGNORECASE)
_PAGE_BREAK_RE = re.compile(r"^={3,}\s*$")
_SCENE_NUMBER_RE = re.compile(r"\s*#([A-Za-z0-9.\-]+)#\s*$")
_EXTENSION_RE = re.compile(r"\s*\([^)]*\)")
_DUAL_RE = re.compile(r"\s*\^\s*$")


@dataclass(frozen=True)
class Line:
    kind: str
    start: int          # code-point offset of the line's first character
    end: int            # offset one past its last character (the newline is not included)
    text: str
    dual: bool = False  # a character cue ending in "^" (the second speaker of a dual dialogue)
    clean: str = ""     # the line without its notes and boneyard (what prints); "" for note lines


def _is_upper(s: str) -> bool:
    return any(c.isalpha() for c in s) and s == s.upper()


def cue_name(text: str) -> str:
    """The speaker of a character cue: no ``@`` force mark, extension "(V.O.)" or dual ``^``."""
    name = text.strip()
    if name.startswith("@"):
        name = name[1:]
    name = _DUAL_RE.sub("", name)
    return _EXTENSION_RE.sub("", name).strip()


_SPAN_RE = re.compile(r"<!--.*?(?:-->|\Z)|/\*.*?(?:\*/|\Z)", re.DOTALL)
_GAPS_RE = re.compile(r"(?<=\S) {2,}(?=\S)")


def parse(text: str) -> list[Line]:
    """Classify every line of *text* (a scene body; blank out frontmatter and AI markers first, see
    ``prepare``). Offsets are code points. Ambiguous text is action, as in Fountain.

    Notes (``<!-- -->``) and boneyard (``/* */``) may sit anywhere, on a line of their own, after text, or
    across lines: lines are classified with them masked out (so ``BOB <!-- n -->`` is still a cue), a line
    that holds only a note is a NOTE or BONEYARD line that does not interrupt dialogue, and ``Line.clean``
    is the line's text without them (what prints)."""
    n_text = len(text)
    spans = [(m.start(), m.end(), NOTE if m.group().startswith("<!--") else BONEYARD)
             for m in _SPAN_RE.finditer(text)]
    masked = list(text)
    removed = bytearray(n_text)
    for a, b, _kind in spans:
        for k in range(a, b):
            if masked[k] != "\n":
                masked[k] = " "
                removed[k] = 1
    span_starts = [a for a, _b, _k in spans]
    raw_lines = text.split("\n")
    masked_lines = "".join(masked).split("\n")
    out: list[Line] = []
    pos = 0
    ctx: str | None = None        # kind of the last line that is not a note or boneyard
    seen_content = False          # a non-blank line was already seen (the title must come first)
    n = len(raw_lines)

    def blank_like(kind: str | None) -> bool:
        return kind is None or kind in SILENT

    for i, raw in enumerate(raw_lines):
        start, end = pos, pos + len(raw)
        pos = end + 1
        line = masked_lines[i].rstrip("\r")
        s = line.strip()
        prev = ctx
        clean = raw
        if any(removed[start:end]):
            clean = _GAPS_RE.sub(" ", "".join(c for k, c in enumerate(raw, start) if not removed[k]))

        if not s:
            if raw.strip():       # only a note or boneyard: it does not break a speech or a gap
                kind = spans[max(0, bisect_right(span_starts, start + len(raw) - len(raw.lstrip())) - 1)][2]
                out.append(Line(kind, start, end, raw, False, ""))
                continue
            # exactly two spaces inside a dialogue block keep the speech going (Fountain)
            nxt = masked_lines[i + 1].strip() if i + 1 < n else ""
            if raw == "  " and prev in (CHARACTER, DIALOGUE, PARENTHETICAL) and nxt:
                out.append(Line(DIALOGUE, start, end, raw, False, raw))
            else:
                out.append(Line(BLANK, start, end, raw, False, raw))
            ctx = out[-1].kind
            continue

        first = not seen_content
        seen_content = True
        after_gap = i == 0 or blank_like(prev)
        j = i + 1                  # the next line that is not only a note decides "a line follows"
        while j < n and not masked_lines[j].strip() and raw_lines[j].strip():
            j += 1
        nxt_blank = j >= n or not masked_lines[j].strip()
        dual = bool(_DUAL_RE.search(s))

        if first and line.startswith("# "):
            kind = TITLE
        elif _PAGE_BREAK_RE.match(s):
            kind = PAGE_BREAK
        elif s.startswith("#"):
            kind = SECTION
        elif s.startswith("="):
            kind = SYNOPSIS
        elif s.startswith("!"):
            kind = ACTION
        elif s.startswith("@") and len(s) > 1:
            kind = CHARACTER
        elif s.startswith(".") and len(s) > 1 and s[1].isalnum():
            kind = SCENE_HEADING
        elif s.startswith(">"):
            kind = CENTERED if s.endswith("<") else TRANSITION
        elif s.startswith("~"):
            kind = LYRICS
        elif prev in (CHARACTER, DIALOGUE, PARENTHETICAL):
            if s.startswith("(") and s.endswith(")") and prev in (CHARACTER, DIALOGUE):
                kind = PARENTHETICAL
            else:
                kind = DIALOGUE
        elif after_gap and _SCENE_RE.match(s):
            kind = SCENE_HEADING
        elif after_gap and nxt_blank and _is_upper(s) and s.endswith("TO:"):
            kind = TRANSITION
        elif after_gap and not nxt_blank and not s.startswith("(") and _is_upper(_EXTENSION_RE.sub("", _DUAL_RE.sub("", s))):
            kind = CHARACTER
        else:
            kind = ACTION
        out.append(Line(kind, start, end, raw, dual and kind == CHARACTER, clean))
        ctx = kind
    return out


def prepare(text: str) -> str:
    """*text* ready for ``parse``: the scene's YAML details and the markers around pending AI drafts become
    same-length whitespace (offsets and rows stay valid), so a draft's lines are classified as if accepted."""
    from . import drafts, scenemeta
    chars = list(scenemeta.blank(text))
    for p in drafts.find_pending(text):
        for rng in ((p.start, p.body_start), (p.body_end, p.end)):
            for k in range(*rng):
                if chars[k] != "\n":
                    chars[k] = " "
    return "".join(chars)


def parse_scene(text: str) -> list[Line]:
    """``parse(prepare(text))``: a scene file as it is on disk or in the editor."""
    return parse(prepare(text))


def spans(text: str) -> list[dict]:
    """Editor spans for a scene: one ``{"kind": "script", "element", "start", "end"}`` per line that is not
    plain action (action is the unformatted default). Code-point offsets; callers convert with ``to_utf16``."""
    return [{"kind": "script", "element": ln.kind, "start": ln.start, "end": ln.end}
            for ln in parse_scene(text) if ln.kind not in (ACTION, BLANK)]


def blank_non_prose(text: str, keep: tuple[str, ...] = ()) -> str:
    """*text* with every line that is not prose (headings, cues, transitions, notes, sections ...) replaced by
    same-length whitespace, for the spell checker. Kinds named in *keep* stay."""
    chars = list(text)
    for ln in parse_scene(text):
        if ln.kind in NOT_PROSE and ln.kind not in keep:
            for k in range(ln.start, ln.end):
                chars[k] = " "
    return "".join(chars)


def cues(text: str) -> list[tuple[int, int, str]]:
    """(start, end, name) of the speaker name in every character cue (code points), for mention scanning."""
    out = []
    for ln in parse_scene(text):
        if ln.kind != CHARACTER:
            continue
        name = cue_name(ln.clean)
        if not name:
            continue
        at = ln.text.find(name)
        out.append((ln.start + at, ln.start + at + len(name), name))
    return out


# -- inline text -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Seg:
    text: str
    italic: bool = False
    bold: bool = False
    underline: bool = False


_INLINE_RE = re.compile(r"(\\[*_\\]|\*\*\*|\*\*|\*|_)")


def inline_runs(text: str) -> list[Seg]:
    """Fountain emphasis -> segments: ``*italic*``, ``**bold**``, ``***bold italic***``, ``_underline_``.
    A marker with no partner on the line is literal; ``\\*`` escapes."""
    toks = _INLINE_RE.split(text)
    out: list[Seg] = []
    state = {"i": False, "b": False, "u": False}
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append(Seg("".join(buf), state["i"], state["b"], state["u"]))
            buf.clear()

    def closes(tok: str, from_index: int) -> bool:
        return any(t == tok for t in toks[from_index:])

    for idx, tok in enumerate(toks):
        if tok.startswith("\\") and len(tok) == 2:
            buf.append(tok[1])
            continue
        if tok not in ("***", "**", "*", "_"):
            buf.append(tok)
            continue
        keys = {"***": "bi", "**": "b", "*": "i", "_": "u"}[tok]
        opening = not all(state[k] for k in keys) and not any(state[k] for k in keys)
        if opening and not closes(tok, idx + 1):
            buf.append(tok)
            continue
        flush()
        for k in keys:
            state[k] = not state[k]
    flush()
    return [s for s in out if s.text]


def plain(text: str) -> str:
    return "".join(s.text for s in inline_runs(text))


# -- elements ---------------------------------------------------------------------------------------


@dataclass
class Block:
    kind: str                 # SCENE_HEADING, ACTION, CHARACTER, PARENTHETICAL, DIALOGUE, TRANSITION,
                              # CENTERED, LYRICS, PAGE_BREAK, SECTION, SYNOPSIS
    lines: list[str] = field(default_factory=list)
    number: str = ""          # scene heading: the "#12#" scene number, if any
    dual: bool = False        # character cue ending in "^"


_SILENT_INLINE_RE = re.compile(r"<!--.*?-->|\[\[.*?\]\]|/\*.*?\*/")


def strip_silent(text: str) -> str:
    """*text* without its inline notes (``<!-- -->``, ``[[ ]]``) and boneyard (``/* */``): they never print."""
    return _SILENT_INLINE_RE.sub("", text)


def blocks(text: str) -> list[Block]:
    """Screenplay elements of a scene (or of a whole script), in order. Notes and boneyard are dropped;
    sections and synopses are kept (outline) but print nothing."""
    out: list[Block] = []
    last: Line | None = None
    for ln in parse(text):
        k = ln.kind
        if k in (BLANK, TITLE, NOTE, BONEYARD):
            if k == BLANK:
                last = ln
            continue
        clean = strip_silent(ln.clean)     # parse() already removed <!-- --> and /* */ wherever they sit
        if ln.text.strip() and not clean.strip():
            continue                       # a line that was only a note
        ln = Line(k, ln.start, ln.end, clean, ln.dual, clean)
        s = ln.text.strip()
        if k == SCENE_HEADING:
            heading = s[1:] if s.startswith(".") else s
            m = _SCENE_NUMBER_RE.search(heading)
            number = m.group(1) if m else ""
            if m:
                heading = heading[:m.start()]
            out.append(Block(k, [heading.strip()], number))
        elif k == ACTION:
            body = ln.text.rstrip()
            if body.lstrip().startswith("!"):          # a forced action: drop the "!" (indent kept)
                lead = len(body) - len(body.lstrip())
                body = body[:lead] + body.lstrip()[1:]
            if out and out[-1].kind == ACTION and last is not None and last.kind != BLANK:
                out[-1].lines.append(body)
            else:
                out.append(Block(k, [body]))
        elif k == CHARACTER:
            name = s[1:] if s.startswith("@") else s
            out.append(Block(k, [_DUAL_RE.sub("", name)], dual=ln.dual))
        elif k == PARENTHETICAL:
            out.append(Block(k, [s]))
        elif k == DIALOGUE:
            if out and out[-1].kind == DIALOGUE and last is not None and last.kind in (DIALOGUE,):
                out[-1].lines.append(s)
            else:
                out.append(Block(k, [s]))
        elif k == TRANSITION:
            out.append(Block(k, [s[1:].strip() if s.startswith(">") else s]))
        elif k == CENTERED:
            out.append(Block(k, [s[1:-1].strip()]))
        elif k == LYRICS:
            out.append(Block(k, [s[1:].strip()]))
        elif k == SECTION:
            out.append(Block(k, [s]))
        elif k == SYNOPSIS:
            out.append(Block(k, [s[1:].strip()]))
        elif k == PAGE_BREAK:
            out.append(Block(k, []))
        last = ln
    return out


# -- layout and pages ---------------------------------------------------------------------------------

LINES_PER_PAGE = 55          # body lines of a page (Courier 12 on 6 lines per inch)
ACTION_WIDTH = 60            # characters (6.0 in at 10 per inch)
DIALOGUE_INDENT, DIALOGUE_WIDTH = 10, 35
PAREN_INDENT, PAREN_WIDTH = 16, 25
CUE_INDENT = 22


@dataclass(frozen=True)
class Row:
    kind: str
    indent: int                  # characters from the left margin
    segs: tuple[Seg, ...]


def _wrap(segs: list[Seg], width: int) -> list[list[Seg]]:
    """Word-wrap styled text to *width* characters, keeping each character's style."""
    chars = [(c, sg) for sg in segs for c in sg.text]
    words: list[list[tuple[str, Seg]]] = []
    cur: list[tuple[str, Seg]] = []
    for c, sg in chars:
        if c == " ":
            if cur:
                words.append(cur)
                cur = []
        else:
            cur.append((c, sg))
    if cur:
        words.append(cur)
    if not words:
        return [[]]
    lines: list[list[tuple[str, Seg]]] = []
    line: list[tuple[str, Seg]] = []
    for w in words:
        while len(w) > width:            # a word longer than the line is broken
            if line:
                lines.append(line)
                line = []
            lines.append(w[:width])
            w = w[width:]
        if not line:
            line = list(w)
        elif len(line) + 1 + len(w) <= width:
            line += [(" ", line[-1][1])] + w
        else:
            lines.append(line)
            line = list(w)
    if line:
        lines.append(line)
    rows: list[list[Seg]] = []
    for ln in lines:
        row: list[Seg] = []
        for c, sg in ln:
            if row and (row[-1].italic, row[-1].bold, row[-1].underline) == (sg.italic, sg.bold, sg.underline):
                row[-1] = Seg(row[-1].text + c, sg.italic, sg.bold, sg.underline)
            else:
                row.append(Seg(c, sg.italic, sg.bold, sg.underline))
        rows.append(row)
    return rows


def _upper(segs: list[Seg]) -> list[Seg]:
    return [Seg(s.text.upper(), s.italic, s.bold, s.underline) for s in segs]


def layout(items: list[Block]) -> list[tuple[Block, int, list[Row]]]:
    """(block, blank rows before it, its rows) for every printing block."""
    out: list[tuple[Block, int, list[Row]]] = []
    prev: str | None = None
    for b in items:
        if b.kind in (SECTION, SYNOPSIS):
            continue
        rows: list[Row] = []
        if b.kind == PAGE_BREAK:
            out.append((b, 0, []))
            prev = b.kind
            continue
        if b.kind == SCENE_HEADING:
            segs = _upper(inline_runs(b.lines[0]))
            for r in _wrap(segs, ACTION_WIDTH):
                rows.append(Row(b.kind, 0, tuple(r)))
        elif b.kind in (ACTION, LYRICS):
            for line in b.lines:
                lead = len(line) - len(line.lstrip(" "))
                for r in _wrap(inline_runs(line.strip()), ACTION_WIDTH - lead):
                    rows.append(Row(b.kind, lead, tuple(r)))
        elif b.kind == CHARACTER:
            for r in _wrap(inline_runs(b.lines[0]), ACTION_WIDTH - CUE_INDENT):
                rows.append(Row(b.kind, CUE_INDENT, tuple(r)))
        elif b.kind == PARENTHETICAL:
            for r in _wrap(inline_runs(b.lines[0]), PAREN_WIDTH):
                rows.append(Row(b.kind, PAREN_INDENT, tuple(r)))
        elif b.kind == DIALOGUE:
            for line in b.lines:
                if not line.strip():
                    rows.append(Row(b.kind, DIALOGUE_INDENT, ()))
                    continue
                for r in _wrap(inline_runs(line), DIALOGUE_WIDTH):
                    rows.append(Row(b.kind, DIALOGUE_INDENT, tuple(r)))
        elif b.kind == TRANSITION:
            segs = _upper(inline_runs(b.lines[0]))
            width = sum(len(s.text) for s in segs)
            rows.append(Row(b.kind, max(0, ACTION_WIDTH - width), tuple(segs)))
        elif b.kind == CENTERED:
            segs = inline_runs(b.lines[0])
            width = sum(len(s.text) for s in segs)
            rows.append(Row(b.kind, max(0, (ACTION_WIDTH - width) // 2), tuple(segs)))
        before = 0 if b.kind in (PARENTHETICAL, DIALOGUE) and prev in (CHARACTER, PARENTHETICAL, DIALOGUE) \
            else (1 if prev is not None else 0)
        out.append((b, before, rows))
        prev = b.kind
    return out


def paginate(items: list[Block]) -> list[list[Row | None]]:
    """Pages of rows (``None`` = a blank row). Rules: a scene heading, character cue or parenthetical never
    ends a page (it moves with what follows), action and dialogue split only with two rows on each side, a
    page break starts a new page, and a blank row is not kept at the top of a page."""
    laid = layout(items)
    pages: list[list[Row | None]] = [[]]

    def new_page() -> None:
        if pages[-1]:
            pages.append([])

    for idx, (b, before, rows) in enumerate(laid):
        if b.kind == PAGE_BREAK:
            new_page()
            continue
        rows = list(rows)
        if not rows:
            continue
        follow = 0                      # rows that must stay on the page with this block
        if b.kind in (SCENE_HEADING, CHARACTER, PARENTHETICAL):
            for nb, nbefore, nrows in laid[idx + 1:idx + 3]:
                if nb.kind == PAGE_BREAK or not nrows:
                    break
                follow += nbefore + min(len(nrows), 2)
                if nb.kind == DIALOGUE:
                    break
        while rows:
            lead = before if pages[-1] else 0
            room = LINES_PER_PAGE - len(pages[-1])
            if lead + len(rows) + follow <= room:
                pages[-1].extend([None] * lead + rows)
                break
            take = room - lead
            if b.kind in (ACTION, DIALOGUE) and len(rows) >= 4 and take >= 2 and pages[-1]:
                take = min(take, len(rows) - 2)
                if take >= 2:
                    pages[-1].extend([None] * lead + rows[:take])
                    rows = rows[take:]
                    new_page()
                    before = 0
                    continue
            if pages[-1]:
                new_page()
                continue
            pages[-1].extend(rows[:LINES_PER_PAGE])    # a block taller than a page
            rows = rows[LINES_PER_PAGE:]
            if rows:
                new_page()
    while len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages


def estimate_pages(text: str) -> float:
    """Pages in eighths (a rough screenplay page count: one page is about a minute of screen time)."""
    rows = 0
    for _b, before, r in layout(blocks(text)):
        rows += before + len(r)
    eighths = -(-rows * 8 // LINES_PER_PAGE) if rows else 0
    return eighths / 8


def format_pages(pages: float) -> str:
    """7.375 -> "7 3/8"; 0.25 -> "2/8"; 3.0 -> "3"."""
    whole = int(pages)
    eighths = round((pages - whole) * 8)
    if eighths == 8:
        whole, eighths = whole + 1, 0
    if not eighths:
        return str(whole)
    frac = f"{eighths}/8"
    return f"{whole} {frac}" if whole else frac


# -- Chisel <-> Fountain text -------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--(?!/?ai\b).*?-->", re.DOTALL)
_NOTE_RE = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)


def _note_to_fountain(m: re.Match) -> str:
    body = m.group(0)[4:-3].strip()
    return "[[" + re.sub(r"\n[ \t]*\n", "\n  \n", body) + "]]"


def notes_to_fountain(text: str) -> str:
    """``<!-- note -->`` -> ``[[note]]`` (a blank line inside a note gets the two spaces Fountain needs)."""
    return _COMMENT_RE.sub(_note_to_fountain, text)


def notes_from_fountain(text: str) -> str:
    """``[[note]]`` -> ``<!-- note -->`` so Chisel does not read a Fountain note as a link to a missing note."""
    return _NOTE_RE.sub(lambda m: "<!-- " + m.group(1).strip() + " -->", text)


def word_count(text: str) -> int:
    """Words a reader would hear or see: notes, boneyard, sections and synopses do not count."""
    return sum(len(ln.clean.split()) for ln in parse(text) if ln.kind not in SILENT and ln.kind != PAGE_BREAK)


# title page ------------------------------------------------------------------------------------------

_TITLE_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$")
_TITLE_KEYS = ("title", "credit", "author", "authors", "source", "notes", "draft date", "date", "contact",
               "copyright", "revision", "header", "footer", "font", "tl", "tc", "tr", "bl", "bc", "br")


def split_title_page(text: str) -> tuple[dict[str, str], str]:
    """({key: value}, the rest of the text). A title page is ``Key: value`` lines (values may continue on
    indented lines) at the very top, ended by a blank line. Keys are lower case."""
    lines = text.lstrip("﻿").split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return {}, text
    first = _TITLE_KEY_RE.match(lines[i])
    if not first or lines[i].startswith((" ", "\t")) or first.group(1).strip().lower() not in _TITLE_KEYS:
        return {}, text
    data: dict[str, str] = {}
    key = ""
    j = i
    while j < len(lines) and lines[j].strip():
        ln = lines[j]
        if ln.startswith((" ", "\t")) and key:
            data[key] = (data[key] + "\n" + ln.strip()).strip("\n")
        else:
            m = _TITLE_KEY_RE.match(ln)
            if not m:
                return {}, text    # not a title page after all
            key = m.group(1).strip().lower()
            data[key] = m.group(2).strip()
        j += 1
    return data, "\n".join(lines[j:])


def title_page_text(title: str, author: str = "", contact: str = "", copyright_: str = "",
                    subtitle: str = "") -> str:
    """The Fountain title page for a project ("" when there is nothing to say)."""
    def one(key: str, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if "\n" in value:
            return f"{key}:\n" + "\n".join("    " + v.strip() for v in value.splitlines() if v.strip()) + "\n"
        return f"{key}: {value}\n"
    body = (one("Title", title) + one("Credit", "Written by" if author.strip() else "")
            + one("Author", author) + one("Source", subtitle) + one("Contact", contact)
            + one("Copyright", copyright_))
    return body + "\n" if body else ""


# import ------------------------------------------------------------------------------------------------


@dataclass
class ImportedScene:
    title: str
    text: str            # the scene file's text, "# Title" first


@dataclass
class ImportedPart:
    title: str | None    # None = scenes before the first "# Section"
    scenes: list[ImportedScene] = field(default_factory=list)


@dataclass
class Imported:
    title_page: dict[str, str]
    parts: list[ImportedPart]

    @property
    def scenes(self) -> int:
        return sum(len(p.scenes) for p in self.parts)


def _heading_title(heading: str) -> str:
    s = heading.strip()
    s = s[1:] if s.startswith(".") else s
    s = _SCENE_NUMBER_RE.sub("", s).strip()
    return (s[:77] + "...") if len(s) > 80 else s


def import_text(text: str) -> Imported:
    """Split a Fountain script into parts (level-1 sections) and scenes (one per scene heading). A synopsis
    right above a scene heading names the scene, else the heading does. Text before the first heading becomes
    a scene called "Opening", unless it is only a transition such as "FADE IN:", which starts the first scene.
    Notes become ``<!-- -->`` comments; boneyard stays as written."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    page, body = split_title_page(text)
    body = notes_from_fountain(body)
    lines = body.split("\n")
    parsed = parse(body)

    parts: list[ImportedPart] = [ImportedPart(None)]
    chunk: list[str] = []
    title: str | None = None     # the scene being collected (None before the first heading)

    def only_a_prelude(content: str) -> bool:
        """Nothing but transitions and notes ("FADE IN:"): it belongs to the scene that follows."""
        lines_ = [ln for ln in parse(content) if ln.kind != BLANK]
        return bool(lines_) and all(
            ln.kind in (TRANSITION, NOTE, BONEYARD)
            or (ln.kind == ACTION and _is_upper(ln.text.strip()) and ln.text.strip().endswith(":"))
            for ln in lines_)

    def finish() -> None:
        nonlocal chunk, title
        content = "\n".join(chunk).strip("\n")
        if title is None and only_a_prelude(content):
            return                         # kept in the chunk: the next scene starts with it
        if content.strip():
            name = title or "Opening"
            parts[-1].scenes.append(ImportedScene(name, f"# {name}\n\n{content}\n"))
        chunk = []
        title = None

    # follows[k]: after line k only blanks, synopses and notes lie between it and a scene heading
    # (one backward pass: a run of synopsis lines must not be rescanned for every line)
    follows = [False] * len(parsed)
    flag = False
    for k in range(len(parsed) - 1, -1, -1):
        follows[k] = flag
        kind_ = parsed[k].kind
        if kind_ == SCENE_HEADING:
            flag = True
        elif kind_ not in (BLANK, SYNOPSIS, NOTE, BONEYARD):
            flag = False

    synopsis: str | None = None
    extras: list[str] = []         # further synopsis lines above the same heading: kept in the scene
    for k, (ln, raw) in enumerate(zip(parsed, lines)):
        s = raw.strip()
        # (the first "# " line of a file is classified as a title; here it is a section)
        if ln.kind in (SECTION, TITLE) and re.match(r"#\s*[^#\s]", s):
            finish()
            synopsis = None
            extras = []
            parts.append(ImportedPart(s[1:].strip()))
        elif ln.kind == SCENE_HEADING:
            finish()
            title = synopsis or _heading_title(ln.clean)
            synopsis = None
            while chunk and not chunk[-1].strip():
                chunk.pop()
            if chunk:                      # a prelude ("FADE IN:") kept from before: one blank line, then the heading
                chunk.append("")
            chunk.append(s)
            for extra in extras:
                chunk += ["", extra]
            extras = []
        elif ln.kind == SYNOPSIS and not s.startswith("==") and s[1:].strip() and follows[k]:
            if synopsis is None:
                synopsis = s[1:].strip()
            else:
                extras.append(s)
        else:
            chunk.append(raw)
    finish()
    return Imported(page, [p for p in parts if p.scenes or p.title is not None])


# export ------------------------------------------------------------------------------------------------


def export_text(title_page: str, parts: list[tuple[str | None, list[tuple[str, str]]]]) -> str:
    """A Fountain document: the title page, then every part as a ``# Section`` and every scene as its text,
    with a ``= synopsis`` of the scene title when the title says more than the heading does. *parts* is
    ``[(part title or None, [(scene title, scene body as Fountain)])]``; bodies are already cleaned."""
    out: list[str] = [title_page] if title_page else []
    for part_title, scenes in parts:
        if part_title:
            out.append(f"# {part_title}\n")
        for title, body in scenes:
            body = body.strip("\n")
            if not body.strip():
                continue
            first = next((ln for ln in parse(body) if ln.kind == SCENE_HEADING), None)
            heading = _heading_title(first.clean) if first else ""
            says_more = title and title.strip().lower() != heading.strip().lower()
            if says_more and first is not None:
                # the synopsis sits right above the heading (what a prelude such as FADE IN: leaves above it)
                body = f"{body[:first.start]}= {title}\n\n{body[first.start:]}"
            elif says_more and title.strip() != "Opening":
                body = f"= {title}\n\n{body}"
            out.append(body + "\n")
    return "\n".join(out).rstrip("\n") + "\n"
