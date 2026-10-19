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
    .trash/20261001-102200-research__tides__almanac.md     (a research note, Wave 4.4)
    .trash/20261001-103000-inspiration__subway.md          (+ ...subway.md.jpg: an inspiration image)

Everything is plain files; ``Project`` mixes this class in. Scenes carry a
``.drafts`` sidecar (core.drafts) that always travels with them.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import applog, comments, drafts
from . import inspiration
from . import entities as ent
from . import research as research_notes
from . import snapshots
from . import fsutil

UNPLACED_DIR = "_unplaced"
PART_FILE = "_part.md"
TRASH_DIR = ".trash"
FRONT_SLUG = "front-matter"
OBJECT_DIRS = ("figures", "tables", "equations")   # research mode objects (core/objects.py)
OBJECT_COMPANIONS = ("png", "jpg", "csv")         # files that ride beside an object's .md in the Trash
MAX_TRASH_NAME = 120  # of the original path part of a .trash/ name

_PREFIX_RE = re.compile(r"(\d+)-(.+)")
_TRASH_RE = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?-((?:manuscript|notebook|research|inspiration|figures|tables|equations)__.+)$")


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


def _rollback(done: list[tuple[Path, Path]]) -> None:
    """Undo staged moves, newest first (best effort: a failed step is skipped
    so the rest still go back)."""
    for current, original in reversed(done):
        try:
            fsutil.replace(current, original)
        except OSError:
            pass


_STAGED_RE = re.compile(r"^\.mv\d+-(.+)$")


def recover_staged(root: Path) -> list[Path]:
    """Move ``.mv<k>-<name>`` leftovers of a rename that died midway back to
    ``<name>``, unless that name is taken (then they are left alone). Returns
    the restored paths."""
    restored: list[Path] = []
    for top in ("manuscript", ".drafts", ".comments", ".snapshots"):
        base = root / top
        if not base.is_dir():
            continue
        for folder, dirs, files in os.walk(base):
            for name in [*dirs, *files]:
                m = _STAGED_RE.match(name)
                if not m:
                    continue
                src, dst = Path(folder) / name, Path(folder) / m.group(1)
                if not dst.exists():
                    fsutil.rename(src, dst)
                    restored.append(dst)
            dirs[:] = [d for d in dirs if not _STAGED_RE.match(d)]
    return restored


