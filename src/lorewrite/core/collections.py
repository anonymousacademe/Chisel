"""Collections: named groups of scenes ("Needs continuity pass", "Mara's arc").

Definitions live in ``project.toml``::

    [collections]
    "Needs continuity pass" = "amber"
    "Mara's arc" = "violet"

(name -> one of ``COLORS``, the design's swatch tokens). Membership lives in
each scene's own frontmatter, ``collections: [Needs continuity pass]`` (see
``core.scenemeta``), so it is plain text that travels with the scene. A name
that scenes use but ``project.toml`` does not define still shows up (grey,
``declared`` false): membership is never hidden. ``project`` arguments are
duck-typed: ``root``, ``meta``, ``all_scene_files()``, ``_write_section``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import scenemeta

SECTION = "collections"
COLORS = ("violet", "amber", "green", "red", "gray")
DEFAULT_COLOR = "gray"
NAME_MAX = 60


@dataclass(frozen=True)
class Collection:
    name: str
    color: str
    declared: bool = True
    scenes: tuple[Path, ...] = field(default=())


def clean_name(name: str) -> str:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("a collection needs a name")
    if len(name) > NAME_MAX:
        raise ValueError(f"a collection name is at most {NAME_MAX} characters")
    return name


def _color(color: str | None) -> str:
    color = (color or DEFAULT_COLOR).strip().lower()
    if color not in COLORS:
        raise ValueError(f"colour must be one of: {', '.join(COLORS)}")
    return color


def declared(project) -> dict[str, str]:
    raw = project.meta.get(SECTION) or {}
    out: dict[str, str] = {}
    for name, color in raw.items() if isinstance(raw, dict) else ():
        name = " ".join(str(name).split())
        if name:
            out[name] = color if color in COLORS else DEFAULT_COLOR
    return out


def _write(project, declared: dict[str, str]) -> None:
    body = "".join(f"{json.dumps(n, ensure_ascii=False)} = {json.dumps(c)}\n"
                   for n, c in declared.items())
    project._write_section(SECTION, body)


def _members(project) -> dict[str, list[Path]]:
    """{collection name: scenes (in project order)} read from the files."""
    out: dict[str, list[Path]] = {}
    for path in project.all_scene_files():
        try:
            names = scenemeta.details(path.read_text(encoding="utf-8"))["collections"]
        except OSError:
            continue
        for name in dict.fromkeys(names):
            out.setdefault(name, []).append(path)
    return out


def list_collections(project) -> list[Collection]:
    """Declared collections in definition order, then undeclared ones scenes use."""
    defs = declared(project)
    members = _members(project)
    out = [Collection(n, c, True, tuple(members.get(n, ()))) for n, c in defs.items()]
    out += [Collection(n, DEFAULT_COLOR, False, tuple(p)) for n, p in sorted(members.items())
            if n not in defs]
    return out


def find(project, name: str) -> Collection | None:
    key = " ".join(str(name or "").split()).casefold()
    return next((c for c in list_collections(project) if c.name.casefold() == key), None)


def create(project, name: str, color: str = "violet") -> str:
    """Define a collection. Returns its (cleaned) name."""
    name, color = clean_name(name), _color(color)
    defs = declared(project)
    if any(n.casefold() == name.casefold() for n in defs):
        raise ValueError(f"a collection named “{name}” already exists")
    defs[name] = color
    _write(project, defs)
    return name


def recolor(project, name: str, color: str) -> None:
    """Change a collection's colour (declares it if scenes already use it)."""
    found = find(project, name)
    if found is None:
        raise LookupError(f"no collection named “{name}”")
    defs = declared(project)
    defs[found.name] = _color(color)
    _write(project, defs)


def _rewrite_members(project, old: str, new: str | None) -> list[Path]:
    """Rename *old* to *new* (None = remove) in every scene's frontmatter.
    Returns the scenes whose files changed."""
    from .project import write_atomic

    changed = []
    for path in project.all_scene_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        names = scenemeta.details(text)["collections"]
        if old not in names:
            continue
        out: list[str] = []
        for n in names:
            n = new if n == old else n
            if n is not None and n not in out:
                out.append(n)
        write_atomic(path, scenemeta.set_details(text, collections=out))
        changed.append(path)
    return changed


def rename(project, old: str, new: str) -> list[Path]:
    """Rename a collection everywhere (definition and every member scene).
    Returns the scene files that changed."""
    found = find(project, old)
    if found is None:
        raise LookupError(f"no collection named “{old}”")
    new = clean_name(new)
    if new.casefold() != found.name.casefold() and find(project, new) is not None:
        raise ValueError(f"a collection named “{new}” already exists")
    defs = declared(project)
    defs = {(new if n == found.name else n): c for n, c in defs.items()}
    defs.setdefault(new, DEFAULT_COLOR)
    changed = _rewrite_members(project, found.name, new)
    _write(project, defs)
    return changed


def delete(project, name: str) -> list[Path]:
    """Remove a collection and its membership from every scene (the scenes
    themselves are untouched). Returns the scene files that changed."""
    found = find(project, name)
    if found is None:
        raise LookupError(f"no collection named “{name}”")
    changed = _rewrite_members(project, found.name, None)
    defs = declared(project)
    defs.pop(found.name, None)
    _write(project, defs)
    return changed


def toggle(project, scene: Path, name: str, member: bool | None = None) -> bool:
    """Put a scene in (or take it out of) a collection, writing its file.
    Returns whether it is a member now. *member* None flips."""
    from .project import write_atomic

    found = find(project, name)
    if found is None:
        raise LookupError(f"no collection named “{name}”")
    text = scene.read_text(encoding="utf-8")
    names = scenemeta.details(text)["collections"]
    now = found.name in names
    want = (not now) if member is None else bool(member)
    if want != now:
        names = [n for n in names if n != found.name] + ([found.name] if want else [])
        write_atomic(scene, scenemeta.set_details(text, collections=names))
    return want

