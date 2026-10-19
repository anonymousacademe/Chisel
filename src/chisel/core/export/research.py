"""Research export: Word, LaTeX and PDF through pandoc (docs/dev/plan-research-mode.md section 8).

    assemble_research(project, opts) -> Book      read-only, the same rules as ``manuscript.assemble``
    convert_research(book, fmt, out, ...) -> ExportResult

``assemble_research`` reads scenes only through ``manuscript._scene_text`` (Parked scenes, the Trash, notebook
notes and scene frontmatter are never read; pending AI drafts are rejected unless ``include_drafts``) and turns
the prose into the research nodes of ``manuscript`` (Heading, Math, Citation, Footnote inline, Figure, Table,
Equation blocks). Numbers come from ``objects.numbering``; the bibliography is the CSL JSON of the sources the
text actually cites (``csljson``).

Escaping. Author text keeps the strict escaping of the fiction path (every character that could form markup,
``$`` and ``@`` included) and pandoc reads it with raw HTML and raw TeX off. Constructs this module GENERATES
bypass escaping: math (``$..$``), citations (``[@key]``), the figure, table and equation syntax. TeX that could
read a file, define a macro or switch category codes is never passed on (``tex_is_safe``): it is replaced by a
notice, so a manuscript can not make xelatex read a file. Style files that name a parent over the network
(``independent-parent``) are refused.

Limits (documented in the export dialog): references and numbers are typed text, not Word fields; list items
are exported as paragraphs; emphasis does not span a math, citation or footnote node's own formatting.
"""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .. import fsutil, objects
from .. import entities as ent
from ..links import find_citations
from ..paper.types import CiteRef
from . import csljson, pandoc
from .manuscript import (Book, Chapter, Citation, Equation, ExportOptions, Figure, Footnote, Heading,
                         Math, Notice, Paragraph, Part, Run, Table, _COMMENT_RE, _HEADING_RE, _BREAK_RE,
                         _scene_text, parse_inline)
from .markdown import _lang_tag

FORMATS = ("docx", "tex", "pdf")
CSL_DIR = Path(__file__).parent / "csl"
DEFAULT_STYLE = "chicago-author-date"
_PUA_FIRST, _PUA_LAST = 0xF000, 0xF8FF       # private-use stand-ins for inline nodes while parse_inline runs
_KIND_WORD = {"fig": "Figure", "tbl": "Table"}


# -- bundled citation styles ----------------------------------------------------------------------


def bundled_styles() -> dict[str, Path]:
    """Name -> path of the CSL styles shipped in ``export/csl/`` (CC BY-SA 3.0, see LICENSE.txt there)."""
    if not CSL_DIR.is_dir():
        return {}
    return {p.stem: p for p in sorted(CSL_DIR.glob("*.csl"))}


def bundled_csl(name: str | None = None) -> Path:
    """The path of a bundled style by plain name (default Chicago author-date). Never takes a path."""
    styles = bundled_styles()
    key = name or DEFAULT_STYLE
    if key not in styles:
        raise ValueError(f"unknown citation style: {key}")
    return styles[key]


