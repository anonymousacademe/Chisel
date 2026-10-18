"""Figures, tables and equations of a research project (docs/dev/plan-research-mode.md 7.1, 7.2).

Files::

    figures/fig-<label>.md  + figures/fig-<label>.png|jpg    (YAML: caption, file, width, alt; body = notes)
    tables/tbl-<label>.md   [+ tables/tbl-<label>.csv]        (YAML: caption; body = a Markdown pipe table)
    equations/eq-<label>.md                                   (YAML: caption (optional); body = LaTeX)

The label is the file-name stem without the kind prefix and is stored nowhere else. Numbers are never stored:
``numbering`` derives them from reading order. Everything here is read-only except ``create_figure``.

Math handling (``strip_math``) is research mode only. Design: ``strip_math(text, keep_length=True, mode="story")``
is a NO-OP unless the caller passes ``mode="research"`` (``project.mode``), so a fiction caller that forgets the
argument can never change a count, a spelling run or a mention scan.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml

from . import drafts, fsutil, scenemeta
from .paper.types import Num, Numbering, ObjectKind, ObjectRef, Placement, RefObject

KINDS: dict[str, tuple[str, str]] = {          # kind -> (folder, file-name prefix)
    "fig": ("figures", "fig-"),
    "tbl": ("tables", "tbl-"),
    "eq": ("equations", "eq-"),
}
IMAGE_EXTS = ("png", "jpg")
MIME = {"png": "image/png", "jpg": "image/jpeg"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
NUMBER_SCHEMES = ("plain", "per-section", "supplementary")
DEFAULT_SCHEME = "plain"

_LABEL = r"[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*"
_LABEL_RE = re.compile(rf"^{_LABEL}$")
_PLACEMENT_RE = re.compile(rf"^[ \t]*!\[\[(fig|tbl|eq):({_LABEL})\]\][ \t]*$", re.MULTILINE)
_REF_RE = re.compile(rf"(?<!!)\[\[(fig|tbl|eq):({_LABEL})\]\]")
_BLOCK_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


# -- parsing -------------------------------------------------------------------------


def find_placements(text: str) -> list[Placement]:
    """Block placements: ``![[fig:x]]`` alone on a line. Offsets cover the ``![[...]]`` only."""
    out = []
    for m in _PLACEMENT_RE.finditer(text):
        start = text.index("![[", m.start())
        out.append(Placement(m.group(1), m.group(2), start, start + len(m.group(0).strip(" \t"))))
    return out


def find_refs(text: str) -> list[ObjectRef]:
    """References in prose: ``[[fig:x]]``. A placement line is not a reference."""
    taken = [(p.start, p.end) for p in find_placements(text)]
    out = []
    for m in _REF_RE.finditer(text):
        if any(s <= m.start() < e for s, e in taken):
            continue
        out.append(ObjectRef(m.group(1), m.group(2), m.start(), m.end()))
    return out


def strip_math(text: str, *, keep_length: bool = True, mode: str = "story") -> str:
    """Remove ``$...$`` and ``$$...$$`` math (pandoc's ``tex_math_dollars`` rule: the opening ``$`` is followed
    by a non-space, the closing ``$`` is preceded by a non-space and not followed by a digit, ``\\$`` is a
    literal dollar, and inline math does not cross a blank line). With *keep_length* the math becomes spaces
    (newlines kept) so offsets and rows survive, as ``scenemeta.blank`` does. A no-op unless ``mode`` is
    ``"research"``: pass ``project.mode``."""
    if mode != "research" or "$" not in text:
        return text
    n, i, out, last = len(text), 0, [], 0

    def blank(seg: str) -> str:
        return "".join(c if c == "\n" else " " for c in seg) if keep_length else ""

    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch != "$":
            i += 1
            continue
        end = -1
        if text.startswith("$$", i):
            j = text.find("$$", i + 2)
            while j != -1 and text[j - 1] == "\\":
                j = text.find("$$", j + 1)
            if j != -1:
                end = j + 2
        if end == -1 and i + 1 < n and not text[i + 1].isspace() and text[i + 1] != "$":
            j = i + 1
            while j < n:
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "\n" and text[j + 1:j + 2] == "\n":   # a blank line ends inline math
                    break
                if c == "$" and not text[j - 1].isspace() and not text[j + 1:j + 2].isdigit():
                    end = j + 1
                    break
                j += 1
        if end == -1:
            i += 1
            continue
        out.append(text[last:i])
        out.append(blank(text[i:end]))
        last = i = end
    out.append(text[last:])
    return "".join(out)


# -- files ---------------------------------------------------------------------------


def _split(text: str) -> tuple[dict, str]:
    m = _BLOCK_RE.match(text)
    if m is None:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}, text[m.end():]
    return (meta if isinstance(meta, dict) else {}), text[m.end():]


def _folder(project, kind: str) -> Path:
    return project.root / KINDS[kind][0]


def _find_image(project, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        p = _folder(project, "fig") / f"{stem}.{ext}"
        if p.is_file():
            return p
    return None


def _rel(project, path: Path) -> str:
    return path.relative_to(project.root).as_posix()


def _object(project, kind: str, md: Path) -> RefObject | None:
    prefix = KINDS[kind][1]
    if not md.name.startswith(prefix) or md.name.startswith("."):
        return None
    label = md.stem[len(prefix):]
    if not _LABEL_RE.match(label):
        return None
    try:
        meta, _body = _split(md.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    file = None
    status = "current"
    if kind == "fig":
        image = _find_image(project, md.stem)
        file = _rel(project, image) if image else None
        if image is None:
            status = "missing"
    elif kind == "tbl":
        csv = md.with_suffix(".csv")
        file = _rel(project, csv) if csv.is_file() else None
    source = meta.get("source")
    try:
        width = float(meta["width"]) if meta.get("width") is not None else None
    except (TypeError, ValueError):
        width = None
    return RefObject(kind, label, _rel(project, md), str(meta.get("caption") or ""),
                     source if source in ("static", "script", "data") else "static",
                     file, width, str(meta.get("alt") or ""), status)


def list_objects(project) -> list[RefObject]:
    """Every figure, table and equation, figures first, each kind sorted by file name."""
    out: list[RefObject] = []
    for kind in KINDS:
        folder = _folder(project, kind)
        if not folder.is_dir():
            continue
        for md in sorted(folder.glob("*.md")):
            if md.is_file() and not md.is_symlink():
                obj = _object(project, kind, md)
                if obj is not None:
                    out.append(obj)
    return out


def sniff_image(data: bytes) -> str | None:
    """``png`` or ``jpg`` from the bytes themselves (a mime type or file name can lie); else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def write_atomic(path: Path, data: bytes) -> None:
    """Write *data* beside *path* through a fresh, randomly named temp file (``mkstemp``: created exclusively, so a
    planted symlink at a guessable name is never followed), then replace. OSError when *path* is a symlink."""
    if path.is_symlink():
        raise OSError(f"{path.name} is a link; Chisel does not write through links")
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        fsutil.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _write(path: Path, text: str) -> None:
    write_atomic(path, text.encode("utf-8"))


