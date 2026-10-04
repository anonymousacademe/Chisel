"""Manuscript structure (core/structure.py): scenes, parts, Parked scenes, Trash, scene details."""

from __future__ import annotations

from pathlib import Path
from . import workspace as ws
from ..core import fsutil, scenemeta
from ..core.project import write_atomic
from ..core.spans import index_to_utf16
from ._bridge import bridge


class StructureMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    def _scene_path(self, doc_id: str) -> Path:
        path, kind = self.resolve_document(doc_id)
        if kind != "scene":
            raise ValueError("not a scene")
        return path

    def _rel_map(self) -> dict[str, str]:
        """{old id: new id} of what the last renaming operation moved, so a UI
        can follow the file it has open (renumbering renames neighbours too)."""
        project = self._require()
        out = {}
        for old, new in project.last_renames.items():
            try:
                out[ws.rel_id(project, old)] = ws.rel_id(project, new)
            except ValueError:
                continue
        return out

    @bridge
    def new_scene(self, title: str, part_id: str | None = None,
                  near_id: str | None = None) -> dict:
        """Create a scene at the end of *part_id* (a "part:..." id); without
        one, in the part of *near_id* (the open scene), else the last part."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("a scene needs a title")
        with self._lock:
            project = self._require()
            if part_id:
                part = ws.part_for_id(project, part_id)
            else:
                near = None
                if near_id:
                    try:
                        near = self._scene_path(near_id)
                    except (ValueError, FileNotFoundError):
                        near = None
                part = project.default_part_for_new(near)
            path = project.next_scene_path(title, part)
            path.parent.mkdir(parents=True, exist_ok=True)
            text = f"# {title}\n\n"
            write_atomic(path, text)
            self._index_file(path, "scene", text)
            return {"id": ws.rel_id(project, path)}

    @bridge
    def rename_scene(self, doc_id: str, title: str) -> dict:
        """Retitle the scene's file on disk. Callers flush their own unsaved
        edits first and reload the document afterwards."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("a scene needs a title")
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            project.rename_scene(path, title)
            self._index_file(path, "scene", fsutil.read_text_lenient(path))
            return {"id": doc_id}

    @bridge
    def move_scene(self, doc_id: str, delta: int) -> dict:
        """Swap with the neighbouring scene inside the same part."""
        with self._lock:
            project = self._require()
            new_path = project.move_scene(self._scene_path(doc_id), int(delta))
            if new_path is None:
                raise ValueError("the scene is already at the edge of its part")
            self.index.rebuild(project)  # two files changed names
            return {"id": ws.rel_id(project, new_path), "remap": self._rel_map()}

    @bridge
    def place_scene(self, doc_id: str, part_id: str | None = None,
                    index: int | None = None, unplaced: bool = False) -> dict:
        """Move a scene into *part_id* (None = the unparted top level) at the
        0-based *index* (default the end), or into Unplaced Scenes. Used by
        "Move to part", drag-to-reorder and Place in the book."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            part = None if unplaced else ws.part_for_id(project, part_id)
            new = project.place_scene(path, part, None if index is None else int(index),
                                      unplaced=bool(unplaced))
            self.index.rebuild(project)
            remap = self._rel_map()
            return {"id": ws.rel_id(project, new), "remap": remap}

    @bridge
    def delete_scene(self, doc_id: str) -> dict:
        """Move the scene (and its draft sidecar) to the Trash."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            rel = ws.rel_id(project, path)
            project.delete_scene(path)
            self.index.remove_file(rel)
            return {}

    @bridge
    def new_part(self, title: str) -> dict:
        with self._lock:
            part = self._require().new_part(title)
            return {"id": ws.part_id(self.project, part)}

    @bridge
    def rename_part(self, part_id: str, title: str) -> dict:
        with self._lock:
            project = self._require()
            project.rename_part(ws.part_for_id(project, part_id), title)
            return {"id": part_id}

    @bridge
    def move_part(self, part_id: str, delta: int) -> dict:
        with self._lock:
            project = self._require()
            new = project.move_part(ws.part_for_id(project, part_id), int(delta))
            if new is None:
                raise ValueError("the part is already at the edge")
            self.index.rebuild(project)
            return {"id": ws.part_id(project, new), "remap": self._rel_map()}

    @bridge
    def delete_part(self, part_id: str) -> dict:
        """Delete an empty part (move or trash its scenes first)."""
        with self._lock:
            project = self._require()
            project.delete_part(ws.part_for_id(project, part_id))
            return {}

    @bridge
    def list_trash(self) -> dict:
        with self._lock:
            project = self._require()
            return {"items": [{
                "name": i.name, "title": i.title, "kind": i.kind,
                "original": i.original.removeprefix("manuscript/") if i.kind == "scene" else i.original,
                "deleted": i.deleted.strftime("%Y-%m-%d %H:%M"),
            } for i in project.list_trash()]}

    @bridge
    def restore_trash(self, name: str) -> dict:
        """Back to the end of its original part (Unplaced if the part is gone)."""
        with self._lock:
            project = self._require()
            kind = next((i.kind for i in project.list_trash() if i.name == name), "scene")
            place = ("book", "") if kind != "scene" else project.restore_place(name)
            path = project.restore_scene(name)
            if kind == "inspiration":   # reference images: no document, no index
                return {"id": path.stem, "unplaced": False, "kind": kind}
            if kind == "research":   # research notes are not in the link index
                return {"id": ws.rel_id(project, path), "unplaced": False, "kind": kind}
            self.index.rebuild(project)
            return {"id": ws.rel_id(project, path), "kind": kind,
                    "unplaced": project.is_unplaced(path),
                    "where": place[0], "part": place[1]}

    @bridge
    def delete_forever(self, name: str) -> dict:
        with self._lock:
            self._require().delete_forever(name)
            return {}

    @bridge
    def empty_trash(self) -> dict:
        with self._lock:
            return {"deleted": self._require().empty_trash()}

    @bridge
    def set_scene_details(self, doc_id: str, text: str, fields: dict) -> dict:
        """Apply detail fields (pov, place, purpose, status, target, collections)
        to the editor's *text*. Returns the edit that replaces the frontmatter
        block (UTF-16 offsets) for the editor to dispatch; nothing is written
        here, the normal autosave persists it."""
        with self._lock:
            self._scene_path(doc_id)
            new = scenemeta.set_details(text, **fields)
            old_end, new_end = scenemeta.body_offset(text), scenemeta.body_offset(new)
            return {
                "edit": {"from": 0, "to": index_to_utf16(text, old_end),
                         "insert": new[:new_end]},
                "details": scenemeta.details(new),
                "bodyStart": index_to_utf16(new, new_end),
            }
