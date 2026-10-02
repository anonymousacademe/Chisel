"""A lorewrite project: a folder of plain Markdown files (SPEC §4)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import drafts
from . import entities as ent
from . import scenemeta, snapshots
from .structure import Structure
from . import fsutil

MANUSCRIPT_DIR = "manuscript"
ENTITIES_DIR = "entities"
CACHE_DIR = ".lorewrite"
PROJECT_FILE = "project.toml"

TYPE_SUBDIRS = {
    "character": "characters",
    "place": "places",
    "object": "objects",
    "faction": "factions",
}

PROJECT_TEMPLATE = """\
title = "{title}"
author = ""
"""

SAMPLE_SCENE = """\
# Opening

Welcome to lorewrite. Wrap a character or place in double brackets —
like [[New Character]] — and it lights up: cyan if it has a note,
orange if it doesn't. Put the cursor on a link and press ctrl+j to
open its note (creating it first if needed).

- ctrl+n   new scene
- ctrl+j   jump to the link under the cursor
- ctrl+p   command palette: open scenes, insert links, organize scenes
- alt+left / alt+right   previous / next scene
- f11      writer mode (hide everything but the editor)
- ctrl+s   save now (your work also autosaves)
- ctrl+b   hide/show the sidebar
- ?        all keybindings

Everything is plain Markdown on disk — your project folder *is* the novel.
"""


def write_atomic(path: Path, text: str) -> None:
    """Write *text* to *path* via a temp file + rename (never a torn file)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def default_project_path(title: str, parent: Path | None = None) -> Path | None:
    """Where a new project called *title* goes by default: ~/novels/<slug>
    (the TUI's launch screen suggests the same). None for a blank title."""
    if not title.strip():
        return None
    return (parent or Path.home() / "novels") / ent.slugify(title)


def retitle_text(text: str, new_title: str) -> str:
    """Replace the first '# ' heading with new_title (or prepend one, after
    any frontmatter block)."""
    head = scenemeta.body_offset(text)
    lines = text[head:].splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines[i] = f"# {new_title}"
            break
    else:
        lines[0:0] = [f"# {new_title}", ""]
    return text[:head] + "\n".join(lines) + "\n"


