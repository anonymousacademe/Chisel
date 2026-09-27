"""A lorewrite project: a folder of plain Markdown files (SPEC §4)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import entities as ent

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


def retitle_text(text: str, new_title: str) -> str:
    """Replace the first '# ' heading with new_title (or prepend one)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines[i] = f"# {new_title}"
            break
    else:
        lines[0:0] = [f"# {new_title}", ""]
    return "\n".join(lines) + "\n"


@dataclass
class Project:
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
                                         encoding="utf-8")
        sample = root / MANUSCRIPT_DIR / "01-opening.md"
        if not sample.exists():
            sample.write_text(SAMPLE_SCENE, encoding="utf-8")
        gitignore = root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(f"{CACHE_DIR}/\n", encoding="utf-8")
        return cls(root=root, title=title)

    @classmethod
    def open(cls, root: Path) -> Project:
        root = root.expanduser().resolve()
        if not (root / PROJECT_FILE).is_file():
            raise FileNotFoundError(f"no {PROJECT_FILE} in {root}")
        with (root / PROJECT_FILE).open("rb") as f:
            meta = tomllib.load(f)
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
        return sorted(self.manuscript_dir.glob("*.md")) + self.list_entity_files()

    # -- scenes --------------------------------------------------------------

    def list_scenes(self) -> list[Path]:
        """Scene files in manuscript order (filename prefix)."""
        return sorted(self.manuscript_dir.glob("*.md"))

    def scene_title(self, path: Path) -> str:
        """First '# ' heading, else the filename stem."""
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    return line[2:].strip()
        except OSError:
            pass
        return path.stem

    def next_scene_path(self, title: str) -> Path:
        """Allocate a numbered filename for a new scene."""
        existing = self.list_scenes()
        highest = 0
        for p in existing:
            m = re.match(r"(\d+)-", p.name)
            if m:
                highest = max(highest, int(m.group(1)))
        return self.manuscript_dir / f"{highest + 1:02d}-{ent.slugify(title)}.md"

    def rename_scene(self, path: Path, new_title: str) -> None:
        """Set a scene's title (its first '# ' heading), atomically."""
        text = retitle_text(path.read_text(encoding="utf-8"), new_title)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def delete_scene(self, path: Path) -> None:
        path.unlink()

    def move_scene(self, path: Path, delta: int) -> Path | None:
        """Swap a scene's numeric prefix with a neighbor's (reorder).

        Returns the moved scene's new path, or None if it can't move
        (already at the edge, or a filename without a numeric prefix).
        """
        scenes = self.list_scenes()
        try:
            i = scenes.index(path)
        except ValueError:
            return None
        j = i + delta
        if not (0 <= j < len(scenes)):
            return None
        a, b = scenes[i], scenes[j]
        ma = re.match(r"(\d+)-(.+)", a.name)
        mb = re.match(r"(\d+)-(.+)", b.name)
        if not ma or not mb:
            return None
        na, sa = ma.groups()
        nb, sb = mb.groups()
        tmp = a.with_name(f".swap-{a.name}")
        a.rename(tmp)
        b.rename(b.with_name(f"{na}-{sb}"))
        new_path = tmp.with_name(f"{nb}-{sa}")
        tmp.rename(new_path)
        return new_path

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
