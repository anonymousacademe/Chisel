"""The outline of a research project: what it is now, and how it differs from the standard structure.

Read-only. ``current_outline`` lists the book's sections in reading order (Parked sections are not part of
the outline); ``standard_diff`` compares it with the journal profile's outline (else the generic manuscript or
proposal profile) and proposes one "add" item for each standard section whose title is missing. The profile
parsing and the starter outline stay in ``core/paper/journals.py`` / ``Project.create``: this module only reads
them. No AI and no writing here (applying items is ``gui/research_outline_api.py``).
"""

from __future__ import annotations

from .. import drafts, fsutil, scenemeta
from . import journals


def section_id(project, path) -> str:
    return path.relative_to(project.root).as_posix()


def part_id(project, part) -> str:
    return "part:" + part.relative_to(project.root).as_posix()


def _text_and_words(project, path) -> tuple[str, int]:
    try:
        text = fsutil.read_text_lenient(path)
    except OSError:
        return "", 0
    originals = drafts.load_originals(project.root, path) if '<!--ai id="' in text else {}
    return text, project.count_words(text, originals)


def current_outline(project) -> dict:
    """{kind, journal, journalName, sections:[{id, title, part, partTitle, frontMatter, position, words,
    purpose}]} in reading order. ``part`` is the part's id ("part:manuscript/01-x"), "" for a section at the
    top level; ``position`` counts from 1 inside its part."""
    profile = project.research_profile()
    sections: list[dict] = []
    seen_in_part: dict[str, int] = {}
    for path in project.list_scenes():
        text, words = _text_and_words(project, path)
        part = project.part_of(path)
        pid = part_id(project, part) if part is not None else ""
        seen_in_part[pid] = seen_in_part.get(pid, 0) + 1
        sections.append({
            "id": section_id(project, path),
            "title": project.scene_title(path),
            "part": pid,
            "partTitle": project.part_title(part) if part is not None else "",
            "frontMatter": bool(part is not None and project.part_is_front_matter(part)),
            "position": seen_in_part[pid],
            "words": words,
            "purpose": scenemeta.details(text).get("purpose", ""),
        })
    return {"kind": project.research_kind, "journal": profile.id if profile else "",
            "journalName": profile.name if profile else "", "sections": sections}


def standard_profile(project):
    """The profile whose outline is "the standard structure": the journal's, else the generic one of the kind."""
    return journals.starter_profile(project.research_kind, project.journal)


def standard_parts(profile) -> list[tuple[str, tuple]]:
    """[(part title as the project names it, sections)] of a profile (front matter is "Front matter")."""
    if profile is None:
        return []
    return [("Front matter" if p.front_matter else p.part, p.sections) for p in profile.outline]


def standard_diff(project) -> dict:
    """{name, items}: one "add" item for each standard section whose title (case-insensitive) is missing from
    the current outline, none for the ones present. Offline: no AI."""
    profile = standard_profile(project)
    if profile is None:
        return {"name": "", "items": []}
    outline = current_outline(project)
    have = {s["title"].casefold() for s in outline["sections"]}
    items: list[dict] = []
    for part_title, sections in standard_parts(profile):
        previous = ""           # id of the last standard section of this part that the project has
        for sec in sections:
            present = next((s for s in outline["sections"]
                            if s["title"].casefold() == sec.title.casefold()), None)
            if present is not None:
                if present["partTitle"].casefold() == part_title.casefold():
                    previous = present["id"]
                continue
            if sec.title.casefold() in have:
                continue
            items.append({
                "id": f"std{len(items) + 1}", "action": "add", "title": sec.title, "section": "",
                "newTitle": "", "part": part_title, "after": previous, "purpose": sec.purpose,
                "why": f"The {profile.name} outline has a section called {sec.title}; yours does not.",
            })
            have.add(sec.title.casefold())
    return {"name": profile.name, "items": items}
