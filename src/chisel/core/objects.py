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


# -- creating and editing tables and equations (F0) ------------------------------------------


MAX_TABLE_ROWS = 60
MAX_TABLE_COLS = 20
MAX_CELL_CHARS = 2000
MAX_LATEX_CHARS = 10_000
MAX_CAPTION_CHARS = 1000
MIN_WIDTH, MAX_WIDTH = 1.0, 20.0
KIND_WORDS = {"fig": "figure", "tbl": "table", "eq": "equation"}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _strip_markers(text: str, *, join_braces: bool = False) -> str:
    """Remove comment openers and closers and double curly braces until none survive (also one made by removing
    another). With *join_braces* (LaTeX, where ``\\frac{{a}}{b}`` is legal) a brace pair is split with a space
    instead, which TeX reads the same."""
    while True:
        before = text
        for frag in ("<!--", "-->"):
            text = text.replace(frag, "")
        if join_braces:
            text = text.replace("{{", "{ {").replace("}}", "} }")
        else:
            text = text.replace("{{", "").replace("}}", "")
        if text == before:
            return text


def clean_line(value, limit: int = MAX_CAPTION_CHARS) -> str:
    """A caption or alt text: one line, no markers, no control characters."""
    text = _CONTROL.sub(" ", str(value if value is not None else "")).replace("\r", "\n")
    text = _strip_markers(text)
    return " ".join(text.split())[:limit].strip()


def clean_latex(value) -> str:
    """LaTeX source: markers removed (see ``_strip_markers``), never longer than MAX_LATEX_CHARS (ValueError)."""
    text = _CONTROL.sub(" ", str(value if value is not None else "")).replace("\r\n", "\n").replace("\r", "\n")
    text = _strip_markers(text, join_braces=True).strip()
    if not text:
        raise ValueError("an equation needs some LaTeX")
    if len(text) > MAX_LATEX_CHARS:
        raise ValueError(f"an equation is limited to {MAX_LATEX_CHARS:,} characters")
    return text


def _check_label(label: str, what: str) -> str:
    label = (label or "").strip()
    if not _LABEL_RE.match(label):
        raise ValueError(f"a {what} label uses letters, digits, hyphens and underscores")
    return label


def _head(meta: dict) -> str:
    return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=10_000,
                                    default_flow_style=False) + "---\n"


def _new_note(project, kind: str, label: str, meta: dict, body: str) -> RefObject:
    folder = _folder(project, kind)
    md = folder / f"{KINDS[kind][1]}{label}.md"
    if md.exists() or md.is_symlink():
        raise ValueError(f"a {KIND_WORDS[kind]} labelled {label} already exists")
    folder.mkdir(parents=True, exist_ok=True)
    _write(md, _head(meta) + body)
    obj = _object(project, kind, md)
    assert obj is not None
    return obj


def create_table(project, label: str, caption: str, cells, align) -> RefObject:
    """Add ``tables/tbl-<label>.md`` with a canonical pipe table (``tables.to_pipe``). ValueError for a bad
    label, a label in use, more than 60 rows or 20 columns, a cell over 2000 characters or a bad alignment."""
    from . import tables
    label = _check_label(label, "table")
    if not isinstance(cells, (list, tuple)) or not cells or not all(isinstance(r, (list, tuple)) for r in cells):
        raise ValueError("a table needs a header row and at least one column")
    if len(cells) > MAX_TABLE_ROWS:
        raise ValueError(f"a table is limited to {MAX_TABLE_ROWS} rows")
    width = max(len(r) for r in cells)
    align = [str(a) for a in align] if align else ["default"] * len(cells[0])
    if not align or width == 0:
        raise ValueError("a table needs a header row and at least one column")
    if width > len(align):
        raise ValueError("a row has more cells than the table has columns")
    if len(align) > MAX_TABLE_COLS:
        raise ValueError(f"a table is limited to {MAX_TABLE_COLS} columns")
    rows = [[str(c if c is not None else "") for c in r] for r in cells]
    if any(len(c) > MAX_CELL_CHARS for r in rows for c in r):
        raise ValueError(f"a table cell is limited to {MAX_CELL_CHARS:,} characters")
    text = tables.to_pipe(tables.Table(rows, align))       # validates the alignments
    return _new_note(project, "tbl", label, {"caption": clean_line(caption)}, text + "\n")


