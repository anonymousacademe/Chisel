"""Inspiration images: pictures of a setting the author keeps on screen while writing.

    inspiration/20261001-175300-a-dark-subway-platform.jpg
    inspiration/20261001-175300-a-dark-subway-platform.md

The ``.md`` next to each picture is its sidecar: YAML frontmatter plus the
author's notes. Plain author data in the project folder (never in ``.lorewrite/``,
never git-ignored).

    ---
    prompt: A dark subway platform at night, flickering fluorescent lights
    model: google/gemini-3.1-flash-lite-image
    scene: manuscript/02-part-ii/03-the-tunnel.md     # optional
    created: '2026-10-01T17:53:00'
    cost: 0.0336
    pinned: true          # shown with that scene
    title: Platform 9     # optional display name
    ---
    Optional notes by the author.

Reference only: nothing here is ever inserted into the prose, counted, indexed,
spell-checked or sent to an AI. An image's *id* is its file stem; it crosses the
GUI bridge, so ``_sidecar`` is the only door to a path (it refuses anything that
is not a plain id). Deleting moves both files to the project Trash
(``Structure.trash_inspiration``); renaming or moving a scene rewrites the
``scene:`` links (``remap_scenes``). ``project`` arguments are duck-typed: ``root``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from . import desktop
from . import fsutil

INSPIRATION_DIR = "inspiration"
EXTENSIONS = ("jpg", "png", "webp")
MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
NOTES_MAX = 5000
PROMPT_MAX = 4000
TITLE_MAX = 120
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_BLOCK_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_ALIASES = {"jpeg": "jpg", "jpe": "jpg", "image/jpeg": "jpg", "image/jpg": "jpg",
            "image/png": "png", "image/webp": "webp"}


@dataclass(frozen=True)
class Image:
    id: str            # the file stem, e.g. "20261001-175300-a-dark-subway-platform"
    ext: str           # "jpg" | "png" | "webp"
    path: Path         # the picture
    meta_path: Path    # its sidecar
    prompt: str
    model: str
    scene: str         # project-relative scene path ("" = not tied to a scene)
    created: str       # ISO local time
    cost: float | None
    pinned: bool
    title: str         # the author's name for it ("" = show the prompt)
    notes: str

    @property
    def label(self) -> str:
        return self.title or " ".join(self.prompt.split())[:80] or self.id


# -- folders and ids --------------------------------------------------------------


def inspiration_dir(project) -> Path:
    return project.root / INSPIRATION_DIR


def normalize_ext(ext: str) -> str:
    """``.JPEG`` / ``image/jpeg`` -> ``jpg``; ValueError for anything not an image we keep."""
    ext = _ALIASES.get((ext or "").strip().lower().lstrip("."), (ext or "").strip().lower().lstrip("."))
    if ext not in EXTENSIONS:
        raise ValueError(f"unsupported image type: {ext or 'unknown'}")
    return ext


def sniff_ext(data: bytes) -> str | None:
    """The type a picture's own bytes claim (the data URL's mime type can lie)."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _check_id(image_id: str) -> str:
    if not isinstance(image_id, str) or not _ID_RE.match(image_id) or ".." in image_id:
        raise ValueError("invalid image id")
    return image_id


def _sidecar(project, image_id: str) -> Path:
    path = inspiration_dir(project) / f"{_check_id(image_id)}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no such inspiration image: {image_id}")
    return path


def _picture(project, image_id: str) -> Path:
    for ext in EXTENSIONS:
        path = inspiration_dir(project) / f"{_check_id(image_id)}.{ext}"
        if path.is_file():
            return path
    raise FileNotFoundError(f"the picture file is missing: {image_id}")


def _slug(prompt: str) -> str:
    words = re.findall(r"[^\W_]+", (prompt or "").casefold())[:6]
    return "-".join(words)[:40].strip("-") or "image"


# -- the sidecar ------------------------------------------------------------------


