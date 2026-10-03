"""Pure builders: Project -> the Workspace JSON the UI renders.

The shapes match gui/src/data/types.ts (keep them in sync; tests/test_gui_workspace.py
and gui/src/data/workspace.test.ts check one shared fixture on each side).
No pywebview, no AI, no I/O beyond reading project files.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core import collections as coll
from ..core import research as research_notes
from ..core import drafts, fsutil, scenemeta
from ..core import entities as ent
from ..core.continuity import get_canon
from ..core.links import find_all_links
from ..core.project import Project
from ..core.style import style_path

STYLE_ID = "style.md"
DICTIONARY_ID = "dictionary.txt"
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
    text = fsutil.read_text_lenient(path)
    originals = (drafts.load_originals(project.root, path)
                 if '<!--ai id="' in text else {})
    return text, originals


def unit_word(project: Project) -> str:
    return project.unit.upper()


def scene_kicker(project: Project, path: Path) -> str:
    """"SCENE 03" / "CHAPTER 03" (numbered globally across parts); front
    matter and unplaced scenes have no number."""
    n = project.scene_number(path)
    if project.is_front_matter(path):
        return "FRONT MATTER"
    if project.is_unplaced(path):
        return "PARKED"
    return f"{unit_word(project)} {n}" if n else unit_word(project)


def part_id(project: Project, part: Path) -> str:
    return "part:" + rel_id(project, part)


def part_for_id(project: Project, ident: str | None) -> Path | None:
    """The part folder behind a "part:manuscript/01-x" id; None for no part.
    ValueError when it names no part of this project."""
    if not ident:
        return None
    rel = ident[len("part:"):] if ident.startswith("part:") else ident
    path = project.root / rel
    if path not in project.list_parts():
        raise ValueError("no such part")
    return path


def split_title(text: str) -> tuple[str | None, str]:
    """(first '# ' heading, rest of the text after that heading line).
    A scene's frontmatter block is skipped."""
    text = scenemeta.strip(text)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:].strip(), "\n".join(lines[i + 1:])
    return None, text