def create_equation(project, label: str, latex: str, caption: str = "") -> RefObject:
    """Add ``equations/eq-<label>.md`` (the LaTeX is the body). ValueError for a bad or used label, empty or
    over-long LaTeX."""
    label = _check_label(label, "equation")
    body = clean_latex(latex)
    cap = clean_line(caption)
    return _new_note(project, "eq", label, {"caption": cap} if cap else {}, body + "\n")


def update_object(project, kind: str, label: str, *, caption=None, alt=None, width=None, latex=None) -> RefObject:
    """Change an object's note in place, atomically; every other frontmatter key and the rest of the body are
    kept. Figure: caption, alt, width (inches, 1 to 20; None leaves it). Equation: latex, caption. Table:
    caption only. A field the kind does not have is a ValueError."""
    if kind not in KINDS:
        raise ValueError("no such figure, table or equation")
    allowed = {"fig": ("caption", "alt", "width"), "tbl": ("caption",), "eq": ("latex", "caption")}[kind]
    given = {"caption": caption, "alt": alt, "width": width, "latex": latex}
    for name, value in given.items():
        if value is not None and name not in allowed:
            raise ValueError(f"a {KIND_WORDS[kind]} has no {name}")
    label = _check_label(label, KIND_WORDS[kind])
    md = _folder(project, kind) / f"{KINDS[kind][1]}{label}.md"
    if not md.is_file() or md.is_symlink():
        raise ValueError(f"no such {KIND_WORDS[kind]}: {kind}:{label}")
    text = md.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = _BLOCK_RE.match(text)
    meta: dict = {}
    body = text
    if m is not None:
        try:
            loaded = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            raise ValueError("the note's front matter is not valid; fix it in the file first") from None
        meta = loaded if isinstance(loaded, dict) else {}
        body = text[m.end():]
    if caption is not None:
        meta["caption"] = clean_line(caption)
    if alt is not None:
        a = clean_line(alt)
        if a:
            meta["alt"] = a
        else:
            meta.pop("alt", None)
    if width is not None:
        try:
            w = float(width)
        except (TypeError, ValueError):
            raise ValueError("the width is a number of inches") from None
        if not (MIN_WIDTH <= w <= MAX_WIDTH):          # also rejects nan
            raise ValueError(f"the width is between {MIN_WIDTH:g} and {MAX_WIDTH:g} inches")
        meta["width"] = int(w) if w == int(w) else round(w, 2)
    if latex is not None:
        body = clean_latex(latex) + "\n"
    if kind == "eq" and not meta.get("caption"):
        meta.pop("caption", None)
    _write(md, (_head(meta) if meta else "") + body)
    obj = _object(project, kind, md)
    assert obj is not None
    return obj


def suggest_label(project, kind: str, caption: str) -> str:
    """A unique plain label for a new object: the caption slugified (ASCII, at most 40 characters), else the
    kind word; ``-2``, ``-3`` when taken."""
    import unicodedata
    if kind not in KINDS:
        raise ValueError("no such figure, table or equation")
    text = unicodedata.normalize("NFKD", str(caption or "")).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-") or KIND_WORDS[kind]
    prefix = KINDS[kind][1]
    taken = {o.label.lower() for o in list_objects(project) if o.kind == kind}
    folder = _folder(project, kind)
    if folder.is_dir():
        taken |= {p.stem[len(prefix):].lower() for p in folder.iterdir() if p.name.startswith(prefix)}
    label, n = slug, 1
    while label in taken:
        n += 1
        label = f"{slug}-{n}"
    return label


def scan_text(project, text: str) -> str:
    """*text* as the object scanners read it: pending drafts, scene details and math blanked, then code (fenced
    and inline) blanked, all same length."""
    from .links import _mask_code
    return _mask_code(_prose_for_scan(text, project.mode))


def references(project, kind: str, label: str) -> dict:
    """Where an object is placed and referenced in the book (``list_scenes``; Parked scenes excluded):
    ``{"placements": [(path, row)], "refs": [(path, row)]}`` with 0-based rows, in reading order."""
    out: dict[str, list] = {"placements": [], "refs": []}
    for scene in project.list_scenes():
        try:
            text = scene.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scan = scan_text(project, text)
        for p in find_placements(scan):
            if p.kind == kind and p.label == label:
                out["placements"].append((scene, text.count("\n", 0, p.start)))
        for r in find_refs(scan):
            if r.kind == kind and r.label == label:
                out["refs"].append((scene, text.count("\n", 0, r.start)))
    return out