def create_figure(project, src_bytes: bytes, label: str, caption: str) -> RefObject:
    """Add ``figures/fig-<label>.<png|jpg>`` and its ``.md``. ValueError for a bad label, a label in use, an
    image that is not PNG or JPG (decided from the bytes) or one over 10 MB."""
    label = (label or "").strip()
    if not _LABEL_RE.match(label):
        raise ValueError("a figure label uses letters, digits, hyphens and underscores")
    if not isinstance(src_bytes, (bytes, bytearray)) or not src_bytes:
        raise ValueError("the image is empty")
    if len(src_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("the image is larger than 10 MB")
    ext = sniff_image(bytes(src_bytes))
    if ext is None:
        raise ValueError("the image must be a PNG or JPG file")
    stem = f"fig-{label}"
    folder = _folder(project, "fig")
    if (folder / f"{stem}.md").exists() or _find_image(project, stem) is not None:
        raise ValueError(f"a figure labelled {label} already exists")
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / f"{stem}.{ext}"
    md = folder / f"{stem}.md"
    write_atomic(image, bytes(src_bytes))
    head = yaml.safe_dump({"caption": caption or "", "file": _rel(project, image)},
                          sort_keys=False, allow_unicode=True, width=10_000, default_flow_style=False)
    try:
        _write(md, f"---\n{head}---\n")
    except OSError:
        image.unlink(missing_ok=True)
        raise
    obj = _object(project, "fig", md)
    assert obj is not None
    return obj


def _figure_file(project, label: str) -> Path:
    """The one door to a figure's image bytes: a plain label, a real file (no symlink) inside ``figures/``.
    ValueError for anything else, FileNotFoundError when the image is missing."""
    if not isinstance(label, str) or not _LABEL_RE.match(label):
        raise ValueError("invalid figure label")
    folder = _folder(project, "fig").resolve()
    for ext in IMAGE_EXTS:
        p = _folder(project, "fig") / f"fig-{label}.{ext}"
        if p.is_symlink():
            raise ValueError("invalid figure label")
        if p.is_file():
            if p.resolve().parent != folder:
                raise ValueError("invalid figure label")
            return p
    raise FileNotFoundError(f"the figure image is missing: {label}")


def read_figure(project, label: str) -> tuple[bytes, str]:
    """The image's bytes and mime type, only ever from ``figures/`` through ``_figure_file``."""
    path = _figure_file(project, label)
    return path.read_bytes(), MIME[path.suffix.lstrip(".")]


def safe_project_path(project, rel: str) -> Path:
    """A project-relative path from frontmatter (``file:``, ``data:``) as an absolute one, or ValueError when
    it is absolute, uses ``..``, or resolves (through a symlink) outside the project."""
    if not isinstance(rel, str) or not rel.strip():
        raise ValueError("empty path")
    p = Path(rel)
    if p.is_absolute() or p.drive or rel.startswith(("/", "\\")) or ".." in p.parts or ".." in rel.replace("\\", "/").split("/"):
        raise ValueError("a project path must stay inside the project")
    full = (project.root / p).resolve()
    if not full.is_relative_to(project.root.resolve()):
        raise ValueError("a project path must stay inside the project")
    return full


# -- numbering -----------------------------------------------------------------------


def _scheme(project, scheme: str | None) -> str:
    if scheme is None:
        raw = (getattr(project, "meta", None) or {}).get("research") or {}
        scheme = raw.get("numbering") if isinstance(raw, dict) else None
    return scheme if scheme in NUMBER_SCHEMES else DEFAULT_SCHEME


def _prose_for_scan(text: str, mode: str) -> str:
    text = drafts.blank_pending(text)            # unaccepted AI text is not the manuscript
    text = scenemeta.blank(text)
    return strip_math(text, mode=mode)


def numbering(project, scheme: str | None = None) -> Numbering:
    """Numbers in reading order (``Project.list_scenes``; Parked scenes are not in the book). An object is
    numbered by its first placement; a second placement of the same label shares the number; an object that is
    never placed has none. *scheme* (default: ``[research] numbering`` in project.toml): ``plain`` (1, 2, 3),
    ``per-section`` (2.1: the part's position, then the order inside the part; scenes outside any part count
    plainly) or ``supplementary`` (S1, S2). ``seq`` is the plain order within the kind in every scheme."""
    scheme = _scheme(project, scheme)
    parts = [p.resolve() for p in project.list_parts()]
    seen: dict[str, Num] = {}
    seq: dict[str, int] = {k: 0 for k in KINDS}
    in_part: dict[tuple[int, str], int] = {}
    mode = project.mode
    for scene in project.list_scenes():
        try:
            text = scene.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        section = 0
        parent = scene.resolve().parent
        if parent in parts:
            section = parts.index(parent) + 1
        for p in find_placements(_prose_for_scan(text, mode)):
            key = f"{p.kind}:{p.label}"
            if key in seen:
                continue
            seq[p.kind] += 1
            if scheme == "supplementary":
                display = f"S{seq[p.kind]}"
            elif scheme == "per-section" and section:
                in_part[(section, p.kind)] = in_part.get((section, p.kind), 0) + 1
                display = f"{section}.{in_part[(section, p.kind)]}"
            else:
                display = str(seq[p.kind])
            seen[key] = Num(seq[p.kind], display)
    return seen