def _parse(text: str) -> tuple[dict, str]:
    m = _BLOCK_RE.match(text)
    if m is None:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}, text[m.end():]
    return (meta if isinstance(meta, dict) else {}), text[m.end():]


def _str(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return "" if value is None else str(value)


def _dump(meta: dict, notes: str) -> str:
    order = ("prompt", "model", "scene", "created", "cost", "pinned", "title")
    data = {k: meta[k] for k in order if meta.get(k) not in (None, "", False)}
    head = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=10_000,
                          default_flow_style=False)
    body = notes.strip()
    return f"---\n{head}---\n" + (f"{body}\n" if body else "")


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def _image(project, sidecar: Path) -> Image | None:
    try:
        meta, notes = _parse(sidecar.read_text(encoding="utf-8"))
        picture = _picture(project, sidecar.stem)
    except (OSError, FileNotFoundError, ValueError):
        return None
    try:
        cost = float(meta["cost"]) if meta.get("cost") is not None else None
    except (TypeError, ValueError):
        cost = None
    return Image(sidecar.stem, picture.suffix.lstrip("."), picture, sidecar,
                 _str(meta.get("prompt")), _str(meta.get("model")), _str(meta.get("scene")),
                 _str(meta.get("created")), cost, meta.get("pinned") is True,
                 _str(meta.get("title")), notes.strip())


def _meta_of(image: Image) -> dict:
    return {"prompt": image.prompt, "model": image.model, "scene": image.scene,
            "created": image.created, "cost": image.cost, "pinned": image.pinned,
            "title": image.title}


# -- operations -------------------------------------------------------------------


def save(project, image_bytes: bytes, ext: str, meta: dict) -> Image:
    """Store a picture and its sidecar. *meta*: ``prompt`` (required), ``model``,
    ``scene`` (project-relative path), ``cost``, ``pinned``, ``title``, ``notes``,
    ``created`` (default now). Returns the saved image."""
    if not image_bytes:
        raise ValueError("the image is empty")
    ext = normalize_ext(ext)
    prompt = " ".join(str(meta.get("prompt") or "").split())[:PROMPT_MAX]
    if not prompt:
        raise ValueError("an inspiration image needs its prompt")
    created = meta.get("created") or datetime.now().isoformat(timespec="seconds")
    try:
        stamp = datetime.fromisoformat(str(created)).strftime("%Y%m%d-%H%M%S")
    except ValueError:
        created = datetime.now().isoformat(timespec="seconds")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = inspiration_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    stem, n = f"{stamp}-{_slug(prompt)}", 1
    while any((folder / f"{stem}.{e}").exists() for e in (*EXTENSIONS, "md")):
        n += 1
        stem = f"{stamp}-{_slug(prompt)}-{n}"
    tmp = folder / f".{stem}.{ext}.tmp"
    tmp.write_bytes(image_bytes)
    fsutil.replace(tmp, folder / f"{stem}.{ext}")
    cost = meta.get("cost")
    record = {"prompt": prompt, "model": str(meta.get("model") or ""),
              "scene": str(meta.get("scene") or ""), "created": str(created),
              "cost": round(float(cost), 6) if cost is not None else None,
              "pinned": bool(meta.get("pinned")) and bool(meta.get("scene")),
              "title": " ".join(str(meta.get("title") or "").split())[:TITLE_MAX]}
    _write(folder / f"{stem}.md", _dump(record, str(meta.get("notes") or "")[:NOTES_MAX]))
    return get(project, stem)


def get(project, image_id: str) -> Image:
    image = _image(project, _sidecar(project, image_id))
    if image is None:
        raise FileNotFoundError(f"no such inspiration image: {image_id}")
    return image


def list_images(project, scene: str | None = None) -> list[Image]:
    """Newest first. *scene* (a project-relative path) keeps only that scene's
    images; None lists everything."""
    folder = inspiration_dir(project)
    if not folder.is_dir():
        return []
    out = []
    for sidecar in folder.glob("*.md"):
        if sidecar.name.startswith(".") or not _ID_RE.match(sidecar.stem):
            continue
        image = _image(project, sidecar)
        if image is not None and (scene is None or image.scene == scene):
            out.append(image)
    return sorted(out, key=lambda i: (i.created, i.id), reverse=True)


