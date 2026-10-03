"""Pending AI text: the marking mechanism for every generated span (SPEC §7 M4).

AI-written text is stored *in the scene file* between HTML comments, so it
survives saves, reopening and external editors (Obsidian hides HTML comments):

    <!--ai-->generated text<!--/ai-->
    <!--ai id="k3f9q2"-->generated text<!--/ai-->

The second form is a draft that *replaced* something (a selection, or an
``{{expand: …}}`` marker). The id is 6 lowercase base36 characters, unique in
the project; the replaced original lives in a sidecar,
``<project>/.drafts/<scene-filename>.json`` ({"k3f9q2": "original text"}).
The sidecar is author data (not cache, never under ``.chisel/``).

Accept keeps the body as normal text; reject restores the original. If an
original is missing from the sidecar, reject refuses (MissingOriginal) —
prose is never deleted on a failed lookup. Nested or malformed markers are
ignored (plain text), never an error. Pure Python, no Textual.
"""

from __future__ import annotations

import json
import re
import secrets
import string
from dataclasses import dataclass
from pathlib import Path

from . import scenemeta
from . import fsutil

DRAFTS_DIR = ".drafts"
_ID_ALPHABET = string.ascii_lowercase + string.digits

# Body may not contain another opening tag or a closing tag: an unclosed or
# nested draft never matches, so it is treated as plain text.
_PENDING_RE = re.compile(
    r'<!--ai(?: id="([a-z0-9]{6})")?-->'
    r"((?:(?!<!--ai)(?!<!--/ai-->).)*)"
    r"<!--/ai-->",
    re.DOTALL,
)
_EXPAND_RE = re.compile(r"\{\{expand:\s*([^{}]*?)\s*\}\}")


class MissingOriginal(Exception):
    """A draft's replaced text is not in the sidecar; reject must refuse."""

    def __init__(self, draft_id: str) -> None:
        super().__init__(f"original text for draft {draft_id} is missing")
        self.draft_id = draft_id


@dataclass(frozen=True)
class Pending:
    start: int  # offset of the opening tag
    end: int  # offset one past the closing tag
    body_start: int
    body_end: int
    id: str | None  # None for pure insertions


@dataclass(frozen=True)
class ExpandMarker:
    start: int
    end: int
    instruction: str


# -- sidecar ----------------------------------------------------------------


def sidecar_key(project_root: Path, scene_path: Path) -> str:
    """The scene's project-relative path with ``/`` written as ``__``
    (``manuscript__02-ghost__01-a.md``): scenes in different parts may share
    a filename, so the name alone cannot key a sidecar."""
    try:
        rel = scene_path.relative_to(project_root)
    except ValueError:
        try:
            rel = scene_path.resolve().relative_to(project_root.resolve())
        except (OSError, ValueError):
            rel = Path(scene_path.name)
    return rel.as_posix().replace("/", "__")


def sidecar_path(project_root: Path, scene_path: Path) -> Path:
    return project_root / DRAFTS_DIR / f"{sidecar_key(project_root, scene_path)}.json"


def migrate_sidecars(project_root: Path) -> int:
    """Rename pre-parts sidecars (``.drafts/<scene-filename>.json``) to the
    path-keyed form. Only files whose scene sits directly in ``manuscript/``
    are touched; returns how many were renamed."""
    folder = project_root / DRAFTS_DIR
    if not folder.is_dir():
        return 0
    moved = 0
    for path in sorted(folder.glob("*.json")):
        name = path.name[:-len(".json")]
        if name.startswith(("manuscript__", ".")) or "__" in name:
            continue
        if not (project_root / "manuscript" / name).is_file():
            continue
        target = folder / f"manuscript__{name}.json"
        if target.exists():
            continue
        fsutil.replace(path, target)
        moved += 1
    return moved


def load_originals(project_root: Path, scene_path: Path) -> dict[str, str]:
    try:
        data = json.loads(sidecar_path(project_root, scene_path)
                          .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str)}


def save_originals(project_root: Path, scene_path: Path,
                   originals: dict[str, str]) -> None:
    """Write the sidecar atomically; delete the file when there is nothing."""
    path = sidecar_path(project_root, scene_path)
    if not originals:
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()  # tidy: only succeeds when nothing else is in it
        except OSError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(originals, indent=2, ensure_ascii=False),
                   encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def add_original(project_root: Path, scene_path: Path, draft_id: str,
                 original: str) -> None:
    originals = load_originals(project_root, scene_path)
    originals[draft_id] = original
    save_originals(project_root, scene_path, originals)


def drop_original(project_root: Path, scene_path: Path, draft_id: str) -> None:
    originals = load_originals(project_root, scene_path)
    if originals.pop(draft_id, None) is not None:
        save_originals(project_root, scene_path, originals)


def move_sidecar(project_root: Path, old_scene: Path, new_scene: Path) -> None:
    """Carry a scene's sidecar along with a rename."""
    old = sidecar_path(project_root, old_scene)
    if old.is_file():
        new = sidecar_path(project_root, new_scene)
        new.parent.mkdir(parents=True, exist_ok=True)
        fsutil.replace(old, new)


