"""Assemble the book for export: the manuscript in reading order, as a small
model every writer shares (PDF, DOCX, EPUB, Markdown, LaTeX).

Pure Python, no Textual, no ReportLab. Reads files only; nothing is changed.

    Book
      parts: list[Part]      the unparted scenes first (title None), then real parts
        chapters: list[Chapter]   one per scene (or one per part when continuous)
          blocks: Paragraph (runs of plain/italic/bold text) | Break

What is left out: Unplaced Scenes, the Trash, research, comments, notes, scene
details (frontmatter). What is changed: ``[[Name|text]]`` -> its display text,
``{{expand: ...}}`` markers are removed (and reported), pending AI drafts are
rejected (or accepted, option) so unaccepted AI text is not in the book.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from pathlib import Path

from .. import drafts, scenemeta
from .. import structure as st
from ..links import WIKILINK_RE

FORMATS = ("pdf", "docx", "epub", "md", "tex")
NUMBERINGS = ("words", "numbers", "titles-only")
PAGE_SIZES = ("trade", "a5", "letter", "a4")


@dataclass(frozen=True)
class ExportOptions:
    format: str = "pdf"
    layout: str = "book"           # pdf only: book | manuscript | plain-proof
    page_size: str = "trade"       # trade (6x9 in) | a5 | letter | a4
    font: str = ""                 # "" = the layout's default
    numbering: str = "words"       # "Chapter 3" | "3" | title only
    toc: bool = True
    include_front_matter: bool = True
    include_drafts: bool = False   # pending AI drafts: False = original text
    continuous: bool = False       # scenes flow on with a break ornament
    copyright: str = ""            # edition / copyright line on the title page

    @classmethod
    def from_dict(cls, raw: dict | None) -> ExportOptions:
        """Options from untrusted input (the GUI bridge, project.toml): unknown
        keys are ignored, bad values raise ValueError with a plain message."""
        raw = raw or {}
        kw = {}
        for f in fields(cls):
            if f.name not in raw:
                continue
            value, default = raw[f.name], getattr(cls, f.name)
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise ValueError(f"{f.name} must be true or false")
            else:
                if not isinstance(value, str):
                    raise ValueError(f"{f.name} must be text")
                value = value.strip()
            kw[f.name] = value
        opts = cls(**kw)
        if opts.format not in FORMATS:
            raise ValueError(f"unknown export format: {opts.format}")
        if opts.numbering not in NUMBERINGS:
            raise ValueError(f"unknown numbering: {opts.numbering}")
        if opts.page_size not in PAGE_SIZES:
            raise ValueError(f"unknown page size: {opts.page_size}")
        return opts

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# -- the model -----------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    text: str
    italic: bool = False
    bold: bool = False


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Run, ...]

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass(frozen=True)
class Break:
    """A scene break inside a chapter (drawn as an ornament)."""


@dataclass
class Chapter:
    title: str                     # the scene's heading ("" when continuous)
    label: str = ""                # "Chapter 3" / "3" / "" per numbering
    blocks: list = field(default_factory=list)
    number: int | None = None      # position in the book, front matter excluded
    scene: str = ""                # project-relative path (for messages)


@dataclass
class Part:
    title: str | None              # None = scenes sitting directly in manuscript/
    label: str = ""                # "Part I"
    chapters: list[Chapter] = field(default_factory=list)
    front: bool = False            # front matter: no numbers, no part page


@dataclass(frozen=True)
class Notice:
    kind: str                      # "expand" | "draft-missing" | "empty"
    scene: str
    message: str


@dataclass
class Book:
    title: str
    author: str
    options: ExportOptions
    subtitle: str = ""
    copyright: str = ""            # the export's override, else the project's
    contact: str = ""
    language: str = "en"
    parts: list[Part] = field(default_factory=list)
    words: int = 0
    scenes: int = 0
    draft_scenes: list[str] = field(default_factory=list)  # titles of scenes with pending AI drafts
    warnings: list[Notice] = field(default_factory=list)

    def chapters(self):
        for part in self.parts:
            yield from part.chapters

    @property
    def real_parts(self) -> int:
        return sum(1 for p in self.parts if p.title is not None and not p.front)

    def messages(self) -> list[str]:
        """Plain sentences for the author: unaccepted AI drafts, then the rest."""
        out = []
        n = len(self.draft_scenes)
        if n:
            what = "included as written" if self.options.include_drafts else "left out (the original text is used)"
            out.append(f"{n} scene{'s have' if n != 1 else ' has'} unaccepted AI drafts, {what}.")
        out += [w.message for w in self.warnings]
        return out

    def summary(self) -> dict:
        return {
            "scenes": self.scenes,
            "words": self.words,
            "parts": self.real_parts,
            "draft_scenes": len(self.draft_scenes),
            "warnings": [{"kind": w.kind, "scene": w.scene, "message": w.message}
                         for w in self.warnings],
        }


# -- text -> blocks ---------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BREAK_RE = re.compile(r"^\s*([*\-_])(?:\s*\1){2,}\s*$")
_HASH_BREAK_RE = re.compile(r"^\s*#\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ESCAPES = "\\`*_{}[]()#+-.!|~<>"
_ESC_BASE = 0xE000  # private-use stand-ins for backslash-escaped characters
_INLINE_RE = re.compile(r"(\*\*\*|\*\*|\*|(?<!\w)_{1,3}(?!_)|(?<!_)_{1,3}(?!\w)|`)")


def _escape(text: str) -> str:
    return re.sub(r"\\([" + re.escape(_ESCAPES) + r"])",
                  lambda m: chr(_ESC_BASE + _ESCAPES.index(m.group(1))), text)


def _unescape(text: str) -> str:
    return "".join(_ESCAPES[ord(c) - _ESC_BASE]
                   if _ESC_BASE <= ord(c) < _ESC_BASE + len(_ESCAPES) else c
                   for c in text)


def parse_inline(text: str) -> tuple[Run, ...]:
    """Markdown inline formatting -> runs. ``*i*``/``_i_`` italic, ``**b**``
    bold, ``***bi***`` both, backticks are dropped (code is plain). A marker
    with no closing partner is literal text. Backslash escapes are honoured."""
    text = _escape(text)
    runs: list[Run] = []
    italic = bold = False
    pos = 0
    buf: list[str] = []

    def flush() -> None:
        if buf:
            runs.append(Run(_unescape("".join(buf)), italic, bold))
            buf.clear()

    def closes(token: str, start: int) -> bool:
        """Is there a later *token* that could close one opened here?"""
        j = text.find(token, start)
        while j != -1:
            word_after = j + len(token) < len(text) and text[j + len(token)].isalnum()
            if j > 0 and not text[j - 1].isspace() and not (token[0] == "_" and word_after):
                return True
            j = text.find(token, j + 1)
        return False

    while pos < len(text):
        m = _INLINE_RE.search(text, pos)
        if m is None:
            buf.append(text[pos:])
            break
        buf.append(text[pos:m.start()])
        tok = m.group(1)
        pos = m.end()
        kind = tok[0]
        if kind == "`":
            continue  # drop the backtick, keep the text
        after_ws = pos >= len(text) or text[pos].isspace()
        before_ws = m.start() == 0 or text[m.start() - 1].isspace()
        n = len(tok)
        # which states does this token toggle?
        toggles = ("bi" if n == 3 else "b" if n == 2 else "i")
        opening_state = (("b" in toggles and not bold) or ("i" in toggles and not italic))
        if opening_state:
            if after_ws or not closes(tok, pos):
                buf.append(tok)
                continue
        else:
            if before_ws:
                buf.append(tok)
                continue
        flush()
        if "b" in toggles:
            bold = not bold
        if "i" in toggles:
            italic = not italic
    flush()
    merged: list[Run] = []
    for r in runs:
        if not r.text:
            continue
        if merged and (merged[-1].italic, merged[-1].bold) == (r.italic, r.bold):
            merged[-1] = Run(merged[-1].text + r.text, r.italic, r.bold)
        else:
            merged.append(r)
    return tuple(merged)


def parse_blocks(body: str, break_hash: bool = False) -> list:
    """Scene text -> Paragraph / Break blocks. Blank lines separate paragraphs;
    hard-wrapped lines are joined; ``***`` / ``---`` / ``* * *`` lines are
    scene breaks. Sub-headings become bold paragraphs, ``>`` quote marks and
    HTML comments are dropped."""
    blocks: list = []
    lines: list[str] = []

    def end_paragraph() -> None:
        if not lines:
            return
        text = " ".join(s.strip() for s in lines).strip()
        lines.clear()
        runs = parse_inline(text)
        if "".join(r.text for r in runs).strip():
            blocks.append(Paragraph(runs))

    for raw in _COMMENT_RE.sub("", body).splitlines():
        line = raw.rstrip()
        if not line.strip():
            end_paragraph()
        elif _BREAK_RE.match(line) or (break_hash and _HASH_BREAK_RE.match(line)):
            end_paragraph()
            if not blocks or not isinstance(blocks[-1], Break):
                blocks.append(Break())
        else:
            h = _HEADING_RE.match(line)
            if h:
                end_paragraph()
                runs = tuple(Run(r.text, r.italic, True) for r in parse_inline(h.group(2)))
                if runs:
                    blocks.append(Paragraph(runs))
                continue
            lines.append(re.sub(r"^\s*>\s?", "", line))
    end_paragraph()
    while blocks and isinstance(blocks[-1], Break):
        blocks.pop()  # a scene never ends on an ornament
    while blocks and isinstance(blocks[0], Break):
        blocks.pop(0)
    return blocks


def count_words(blocks: list) -> int:
    return sum(len(b.text.split()) for b in blocks if isinstance(b, Paragraph))


def roman(n: int) -> str:
    out = ""
    for value, sym in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                       (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                       (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out += sym
            n -= value
    return out


def _deslug(name: str) -> str:
    words = re.split(r"[-_\s]+", st._slug_of(name))
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or name


# -- assembling ---------------------------------------------------------------------


def _scene_text(project, path: Path, opts: ExportOptions, book: Book,
                rel: str) -> tuple[str, str]:
    """(title, body text) of one scene, with drafts resolved, details and the
    heading removed, links flattened and expand markers dropped."""
    text = path.read_text(encoding="utf-8")
    pend = drafts.find_pending(text)
    if pend:
        label = rel
        book.draft_scenes.append(label)
        originals = drafts.load_originals(project.root, path)
        if opts.include_drafts:
            text = drafts.accept_all(text)
        else:
            for p in pend:
                if p.id and p.id not in originals:
                    book.warnings.append(Notice(
                        "draft-missing", rel,
                        f"{rel}: an AI draft replaced text whose original is missing; "
                        "it is left out of the export"))
            text = drafts.reject_all(text, originals)
    text = scenemeta.strip(text)

    title = ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            del lines[i]
            text = "\n".join(lines)
        break
    if not title:
        title = _deslug(path.name)

    for marker in drafts.find_expand_markers(text):
        book.warnings.append(Notice(
            "expand", rel, f"{rel}: expand marker removed: {marker.instruction}"))
    text = drafts._EXPAND_RE.sub("", text)
    text = WIKILINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)
    return title, text


def assemble(project, options: ExportOptions | None = None) -> Book:
    opts = options or ExportOptions()
    info = project.author_info()
    # Use pen_name if set, otherwise author
    author = info["pen_name"] or info["author"]
    book = Book(title=project.title, author=author, options=opts,
                subtitle=info["subtitle"], copyright=opts.copyright.strip() or info["copyright"],
                contact=info["contact"], language=info["language"])
    unit_word = "Chapter" if project.unit == "chapter" else "Scene"

    groups: list[tuple[Part, list[Path]]] = []
    top = project.part_scenes(None)
    if top:
        groups.append((Part(title=None), top))
    parts_numbered = 0
    for folder in project.list_parts():
        front = project.part_is_front_matter(folder)
        if front and not opts.include_front_matter:
            continue
        scenes = project.part_scenes(folder)
        if not scenes:
            continue
        part = Part(title=project.part_title(folder), front=front)
        if not front:
            parts_numbered += 1
            if opts.numbering != "titles-only":
                part.label = f"Part {roman(parts_numbered)}"
        groups.append((part, scenes))

    number = 0
    for part, scenes in groups:
        chapters: list[Chapter] = []
        for path in scenes:
            rel = path.relative_to(project.root).as_posix()
            title, body = _scene_text(project, path, opts, book, rel)
            blocks = parse_blocks(body)
            if not blocks:
                book.warnings.append(Notice("empty", rel, f"{rel}: the scene has no text"))
            ch = Chapter(title=title, blocks=blocks, scene=rel)
            if not part.front:
                number += 1
                ch.number = number
                if opts.numbering == "words":
                    ch.label = f"{unit_word} {number}"
                elif opts.numbering == "numbers":
                    ch.label = str(number)
            chapters.append(ch)
            book.scenes += 1
            book.words += count_words(blocks)
        if opts.continuous and chapters and not part.front:
            merged = Chapter(title="", blocks=[], scene=chapters[0].scene,
                             number=chapters[0].number)
            for ch in chapters:
                if merged.blocks and ch.blocks:
                    merged.blocks.append(Break())
                merged.blocks.extend(ch.blocks)
            chapters = [merged]
        part.chapters = chapters
        book.parts.append(part)
    return book
