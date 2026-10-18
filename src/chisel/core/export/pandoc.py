"""DOCX, EPUB and LaTeX through pandoc (a subprocess with a timeout). The input
is the Markdown from ``markdown.to_markdown``, which escapes every character
that could mean markup and is read with raw HTML/TeX, links' attributes and
includes switched off, so pandoc has nothing to fetch (no network). pandoc's
own ``--sandbox`` is not used: it stops this pandoc from finding its DOCX and
EPUB templates."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..desktop import NO_CONSOLE
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
                              capture_output=True, timeout=TIMEOUT, cwd=out.parent, **NO_CONSOLE)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pandoc took longer than {TIMEOUT} seconds and was stopped") from None
    if done.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("pandoc failed: " + (detail[-1] if detail else f"exit {done.returncode}"))


# -- research branch (core/export/research.py; the fiction path above is not touched) ------------------
# Same safety stance as the fiction reader: raw HTML and raw TeX stay off, so author text can never smuggle
# markup. What research needs is switched on because ``research.py`` generates it and escapes every
# character of author text that could form it: ``$`` math, ``@`` citations, pipe/simple tables, image and
# footnote syntax, header attributes ({-} for unnumbered front matter) and the ``{=latex}`` raw block used
# for numbered LaTeX equations (an author's backtick is escaped, so no fenced block can come from prose).
_RESEARCH_READER = ("markdown+smart-raw_html-raw_tex+tex_math_dollars-tex_math_single_backslash"
                    "+citations+raw_attribute+pipe_tables+simple_tables+implicit_figures+link_attributes"
                    "+header_attributes+inline_notes+footnotes"
                    "-fenced_divs-bracketed_spans-fancy_lists-example_lists-startnum-multiline_tables"
                    "-grid_tables-definition_lists-auto_identifiers-latex_macros"
                    "-pandoc_title_block-mmd_title_block")
RESEARCH_TIMEOUT = 120
PDF_TIMEOUT = 600          # a TeX engine can be slow on the first run (fonts, format files)
TEX_ENGINES = ("xelatex", "lualatex", "pdflatex")
# what the default template and our output use; shown when the engine reports a missing file
TEX_PACKAGES = ("amsmath", "unicode-math", "fontspec", "graphicx", "hyperref", "booktabs", "longtable",
                "xcolor", "geometry", "microtype")
_MISSING_STY = re.compile(r"File [`']([^'`\s]+\.(?:sty|cls|def|fd|cfg))' not found")


def find_pdf_engine() -> str | None:
    """The first TeX engine on PATH (xelatex preferred), as a full path."""
    for name in TEX_ENGINES:
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def run_research(markdown: str, fmt: str, out: Path, *, bibliography: Path | None = None,
                 csl: Path | None = None, reference_doc: Path | None = None,
                 resource_path: Path | None = None, toc: bool = True,
                 number_sections: bool = True, allow_tex_install: bool = False) -> None:
    """Write generated research Markdown to *out* as docx | tex | pdf. Citeproc runs when *bibliography*
    is given. Runs from ``out.parent`` (the exports folder), so the Markdown must name images by absolute
    path; *resource_path* (the project root) is also passed. Raises RuntimeError with a plain message."""
    exe = find()
    if exe is None:
        raise RuntimeError("pandoc is not installed; install it to export DOCX, LaTeX or PDF")
    if fmt not in ("docx", "tex", "pdf"):
        raise ValueError(f"research export does not write {fmt}")
    cmd = [exe, "-f", _RESEARCH_READER, "-o", str(out)]
    timeout = RESEARCH_TIMEOUT
    if fmt == "docx":
        cmd += ["-t", "docx"]
        if reference_doc is not None:
            cmd.append(f"--reference-doc={reference_doc}")
    elif fmt == "tex":
        cmd += ["-t", "latex", "--standalone"]
    else:
        engine = find_pdf_engine()
        if engine is None:
            raise RuntimeError("PDF export needs a TeX engine (xelatex, lualatex or pdflatex); "
                               "install MiKTeX, TeX Live or Tectonic, or export LaTeX or Word instead")
        cmd += ["-t", "pdf", f"--pdf-engine={engine}"]
        if "miktex" in engine.lower() and not allow_tex_install:
            # never open the installer dialog or fetch a package (network is explicit): a missing one
            # fails with a message; the author may opt in with allow_tex_install
            cmd.append("--pdf-engine-opt=--disable-installer")
        timeout = PDF_TIMEOUT
    if toc:
        cmd.append("--toc")
    if number_sections:
        cmd.append("--number-sections")
    if bibliography is not None:
        cmd += ["--citeproc", f"--bibliography={bibliography}"]
        if csl is not None:
            cmd.append(f"--csl={csl}")
    if resource_path is not None:
        cmd.append(f"--resource-path={os.pathsep.join(['.', str(resource_path)])}")
    try:
        done = subprocess.run(cmd, input=markdown.encode("utf-8"), capture_output=True,
                              timeout=timeout, cwd=out.parent, **NO_CONSOLE)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"pandoc took longer than {timeout} seconds and was stopped") from None
    err = done.stderr.decode("utf-8", "replace")
    if done.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        missing = _MISSING_STY.search(err)
        if missing:
            raise RuntimeError(f"the TeX engine needs {missing.group(1)}; install that package with your "
                               "TeX distribution and export again (Chisel never lets it install by itself)")
        lines = [ln for ln in err.strip().splitlines() if ln.strip()]
        raise RuntimeError("pandoc failed: " + (lines[-1] if lines else f"exit {done.returncode}"))