def delete_sidecar(project_root: Path, scene_path: Path) -> None:
    path = sidecar_path(project_root, scene_path)
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def all_ids(project_root: Path) -> set[str]:
    """Every draft id recorded in any sidecar of the project."""
    ids: set[str] = set()
    for path in (project_root / DRAFTS_DIR).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            ids.update(k for k in data if isinstance(k, str))
    return ids


def new_id(taken: set[str]) -> str:
    """A fresh 6-char lowercase base36 id not in *taken*."""
    while True:
        candidate = "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
        if candidate not in taken:
            return candidate


def wrap(body: str, draft_id: str | None = None) -> str:
    """The marked-up form of a generated *body*; pass *draft_id* when the
    draft replaces something (store the original with add_original)."""
    body = body.replace("<!--", "<!-")  # a body can never forge/close a marker
    if draft_id is None:
        return f"<!--ai-->{body}<!--/ai-->"
    return f'<!--ai id="{draft_id}"-->{body}<!--/ai-->'


def fresh_id(project_root: Path, text: str) -> str:
    """A draft id unused anywhere in the project's sidecars or in *text*."""
    return new_id(all_ids(project_root)
                  | {p.id for p in find_pending(text) if p.id})


def prepare_draft(text: str, mode: str, body: str, start: int, end: int,
                  draft_id: str | None = None) -> tuple[str, int, int]:
    """How to put generated *body* into *text* as a pending draft:
    ``(insert, from, to)`` — replace ``text[from:to]`` with *insert*.

    ``draft`` inserts at *start* (a space is added when it would glue onto the
    previous word); ``rewrite``/``expand`` replace ``[start, end)`` and need a
    *draft_id* whose original the caller has stored with add_original()
    **before** the marker is written.
    """
    if mode == "draft":
        if start > 0 and not text[start - 1].isspace() and body \
                and not body[0].isspace():
            body = " " + body
        return wrap(body), start, start
    if draft_id is None:
        raise ValueError("rewrite/expand drafts need a draft id")
    return wrap(body, draft_id), start, end


def find_pending(text: str) -> list[Pending]:
    """Every well-formed pending draft in *text*, in document order."""
    return [Pending(m.start(), m.end(), m.start(2), m.end(2), m.group(1))
            for m in _PENDING_RE.finditer(text)]


def pending_at(text: str, offset: int) -> Pending | None:
    """The pending draft containing *offset* (edges count), if any."""
    for p in find_pending(text):
        if p.start <= offset <= p.end:
            return p
    return None


def accept(text: str, pending: Pending) -> str:
    """Remove the markers, keep the body as normal text."""
    return text[:pending.start] + text[pending.body_start:pending.body_end] \
        + text[pending.end:]


def reject(text: str, pending: Pending,
           originals: dict[str, str] | None = None) -> str:
    """Restore the original text (or remove a pure insertion).

    Raises MissingOriginal if the draft replaced something and *originals*
    doesn't have it — nothing is changed."""
    original = ""
    if pending.id is not None:
        if pending.id not in (originals or {}):
            raise MissingOriginal(pending.id)
        original = originals[pending.id]
    return text[:pending.start] + original + text[pending.end:]


def accept_all(text: str) -> str:
    for p in reversed(find_pending(text)):
        text = accept(text, p)
    return text


def reject_all(text: str, originals: dict[str, str] | None = None) -> str:
    """Reject every draft. Lenient: a missing original becomes "" — use this
    for read-only views (AI context, counts), never to rewrite the file."""
    for p in reversed(find_pending(text)):
        original = (originals or {}).get(p.id, "") if p.id else ""
        text = text[:p.start] + original + text[p.end:]
    return text


def strip_pending(text: str, originals: dict[str, str] | None = None) -> str:
    """The text as if every pending draft were rejected: unaccepted AI text
    is not canon and not the author's prose."""
    return reject_all(text, originals)


def count_words(text: str, originals: dict[str, str] | None = None) -> int:
    """Words in *text*, not counting pending AI drafts (unaccepted AI text)
    or the scene's YAML frontmatter (details are not prose)."""
    return len(scenemeta.strip(strip_pending(text, originals)).split())


def blank_pending(text: str) -> str:
    """Replace every pending draft (markers and body) with same-length
    whitespace, keeping newlines: unaccepted AI text disappears from any scan
    while offsets, rows and columns of everything else stay valid."""
    chars = list(text)
    for p in find_pending(text):
        for i in range(p.start, p.end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def find_expand_markers(text: str) -> list[ExpandMarker]:
    """``{{expand: instruction}}`` markers, in document order."""
    return [ExpandMarker(m.start(), m.end(), m.group(1))
            for m in _EXPAND_RE.finditer(text)]


def expand_marker_at(text: str, offset: int) -> ExpandMarker | None:
    for marker in find_expand_markers(text):
        if marker.start <= offset <= marker.end:
            return marker
    return None