@dataclass(frozen=True)
class TrashItem:
    name: str            # file name inside .trash/ (the id)
    path: Path
    original: str        # project-relative path the scene (or research note) had
    deleted: datetime
    title: str
    kind: str = "scene"  # "scene" | "research" | "inspiration" | "object" (figure, table, equation)


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
        done: list[tuple[Path, Path]] = []  # (where it is now, where it was)
        try:
            staged = []
            for k, (old, new) in enumerate(pairs):
                tmp = old.with_name(f".mv{k}-{old.name}")
                fsutil.rename(old, tmp)
                done.append((tmp, old))
                side_old = drafts.sidecar_path(self.root, old)
                side_tmp = None
                if side_old.is_file():
                    side_tmp = side_old.with_name(f".mv{k}-{side_old.name}")
                    fsutil.replace(side_old, side_tmp)
                    done.append((side_tmp, side_old))
                snap_tmp = snapshots.stage(self.root, old, str(k))
                if snap_tmp is not None:
                    done.append((snap_tmp, snapshots.scene_dir(self.root, old)))
                note_tmp = comments.stage(self.root, old, str(k))
                if note_tmp is not None:
                    done.append((note_tmp, comments.sidecar_path(self.root, old)))
                staged.append((tmp, new, side_tmp, snap_tmp, note_tmp))
            for tmp, new, side_tmp, snap_tmp, note_tmp in staged:
                new.parent.mkdir(parents=True, exist_ok=True)
                fsutil.rename(tmp, new)
                done.append((new, tmp))
                if side_tmp is not None:
                    side_new = drafts.sidecar_path(self.root, new)
                    side_new.parent.mkdir(parents=True, exist_ok=True)
                    fsutil.replace(side_tmp, side_new)
                    done.append((side_new, side_tmp))
                if snap_tmp is not None:
                    snapshots.unstage(self.root, snap_tmp, new)
                    done.append((snapshots.scene_dir(self.root, new), snap_tmp))
                if note_tmp is not None:
                    comments.unstage(self.root, note_tmp, new)
                    done.append((comments.sidecar_path(self.root, new), note_tmp))
        except BaseException:
            _rollback(done)  # never leave a scene hidden under a .mv name
            self.last_renames = {}
            raise
        inspiration.remap_paths(self, self.last_renames)

    # -- closing gaps (after a delete or a restore) -----------------------------

    def renumber_folder(self, folder: Path) -> dict[Path, Path]:
        """Renumber the numbered scenes of *folder* contiguously (01, 02, ...),
        keeping each slug and the order. Files without a numeric prefix, the
        Unplaced folder and a front-matter part are left alone, and a folder
        that is already contiguous renames nothing. Goes through
        ``_apply_renames`` (sidecars, comments and snapshots follow); sets
        ``last_renames`` and returns it."""
        if folder == self.unplaced_dir or (
                folder != self.manuscript_dir and self.part_is_front_matter(folder)):
            self.last_renames = {}
            return {}
        files = [p for p in self._scene_files(folder) if _prefix(p.name) is not None]
        width = max([2, len(str(len(files)))]
                    + [len(re.match(r"\d+", p.name).group()) for p in files])
        pairs = [(p, folder / f"{_num(n + 1, width)}-{_slug_of(p.name)}.md")
                 for n, p in enumerate(files)]
        self._apply_renames(pairs)
        return dict(self.last_renames)

    def renumber_parts(self) -> dict[Path, Path]:
        """Renumber the part folders (front matter excluded) 01, 02, ... in
        order. Every scene inside moves through ``_apply_renames`` first, then
        the folder's other files (``_part.md``) follow and the empty folder
        goes. A target that exists and is not empty is skipped, never
        overwritten. ``last_renames`` holds scenes and folders."""
        parts = [p for p in self.list_parts()
                 if not self.part_is_front_matter(p) and _prefix(p.name) is not None]
        width = max([2, len(str(len(parts)))]
                    + [len(re.match(r"\d+", p.name).group()) for p in parts])
        total: dict[Path, Path] = {}
        for n, old in enumerate(parts):
            new = old.with_name(f"{_num(n + 1, width)}-{_slug_of(old.name)}")
            if new == old:
                continue
            if new.exists() and (not new.is_dir() or any(new.iterdir())):
                continue
            self._apply_renames([(p, new / p.name) for p in self._scene_files(old)])
            total.update(self.last_renames)
            for rest in list(old.iterdir()):
                new.mkdir(parents=True, exist_ok=True)
                fsutil.rename(rest, new / rest.name)
            old.rmdir()
            total[old] = new
        self.last_renames = total
        return total

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
        exactly what was asked for; the folder it left keeps its numbers (a gap;
        only a delete or a restore closes gaps, see ``renumber_folder``).
        ``last_renames`` lists every file that changed name.
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
        (part / PART_FILE).write_text(f"# {title}\n", encoding="utf-8", newline="\n")
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
        snap_staged = []
        note_staged = []
        self.last_renames = {**dict(moves), a: new_a, b: new_b}
        done: list[tuple[Path, Path]] = []  # (where it is now, where it was)
        try:
            for k, (old, new) in enumerate(moves):
                side = drafts.sidecar_path(self.root, old)
                if side.is_file():
                    tmp = side.with_name(f".mv{k}-{side.name}")
                    fsutil.replace(side, tmp)
                    done.append((tmp, side))
                    staged.append((tmp, drafts.sidecar_path(self.root, new)))
                snap = snapshots.stage(self.root, old, str(k))
                if snap is not None:
                    done.append((snap, snapshots.scene_dir(self.root, old)))
                    snap_staged.append((snap, new))
                note = comments.stage(self.root, old, str(k))
                if note is not None:
                    done.append((note, comments.sidecar_path(self.root, old)))
                    note_staged.append((note, new))
            tmp_a = a.with_name(f".swap-{a.name}")
            fsutil.rename(a, tmp_a)
            done.append((tmp_a, a))
            fsutil.rename(b, new_b)
            done.append((new_b, b))
            fsutil.rename(tmp_a, new_a)
            done.append((new_a, tmp_a))
            for tmp, dest in staged:
                dest.parent.mkdir(parents=True, exist_ok=True)
                fsutil.replace(tmp, dest)
                done.append((dest, tmp))
            for snap, new in snap_staged:
                snapshots.unstage(self.root, snap, new)
                done.append((snapshots.scene_dir(self.root, new), snap))
            for note, new in note_staged:
                comments.unstage(self.root, note, new)
                done.append((comments.sidecar_path(self.root, new), note))
        except BaseException:
            _rollback(done)
            self.last_renames = {}
            raise
        inspiration.remap_paths(self, self.last_renames)
        return new_a

    def delete_part(self, part: Path) -> None:
        """Delete an empty part (its ``_part.md`` goes with it); the parts after
        it are renumbered (front matter stays)."""
        self.last_renames = {}
        if part not in self.list_parts():
            raise ValueError("not a part of this manuscript")
        if self._scene_files(part):
            raise ValueError("the part still has scenes - move them out first")
        (part / PART_FILE).unlink(missing_ok=True)
        try:
            part.rmdir()
        except OSError as exc:
            raise ValueError("the part folder still holds other files") from exc
        self.renumber_parts()   # close the gap; last_renames tells a UI what moved

    # -- trash ---------------------------------------------------------------------

    def _trash_dest(self, path: Path) -> Path:
        """A free ``.trash/<stamp>-<project-relative path, "/" as "__">`` name."""
        rel = path.relative_to(self.root).as_posix().replace("/", "__")
        if len(rel) > MAX_TRASH_NAME:  # keep the extension; the folders stay readable
            stem, dot, ext = rel.rpartition(".")
            rel = (stem or rel)[:MAX_TRASH_NAME].rstrip("-_ ") + (dot + ext if stem else "")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.trash_dir.mkdir(exist_ok=True)
        dest, n = self.trash_dir / f"{stamp}-{rel}", 1
        while dest.exists():
            n += 1
            dest = self.trash_dir / f"{stamp}-{n}-{rel}"
        return dest

    def trash_research(self, path: Path) -> Path:
        """Move a notebook note to the Trash (name keeps its ``notebook/``
        relative path). Returns its new path inside ``.trash/``."""
        if not research_notes.is_research_path(self, path) or not path.is_file():
            raise FileNotFoundError("no such research note")
        dest = self._trash_dest(path)
        fsutil.replace(path, dest)
        return dest

    def trash_inspiration(self, image_id: str) -> Path:
        """Move an inspiration image (picture + sidecar) to the Trash: the sidecar
        becomes the ``.md`` item, the picture rides along as ``<item>.<ext>``.
        Returns the item's path inside ``.trash/``."""
        image = inspiration.get(self, image_id)
        dest = self._trash_dest(image.meta_path)
        fsutil.replace(image.path, dest.with_name(f"{dest.name}.{image.ext}"))
        fsutil.replace(image.meta_path, dest)
        return dest

    def trash_object(self, object_id: str) -> Path:
        """Move a figure, table or equation (its ``.md`` plus the image or CSV beside it) to the Trash. The
        companions ride along as ``<item>.<ext>``. *object_id* is the project-relative path of the ``.md``."""
        md = (self.root / object_id).resolve()
        folder = md.parent
        if (md.suffix != ".md" or folder.parent != self.root.resolve()
                or folder.name not in OBJECT_DIRS or not md.is_file()):
            raise FileNotFoundError("no such figure, table or equation")
        dest = self._trash_dest(self.root / folder.name / md.name)
        for ext in OBJECT_COMPANIONS:
            companion = md.with_suffix(f".{ext}")
            if companion.is_file():
                fsutil.replace(companion, dest.with_name(f"{dest.name}.{ext}"))
        fsutil.replace(md, dest)
        return dest

    def delete_scene(self, path: Path) -> Path:
        """Move a scene to the Trash (with its draft sidecar). Returns the
        file's new path inside ``.trash/``. The scenes left in its folder are
        renumbered contiguously (``last_renames`` says which moved); Unplaced
        and front matter keep their numbers."""
        self.last_renames = {}
        dest = self._trash_dest(path)
        side = drafts.sidecar_path(self.root, path)
        if side.is_file():
            fsutil.replace(side, dest.with_name(dest.name + ".drafts.json"))
            try:
                side.parent.rmdir()
            except OSError:
                pass
        snapshots.archive(self.root, path, dest.with_name(dest.name + ".snapshots"))
        comments.archive(self.root, path, dest.with_name(dest.name + ".comments.json"))
        fsutil.replace(path, dest)
        try:
            self.renumber_folder(path.parent)
        except OSError as exc:   # the scene is safely in the Trash; a gap is harmless
            applog.log_exc("renumber after delete", exc)
            self.last_renames = {}
        return dest

    def list_trash(self) -> list[TrashItem]:
        """Trashed scenes and research notes, newest first."""
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
            if original.startswith(("notebook/", "research/")):
                if original.startswith("research/"):   # trashed before the Notebook rename
                    original = research_notes.NOTEBOOK_DIR + original[len("research"):]
                items.append(TrashItem(p.name, p, original, when, research_notes.title_of(p), "research"))
            elif original.split("/", 1)[0] in OBJECT_DIRS:
                items.append(TrashItem(p.name, p, original, when, self._object_title(p), "object"))
            elif original.startswith("inspiration/"):
                items.append(TrashItem(p.name, p, original, when, inspiration.trashed_label(p), "inspiration"))
            else:
                items.append(TrashItem(p.name, p, original, when, self.scene_title(p)))
        return sorted(items, key=lambda i: (i.deleted, i.name), reverse=True)

    def _trash_item(self, name: str) -> TrashItem:
        for item in self.list_trash():
            if item.name == name:
                return item
        raise FileNotFoundError(f"not in the trash: {name}")

    def _restore_research(self, item: TrashItem) -> Path:
        """Back to its original path (a free name if one was made since); if its
        folder is gone, into ``notebook/`` itself."""
        orig = self.root / item.original
        folder = orig.parent if orig.parent.is_dir() else research_notes.research_dir(self)
        folder.mkdir(parents=True, exist_ok=True)
        final = orig if orig.parent == folder and not orig.exists() \
            else research_notes._free_path(folder, orig.stem)
        fsutil.replace(item.path, final)
        self._tidy_trash()
        return final

    @staticmethod
    def _object_title(trashed: Path) -> str:
        """The caption of a trashed object, else its label."""
        try:
            head = trashed.read_text(encoding="utf-8")[:2000]
            m = re.search(r"^caption:[ \t]*(.+?)[ \t]*$", head, re.MULTILINE)
            if m and m.group(1).strip("'\""):
                return m.group(1).strip("'\"")
        except (OSError, UnicodeDecodeError):
            pass
        return Path(_TRASH_RE.match(trashed.name).group(3).replace("__", "/")).stem

    def _restore_object(self, item: TrashItem) -> Path:
        """The ``.md`` and its image/CSV back into the object's folder (a free name if one was made since)."""
        orig = self.root / item.original
        folder = orig.parent
        folder.mkdir(parents=True, exist_ok=True)
        stem, n = orig.stem, 1
        while any((folder / f"{stem}.{e}").exists() for e in ("md",) + OBJECT_COMPANIONS):
            n += 1
            stem = f"{orig.stem}-{n}"
        for ext in OBJECT_COMPANIONS:
            companion = item.path.with_name(f"{item.path.name}.{ext}")
            if companion.is_file():
                fsutil.replace(companion, folder / f"{stem}.{ext}")
        final = folder / f"{stem}.md"
        fsutil.replace(item.path, final)
        self._tidy_trash()
        return final

    def _restore_inspiration(self, item: TrashItem) -> Path:
        """Picture and sidecar back into ``inspiration/`` (a free name if one was
        made since). Returns the sidecar's path."""
        folder = inspiration.inspiration_dir(self)
        folder.mkdir(parents=True, exist_ok=True)
        stem = Path(item.original).stem
        picture = next((p for e in inspiration.EXTENSIONS
                        if (p := item.path.with_name(f"{item.path.name}.{e}")).is_file()), None)
        ext = picture.suffix.lstrip(".") if picture else "jpg"
        final, n = folder / f"{stem}.md", 1
        while final.exists() or any((folder / f"{final.stem}.{e}").exists() for e in inspiration.EXTENSIONS):
            n += 1
            final = folder / f"{stem}-{n}.md"
        if picture is not None:
            fsutil.replace(picture, folder / f"{final.stem}.{ext}")
        fsutil.replace(item.path, final)
        self._tidy_trash()
        return final

    def restore_place(self, name: str) -> tuple[str, str]:
        """Where ``restore_scene(name)`` will put a scene: ``("part", title)``,
        ``("book", "")`` (top level), ``("unplaced", "")`` (it came from there)
        or ``("gone", "")`` (its part no longer exists, so Unplaced)."""
        item = self._trash_item(name)
        folder = (self.root / item.original).parent
        if folder == self.unplaced_dir:
            return "unplaced", ""
        if folder == self.manuscript_dir:
            return "book", ""
        if folder in self.list_parts():
            return "part", self.part_title(folder)
        return "gone", ""

    def restore_scene(self, name: str) -> Path:
        """Put a trashed scene back at its original position in its original
        part (or the top level; one that came from Unplaced goes to the end),
        and renumber that folder contiguously; if the part is gone, Unplaced.
        A trashed research note goes back to its original path instead."""
        self.last_renames = {}
        item = self._trash_item(name)
        if item.kind == "research":
            return self._restore_research(item)
        if item.kind == "inspiration":
            return self._restore_inspiration(item)
        if item.kind == "object":
            return self._restore_object(item)
        orig = self.root / item.original
        folder = orig.parent
        if folder != self.manuscript_dir and folder not in self.list_parts():
            # the part may have been renumbered since: find it by its slug
            folder = next((p for p in self.list_parts()
                           if _slug_of(p.name) == _slug_of(folder.name)
                           and folder.parent == self.manuscript_dir), folder)
        if folder == self.manuscript_dir or folder in self.list_parts():
            dest_dir = folder
        else:
            dest_dir = self.unplaced_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        final = self._next_in(dest_dir, _slug_of(orig.name))
        final.parent.mkdir(parents=True, exist_ok=True)
        fsutil.replace(item.path, final)
        side = item.path.with_name(item.path.name + ".drafts.json")
        if side.is_file():
            target = drafts.sidecar_path(self.root, final)
            target.parent.mkdir(parents=True, exist_ok=True)
            fsutil.replace(side, target)
        snapshots.unarchive(self.root, item.path.with_name(item.path.name + ".snapshots"), final)
        comments.unarchive(self.root, item.path.with_name(item.path.name + ".comments.json"), final)
        self._tidy_trash()
        at = _prefix(orig.name)
        if at is not None and dest_dir != self.unplaced_dir and not (
                dest_dir != self.manuscript_dir and self.part_is_front_matter(dest_dir)):
            try:   # back where it was (its old number), neighbours renumbered
                final = self.place_scene(
                    final, None if dest_dir == self.manuscript_dir else dest_dir, max(0, at - 1))
            except OSError as exc:   # restored at the end; the order can be fixed by hand
                applog.log_exc("renumber after restore", exc)
        return final

    def _next_in(self, folder: Path, slug: str) -> Path:
        highest = max((_prefix(p.name) or 0 for p in self._scene_files(folder)),
                      default=0)
        return folder / f"{_num(highest + 1)}-{slug}.md"

    def delete_forever(self, name: str) -> None:
        item = self._trash_item(name)
        item.path.unlink(missing_ok=True)
        item.path.with_name(item.path.name + ".drafts.json").unlink(missing_ok=True)
        item.path.with_name(item.path.name + ".comments.json").unlink(missing_ok=True)
        for ext in dict.fromkeys(inspiration.EXTENSIONS + OBJECT_COMPANIONS):
            item.path.with_name(f"{item.path.name}.{ext}").unlink(missing_ok=True)
        shutil.rmtree(item.path.with_name(item.path.name + ".snapshots"), ignore_errors=True)
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