def excerpt(text: str, limit: int = 180) -> str:
    """First prose of a scene (no headings, no draft markers), for the corkboard."""
    _, body = split_title(scenemeta.strip(drafts.strip_pending(text)))
    prose = " ".join(ln.strip() for ln in body.splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#"))
    return prose if len(prose) <= limit else prose[:limit].rsplit(" ", 1)[0] + "…"


def headings(text: str) -> list[str]:
    """Markdown headings after the scene title, for the outline view."""
    _, body = split_title(scenemeta.strip(text))
    return [re.sub(r"^#+\s*", "", ln).strip() for ln in body.splitlines()
            if re.match(r"#{1,6}\s+\S", ln)]


def mention_counts(text: str, entities: list[ent.Entity]) -> list[tuple[ent.Entity, int]]:
    """(entity, occurrences) for everything a scene links to or mentions,
    ordered by first appearance. Pending AI drafts don't count, nor does the
    details block (except a POV / place that names an entity)."""
    names = [n for e in entities for n in e.names]
    order: list[ent.Entity] = []
    counts: dict[str, int] = {}
    scan = scenemeta.blank(drafts.blank_pending(text), keep=scenemeta.MENTION_FIELDS)
    for link in find_all_links(scan, names):
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
            text = fsutil.read_text_lenient(path)
        except OSError:
            continue
        title, _ = split_title(text)
        if project.is_scene_path(path):
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
    """Every scene in reading order (book scenes, then unplaced ones)."""
    out = []
    for path in project.all_scene_files():
        try:
            text, originals = read_text(project, path)
        except OSError:
            continue
        title, _ = split_title(text)
        part = project.part_of(path)
        out.append({
            "id": rel_id(project, path),
            "number": project.scene_number(path),
            "title": title or path.stem,
            "words": drafts.count_words(text, originals),
            "excerpt": excerpt(text),
            "headings": headings(text),
            "part": part_id(project, part) if part else None,
            "frontMatter": project.is_front_matter(path),
            "unplaced": project.is_unplaced(path),
            "details": scenemeta.details(text),
        })
    return out


def book_words(scenes: list[dict]) -> int:
    """Words of the book: front matter and unplaced scenes do not count."""
    return sum(s["words"] for s in scenes if not s["frontMatter"] and not s["unplaced"])


def entity_summaries(project: Project, entities: list[ent.Entity]) -> list[dict]:
    return [{
        "id": rel_id(project, e.path), "name": e.name, "type": e.type,
        "aliases": list(e.aliases), "words": len(e.body.split()),
    } for e in entities if e.path is not None]


def part_summaries(project: Project, scenes: list[dict]) -> list[dict]:
    """Parts in book order with their scene ids (pickers and drag-to-reorder)."""
    out = []
    for part in project.list_parts():
        pid = part_id(project, part)
        mine = [s for s in scenes if s["part"] == pid]
        out.append({
            "id": pid, "title": project.part_title(part),
            "frontMatter": project.part_is_front_matter(part),
            "words": sum(s["words"] for s in mine),
            "sceneIds": [s["id"] for s in mine],
        })
    return out


def collection_summaries(project: Project, scenes: list[dict]) -> list[dict]:
    """Collections (declared first) with the scenes in each, from the scene
    summaries already read (no second pass over the files)."""
    members: dict[str, list[str]] = {}
    for s in scenes:
        for name in s["details"]["collections"]:
            members.setdefault(name, []).append(s["id"])
    declared = coll.declared(project)
    rows = [(n, c, True) for n, c in declared.items()]
    rows += [(n, coll.DEFAULT_COLOR, False) for n in sorted(members) if n not in declared]
    return [{"name": n, "color": c, "declared": d, "count": len(members.get(n, [])),
             "sceneIds": members.get(n, [])} for n, c, d in rows]


def research_summaries(project: Project) -> list[dict]:
    return [{"id": rel_id(project, n.path), "title": n.title, "words": n.words,
             "folder": n.rel.rsplit("/", 1)[0] if "/" in n.rel else ""}
            for n in research_notes.list_notes(project)]


def research_node(research: list[dict]) -> dict:
    """The binder's Notebook group: notes, with their subfolders as folders."""
    root: dict = {"id": "group:research", "title": "Notebook", "kind": "research",
                  "meta": str(len(research)) if research else None, "children": []}
    folders: dict[str, dict] = {}
    for r in research:
        parent = root
        path = ""
        for part in [p for p in r["folder"].split("/") if p]:
            path = f"{path}/{part}" if path else part
            if path not in folders:
                node = {"id": f"group:research/{path}", "title": part, "kind": "folder", "children": []}
                folders[path] = node
                parent["children"].append(node)
            parent = folders[path]
        parent["children"].append({"id": r["id"], "title": r["title"], "kind": "document",
                                   "meta": fmt_words(r["words"])})
    return root


def _scene_node(s: dict, project: Project) -> dict:
    node = {
        "id": s["id"],
        "title": f"{s['number']}  {s['title']}" if s["number"] else s["title"],
        "kind": "document", "meta": fmt_words(s["words"]),
    }
    if s["frontMatter"]:
        node["muted"] = True
    return node


PARKED_TITLE = "Parked scenes"
PARKED_HELP = "Written but not part of the book. Not counted in word totals or export. Still searchable."


def build_binder(project: Project, scenes: list[dict], entities: list[dict],
                 has_style: bool, parts: list[dict] | None = None,
                 trash_count: int = 0, research: list[dict] | None = None) -> list[dict]:
    parts = parts if parts is not None else part_summaries(project, scenes)
    placed = [s for s in scenes if not s["unplaced"]]
    unplaced = [s for s in scenes if s["unplaced"]]
    loose = [s for s in placed if s["part"] is None]
    by_id = {s["id"]: s for s in scenes}
    total = book_words(scenes)

    children: list[dict] = []
    for p in parts:
        if p["frontMatter"]:  # first, muted, as designed; not in the word total
            children.append({
                "id": p["id"], "title": p["title"], "kind": "part", "muted": True,
                "meta": fmt_words(p["words"]) if p["words"] else None,
                "children": [_scene_node(by_id[i], project) for i in p["sceneIds"]],
            })
    if loose or not any(not p["frontMatter"] for p in parts):
        children.append({
            "id": "group:manuscript", "title": "Manuscript", "kind": "folder",
            "meta": fmt_words(sum(s["words"] for s in loose)), "expanded": True,
            "children": [_scene_node(s, project) for s in loose],
        })
    for p in parts:
        if not p["frontMatter"]:
            children.append({
                "id": p["id"], "title": p["title"], "kind": "part",
                "meta": fmt_words(p["words"]), "expanded": True,
                "children": [_scene_node(by_id[i], project) for i in p["sceneIds"]],
            })
    characters = [e for e in entities if e["type"] == "character"]
    world = [e for e in entities if e["type"] in WORLD_TYPES]
    binder = [{
        "id": "project", "title": project.title, "kind": "project",
        "meta": fmt_words(total), "expanded": True, "children": children,
    }, {
        "id": "group:characters", "title": "Characters", "kind": "characters",
        "children": [{"id": e["id"], "title": e["name"], "kind": "entity"}
                     for e in characters],
    }, {
        "id": "group:world", "title": "World Bible", "kind": "world",
        "children": [{"id": e["id"], "title": e["name"], "kind": "entity",
                      "meta": e["type"]} for e in world],
    }]
    # always listed: opening it before it exists creates the stub (Api.ensure_style)
    binder.append({"id": STYLE_ID, "title": "Style Guide", "kind": "style",
                   **({} if has_style else {"meta": "new"})})
    # always listed: opening it creates it with a comment header (Api.open_dictionary)
    binder.append({"id": DICTIONARY_ID, "title": "Dictionary", "kind": "dictionary"})
    binder.append(research_node(research or []))
    if unplaced:   # Parked scenes (folder manuscript/_unplaced/): listed only while it holds scenes
        binder.append({"id": "group:unplaced", "title": PARKED_TITLE, "kind": "inbox",
                       "description": PARKED_HELP, "meta": str(len(unplaced)),
                       "children": [_scene_node(s, project) for s in unplaced]})
    binder += [
        {"id": "group:trash", "title": "Trash", "kind": "trash",
         "meta": str(trash_count) if trash_count else None, "muted": not trash_count},
    ]
    return [_drop_none(n) for n in binder]


def _drop_none(node: dict) -> dict:
    """Optional keys are absent, not null (the TS types say `meta?: string`)."""
    out = {k: v for k, v in node.items() if v is not None}
    if "children" in out:
        out["children"] = [_drop_none(c) for c in out["children"]]
    return out


def initials(name: str, fallback: str = "LW") -> str:
    parts = re.findall(r"[^\W\d_]+", name or "")
    if not parts:
        return fallback
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def build_workspace(project: Project, entities: list[ent.Entity], *,
                    baseline_words: int, session_minutes: int,
                    ai_cost: float, stats: dict | None = None) -> dict:
    scenes = scene_summaries(project)
    summaries = entity_summaries(project, entities)
    parts = part_summaries(project, scenes)
    has_style = style_path(project).is_file()
    project_words = book_words(scenes)
    trash_count = len(project.list_trash())
    research = research_summaries(project)
    info = project.author_info()
    # Show pen_name if set, otherwise author
    display_name = info["pen_name"] or info["author"]
    return {
        "project": {
            "title": project.title, "author": display_name,
            "initials": initials(display_name), "path": str(project.root),
            "documentCount": len(scenes) + len(summaries) + (1 if has_style else 0),
            "unit": project.unit,
            "draft": project.draft,
        },
        "binder": build_binder(project, scenes, summaries, has_style, parts, trash_count, research),
        "scenes": scenes,
        "parts": parts,
        "collections": collection_summaries(project, scenes),
        "research": research,
        "entities": summaries,
        "status": {
            "projectWords": project_words,
            "sessionWords": project_words - baseline_words,
            "sessionMinutes": session_minutes,
            "aiCost": ai_cost,
            "hasStyle": has_style,
            "trashCount": trash_count,
            "stats": stats,
        },
    }
