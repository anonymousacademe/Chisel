"""Attachments: material the author adds to an assistant chat's context.

A paperclip pick is a ``{"kind", "id"}``: a scene, an entity note, a research
note, or a scene's open *comments* (comments are author notes and reach the AI
only this way). ``id`` is the project-relative path of the file. Everything is
resolved and size-capped here so the UIs (and any front end) share one rule:
each item at most ``ITEM_CHARS`` characters, all together at most
``TOTAL_CHARS``; what does not fit is reported, never silently sent.
Pending AI drafts and a scene's details block are not prose and are removed.
"""

from __future__ import annotations

from pathlib import Path

from . import comments, drafts, scenemeta
from . import entities as ent
from . import research as research_notes

KINDS = ("scene", "note", "research", "comments")
LABEL = {"scene": "SCENE", "note": "NOTE", "research": "RESEARCH NOTE", "comments": "COMMENTS ON SCENE"}
ITEM_CHARS = 8000
TOTAL_CHARS = 24000
MAX_ITEMS = 12
MIN_ROOM = 200   # less room than this and an item is skipped rather than sent as a stub


def _path(project, ident: str) -> Path:
    path = (project.root / ident).resolve()
    if not path.is_relative_to(project.root.resolve()) or path.suffix != ".md":
        raise ValueError("invalid attachment")
    return path


def resolve(project, kind: str, ident: str) -> tuple[str, str]:
    """(title, text) of an attachment. ValueError / FileNotFoundError when it
    names nothing attachable."""
    if kind not in KINDS:
        raise ValueError(f"cannot attach a {kind}")
    path = _path(project, ident)
    if not path.is_file():
        raise FileNotFoundError(f"{ident} no longer exists")
    raw = path.read_text(encoding="utf-8")
    if kind in ("scene", "comments"):
        if not project.is_scene_path(path):
            raise ValueError("not a scene")
        title = project.scene_title(path)
        if kind == "comments":
            open_ = [c for c in comments.load(project.root, path) if not c.resolved]
            if not open_:
                raise ValueError(f"“{title}” has no open comments")
            lines = "\n".join(f"- On “{' '.join(c.quote.split())}”: {c.body}" for c in open_)
            return title, lines.replace("<!--", "<!-")   # an echoed marker must never reach a scene
        originals = drafts.load_originals(project.root, path) if '<!--ai id="' in raw else {}
        return title, scenemeta.strip(drafts.strip_pending(raw, originals)).strip()
    if kind == "note":
        if path.parent.parent != project.entities_dir.resolve():
            raise ValueError("not a note")
        entity = ent.load_entity(path)
        return entity.name, f"({entity.type})\n{entity.body.strip()}"
    if not research_notes.is_research_path(project, path):
        raise ValueError("not a research note")
    return research_notes.title_of(path, raw), raw.strip()


def build(project, items: list[dict]) -> tuple[str, list[dict]]:
    """The context text for *items* and a report ``[{kind, id, title, chars,
    truncated, skipped}]`` the UI can show. Items that cannot be resolved are
    reported as skipped with a ``reason``."""
    sections: list[str] = []
    report: list[dict] = []
    used = 0
    seen: set[tuple[str, str]] = set()
    for item in items[:MAX_ITEMS]:
        kind, ident = str(item.get("kind")), str(item.get("id"))
        if (kind, ident) in seen:
            continue
        seen.add((kind, ident))
        row = {"kind": kind, "id": ident, "title": ident, "chars": 0, "truncated": False, "skipped": False}
        try:
            title, text = resolve(project, kind, ident)
        except (ValueError, FileNotFoundError, OSError) as exc:
            report.append({**row, "skipped": True, "reason": str(exc)})
            continue
        row["title"] = title
        if not text:
            report.append({**row, "skipped": True, "reason": "it is empty"})
            continue
        room = TOTAL_CHARS - used
        if room < MIN_ROOM:
            report.append({**row, "skipped": True, "reason": "too much is attached already"})
            continue
        limit = min(ITEM_CHARS, room)
        if len(text) > limit:
            text, row["truncated"] = (text[:limit - 2].rsplit(" ", 1)[0] + " …")[:limit], True
        used += len(text)
        row["chars"] = len(text)
        sections.append(f"ATTACHED {LABEL[kind]}: {title}\n{text}")
        report.append(row)
    return "\n\n".join(sections), report


def attachable(project, entities: list[ent.Entity]) -> list[dict]:
    """Everything that can be attached, with an approximate size in words:
    scenes (book and Unplaced), entity notes, research notes, and the scenes
    that have open comments."""
    out: list[dict] = []
    for path in project.all_scene_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = path.relative_to(project.root).as_posix()
        title = project.scene_title(path)
        out.append({"kind": "scene", "id": rel, "title": title,
                    "words": len(scenemeta.strip(drafts.strip_pending(text)).split())})
        open_ = [c for c in comments.load(project.root, path) if not c.resolved]
        if open_:
            out.append({"kind": "comments", "id": rel, "title": title,
                        "words": sum(len(c.quote.split()) + len(c.body.split()) for c in open_),
                        "count": len(open_)})
    for e in entities:
        if e.path is not None:
            out.append({"kind": "note", "id": e.path.relative_to(project.root).as_posix(),
                        "title": e.name, "words": len(e.body.split()), "detail": e.type})
    for n in research_notes.list_notes(project):
        out.append({"kind": "research", "id": f"{research_notes.RESEARCH_DIR}/{n.rel}",
                    "title": n.title, "words": n.words})
    return out
