"""The book as Markdown: the single-file export, and the input for pandoc
(DOCX, EPUB, LaTeX). Paragraph text is re-escaped from the model, so nothing in
a scene can turn into markup by accident."""

from __future__ import annotations

import json
import re

from .manuscript import Book, Break, Paragraph, Run

_LIGHT = "\\*_[]<>`"
_STRICT = _LIGHT + "#$~^|{}@"


def _escape(text: str, strict: bool) -> str:
    chars = _STRICT if strict else _LIGHT
    text = "".join("\\" + c if c in chars else c for c in text)
    return text


def _runs(runs: tuple[Run, ...], strict: bool) -> str:
    out = []
    for r in runs:
        text = _escape(r.text, strict)
        if not text.strip():
            out.append(text)
            continue
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()
        mark = "***" if r.bold and r.italic else "**" if r.bold else "*" if r.italic else ""
        out.append(f"{lead}{mark}{core}{mark}{trail}")
    para = "".join(out)
    # a paragraph must not start like a list item
    return re.sub(r"^(\d+)([.)])(?=\s)", r"\1\\\2", re.sub(r"^([-+])(?=\s)", r"\\\1", para))


def _lang_tag(language: str) -> str:
    """A BCP 47-looking tag for pandoc's ``lang`` ("en_GB" -> "en-GB"); "en" if odd."""
    tag = language.strip().replace("_", "-")
    return tag if re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", tag) else "en"


def to_markdown(book: Book, *, pandoc: bool = False) -> str:
    """Markdown text for *book*. With ``pandoc`` the text carries a YAML
    metadata block (title, author) and is escaped for pandoc's reader; without
    it the file opens with a plain title block."""
    strict = pandoc
    lines: list[str] = []
    if pandoc:
        def meta(key: str, value: str) -> None:
            if value:
                lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        lines.append("---")
        meta("title", book.title)
        meta("subtitle", book.subtitle)
        meta("author", book.author)
        meta("subject", book.subtitle)      # DOCX document properties
        meta("rights", book.copyright)      # EPUB dc:rights
        meta("lang", _lang_tag(book.language))
        lines += ["---", ""]
    else:
        lines += [f"# {_escape(book.title, False)}", ""]
        if book.subtitle:
            lines += [f"## {_escape(book.subtitle, False)}", ""]
        if book.author:
            lines += [f"*{_escape(book.author, False)}*", ""]
    if book.copyright:
        lines += [_escape(book.copyright, strict), ""]
    deep = book.real_parts > 0
    for part in book.parts:
        if part.title is not None and not part.front:
            heading = f"{part.label}: {part.title}" if part.label else part.title
            lines += [f"# {_escape(heading, strict)}", ""]
        for ch in part.chapters:
            shown = f"{ch.label}: {ch.title}" if ch.label and ch.title else (ch.title or ch.label)
            if shown:
                level = "##" if deep and not part.front and part.title is not None else "#"
                lines += [f"{level} {_escape(shown, strict)}", ""]
            for block in ch.blocks:
                if isinstance(block, Break):
                    lines += ["* * *", ""]
                elif isinstance(block, Paragraph):
                    lines += [_runs(block.runs, strict), ""]
    return "\n".join(lines).rstrip() + "\n"
