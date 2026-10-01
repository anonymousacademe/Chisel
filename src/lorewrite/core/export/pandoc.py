"""DOCX, EPUB and LaTeX through pandoc (a subprocess with a timeout). The input
is the Markdown from ``markdown.to_markdown``, which escapes every character
that could mean markup and is read with raw HTML/TeX, links' attributes and
includes switched off, so pandoc has nothing to fetch (no network). pandoc's
own ``--sandbox`` is not used: it stops this pandoc from finding its DOCX and
EPUB templates."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .manuscript import Book
from .markdown import to_markdown

TIMEOUT = 120
_TARGETS = {"docx": "docx", "epub": "epub3", "tex": "latex"}
# the reader takes plain text plus emphasis and headings, nothing else
_READER = ("markdown+smart-raw_html-raw_tex-tex_math_dollars-tex_math_single_backslash"
           "-citations-fenced_divs-bracketed_spans-fancy_lists-example_lists-startnum"
           "-pipe_tables-simple_tables-multiline_tables-grid_tables-definition_lists"
           "-implicit_figures-inline_notes-footnotes-link_attributes-header_attributes"
           "-auto_identifiers")


def find() -> str | None:
    return shutil.which("pandoc")


def convert(book: Book, fmt: str, out: Path) -> None:
    """Write *book* to *out* as *fmt* ("docx" | "epub" | "tex"). Raises
    RuntimeError with pandoc's own message on failure."""
    exe = find()
    if exe is None:
        raise RuntimeError("pandoc is not installed; install it to export DOCX, EPUB or LaTeX")
    if fmt not in _TARGETS:
        raise ValueError(f"pandoc does not write {fmt}")
    cmd = [exe, "-f", _READER, "-t", _TARGETS[fmt], "-o", str(out)]
    if book.options.toc and fmt in ("docx", "tex", "epub"):
        cmd.append("--toc")
    if fmt == "epub":
        cmd.append(f"--split-level={2 if book.real_parts else 1}")
    if fmt == "tex":
        cmd.append("--standalone")
    try:
        done = subprocess.run(cmd, input=to_markdown(book, pandoc=True).encode("utf-8"),
                              capture_output=True, timeout=TIMEOUT, cwd=out.parent)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pandoc took longer than {TIMEOUT} seconds and was stopped") from None
    if done.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("pandoc failed: " + (detail[-1] if detail else f"exit {done.returncode}"))
