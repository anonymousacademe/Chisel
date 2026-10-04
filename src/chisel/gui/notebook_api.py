"""Notebook notes (core/research.py; 'research' is the old name). The Ask-my-notebook chat stays in api.py."""

from __future__ import annotations

from . import workspace as ws
from ..core import research as research_notes
from ._bridge import bridge


class NotebookMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.
    # Plain Markdown notes in notebook/: not scenes, not entities, not indexed.

    def _research_payload(self) -> dict:
        project = self._require()
        return {"research": ws.research_summaries(project)}

    @bridge
    def new_research_note(self, title: str, template: str = "") -> dict:
        """A new notebook note; *template* is blank / idea / location / timeline."""
        with self._lock:
            path = research_notes.new_note(self._require(), title, template=template)
            return {"id": ws.rel_id(self._require(), path)}

    @bridge
    def send_to_notebook(self, text: str, doc_id: str = "") -> dict:
        """Copy a selected passage into notebook/clippings.md (never edits the scene)."""
        with self._lock:
            project = self._require()
            source = ""
            if doc_id:
                path, kind = self.resolve_document(doc_id)
                if kind == "scene":
                    source = project.scene_title(path)
            path = research_notes.append_clipping(project, text, source)
            return {"id": ws.rel_id(project, path)}

    @bridge
    def new_research_from_url(self, url: str, title: str = "") -> dict:
        """A note holding just the link and a title; the page is never fetched."""
        with self._lock:
            project = self._require()
            path = research_notes.note_from_url(project, url, title)
            return {"id": ws.rel_id(project, path), "title": research_notes.title_of(path)}

    @bridge
    def delete_research_note(self, doc_id: str) -> dict:
        """Move a notebook note to the Trash (the UI confirms first)."""
        with self._lock:
            path, kind = self.resolve_document(doc_id)
            if kind != "research":
                raise ValueError("not a notebook note")
            research_notes.delete_note(self._require(), path)
            return {}