def check_csl(path: Path) -> None:
    """Refuse a style that is not a readable, self-contained CSL file: a dependent style would make pandoc
    fetch its parent from the network."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise ValueError(f"the citation style could not be read: {Path(path).name}") from None
    if "<style" not in text or "http://purl.org/net/xbiblio/csl" not in text:
        raise ValueError(f"{Path(path).name} is not a CSL style file")
    if re.search(r"""rel\s*=\s*["']independent-parent["']""", text):
        raise ValueError(f"{Path(path).name} is a dependent style that needs its parent downloaded; "
                         "choose an independent CSL style")


# -- unsafe TeX -----------------------------------------------------------------------------------

_UNSAFE_TEX = re.compile(
    r"\\(?:input|include|includeonly|openin|openout|read|readline|write|immediate|catcode|csname|"
    r"usepackage|RequirePackage|documentclass|verbatiminput|lstinputlisting|directlua|luaexec|special|"
    r"pdfliteral|scantokens|endinput|InputIfFileExists|IfFileExists|includegraphics|shipout|"
    r"def|edef|gdef|xdef|let|futurelet|newcommand|renewcommand|providecommand|newenvironment|"
    r"DeclareRobustCommand|ShellEscape|pdfshellescape)(?![A-Za-z])|\^\^")


def tex_is_safe(tex: str) -> bool:
    """False for TeX that reads files, defines macros, changes category codes or spells a control sequence
    in ``^^`` notation: none of it belongs in an equation, and xelatex would run it."""
    return _UNSAFE_TEX.search(tex) is None


def _tex_clean(tex: str, *, single_line: bool) -> str:
    """Drop TeX ``%`` comments; optionally join the lines (inline math, table cells)."""
    lines = [re.sub(r"(?<!\\)%.*$", "", ln) for ln in tex.strip().split("\n")]
    if single_line:
        return " ".join(ln.strip() for ln in lines if ln.strip()).strip()
    return "\n".join(ln.rstrip() for ln in lines).strip()


# -- math spans (one rule source: objects.strip_math) -------------------------------------------------


def _math_spans(text: str) -> list[tuple[int, int]]:
    """``[start, end)`` of every ``$..$`` / ``$$..$$`` in *text*, as ``objects.strip_math`` (pandoc's
    ``tex_math_dollars`` rule) decides them: a span starts where that function blanks a ``$`` and ends at the
    first later ``$`` that closes it on its own."""
    if "$" not in text:
        return []
    mask = objects.strip_math(text, mode="research")
    spans: list[tuple[int, int]] = []
    n, i = len(text), 0
    while i < n:
        if text[i] == "$" and mask[i] != "$":
            j = text.find("$", i + 1)
            while j != -1:
                seg = objects.strip_math(text[i:j + 2], mode="research")   # +1 char: the digit rule
                if not seg[:j + 1 - i].strip():
                    end = j + 1
                    if text[end:end + 1] == "$" and len(seg) > end - i and not seg[end - i].strip():
                        end += 1                                          # the second $ of a closing $$
                    spans.append((i, end))
                    i = end
                    break
                j = text.find("$", j + 1)
            else:
                i += 1
            continue
        i += 1
    return spans


def _inside(spans, pos: int) -> bool:
    return any(s <= pos < e for s, e in spans)


def _footnote_spans(text: str, math) -> list[tuple[int, int]]:
    """``^[ ... ]`` inline notes, brackets balanced (``[[@k]]`` inside a note counts), math skipped."""
    out: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n - 1:
        if text[i] == "^" and text[i + 1] == "[" and not _inside(math, i) and (i == 0 or text[i - 1] != "\\"):
            depth, j = 0, i + 1
            while j < n:
                if _inside(math, j):
                    j += 1
                    continue
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                depth += c == "["
                depth -= c == "]"
                if depth == 0:
                    out.append((i, j + 1))
                    break
                j += 1
            i = out[-1][1] if out and out[-1][0] == i else i + 2
            continue
        i += 1
    return out


# -- parsing context ----------------------------------------------------------------------------------


class _Ctx:
    """What the parser needs from the project, and where it reports."""

    def __init__(self, project, book: Book):
        self.project = project
        self.book = book
        self.numbering = objects.numbering(project)
        self.objects = {f"{o.kind}:{o.label}": o for o in objects.list_objects(project)}
        self.scene = ""
        self.cited: list[str] = []
        self.first_scene: dict[str, str] = {}

    def note(self, kind: str, message: str) -> None:
        self.book.warnings.append(Notice(kind, self.scene, f"{self.scene}: {message}" if self.scene else message))

    def cite(self, key: str) -> None:
        if key not in self.first_scene:
            self.first_scene[key] = self.scene
            self.cited.append(key)

    def number(self, kind: str, label: str) -> str:
        num = self.numbering.get(f"{kind}:{label}")
        return num.display if num else ""

    def ref_text(self, kind: str, label: str) -> str:
        """The words a ``[[fig:x]]`` becomes: "Figure 2", "Table 1", "Eq. (3)"."""
        key = f"{kind}:{label}"
        if key not in self.objects:
            self.note("ref-missing", f"[[{key}]] refers to a {_KIND_WORD.get(kind, 'equation')} "
                                     "that does not exist")
            return f"{_KIND_WORD.get(kind, 'Eq.')} ??"
        n = self.number(kind, label)
        if not n:
            self.note("ref-unplaced", f"[[{key}]] is referred to but never placed in the text")
            return f"{_KIND_WORD.get(kind, 'Eq.')} ??"
        return f"Eq. ({n})" if kind == "eq" else f"{_KIND_WORD[kind]} {n}"


# -- inline text -> nodes -----------------------------------------------------------------------------


_DOLLAR = ""       # stands in for a backslash-escaped dollar while parse_inline runs


def _literal_dollars(text: str) -> str:
    """A backslash before a dollar is a literal dollar (pandoc's rule); an escaped backslash is skipped."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] in "\\$":
            out.append(_DOLLAR if text[i + 1] == "$" else text[i:i + 2])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def parse_research_inline(text: str, ctx: _Ctx) -> tuple:
    """Prose -> ``Run`` / ``Math`` / ``Citation`` / ``Footnote`` nodes. ``[[fig:x]]`` becomes its words."""
    text = "".join(c for c in text if not _PUA_FIRST <= ord(c) <= _PUA_LAST and c != _DOLLAR)
    math = _math_spans(text)
    notes = _footnote_spans(text, math)
    taken = list(math) + notes
    spans: list[tuple[int, int, str, object]] = [(s, e, "math", None) for s, e in math]
    spans += [(s, e, "note", None) for s, e in notes]
    for c in find_citations(text):
        if not _inside(taken, c.start):
            spans.append((c.start, c.end, "cite", c))
            taken.append((c.start, c.end))
    for r in objects.find_refs(text):
        if not _inside(taken, r.start):
            spans.append((r.start, r.end, "ref", r))
            taken.append((r.start, r.end))
    spans.sort(key=lambda s: s[0])
    working: list[str] = []
    nodes: list = []
    pos = 0
    for s, e, kind, payload in spans:
        if s < pos:
            continue
        working.append(text[pos:s])
        pos = e
        if kind == "ref":
            working.append(ctx.ref_text(payload.kind, payload.label))
            continue
        node = _node(kind, text[s:e], payload, ctx)
        if node is None:
            working.append(text[s:e])
            continue
        if isinstance(node, str):             # a replacement sentence (unsafe math)
            working.append(node)
            continue
        working.append(chr(_PUA_FIRST + len(nodes)))
        nodes.append(node)
        if _PUA_FIRST + len(nodes) > _PUA_LAST:
            break
    working.append(text[pos:])
    runs = parse_inline(_literal_dollars("".join(working)))
    out: list = []
    for r in runs:
        buf: list[str] = []

        def flush() -> None:
            piece = re.sub(r"\s*\n\s*", " ", "".join(buf)).replace(_DOLLAR, "$")
            if piece:
                out.append(Run(piece, r.italic, r.bold))
            buf.clear()

        for c in r.text:
            if _PUA_FIRST <= ord(c) <= _PUA_LAST and ord(c) - _PUA_FIRST < len(nodes):
                flush()
                out.append(nodes[ord(c) - _PUA_FIRST])
            else:
                buf.append(c)
        flush()
    return tuple(out)


def _node(kind: str, raw: str, payload, ctx: _Ctx):
    if kind == "math":
        display = raw.startswith("$$")
        inner = raw[2:-2] if display else raw[1:-1]
        if not tex_is_safe(inner):
            ctx.note("math-unsafe", "math with a file, macro or category-code command was left out")
            return "[math left out]"
        tex = _tex_clean(inner, single_line=not display)
        return Math(tex, display) if tex else None
    if kind == "cite":
        for ref in payload.refs:
            ctx.cite(ref.key)
        return Citation(tuple(payload.refs), payload.kind)
    if kind == "note":
        inner = parse_research_inline(raw[2:-1], ctx)
        return Footnote(inner) if inner else None
    return None


# -- blocks ---------------------------------------------------------------------------------------------


def _text_blocks(segment: str, ctx: _Ctx) -> list:
    """Paragraphs and headings of a run of prose (no placement lines in it)."""
    segment = _COMMENT_RE.sub("", segment)
    math = _math_spans(segment)
    blocks: list = []
    lines: list[str] = []

    def end() -> None:
        if not lines:
            return
        text = "\n".join(lines).strip()
        lines.clear()
        inline = parse_research_inline(text, ctx)
        if "".join(getattr(r, "text", "") for r in inline).strip() or any(
                isinstance(r, (Math, Citation, Footnote)) for r in inline):
            blocks.append(Paragraph(inline))

    pos = 0
    for raw in segment.split("\n"):
        start, pos = pos, pos + len(raw) + 1
        line = raw.rstrip()
        if any(a < start < b for a, b in math):
            lines.append(line)              # a line inside a multi-line $$ block
            continue
        if not line.strip():
            end()
        elif _BREAK_RE.match(line):
            end()                           # scene breaks mean nothing in a paper
        else:
            h = _HEADING_RE.match(line)
            if h:
                end()
                inline = parse_research_inline(h.group(2), ctx)
                if inline:
                    blocks.append(Heading(len(h.group(1)), inline))
                continue
            lines.append(re.sub(r"^\s*>\s?", "", line).strip())
    end()
    return blocks


def _frontmatter_body(path: Path) -> tuple[dict, str]:
    return objects._split(path.read_text(encoding="utf-8"))


def _figure_block(ctx: _Ctx, label: str):
    obj = ctx.objects.get(f"fig:{label}")
    if obj is None:
        ctx.note("ref-missing", f"![[fig:{label}]] places a figure that does not exist")
        return Paragraph((Run(f"[figure {label} is missing]"),))
    try:
        path = objects._figure_file(ctx.project, label).resolve().as_posix()
    except (OSError, ValueError):
        ctx.note("figure-missing", f"the image of figure {label} is missing")
        return Paragraph((Run(f"[the image of figure {label} is missing]"),))
    return Figure(label, ctx.number("fig", label), parse_research_inline(obj.caption, ctx), path,
                  obj.width, obj.alt)


def _table_block(ctx: _Ctx, label: str):
    from ..tables import parse_pipe
    obj = ctx.objects.get(f"tbl:{label}")
    if obj is None:
        ctx.note("ref-missing", f"![[tbl:{label}]] places a table that does not exist")
        return Paragraph((Run(f"[table {label} is missing]"),))
    try:
        _meta, body = _frontmatter_body(ctx.project.root / obj.path)
        table = parse_pipe(body)
    except (OSError, ValueError, UnicodeDecodeError):
        ctx.note("ref-missing", f"table {label} has no pipe table in its note")
        return Paragraph((Run(f"[table {label} has no data]"),))
    cells = tuple(tuple(parse_research_inline(c, ctx) for c in row) for row in table.cells)
    return Table(label, ctx.number("tbl", label), parse_research_inline(obj.caption, ctx), cells,
                 tuple(table.align))


def _equation_block(ctx: _Ctx, label: str):
    obj = ctx.objects.get(f"eq:{label}")
    if obj is None:
        ctx.note("ref-missing", f"![[eq:{label}]] places an equation that does not exist")
        return Paragraph((Run(f"[equation {label} is missing]"),))
    try:
        _meta, body = _frontmatter_body(ctx.project.root / obj.path)
    except (OSError, UnicodeDecodeError):
        ctx.note("ref-missing", f"equation {label} could not be read")
        return Paragraph((Run(f"[equation {label} is missing]"),))
    tex = body.strip()
    if tex.startswith("$$") and tex.endswith("$$") and len(tex) >= 4:
        tex = tex[2:-2]
    tex = _tex_clean(tex, single_line=False)
    if not tex:
        ctx.note("ref-missing", f"equation {label} is empty")
        return Paragraph((Run(f"[equation {label} is empty]"),))
    if not tex_is_safe(tex):
        ctx.note("math-unsafe", f"equation {label} has a file, macro or category-code command and was left out")
        return Paragraph((Run(f"[equation {label} left out]"),))
    return Equation(label, ctx.number("eq", label), tex, parse_research_inline(obj.caption, ctx))


def parse_research_blocks(body: str, ctx: _Ctx) -> list:
    """Scene text -> blocks. Placement lines (``![[fig:x]]`` alone on a line) become Figure / Table / Equation;
    placements are found on the math-blanked text, as ``objects.numbering`` does, so both agree."""
    blocks: list = []
    pos = 0
    for p in objects.find_placements(objects.strip_math(body, mode="research")):
        blocks += _text_blocks(body[pos:p.start], ctx)
        if p.kind == "fig":
            blocks.append(_figure_block(ctx, p.label))
        elif p.kind == "tbl":
            blocks.append(_table_block(ctx, p.label))
        else:
            blocks.append(_equation_block(ctx, p.label))
        pos = p.end
    blocks += _text_blocks(body[pos:], ctx)
    return blocks


def _count_words(blocks: list) -> int:
    return sum(len(b.text.split()) for b in blocks if isinstance(b, Paragraph))


# -- assembling --------------------------------------------------------------------------------------------


def assemble_research(project, options: ExportOptions | None = None) -> Book:
    """The research manuscript as a Book. Read-only; ValueError for a story project."""
    if project.mode != "research":
        raise ValueError("research export needs a research project")
    opts = options or ExportOptions(format="docx")
    info = project.author_info()
    author = info["pen_name"] or info["author"]
    book = Book(title=project.title, author=author, options=opts, subtitle=info["subtitle"],
                copyright=opts.copyright.strip() or info["copyright"], contact=info["contact"],
                language=info["language"], unit=project.unit)
    ctx = _Ctx(project, book)

    groups: list[tuple[Part, list[Path]]] = []
    top = project.part_scenes(None)
    if top:
        groups.append((Part(title=None), top))
    for folder in project.list_parts():
        front = project.part_is_front_matter(folder)
        if front and not opts.include_front_matter:
            continue
        scenes = project.part_scenes(folder)
        if scenes:
            groups.append((Part(title=project.part_title(folder), front=front), scenes))

    number = 0
    for part, scenes in groups:
        for path in scenes:
            rel = path.relative_to(project.root).as_posix()
            ctx.scene = rel
            title, body = _scene_text(project, path, opts, book, rel, research=True)
            blocks = parse_research_blocks(body, ctx)
            if not blocks:
                book.warnings.append(Notice("empty", rel, f"{rel}: the {project.unit} has no text"))
            ch = Chapter(title=title, blocks=blocks, scene=rel)
            if not part.front:
                number += 1
                ch.number = number
            part.chapters.append(ch)
            book.scenes += 1
            book.words += _count_words(blocks)
        book.parts.append(part)

    entries, unresolved = csljson.build(project.load_entities(), ctx.cited)
    book.cited, book.bibliography, book.unresolved = list(ctx.cited), entries, unresolved
    for key in unresolved:
        scene = ctx.first_scene.get(key, "")
        book.warnings.append(Notice("citation-unresolved", scene,
                                    f"{scene}: no source note has the key @{key}" if scene
                                    else f"no source note has the key @{key}"))
    return book


# -- Book -> pandoc Markdown ---------------------------------------------------------------------------------

_SPECIAL = "\\*_[]<>`#$~^|{}@"


def _esc(text: str) -> str:
    """Strict escaping of author text (the fiction path's set, plus the backslash itself)."""
    return "".join("\\" + c if c in _SPECIAL else c for c in text)


def _guard(para: str) -> str:
    """A paragraph must not start like a list item, a definition or a table caption."""
    para = re.sub(r"^(\d+)([.)])(?=\s)", r"\1\\\2", re.sub(r"^([-+])(?=\s)", r"\\\1", para))
    return re.sub(r"^(Table)?:", lambda m: (m.group(1) or "") + "\\:", para)


def _cite_ref(ref: CiteRef, known: set[str]) -> str:
    out = ""
    if ref.prefix:
        out += _esc(ref.prefix) + " "
    out += ("-" if ref.suppress_author else "") + "@" + ref.key
    tail = [_esc(x) for x in (ref.locator, ref.suffix) if x]
    return out + (", " + ", ".join(tail) if tail else "")


def _citation(node: Citation, known: set[str]) -> str:
    """A pandoc citation for the keys that resolve; keys with no source stay as literal text (only reached
    when the author overrode the unresolved-citation block)."""
    good = [r for r in node.refs if r.key in known]
    lost = [r for r in node.refs if r.key not in known]
    parts = []
    if good:
        if node.kind == "narrative":
            names = [(_esc(r.prefix) + " " if r.prefix else "") + "@" + r.key +
                     (f" [{', '.join(_esc(x) for x in (r.locator, r.suffix) if x)}]"
                      if (r.locator or r.suffix) else "") for r in good]
            parts.append(names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
        else:
            parts.append("[" + "; ".join(_cite_ref(r, known) for r in good) + "]")
    for r in lost:
        parts.append(_esc(f"[@{r.key}]"))
    return " ".join(parts)


def _inline(nodes: tuple, known: set[str], cell: bool = False) -> str:
    """Markdown of inline nodes. In a pipe-table *cell* a pipe is spelled as a character reference (pandoc
    versions differ on an escaped pipe) and a pipe inside math as ``\\vert``."""
    out = []
    for r in nodes:
        if isinstance(r, Run):
            text = _esc(r.text)
            if cell:
                text = text.replace("\\|", "&#124;")
            if not text.strip():
                out.append(text)
                continue
            lead = text[:len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            mark = "***" if r.bold and r.italic else "**" if r.bold else "*" if r.italic else ""
            out.append(f"{lead}{mark}{text.strip()}{mark}{trail}")
        elif isinstance(r, Math):
            tex = r.tex.replace("|", "\\vert{}") if cell else r.tex
            out.append(f"$${tex}$$" if r.display else f"${tex}$")
        elif isinstance(r, Citation):
            out.append(_citation(r, known))
        elif isinstance(r, Footnote):
            out.append("^[" + _inline(r.runs, known, cell) + "]")
    return "".join(out)


def _caption(word: str, number: str, nodes: tuple, known: set[str]) -> str:
    body = _inline(nodes, known).strip()
    head = f"{word} {number}." if number else ""
    return f"{head} {body}".strip()


def _table_md(t: Table, known: set[str]) -> list[str]:
    n = len(t.align) or (len(t.cells[0]) if t.cells else 0)
    rows = [[_inline(c, known, True).replace("\n", " ").strip() for c in (list(r) + [()] * n)[:n]]
            for r in t.cells]
    widths = [max([3] + [len(r[c]) for r in rows]) for c in range(n)]
    delim = []
    for c in range(n):
        a = t.align[c] if c < len(t.align) else "default"
        delim.append((":" if a in ("left", "center") else "") + "-" * widths[c] + (":" if a in ("right", "center") else ""))
    out = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(delim) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    cap = _caption("Table", t.number, t.caption, known)
    return out + ([""] + [f"Table: {cap}"] if cap else [])


_MULTILINE_ENV = re.compile(r"\\begin\{(?:align|alignat|gather|multline|flalign|eqnarray)\*?\}")


def _equation_md(e: Equation, fmt: str) -> list[str]:
    num = re.sub(r"[^A-Za-z0-9.\-]", "", e.number)
    if fmt == "docx":
        eq = f"$${_tex_clean(e.tex, single_line=True)}$$"
        right = f"({num})" if num else ""
        w1, w2 = len(eq) + 4, max(len(right) + 2, 8)
        return ["-" * w1 + "  " + "-" * w2,
                eq.ljust(w1) + "  " + right.rjust(w2),
                "-" * w1 + "  " + "-" * w2]
    if _MULTILINE_ENV.search(e.tex):
        body = e.tex
    else:
        tag = f"\\tag{{{num}}}" if num else ""
        env = "equation" if num else "equation*"
        body = f"\\begin{{{env}}}{tag}\\label{{eq:{e.label}}}\n{e.tex}\n\\end{{{env}}}"
    return ["```{=latex}", body, "```"]


def research_markdown(book: Book, fmt: str) -> str:
    """The pandoc Markdown for *book* (``fmt``: docx | tex | pdf; only equations differ)."""
    known = {entry["id"] for entry in book.bibliography}
    lines = ["---"]

    def meta(key: str, value: str) -> None:
        if value:
            lines.append(f"{key}: {json.dumps(_esc(value), ensure_ascii=False)}")

    meta("title", book.title)
    meta("subtitle", book.subtitle)
    meta("author", book.author)
    meta("lang", _lang_tag(book.language))
    if book.bibliography:
        lines.append('reference-section-title: "References"')
        lines.append("link-citations: true")
    lines += ["---", ""]
    if book.copyright:
        lines += [_esc(book.copyright), ""]
    deep = book.real_parts > 0
    for part in book.parts:
        if part.title is not None and not part.front:
            lines += [f"# {_esc(part.title)}", ""]
        base = 2 if deep and not part.front and part.title is not None else 1
        for ch in part.chapters:
            if ch.title:
                lines += [f"{'#' * base} {_esc(ch.title)}{' {-}' if part.front else ''}", ""]
            for block in ch.blocks:
                if isinstance(block, Paragraph):
                    text = _guard(_inline(block.runs, known)).strip()
                    if text:
                        lines += [text, ""]
                elif isinstance(block, Heading):
                    lines += [f"{'#' * min(6, base + block.level - 1)} {_inline(block.runs, known).strip()}", ""]
                elif isinstance(block, Figure):
                    cap = _caption("Figure", block.number, block.caption, known)
                    attrs = f"#fig:{block.label}" + (f" width={block.width:g}in" if block.width else "")
                    lines += [f"![{cap}](<{block.path}>){{{attrs}}}", ""]
                elif isinstance(block, Table):
                    lines += _table_md(block, known) + [""]
                elif isinstance(block, Equation):
                    lines += _equation_md(block, fmt) + [""]
    return "\n".join(lines).rstrip() + "\n"


# -- converting ---------------------------------------------------------------------------------------------


def convert_research(book: Book, fmt: str, out: Path, *, csl: Path | None, reference_doc: Path | None,
                     resource_path: Path, allow_unresolved: bool = False, allow_tex_install: bool = False):
    """Write *book* to *out* (docx | tex | pdf) and return an ``ExportResult``. Unresolved citations and
    references block the export (RuntimeError listing them) unless *allow_unresolved*, when they stay in the
    text as literal ``[@key]`` / ``Figure ??``. Needs pandoc (and a TeX engine for pdf). MiKTeX may not
    install missing packages by itself unless *allow_tex_install* (it can open a dialog or use the network)."""
    from . import ExportResult
    if fmt not in FORMATS:
        raise ValueError(f"research export does not write {fmt}")
    blocking = [w for w in book.warnings if w.blocking]
    if blocking and not allow_unresolved:
        raise RuntimeError("The export is blocked: " + "; ".join(w.message for w in blocking[:6]) +
                           (f"; and {len(blocking) - 6} more" if len(blocking) > 6 else "") +
                           ". Fix them, or export anyway.")
    if csl is not None:
        check_csl(csl)
    if reference_doc is not None and not Path(reference_doc).is_file():
        raise ValueError("the Word template was not found")
    md = research_markdown(book, fmt)
    out = Path(out)
    with tempfile.TemporaryDirectory(prefix="chisel-bib-") as tmp:
        bib = None
        if book.bibliography:
            bib = Path(tmp) / "references.json"
            bib.write_text(csljson.dumps(book.bibliography), encoding="utf-8", newline="\n")
        pandoc.run_research(md, fmt, out, bibliography=bib, csl=csl, reference_doc=reference_doc,
                            resource_path=resource_path, toc=book.options.toc,
                            number_sections=book.options.numbering != "titles-only",
                            allow_tex_install=allow_tex_install)
    try:
        rel = out.relative_to(Path(resource_path)).as_posix()
    except ValueError:
        rel = out.name
    return ExportResult(path=out, rel=rel, format=fmt, pages=None, words=book.words, scenes=book.scenes,
                        warnings=book.messages())


def run_research_export(project, options: ExportOptions, *, csl: Path | None = None,
                        reference_doc: Path | None = None, allow_unresolved: bool = False,
                        allow_tex_install: bool = False, now: datetime | None = None):
    """Assemble and convert into ``exports/`` under a name that never overwrites an earlier export."""
    from . import _unique_path, exports_dir
    if options.format not in FORMATS:
        raise ValueError(f"research export does not write {options.format}")
    book = assemble_research(project, options)
    if book.scenes == 0:
        raise ValueError("There is nothing to export yet: the paper has no sections.")
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    folder = exports_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    path = _unique_path(folder, f"{ent.slugify(project.title) or 'paper'}-{options.format}-{stamp}", options.format)
    tmp = folder / f".{path.name}.part"
    try:
        result = convert_research(book, options.format, tmp, csl=csl or bundled_csl(),
                                  reference_doc=reference_doc, resource_path=project.root,
                                  allow_unresolved=allow_unresolved, allow_tex_install=allow_tex_install)
        fsutil.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    result.path = path
    result.rel = path.relative_to(project.root).as_posix()
    return result


# -- Word templates ------------------------------------------------------------------------------------------

REQUIRED_STYLES = ("Normal", "Body Text", "First Paragraph", "Compact", "Title", "Author", "Heading 1",
                   "Heading 2", "Heading 3", "Image Caption", "Table Caption", "Table", "Bibliography",
                   "Footnote Text", "Hyperlink")


def missing_styles(reference_doc: Path) -> list[str]:
    """The style names pandoc maps onto that *reference_doc* lacks (the "Check template" step; a funder's
    own .docx rarely has them all). Empty list = usable as is."""
    try:
        with zipfile.ZipFile(reference_doc) as z:
            xml = z.read("word/styles.xml").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        raise ValueError("this is not a Word document or template") from None
    have = {m.casefold() for m in re.findall(r'<w:name\s+w:val="([^"]+)"', xml)}
    return [s for s in REQUIRED_STYLES if s.casefold() not in have]


def starter_reference_doc(dest: Path) -> Path:
    """Write pandoc's own default reference.docx to *dest* (a starting point for a funder template)."""
    import subprocess
    from ..desktop import NO_CONSOLE
    exe = pandoc.find()
    if exe is None:
        raise RuntimeError("pandoc is not installed; install it to make a Word template")
    done = subprocess.run([exe, "--print-default-data-file", "reference.docx"], capture_output=True,
                          timeout=pandoc.RESEARCH_TIMEOUT, **NO_CONSOLE)
    if done.returncode != 0 or not done.stdout:
        raise RuntimeError("pandoc could not write its default Word template")
    Path(dest).write_bytes(done.stdout)
    return Path(dest)
