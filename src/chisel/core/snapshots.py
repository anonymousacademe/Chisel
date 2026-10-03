"""Scene snapshots: verbatim, restorable copies of a scene file.

    .snapshots/manuscript__01-the-recall__02-capsule.md/
      20261001-101500.md               a snapshot (the scene file, frontmatter included)
      20261001-101500--before-restore.md        ... with a label after "--"
      20261001-101500--before-restore.json      the scene's .drafts originals at that moment

The folder is keyed like the draft sidecars (``drafts.sidecar_key``) and, like
them, is author data: plain files, committed with the project, never under
``.chisel/``. Nothing here needs the index. ``project`` arguments are
duck-typed (``root`` and ``all_scene_files()``) so this module stays below
``core.project`` in the import order.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import drafts
from . import settings as user_settings
from . import fsutil

SNAPSHOT_DIR = ".snapshots"
LABEL_MAX = 60
AUTO_LABEL = "auto"

_NAME_RE = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?(?:--(.+))?$")
_BAD_LABEL = re.compile(r"[\\/\x00-\x1f:*?\"<>|]+")


@dataclass(frozen=True)
class Snapshot:
    name: str          # file stem inside the scene's folder (the id)
    path: Path
    when: datetime
    label: str
    words: int


@dataclass(frozen=True)
class Segment:
    """One run of a word diff. ``equal`` has the same text on both sides;
    ``delete`` only ``old``; ``insert`` only ``new``; ``replace`` both."""
    op: str
    old: str
    new: str


# -- locations ---------------------------------------------------------------


def root_dir(project_root: Path) -> Path:
    return project_root / SNAPSHOT_DIR


def scene_dir(project_root: Path, scene: Path) -> Path:
    return root_dir(project_root) / drafts.sidecar_key(project_root, scene)


def clean_label(label: str) -> str:
    """A label that is safe in a file name (and still readable)."""
    label = _BAD_LABEL.sub("-", " ".join((label or "").split()))
    return label[:LABEL_MAX].strip(" .-")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def _parse(path: Path) -> tuple[datetime, str] | None:
    m = _NAME_RE.match(path.stem)
    if not m:
        return None
    try:
        when = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
    except ValueError:
        return None
    return when, m.group(3) or ""


def _file(project_root: Path, scene: Path, name: str) -> Path:
    """The snapshot file for *name*; ValueError for anything that is not a
    plain snapshot id (ids come over the GUI bridge)."""
    if not _NAME_RE.fullmatch(name or ""):
        raise ValueError("invalid snapshot id")
    path = scene_dir(project_root, scene) / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no such snapshot: {name}")
    return path


def _originals(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.with_name(path.stem + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}


def _snapshot(path: Path) -> Snapshot | None:
    parsed = _parse(path)
    if parsed is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):  # unreadable or not UTF-8: not listed
        return None
    return Snapshot(path.stem, path, parsed[0], parsed[1],
                    drafts.count_words(text, _originals(path)))


# -- create / read -----------------------------------------------------------


def create(project, scene: Path, label: str = "", text: str | None = None,
           when: datetime | None = None) -> Snapshot:
    """Copy *scene* (or *text*, the editor's unsaved buffer) into its snapshot
    folder, with the draft originals beside it. Never overwrites."""
    if text is None:
        fsutil.ensure_utf8(scene)  # a snapshot is text; lossy copies are no backup
        text = scene.read_text(encoding="utf-8")
    when = when or datetime.now()
    folder = scene_dir(project.root, scene)
    stamp, n = when.strftime("%Y%m%d-%H%M%S"), 1
    tail = f"--{clean_label(label)}" if clean_label(label) else ""
    stem = f"{stamp}{tail}"
    while (folder / f"{stem}.md").exists():
        n += 1
        stem = f"{stamp}-{n}{tail}"
    originals = drafts.load_originals(project.root, scene)
    if originals:
        _write(folder / f"{stem}.json", json.dumps(originals, indent=2, ensure_ascii=False))
    _write(folder / f"{stem}.md", text)
    return Snapshot(stem, folder / f"{stem}.md", when, clean_label(label),
                    drafts.count_words(text, originals))


def list_snapshots(project, scene: Path) -> list[Snapshot]:
    """Newest first."""
    try:
        files = list(scene_dir(project.root, scene).glob("*.md"))
    except OSError:
        return []
    snaps = [s for s in map(_snapshot, files) if s is not None]

    def newest(s: Snapshot) -> tuple:  # same second: the later write wins
        try:
            return (s.when, s.path.stat().st_mtime_ns, s.name)
        except OSError:
            return (s.when, 0, s.name)

    return sorted(snaps, key=newest, reverse=True)


def latest_time(project, scene: Path) -> datetime | None:
    """When the scene was last snapshotted (cheap: names only, no reads)."""
    try:
        stamps = [p[0] for p in map(_parse, scene_dir(project.root, scene).glob("*.md"))
                  if p is not None]
    except OSError:
        return None
    return max(stamps, default=None)


def read_text(project, scene: Path, name: str) -> str:
    return _file(project.root, scene, name).read_text(encoding="utf-8")


def delete(project, scene: Path, name: str) -> None:
    path = _file(project.root, scene, name)
    path.unlink(missing_ok=True)
    path.with_name(path.stem + ".json").unlink(missing_ok=True)
    try:
        path.parent.rmdir()  # tidy: only when it was the last one
    except OSError:
        pass


def restore(project, scene: Path, name: str, current_text: str | None = None) -> str:
    """Make the scene read as snapshot *name*. The current text (the editor's
    buffer if given, else the file) is snapshotted first, labelled
    ``before-restore``, so a restore can itself be undone. Returns the text."""
    path = _file(project.root, scene, name)
    fsutil.ensure_utf8(scene)  # restoring would overwrite bytes we cannot snapshot
    text = path.read_text(encoding="utf-8")
    create(project, scene, "before-restore", current_text)
    _write(scene, text)
    drafts.save_originals(project.root, scene, _originals(path))
    return text


def snapshot_all(project, label: str = "") -> int:
    """One snapshot per scene of the project (book and Unplaced), same label."""
    count = 0
    for scene in project.all_scene_files():
        if not fsutil.is_valid_utf8(scene):
            continue  # cannot be snapshotted as text
        create(project, scene, label)
        count += 1
    return count


def auto_enabled() -> bool:
    """User setting ``auto_snapshot`` (default on): the daily safety net."""
    return bool(user_settings.get("auto_snapshot", True))


_daily_done: dict[str, str] = {}  # scene path -> "YYYYMMDD" already ensured


def ensure_daily(project, scene: Path, new_text: str) -> Snapshot | None:
    """Safety net: before the first save that changes *scene* on a given day,
    snapshot what is on disk (label ``auto``). Does nothing when the text is
    unchanged, a snapshot from today exists, or the latest snapshot already
    holds exactly this text."""
    today = datetime.now().strftime("%Y%m%d")
    key = str(scene)
    if _daily_done.get(key) == today:
        return None
    try:
        disk = scene.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None  # a new file has no earlier state; a non-UTF-8 one is refused by the save
    if disk == new_text:
        return None
    _daily_done[key] = today
    latest = latest_time(project, scene)
    if latest is not None and latest.strftime("%Y%m%d") == today:
        return None
    snaps = list_snapshots(project, scene)
    try:
        if snaps and snaps[0].path.read_text(encoding="utf-8") == disk:
            return None
    except (OSError, ValueError):
        pass
    return create(project, scene, AUTO_LABEL, disk)


# -- carrying along with the scene -------------------------------------------


def stage(project_root: Path, scene: Path, tag: str) -> Path | None:
    """Move a scene's snapshot folder aside (renames are two-phase); the
    return value goes to ``unstage``. None when there is nothing to carry."""
    old = scene_dir(project_root, scene)
    if not old.is_dir():
        return None
    tmp = old.with_name(f".mv{tag}-{old.name}")
    fsutil.replace(old, tmp)
    return tmp


def unstage(project_root: Path, staged: Path, new_scene: Path) -> None:
    new = scene_dir(project_root, new_scene)
    new.parent.mkdir(parents=True, exist_ok=True)
    fsutil.replace(staged, new)


def archive(project_root: Path, scene: Path, dest: Path) -> None:
    """Move the folder to *dest* (the Trash keeps a deleted scene's history)."""
    old = scene_dir(project_root, scene)
    if old.is_dir():
        fsutil.replace(old, dest)


def unarchive(project_root: Path, src: Path, scene: Path) -> None:
    if src.is_dir():
        new = scene_dir(project_root, scene)
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            shutil.rmtree(new, ignore_errors=True)
        fsutil.replace(src, new)


# -- compare -------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\s*\S+\s*|\s+")
_MAX_CELLS = 40_000_000  # token pairs a hunk may compare before we give up


def _merge(segs: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for s in segs:
        if out and out[-1].op == s.op:
            p = out.pop()
            s = Segment(s.op, p.old + s.old, p.new + s.new)
        out.append(s)
    return out


def _word_diff(old: str, new: str) -> list[Segment]:
    a, b = _TOKEN_RE.findall(old), _TOKEN_RE.findall(new)
    if len(a) * len(b) > _MAX_CELLS:
        return [Segment("replace", old, new)]
    segs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        o, n = "".join(a[i1:i2]), "".join(b[j1:j2])
        segs.append(Segment({"equal": "equal", "delete": "delete", "insert": "insert",
                             "replace": "replace"}[tag], o, n))
    return segs


def diff_words(old: str, new: str) -> list[Segment]:
    """Word-level difference of two texts: matched lines first (cheap), then
    the words inside the lines that changed. Whitespace travels with the word
    before it, so concatenating ``old`` (or ``new``) of all segments gives the
    original text back exactly."""
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    segs: list[Segment] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        o, n = "".join(a[i1:i2]), "".join(b[j1:j2])
        segs += [Segment("equal", o, n)] if tag == "equal" else _word_diff(o, n)
    return _merge(segs)


def diff_stats(segs: list[Segment]) -> tuple[int, int]:
    """(words added, words removed) of a diff."""
    added = sum(len(s.new.split()) for s in segs if s.op != "equal")
    removed = sum(len(s.old.split()) for s in segs if s.op != "equal")
    return added, removed


def ago(when: datetime, now: datetime | None = None) -> str:
    """'just now', '12 min ago', '3 h ago', '2 days ago', else the date."""
    secs = int(((now or datetime.now()) - when).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    if secs < 86400 * 14:
        days = secs // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"
    return when.strftime("%Y-%m-%d")
