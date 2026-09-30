"""Pure builders: Project -> the Workspace JSON the UI renders.

The shapes match gui/src/data/types.ts (keep them in sync; tests/test_gui_workspace.py
and gui/src/data/workspace.test.ts check one shared fixture on each side).
No pywebview, no AI, no I/O beyond reading project files.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core import drafts
from ..core import entities as ent
from ..core.continuity import get_canon
from ..core.links import find_all_links
from ..core.project import Project
from ..core.style import style_path

STYLE_ID = "style.md"
WORLD_TYPES = ("place", "object", "faction")


def fmt_words(n: int) -> str:
    """42700 -> '42.7k'; under a thousand stays exact."""
    if n < 1000:
        return str(n)
    value = n / 1000
    return f"{value:.1f}k" if value < 100 else f"{round(value)}k"


def rel_id(project: Project, path: Path) -> str:
    return path.relative_to(project.root).as_posix()


def read_text(project: Project, path: Path) -> tuple[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    originals = (drafts.load_originals(project.root, path)
                 if '<!--ai id="' in text else {})
    return text, originals


def scene_number(path: Path) -> str:
    m = re.match(r"(\d+)-", path.name)
    return m.group(1) if m else ""


def scene_kicker(path: Path) -> str:
    n = scene_number(path)
    return f"SCENE {n}" if n else "SCENE"


def split_title(text: str) -> tuple[str | None, str]:
    """(first '# ' heading, rest of the text after that heading line)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:].strip(), "\n".join(lines[i + 1:])
    return None, text


