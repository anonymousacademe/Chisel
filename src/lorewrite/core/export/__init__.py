"""Export the manuscript (SPEC M7): assemble the book once (``manuscript``),
then write it as a PDF layout (ReportLab, ``layouts``), DOCX / EPUB / LaTeX
(pandoc) or one Markdown file.

Files go to ``<project>/exports/<slug>-<layout>-<YYYYMMDD-HHMM>.<ext>``, never
over an earlier export. The last options used are remembered per project in
``project.toml`` ``[export]``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import desktop
from .. import entities as ent
from . import layouts, markdown, pandoc
from .manuscript import Book, ExportOptions, assemble
from .. import fsutil

EXPORTS_DIR = "exports"
FORMATS = {  # key -> (label, extension)
    "pdf": ("PDF", "pdf"),
    "docx": ("Word (DOCX)", "docx"),
    "epub": ("EPUB", "epub"),
    "md": ("Markdown", "md"),
    "tex": ("LaTeX source", "tex"),
}
Progress = Callable[[str, float], None]


@dataclass
class ExportResult:
    path: Path
    rel: str                       # project-relative, "exports/..."
    format: str
    pages: int | None
    words: int
    scenes: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"rel": self.rel, "name": self.path.name, "format": self.format,
                "pages": self.pages, "words": self.words, "scenes": self.scenes,
                "warnings": self.warnings}


def exports_dir(project) -> Path:
    return project.root / EXPORTS_DIR


# -- remembered options ----------------------------------------------------------


def load_options(project) -> ExportOptions:
    """The options last used for this project (defaults when none, or when the
    stored values are not valid)."""
    try:
        return ExportOptions.from_dict(project.meta.get("export") or {})
    except ValueError:
        return ExportOptions()


def save_options(project, opts: ExportOptions) -> None:
    body = "".join(
        f"{k} = {'true' if v else 'false'}\n" if isinstance(v, bool) else f"{k} = {json.dumps(v)}\n"
        for k, v in opts.to_dict().items())
    project._write_section("export", body)


# -- what is available --------------------------------------------------------------


def describe(project) -> dict:
    """What the export dialog / form needs: formats and whether each can run,
    the layouts with the options each honours, and the remembered options."""
    has_pdf = layouts.reportlab_available()
    has_pandoc = pandoc.find() is not None
    formats = []
    for key, (label, ext) in FORMATS.items():
        reason = ""
        if key == "pdf" and not has_pdf:
            reason = "install ReportLab: pip install 'lorewrite[export]'"
        elif key in ("docx", "epub", "tex") and not has_pandoc:
            reason = "install pandoc"
        formats.append({"key": key, "label": label, "ext": ext, "available": not reason,
                        "reason": reason})
    return {"formats": formats,
            "layouts": [l.describe() for l in layouts.all_layouts()] if has_pdf else [],
            "options": load_options(project).to_dict()}


def summarize(project, opts: ExportOptions) -> dict:
    """The live summary line: scenes, words, parts, drafts, warnings."""
    book = assemble(project, opts)
    out = book.summary()
    out["messages"] = book.messages()
    return out


def summary_line(s: dict, unit: str = "scene") -> str:
    """"4 scenes, 1,502 words, 2 parts; 1 scene has unaccepted AI drafts" (the
    same sentence the desktop dialog shows) from ``summarize``."""
    def plural(n: int, word: str) -> str:
        return f"{n:,} {word}{'' if n == 1 else 's'}"
    bits = [plural(s["scenes"], unit), plural(s["words"], "word")]
    if s["parts"]:
        bits.append(plural(s["parts"], "part"))
    line = ", ".join(bits)
    if s["draft_scenes"]:
        n = s["draft_scenes"]
        line += f"; {plural(n, unit)} {'has' if n == 1 else 'have'} unaccepted AI drafts"
    return line


# -- running an export ------------------------------------------------------------------


def _unique_path(folder: Path, stem: str, ext: str) -> Path:
    path = folder / f"{stem}.{ext}"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}.{ext}"
        n += 1
    return path


def run_export(project, options: ExportOptions, progress: Progress | None = None,
               now: datetime | None = None) -> ExportResult:
    """Write the export and return where it went. Raises ValueError /
    RuntimeError with a message for the author (nothing to export, missing
    tool); a failed export leaves no partial file behind."""
    note = progress or (lambda stage, fraction: None)
    opts = options
    warnings: list[str] = []
    layout = None
    if opts.format == "pdf":
        if not layouts.reportlab_available():
            raise RuntimeError("PDF export needs ReportLab: pip install 'lorewrite[export]'")
        layout = layouts.get(opts.layout)
        opts = layout.resolve(opts)
        from . import pdfkit
        if opts.font not in pdfkit.fonts_present():
            key = pdfkit.fallback_font(opts.font, layout.fonts)
            if key is None:
                raise RuntimeError(f"{pdfkit.font_label(opts.font)} is not installed")
            warnings.append(f"{pdfkit.font_label(opts.font)} is not installed; "
                            f"used {pdfkit.font_label(key)}.")
            opts = ExportOptions.from_dict({**opts.to_dict(), "font": key})
    elif opts.format in ("docx", "epub", "tex") and pandoc.find() is None:
        raise RuntimeError("pandoc is not installed; install it to export DOCX, EPUB or LaTeX")

    note("Reading scenes", 0.1)
    book = assemble(project, opts)
    if book.scenes == 0:
        raise ValueError("There is nothing to export yet: the book has no scenes.")

    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    ext = FORMATS[opts.format][1]
    folder = exports_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    slug = ent.slugify(project.title) or "manuscript"
    path = _unique_path(folder, f"{slug}-{layout.name if layout else opts.format}-{stamp}", ext)
    tmp = folder / f".{path.name}.part"
    pages = None
    try:
        note("Typesetting" if layout else "Writing the file", 0.4)
        if layout:
            pages = layout.render(book, opts, tmp)
        elif opts.format == "md":
            tmp.write_text(markdown.to_markdown(book), encoding="utf-8", newline="\n")
        else:
            pandoc.convert(book, opts.format, tmp)
        fsutil.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

    note("Done", 1.0)
    try:
        save_options(project, options)
    except OSError:
        pass  # remembering the options is a convenience
    return ExportResult(path=path, rel=path.relative_to(project.root).as_posix(),
                        format=opts.format, pages=pages, words=book.words, scenes=book.scenes,
                        warnings=warnings + book.messages())


# -- opening results (only ever on a click) ------------------------------------------------


def resolve_export(project, name: str) -> Path:
    """An existing file or the folder itself ("" ) inside ``exports/``; the only
    way a path from the UI reaches the file system."""
    folder = exports_dir(project)
    if not name:
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("not an export file")
    path = folder / name
    if not path.is_file():
        raise FileNotFoundError(f"{name} is no longer in the exports folder")
    return path


def open_in_desktop(path: Path) -> None:
    """Hand *path* to the desktop's default application."""
    if not desktop.open_path(path):
        raise RuntimeError("the desktop could not open this file; open it from your file manager")
