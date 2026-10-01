"""Manuscript structure on disk: parts, unplaced scenes and the trash.

    manuscript/
      00-front-matter/        a part named front-matter: not counted as book
      01-the-recall/          a part is a folder; optional _part.md holds its
        _part.md              title (first "# heading") and the author's notes
        01-rain-on-the-spur.md
      02-ghost-frequency/
      _unplaced/              written, not in the book (not counted, not read
                              by continuity, still indexed for backlinks)
      05-loose-scene.md       scenes may still sit directly in manuscript/
    .trash/20261001-101500-manuscript__01-the-recall__01-a.md

Everything is plain files; ``Project`` mixes this class in. Scenes carry a
``.drafts`` sidecar (core.drafts) that always travels with them.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import drafts
from . import entities as ent

UNPLACED_DIR = "_unplaced"
PART_FILE = "_part.md"
TRASH_DIR = ".trash"
FRONT_SLUG = "front-matter"

_PREFIX_RE = re.compile(r"(\d+)-(.+)")
_TRASH_RE = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?-(manuscript__.+)$")


def _sort_key(name: str) -> tuple[int, int, str]:
    """Numeric filename prefix first (``2-`` before ``10-``), then the name."""
    m = re.match(r"(\d+)-", name)
    return (0, int(m.group(1)), name) if m else (1, 0, name)


def _prefix(name: str) -> int | None:
    m = re.match(r"(\d+)-", name)
    return int(m.group(1)) if m else None


def _slug_of(name: str) -> str:
    """A scene/part filename without its numeric prefix (and ``.md``)."""
    stem = name[:-3] if name.endswith(".md") else name
    m = _PREFIX_RE.fullmatch(stem)
    return m.group(2) if m else stem


def _num(n: int, width: int = 2) -> str:
    return f"{n:0{max(width, 2)}d}"


@dataclass(frozen=True)
class TrashItem:
    name: str            # file name inside .trash/ (the id)
    path: Path
    original: str        # project-relative path the scene had
    deleted: datetime
    title: str


class Structure:
    """Mixin for ``Project`` (uses ``self.root`` / ``self.manuscript_dir``)."""

    root: Path
    manuscript_dir: Path
    meta: dict
    #: {old path: new path} of everything the last renaming operation moved
    #: (scenes, and part folders for move_part); lets a UI follow open files.
    last_renames: dict[Path, Path] = {}

    # -- reading -----------------------------------------------------------

    @property
    def unplaced_dir(self) -> Path:
        return self.manuscript_dir / UNPLACED_DIR

    @property
    def trash_dir(self) -> Path:
        return self.root / TRASH_DIR

    @staticmethod
    def _scene_files(folder: Path) -> list[Path]:
        try:
            files = [p for p in folder.iterdir()
                     if p.is_file() and p.suffix == ".md" and not p.name.startswith(("_", "."))]
        except OSError:
            return []
        return sorted(files, key=lambda p: _sort_key(p.name))

    def list_parts(self) -> list[Path]:
        """Part folders in book order (numeric prefix)."""
        try:
            dirs = [p for p in self.manuscript_dir.iterdir()
                    if p.is_dir() and not p.name.startswith(("_", "."))]
        except OSError:
            return []
        return sorted(dirs, key=lambda p: _sort_key(p.name))

    def list_scenes(self) -> list[Path]:
        """Every scene of the book in reading order: scenes directly in
        ``manuscript/`` first, then each part's scenes. Unplaced scenes are
        not part of the book (see ``list_unplaced``)."""
        scenes = self._scene_files(self.manuscript_dir)
        for part in self.list_parts():
            scenes += self._scene_files(part)
        return scenes

    def list_unplaced(self) -> list[Path]:
        return self._scene_files(self.unplaced_dir)

    def all_scene_files(self) -> list[Path]:
        """Book scenes plus unplaced ones (what the index covers)."""
        return self.list_scenes() + self.list_unplaced()

    def part_scenes(self, part: Path | None) -> list[Path]:
        """Scenes of a part, or of the unparted top level when *part* is None."""
        return self._scene_files(part if part is not None else self.manuscript_dir)

    def has_parts(self) -> bool:
        return bool(self.list_parts())

    def part_of(self, path: Path) -> Path | None:
        """The part folder holding scene *path*; None for unparted scenes
        (and for unplaced ones)."""
        parent = path.parent
        if parent.parent == self.manuscript_dir and parent.name != UNPLACED_DIR \
                and not parent.name.startswith("."):
            return parent
        return None

    def is_unplaced(self, path: Path) -> bool:
        return path.parent == self.unplaced_dir

    def is_scene_path(self, path: Path | None) -> bool:
        """A manuscript scene file: directly in manuscript/, in a part, or
        in _unplaced (not _part.md, not an entity or other project file)."""
        if path is None or path.suffix != ".md" or path.name.startswith(("_", ".")):
            return False
        try:
            rel = path.relative_to(self.manuscript_dir)
        except ValueError:
            return False
        if len(rel.parts) == 1:
            return True
        return len(rel.parts) == 2 and not rel.parts[0].startswith(".")

    @staticmethod
    def part_is_front_matter(part: Path) -> bool:
        return _slug_of(part.name) == FRONT_SLUG

    def is_front_matter(self, path: Path) -> bool:
        part = self.part_of(path)
        return part is not None and self.part_is_front_matter(part)

    def counted_scenes(self) -> list[Path]:
        """Scenes that count toward manuscript words (book minus front matter)."""
        return [p for p in self.list_scenes() if not self.is_front_matter(p)]

    def part_title(self, part: Path) -> str:
        """First ``# heading`` of the part's ``_part.md``, else the folder name
        de-slugged (``02-ghost-frequency`` -> ``Ghost Frequency``)."""
        try:
            for line in (part / PART_FILE).read_text(encoding="utf-8").splitlines():
                if line.startswith("# ") and line[2:].strip():
                    return line[2:].strip()
        except OSError:
            pass
        words = re.split(r"[-_\s]+", _slug_of(part.name))
        return " ".join(w[:1].upper() + w[1:] for w in words if w) or part.name

    def part_notes(self, part: Path) -> str:
        """The author's notes in ``_part.md`` (everything but the heading)."""
        try:
            text = (part / PART_FILE).read_text(encoding="utf-8")
        except OSError:
            return ""
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                del lines[i]
                break
        return "\n".join(lines).strip()

    def scene_number(self, path: Path) -> str:
        """The number shown for a scene ("03"). Unparted projects keep the
        filename prefix as always; once there are parts, numbering is global
        across them (position in the book, front matter excluded). Front
        matter and unplaced scenes have no number."""
        if self.is_unplaced(path) or self.is_front_matter(path):
            return ""
        if not self.has_parts():
            m = re.match(r"(\d+)-", path.name)
            return m.group(1) if m else ""
        try:
            return _num(self.counted_scenes().index(path) + 1)
        except ValueError:
            return ""

    # -- display unit ---------------------------------------------------------

    @property
    def unit(self) -> str:
        """``"scene"`` (default) or ``"chapter"``: only a label."""
        raw = (self.meta.get("manuscript") or {}).get("unit")
        return raw if raw in ("scene", "chapter") else "scene"

    # -- scene filenames --------------------------------------------------------

    def next_scene_path(self, title: str, part: Path | None = None) -> Path:
        """Allocate a numbered filename for a new scene at the end of *part*
        (or of the unparted top level)."""
        folder = part if part is not None else self.manuscript_dir
        highest = max((_prefix(p.name) or 0 for p in self._scene_files(folder)),
                      default=0)
        return folder / f"{_num(highest + 1)}-{ent.slugify(title)}.md"

    def default_part_for_new(self, near: Path | None = None) -> Path | None:
        """Where a new scene goes: the part of the scene being worked on,
        else the last real part, else the top level."""
        if near is not None and self.is_scene_path(near) and not self.is_unplaced(near):
            return self.part_of(near)
        parts = [p for p in self.list_parts() if not self.part_is_front_matter(p)]
        return parts[-1] if parts else None

    # -- scene operations ---------------------------------------------------------

    def _apply_renames(self, pairs: list[tuple[Path, Path]]) -> None:
        """Rename files (and their draft sidecars) old->new in two phases, so
        swaps and cycles never collide. Creates destination folders."""
        pairs = [(a, b) for a, b in pairs if a != b]
        self.last_renames = dict(pairs)
        staged = []
        for k, (old, new) in enumerate(pairs):
            tmp = old.with_name(f".mv{k}-{old.name}")
            old.rename(tmp)
            side_old = drafts.sidecar_path(self.root, old)
            side_tmp = None
            if side_old.is_file():
                side_tmp = side_old.with_name(f".mv{k}-{side_old.name}")
                side_old.replace(side_tmp)
            staged.append((tmp, new, side_tmp))
        for tmp, new, side_tmp in staged:
            new.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(new)
            if side_tmp is not None:
                side_new = drafts.sidecar_path(self.root, new)
                side_new.parent.mkdir(parents=True, exist_ok=True)
                side_tmp.replace(side_new)

    def move_scene(self, path: Path, delta: int) -> Path | None:
        """Swap a scene's numeric prefix with a neighbor's within its part
        (or the unparted/unplaced group). Returns the new path, or None at the
        edge or for a filename without a numeric prefix."""
        group = self._scene_files(path.parent)
        try:
            i = group.index(path)
        except ValueError:
            return None
        j = i + delta
        if not (0 <= j < len(group)):
            return None
        a, b = group[i], group[j]
        ma = re.match(r"(\d+)-(.+)", a.name)
        mb = re.match(r"(\d+)-(.+)", b.name)
        if not ma or not mb:
            return None
        na, sa = ma.groups()
        nb, sb = mb.groups()
        new_a = a.with_name(f"{nb}-{sa}")
        self._apply_renames([(a, new_a), (b, b.with_name(f"{na}-{sb}"))])
        return new_a

    def place_scene(self, path: Path, part: Path | None = None,
                    index: int | None = None, *, unplaced: bool = False) -> Path:
        """Move a scene into *part* (None = unparted top level; *unplaced*
        = the Unplaced Scenes folder) at 0-based *index* (default: the end).
        The destination's scenes are renumbered contiguously so the order is
        exactly what was asked for; the folder it left keeps its numbers (a gap,
        as after a delete: only the destination is renumbered, to keep file
        churn down). ``last_renames`` lists every file that changed name.
        Returns the scene's new path."""
        if not self.is_scene_path(path):
            raise ValueError("not a manuscript scene")
        dest = self.unplaced_dir if unplaced else (
            part if part is not None else self.manuscript_dir)
        if not unplaced and part is not None and part.parent != self.manuscript_dir:
            raise ValueError("not a part of this manuscript")
        others = [p for p in self._scene_files(dest) if p != path]
        at = len(others) if index is None else max(0, min(int(index), len(others)))
        ordered = others[:at] + [path] + others[at:]
        width = len(str(len(ordered)))
        pairs = [(p, dest / f"{_num(n + 1, width)}-{_slug_of(p.name)}.md")
                 for n, p in enumerate(ordered)]
        self._apply_renames(pairs)
        return dict(pairs)[path]

    def move_scene_to_part(self, path: Path, part: Path | None) -> Path:
        """Move a scene to the end of *part* (None = unparted top level)."""
        return self.place_scene(path, part)

    def unplace_scene(self, path: Path) -> Path:
        return self.place_scene(path, unplaced=True)

    # -- parts -------------------------------------------------------------------

    def new_part(self, title: str) -> Path:
        title = " ".join(title.split())
        if not title:
            raise ValueError("a part needs a title")
        highest = max((_prefix(p.name) or 0 for p in self.list_parts()), default=0)
        part = self.manuscript_dir / f"{_num(highest + 1)}-{ent.slugify(title)}"
        if part.exists():
            raise ValueError(f"a part folder named {part.name} already exists")
        part.mkdir(parents=True)
        (part / PART_FILE).write_text(f"# {title}\n", encoding="utf-8")
        return part

    def rename_part(self, part: Path, title: str) -> None:
        """Set a part's title (the heading of its ``_part.md``; notes below it
        are kept). The folder keeps its name, so no scene path changes."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("a part needs a title")
        from .project import retitle_text, write_atomic
        note = part / PART_FILE
        old = note.read_text(encoding="utf-8") if note.is_file() else ""
        write_atomic(note, retitle_text(old, title) if old else f"# {title}\n")

    def move_part(self, part: Path, delta: int) -> Path | None:
        """Swap numeric prefixes with the neighboring part. Returns the part's
        new folder, or None at the edge / without numeric prefixes."""
        parts = self.list_parts()
        try:
            i = parts.index(part)
        except ValueError:
            return None
        j = i + delta
        if not (0 <= j < len(parts)):
            return None
        a, b = parts[i], parts[j]
        ma = re.match(r"(\d+)-(.+)", a.name)
        mb = re.match(r"(\d+)-(.+)", b.name)
        if not ma or not mb:
            return None
        (na, sa), (nb, sb) = ma.groups(), mb.groups()
        new_a, new_b = a.with_name(f"{nb}-{sa}"), b.with_name(f"{na}-{sb}")
        # every scene inside changes path: sidecars follow (via temp names)
        moves = [(p, new_a / p.name) for p in self._scene_files(a)]
        moves += [(p, new_b / p.name) for p in self._scene_files(b)]
        staged = []
        for k, (old, new) in enumerate(moves):
            side = drafts.sidecar_path(self.root, old)
            if side.is_file():
                tmp = side.with_name(f".mv{k}-{side.name}")
                side.replace(tmp)
                staged.append((tmp, drafts.sidecar_path(self.root, new)))
        self.last_renames = {**dict(moves), a: new_a, b: new_b}
        tmp_a = a.with_name(f".swap-{a.name}")
        a.rename(tmp_a)
        b.rename(new_b)
        tmp_a.rename(new_a)
        for tmp, dest in staged:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp.replace(dest)
        return new_a

    def delete_part(self, part: Path) -> None:
        """Delete an empty part (its ``_part.md`` goes with it)."""
        if part not in self.list_parts():
            raise ValueError("not a part of this manuscript")
        if self._scene_files(part):
            raise ValueError("the part still has scenes - move them out first")
        (part / PART_FILE).unlink(missing_ok=True)
        try:
            part.rmdir()
        except OSError as exc:
            raise ValueError("the part folder still holds other files") from exc

    # -- trash ---------------------------------------------------------------------

    def delete_scene(self, path: Path) -> Path:
        """Move a scene to the Trash (with its draft sidecar). Returns the
        file's new path inside ``.trash/``."""
        rel = path.relative_to(self.root).as_posix().replace("/", "__")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.trash_dir.mkdir(exist_ok=True)
        dest, n = self.trash_dir / f"{stamp}-{rel}", 1
        while dest.exists():
            n += 1
            dest = self.trash_dir / f"{stamp}-{n}-{rel}"
        side = drafts.sidecar_path(self.root, path)
        if side.is_file():
            side.replace(dest.with_name(dest.name + ".drafts.json"))
            try:
                side.parent.rmdir()
            except OSError:
                pass
        path.replace(dest)
        return dest

    def list_trash(self) -> list[TrashItem]:
        """Trashed scenes, newest first."""
        items = []
        try:
            files = list(self.trash_dir.glob("*.md"))
        except OSError:
            return []
        for p in files:
            m = _TRASH_RE.match(p.name)
            if not m:
                continue
            try:
                when = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
            except ValueError:
                continue
            original = m.group(3).replace("__", "/")
            items.append(TrashItem(p.name, p, original, when, self.scene_title(p)))
        return sorted(items, key=lambda i: (i.deleted, i.name), reverse=True)

    def _trash_item(self, name: str) -> TrashItem:
        for item in self.list_trash():
            if item.name == name:
                return item
        raise FileNotFoundError(f"not in the trash: {name}")

    def restore_scene(self, name: str) -> Path:
        """Put a trashed scene back at the end of its original part (or the
        top level / Unplaced it came from); if that part is gone, Unplaced."""
        item = self._trash_item(name)
        orig = self.root / item.original
        folder = orig.parent
        if folder == self.manuscript_dir or folder in self.list_parts():
            dest_dir = folder
        else:
            dest_dir = self.unplaced_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        final = self._next_in(dest_dir, _slug_of(orig.name))
        final.parent.mkdir(parents=True, exist_ok=True)
        item.path.replace(final)
        side = item.path.with_name(item.path.name + ".drafts.json")
        if side.is_file():
            target = drafts.sidecar_path(self.root, final)
            target.parent.mkdir(parents=True, exist_ok=True)
            side.replace(target)
        self._tidy_trash()
        return final

    def _next_in(self, folder: Path, slug: str) -> Path:
        highest = max((_prefix(p.name) or 0 for p in self._scene_files(folder)),
                      default=0)
        return folder / f"{_num(highest + 1)}-{slug}.md"

    def delete_forever(self, name: str) -> None:
        item = self._trash_item(name)
        item.path.unlink(missing_ok=True)
        item.path.with_name(item.path.name + ".drafts.json").unlink(missing_ok=True)
        self._tidy_trash()

    def empty_trash(self) -> int:
        n = len(self.list_trash())
        if self.trash_dir.is_dir():
            shutil.rmtree(self.trash_dir, ignore_errors=True)
        return n

    def _tidy_trash(self) -> None:
        try:
            self.trash_dir.rmdir()  # only when nothing is left
        except OSError:
            pass