def pinned_for(project, scene: str) -> list[Image]:
    return [i for i in list_images(project, scene) if i.pinned]


_UNSET = object()


def update(project, image_id: str, *, pinned=_UNSET, scene=_UNSET, title=_UNSET,
           notes=_UNSET) -> Image:
    """Pin / unpin, move to another scene (``""`` detaches and unpins), rename
    (``title``) or edit the notes. Pinning needs a scene (pass *scene*, or the
    image must already have one)."""
    image = get(project, image_id)
    meta = _meta_of(image)
    body = image.notes
    if scene is not _UNSET:
        meta["scene"] = str(scene or "")
    if title is not _UNSET:
        meta["title"] = " ".join(str(title or "").split())[:TITLE_MAX]
    if notes is not _UNSET:
        body = str(notes or "")[:NOTES_MAX]
    if pinned is not _UNSET:
        meta["pinned"] = bool(pinned)
    if meta["pinned"] and not meta["scene"]:
        if pinned is not _UNSET and pinned:
            raise ValueError("pin an image to a scene - open a scene first")
        meta["pinned"] = False
    _write(image.meta_path, _dump(meta, body))
    return get(project, image_id)


def read_file(project, image_id: str) -> tuple[bytes, str]:
    """The picture's bytes and mime type (only ever from inside ``inspiration/``)."""
    picture = _picture(project, image_id)
    folder = inspiration_dir(project).resolve()
    if picture.resolve().parent != folder:       # a symlink pointing elsewhere
        raise ValueError("invalid image id")
    return picture.read_bytes(), MIME[picture.suffix.lstrip(".")]


def remap_scenes(project, mapping: dict[str, str]) -> int:
    """Follow a scene move: rewrite ``scene:`` in every sidecar that names an old
    path (all at once, so swaps do not collide). Returns how many changed."""
    changed = 0
    for image in list_images(project):
        new = mapping.get(image.scene)
        if image.scene and new and new != image.scene:
            meta = _meta_of(image)
            meta["scene"] = new
            _write(image.meta_path, _dump(meta, image.notes))
            changed += 1
    return changed


def remap_paths(project, pairs: dict[Path, Path]) -> int:
    """``remap_scenes`` for the {old path: new path} of ``Structure.last_renames``
    (part folders in it are ignored: they name no scene)."""
    root = project.root
    mapping = {}
    for old, new in pairs.items():
        try:
            if old.suffix == ".md" and new.suffix == ".md":
                mapping[old.relative_to(root).as_posix()] = new.relative_to(root).as_posix()
        except ValueError:
            continue
    return remap_scenes(project, mapping) if mapping else 0


def trashed_label(sidecar: Path) -> str:
    """What the Trash lists for a trashed image: its title, else its prompt."""
    try:
        meta, _ = _parse(sidecar.read_text(encoding="utf-8"))
    except OSError:
        meta = {}
    return " ".join((_str(meta.get("title")) or _str(meta.get("prompt")) or sidecar.stem).split())[:80]


def save_batch(project, pictures: list[tuple[bytes, str]], prompt: str, model: str,
               scene: str, pin: bool, cost: float | None) -> list[Image]:
    """Save every picture one generation call returned; the call's cost is split
    between them and only the first is pinned (to *scene*, when *pin*)."""
    each = None if cost is None else cost / max(1, len(pictures))
    return [save(project, data, ext, {"prompt": prompt, "model": model, "scene": scene,
                                      "cost": each, "pinned": pin and k == 0})
            for k, (data, ext) in enumerate(pictures)]


def open_path(path: Path) -> bool:
    """Hand *path* (a picture or the folder) to the desktop. Only ever called from
    an explicit choice; False when it cannot be done."""
    return desktop.open_path(path)