@dataclass
class Project(Structure):
    root: Path
    title: str = "Untitled"
    meta: dict = field(default_factory=dict)

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, root: Path, title: str) -> Project:
        root = root.expanduser().resolve()
        (root / MANUSCRIPT_DIR).mkdir(parents=True, exist_ok=True)
        for sub in TYPE_SUBDIRS.values():
            (root / ENTITIES_DIR / sub).mkdir(parents=True, exist_ok=True)
        (root / PROJECT_FILE).write_text(PROJECT_TEMPLATE.format(title=title),
                                         encoding="utf-8", newline="\n")
        sample = root / MANUSCRIPT_DIR / "01-opening.md"
        if not sample.exists():
            sample.write_text(SAMPLE_SCENE, encoding="utf-8", newline="\n")
        gitignore = root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(f"{CACHE_DIR}/\n", encoding="utf-8", newline="\n")
        return cls(root=root, title=title)

    @classmethod
    def open(cls, root: Path) -> Project:
        root = root.expanduser().resolve()
        if not (root / PROJECT_FILE).is_file():
            raise FileNotFoundError(f"no {PROJECT_FILE} in {root}")
        with (root / PROJECT_FILE).open("rb") as f:
            meta = tomllib.load(f)
        drafts.migrate_sidecars(root)  # pre-parts sidecars -> path-keyed names
        return cls(root=root, title=str(meta.get("title", "Untitled")), meta=meta)

    def editor_settings(self) -> dict:
        """Per-project editor preferences from project.toml [editor].

        editor.padding: side padding in characters (0-8, default 0)
        editor.line_numbers: show line numbers (default true)
        """
        raw = self.meta.get("editor") or {}
        padding = raw.get("padding", 0)
        try:
            padding = max(0, min(8, int(padding)))
        except (TypeError, ValueError):
            padding = 0
        return {
            "padding": padding,
            "line_numbers": bool(raw.get("line_numbers", True)),
        }

    def update_editor_settings(
        self, padding: int | None = None, line_numbers: bool | None = None
    ) -> None:
        """Write [editor] prefs into project.toml, preserving everything else.

        Textual section replacement (tomllib is read-only); safe for the
        simple project.toml files lorewrite writes.
        """
        current = self.editor_settings()
        new_padding = current["padding"] if padding is None else max(0, min(8, int(padding)))
        new_ln = current["line_numbers"] if line_numbers is None else bool(line_numbers)
        self._write_section("editor", (
            f"padding = {new_padding}\n"
            f"line_numbers = {'true' if new_ln else 'false'}\n"
        ))

    @property
    def draft(self) -> int:
        """Which draft of the book this is (project.toml [manuscript] draft,
        default 1)."""
        try:
            return max(1, int((self.meta.get("manuscript") or {}).get("draft", 1)))
        except (TypeError, ValueError):
            return 1

    def start_new_draft(self) -> int:
        """Snapshot every scene as ``end-of-draft-N``, then count up. Returns
        the new draft number. Nothing is counted if a snapshot fails."""
        n = self.draft
        snapshots.snapshot_all(self, f"end-of-draft-{n}")
        self.update_manuscript_settings(draft=n + 1)
        return n + 1

    def update_manuscript_settings(self, unit: str | None = None,
                                   draft: int | None = None) -> None:
        """Write [manuscript] prefs (unit = "scene" | "chapter", draft = N)
        into project.toml."""
        if unit is not None and unit not in ("scene", "chapter"):
            raise ValueError("unit must be 'scene' or 'chapter'")
        raw = dict(self.meta.get("manuscript") or {})
        raw["unit"] = unit or self.unit
        if draft is not None:
            raw["draft"] = max(1, int(draft))
        body = "".join(
            f'{k} = "{v}"\n' if isinstance(v, str) else f"{k} = {v}\n"
            for k, v in raw.items() if isinstance(v, (str, int)) and not isinstance(v, bool))
        self._write_section("manuscript", body)

    def _write_section(self, name: str, body: str) -> None:
        """Replace (or append) the [name] table of project.toml, preserving
        everything else, atomically; refresh the in-memory meta."""
        section = f"[{name}]\n{body}"
        path = self.root / PROJECT_FILE
        text = path.read_text(encoding="utf-8")
        if re.search(rf"(?m)^\[{name}\]\s*$", text):
            text = re.sub(rf"(?ms)^\[{name}\]\s*\n.*?(?=^\[|\Z)", lambda _: section + "\n", text)
        else:
            text = text.rstrip("\n") + "\n\n" + section
        write_atomic(path, text)
        with path.open("rb") as f:
            self.meta = tomllib.load(f)

    @classmethod
    def is_project(cls, root: Path) -> bool:
        return (root.expanduser() / PROJECT_FILE).is_file()

    # -- paths -------------------------------------------------------------

    @property
    def manuscript_dir(self) -> Path:
        return self.root / MANUSCRIPT_DIR

    @property
    def entities_dir(self) -> Path:
        return self.root / ENTITIES_DIR

    @property
    def index_path(self) -> Path:
        return self.root / CACHE_DIR / "index.sqlite"

    def all_markdown_files(self) -> list[Path]:
        return self.all_scene_files() + self.list_entity_files()

    # -- scenes (listing, parts, trash: core/structure.py) -------------------

    def scene_title(self, path: Path) -> str:
        """First '# ' heading, else the filename stem."""
        try:
            text = path.read_text(encoding="utf-8")
            for line in text[scenemeta.body_offset(text):].splitlines():
                if line.startswith("# "):
                    return line[2:].strip()
        except OSError:
            pass
        return path.stem

    def rename_scene(self, path: Path, new_title: str) -> None:
        """Set a scene's title (its first '# ' heading), atomically."""
        write_atomic(path, retitle_text(path.read_text(encoding="utf-8"), new_title))

    # -- entities ------------------------------------------------------------

    def list_entity_files(self) -> list[Path]:
        return sorted(self.entities_dir.glob("*/*.md"))

    def load_entities(self) -> list[ent.Entity]:
        return [ent.load_entity(p) for p in self.list_entity_files()]

    def entity_path(self, entity: ent.Entity) -> Path:
        sub = TYPE_SUBDIRS.get(entity.type, "characters")
        return self.entities_dir / sub / f"{ent.slugify(entity.name)}.md"

    def create_entity(self, name: str, etype: str = "character") -> tuple[ent.Entity, Path]:
        """Create a new entity note from the template. Returns (entity, path)."""
        entity = ent.Entity(name=name, type=etype)
        path = self.entity_path(entity)
        if not path.exists():
            ent.save_entity(entity, path)
        return ent.load_entity(path), path
