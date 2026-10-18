"""Importing a Fountain file into a script project. ``core.fountain.import_text`` splits the text into parts and
scenes; this writes them as new scene files after what the project already has. Nothing existing is changed
or overwritten (the title page only fills project details that are still empty)."""

from __future__ import annotations

import re
from pathlib import Path

from . import entities as ent
from . import fountain
from .project import Project, write_atomic
from .structure import _num, _prefix

MAX_BYTES = 5_000_000


def read_file(path: Path) -> str:
    """The text of a Fountain file: UTF-8 (with or without a BOM), else Windows-1252 (older Final Draft and
    Highland exports). ``ValueError`` for a file that is too big to be a script."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"{path.name} was not found")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"{path.name} is larger than {MAX_BYTES // 1_000_000} MB: not a Fountain script")
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _file_title(title: str) -> str:
    """A scene title for the file name: "INT. A - DAY" becomes "INT. A DAY" (no run of hyphens in the name)."""
    return re.sub(r"\s+[-–—]+\s+", " ", title).strip() or title


def _allocate(project: Project, counters: dict, title: str, part: Path | None) -> Path:
    """The next numbered scene file in *part* (``Project.next_scene_path`` without rescanning the folder for
    every scene: a TV-length script has thousands, and the scan made the import quadratic)."""
    folder = part if part is not None else project.manuscript_dir
    if folder not in counters:
        counters[folder] = max((_prefix(p.name) or 0 for p in project._scene_files(folder)), default=0)
    counters[folder] += 1
    return folder / f"{_num(counters[folder])}-{ent.slugify(title)}.md"


def _fill_details(project: Project, page: dict[str, str]) -> list[str]:
    """Author, contact and copyright from the title page, only where the project has none yet."""
    info = project.author_info()
    wanted = {"author": page.get("author") or page.get("authors") or "",
              "contact": page.get("contact", ""), "copyright": page.get("copyright", "")}
    patch: dict[str, str] = {}
    for key, value in wanted.items():
        if value.strip() and not info[key]:
            patch["copyright_" if key == "copyright" else key] = value
    if patch:
        project.update_author_info(**patch)
    return [k.rstrip("_") for k in patch]


def import_into(project: Project, text: str, name: str = "the file") -> dict:
    """Add the script in *text* (Fountain) to *project*: a part per ``# Section`` and a scene per scene
    heading. Scenes before the first section go to the top level when the project has no parts and the file
    has none; otherwise they get a part of their own, so imported scenes never slide in above existing parts.
    Returns ``{"scenes", "parts", "first", "filled", "name"}`` (``first`` = id of the first new scene)."""
    if project.mode != "script":
        raise ValueError("Importing a Fountain file is for script projects: start a new project and choose Script.")
    imp = fountain.import_text(text)
    if imp.scenes == 0 and not any(p.title for p in imp.parts):
        raise ValueError(f"{name} has no scenes: Chisel looks for scene headings such as INT. KITCHEN - DAY.")
    has_sections = any(p.title for p in imp.parts)
    flat = not has_sections and not project.list_parts()
    counters: dict[Path, int] = {}
    made_parts = 0
    first = ""
    scenes = 0
    for part in imp.parts:
        if not part.scenes and not part.title:
            continue
        folder = None
        if part.title:
            folder = project.new_part(part.title)
            made_parts += 1
        elif not flat:
            folder = project.new_part(imp.title_page.get("title") or "Imported script")
            made_parts += 1
        for scene in part.scenes:
            path = _allocate(project, counters, _file_title(scene.title), folder)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(path, scene.text)
            scenes += 1
            if not first:
                first = path.relative_to(project.root).as_posix()
    return {"scenes": scenes, "parts": made_parts, "first": first,
            "filled": _fill_details(project, imp.title_page), "name": name}