def excerpt(text: str, limit: int = 180) -> str:
    """First prose of a scene (no headings, no draft markers), for the corkboard."""
    _, body = split_title(drafts.strip_pending(text))
    prose = " ".join(ln.strip() for ln in body.splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#"))
    return prose if len(prose) <= limit else prose[:limit].rsplit(" ", 1)[0] + "…"


def headings(text: str) -> list[str]:
    """Markdown headings after the scene title, for the outline view."""
    _, body = split_title(text)
    return [re.sub(r"^#+\s*", "", ln).strip() for ln in body.splitlines()
            if re.match(r"#{1,6}\s+\S", ln)]


def mention_counts(text: str, entities: list[ent.Entity]) -> list[tuple[ent.Entity, int]]:
    """(entity, occurrences) for everything a scene links to or mentions,
    ordered by first appearance. Pending AI drafts don't count."""
    names = [n for e in entities for n in e.names]
    order: list[ent.Entity] = []
    counts: dict[str, int] = {}
    for link in find_all_links(drafts.blank_pending(text), names):
        entity = ent.resolve(link.target, entities)
        if entity is None:
            continue
        if entity.name not in counts:
            order.append(entity)
        counts[entity.name] = counts.get(entity.name, 0) + 1
    return [(e, counts[e.name]) for e in order]


def scene_context(text: str, entities: list[ent.Entity], index) -> list[dict]:
    """The "retrieved context" of a scene: entities it mentions, how often,
    and how many lines across the project link to each."""
    return [{
        "name": e.name, "type": e.type, "count": n,
        "backlinks": len(index.backlinks(e)) if index is not None else 0,
    } for e, n in mention_counts(text, entities)]


def summary_line(body: str, limit: int = 240) -> str:
    """First paragraph of a note body (hover cards)."""
    for block in re.split(r"\n\s*\n", body.strip()):
        block = " ".join(block.split())
        if block and not block.startswith("#"):
            return block if len(block) <= limit else block[:limit].rsplit(" ", 1)[0] + "…"
    return ""


def entity_payload(project: Project, entity: ent.Entity, index) -> dict:
    """An entity note for the Notes tab and hover cards, with backlinks."""
    backlinks = []
    for b in (index.backlinks(entity) if index is not None else []):
        path = project.root / b.source
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        title, _ = split_title(text)
        if path.parent == project.manuscript_dir:
            kind, label = "scene", title or path.stem
        else:
            kind, label = "entity", ent.Entity.from_markdown(text, path).name
        backlinks.append({"sourceId": b.source, "sourceKind": kind,
                          "sourceTitle": label, "row": b.row, "line": b.line.strip()})
    return {
        "id": rel_id(project, entity.path), "name": entity.name, "type": entity.type,
        "aliases": list(entity.aliases), "body": entity.body,
        "canon": get_canon(entity.body), "summary": summary_line(entity.body),
        "backlinks": backlinks,
    }


def scene_summaries(project: Project) -> list[dict]:
    out = []
    for path in project.list_scenes():
        try:
            text, originals = read_text(project, path)
        except OSError:
            continue
        title, _ = split_title(text)
        out.append({
            "id": rel_id(project, path),
            "number": scene_number(path),
            "title": title or path.stem,
            "words": drafts.count_words(text, originals),
            "excerpt": excerpt(text),
            "headings": headings(text),
        })
    return out


def entity_summaries(project: Project, entities: list[ent.Entity]) -> list[dict]:
    return [{
        "id": rel_id(project, e.path), "name": e.name, "type": e.type,
        "aliases": list(e.aliases), "words": len(e.body.split()),
    } for e in entities if e.path is not None]


def _placeholder(id: str, title: str, kind: str = "folder", **extra) -> dict:
    return {"id": f"ph:{id}", "title": title, "kind": kind, "placeholder": True,
            "muted": True, **extra}


def build_binder(project: Project, scenes: list[dict], entities: list[dict],
                 has_style: bool) -> list[dict]:
    total = sum(s["words"] for s in scenes)
    manuscript = {
        "id": "group:manuscript", "title": "Manuscript", "kind": "folder",
        "meta": fmt_words(total), "expanded": True,
        "children": [{
            "id": s["id"],
            "title": f"{s['number']}  {s['title']}" if s["number"] else s["title"],
            "kind": "document", "meta": fmt_words(s["words"]),
        } for s in scenes],
    }
    characters = [e for e in entities if e["type"] == "character"]
    world = [e for e in entities if e["type"] in WORLD_TYPES]
    binder = [{
        "id": "project", "title": project.title, "kind": "project",
        "meta": fmt_words(total), "expanded": True,
        "children": [
            _placeholder("front", "Front Matter"),
            manuscript,
            _placeholder("part1", "Part I"),
            _placeholder("part2", "Part II"),
            _placeholder("part3", "Part III"),
        ],
    }, {
        "id": "group:characters", "title": "Characters", "kind": "characters",
        "children": [{"id": e["id"], "title": e["name"], "kind": "entity"}
                     for e in characters],
    }, {
        "id": "group:world", "title": "World Bible", "kind": "world",
        "children": [{"id": e["id"], "title": e["name"], "kind": "entity",
                      "meta": e["type"]} for e in world],
    }]
    if has_style:
        binder.append({"id": STYLE_ID, "title": "Style Guide", "kind": "style"})
    binder += [
        _placeholder("research", "Research", "research"),
        _placeholder("unplaced", "Unplaced Scenes", "inbox"),
        _placeholder("trash", "Trash", "trash"),
    ]
    return binder


def initials(name: str, fallback: str = "LW") -> str:
    parts = re.findall(r"[^\W\d_]+", name or "")
    if not parts:
        return fallback
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def build_workspace(project: Project, entities: list[ent.Entity], *,
                    baseline_words: int, session_minutes: int,
                    ai_cost: float) -> dict:
    scenes = scene_summaries(project)
    summaries = entity_summaries(project, entities)
    has_style = style_path(project).is_file()
    project_words = sum(s["words"] for s in scenes)
    author = str(project.meta.get("author") or "")
    return {
        "project": {
            "title": project.title, "author": author,
            "initials": initials(author), "path": str(project.root),
            "documentCount": len(scenes) + len(summaries) + (1 if has_style else 0),
        },
        "binder": build_binder(project, scenes, summaries, has_style),
        "scenes": scenes,
        "entities": summaries,
        "status": {
            "projectWords": project_words,
            "sessionWords": project_words - baseline_words,
            "sessionMinutes": session_minutes,
            "aiCost": ai_cost,
            "hasStyle": has_style,
        },
    }
