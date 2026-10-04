"""Comments (core/comments.py) and collections (core/collections.py)."""

from __future__ import annotations

from pathlib import Path
from . import workspace as ws
from ..core import collections as coll, comments, fsutil
from ..core.spans import from_utf16, index_to_utf16
from ._bridge import bridge


class AnnotationsMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.
    # Comments: author notes anchored to a passage, in .comments/<scene>.json, never in the prose;
    # positions are computed against the editor's text (UTF-16). Collections: definitions in
    # project.toml, membership in each scene's frontmatter; the calls rewrite other scenes' files,
    # so the client flushes first and reopens after.

    def _comment_rows(self, path: Path, text: str) -> list[dict]:
        project = self._require()
        rows = []
        for p in comments.reanchor(project.root, path, text):
            c = p.comment
            rows.append({
                **c.as_dict(), "detached": p.detached,
                "start": None if p.start is None else index_to_utf16(text, p.start),
                "end": None if p.end is None else index_to_utf16(text, p.end),
                "row": None if p.start is None else text.count("\n", 0, p.start),
            })
        return rows

    def _comment_text(self, path: Path, text: str | None) -> str:
        return text if text is not None else fsutil.read_text_lenient(path)

    @bridge
    def list_comments(self, doc_id: str, text: str | None = None) -> dict:
        """The scene's comments, detached ones first, then top to bottom."""
        with self._lock:
            path = self._scene_path(doc_id)
            text = self._comment_text(path, text)
            return {"comments": self._comment_rows(path, text)}

    @bridge
    def add_comment(self, doc_id: str, text: str, start: int, end: int, body: str) -> dict:
        """Comment on text[start:end] (UTF-16 offsets into the editor's *text*)."""
        with self._lock:
            path = self._scene_path(doc_id)
            c = comments.add(self._require().root, path, text,
                             from_utf16(text, start), from_utf16(text, end), body)
            return {"id": c.id, "comments": self._comment_rows(path, text)}

    @bridge
    def edit_comment(self, doc_id: str, comment_id: str, body: str, text: str | None = None) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            comments.edit(self._require().root, path, comment_id, body)
            return {"comments": self._comment_rows(path, self._comment_text(path, text))}

    @bridge
    def resolve_comment(self, doc_id: str, comment_id: str, resolved: bool = True,
                        text: str | None = None) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            comments.resolve(self._require().root, path, comment_id, resolved)
            return {"comments": self._comment_rows(path, self._comment_text(path, text))}

    @bridge
    def delete_comment(self, doc_id: str, comment_id: str, text: str | None = None) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            comments.delete(self._require().root, path, comment_id)
            return {"comments": self._comment_rows(path, self._comment_text(path, text))}

    def _collections_payload(self) -> dict:
        project = self._require()
        return {"collections": ws.collection_summaries(project, ws.scene_summaries(project))}

    def _ids(self, paths) -> list[str]:
        project = self._require()
        return [ws.rel_id(project, p) for p in paths]

    @bridge
    def list_collections(self) -> dict:
        with self._lock:
            return self._collections_payload()

    @bridge
    def create_collection(self, name: str, color: str = "violet") -> dict:
        with self._lock:
            coll.create(self._require(), name, color)
            return self._collections_payload()

    @bridge
    def recolor_collection(self, name: str, color: str) -> dict:
        with self._lock:
            coll.recolor(self._require(), name, color)
            return self._collections_payload()

    @bridge
    def rename_collection(self, name: str, new_name: str) -> dict:
        with self._lock:
            changed = coll.rename(self._require(), name, new_name)
            return {**self._collections_payload(), "changed": self._ids(changed)}

    @bridge
    def delete_collection(self, name: str) -> dict:
        """Remove the collection and its membership from every scene (no scene is deleted)."""
        with self._lock:
            changed = coll.delete(self._require(), name)
            return {**self._collections_payload(), "changed": self._ids(changed)}
