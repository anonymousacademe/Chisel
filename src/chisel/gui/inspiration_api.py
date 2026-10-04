"""Inspiration pictures (core/inspiration.py): listing, upload, edit, delete. The AI calls (describe, generate) stay in api.py."""

from __future__ import annotations

from . import inspiration as insp_api, workspace as ws
from ._bridge import bridge


class InspirationMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.
    # Reference pictures kept beside the writing; never inserted into prose. Thin wrappers over
    # gui/inspiration.py.

    def _item_link(self, doc_id: str | None) -> str:
        """The project-relative path of any item (scene, entity note, notebook note, ...) a
        picture can be for; "" for no item. ValueError / FileNotFoundError for an id that
        names no document."""
        if not doc_id:
            return ""
        path, _ = self.resolve_document(doc_id)
        return ws.rel_id(self._require(), path)

    @bridge
    def list_inspiration(self, doc_id: str | None = None) -> dict:
        """Every picture (newest first). With *doc_id* (any document id) `mine` lists the ids
        of the pictures made for that item; an id that names nothing is an error."""
        with self._lock:
            project = self._require()
            link = self._item_link(doc_id)
            out = insp_api.listing(project)
            if doc_id:
                out["mine"] = [i["id"] for i in out["images"] if i["for"] == link]
            return out

    @bridge
    def inspiration_image(self, image_id: str) -> dict:
        """The picture as a data URL (only files inside inspiration/)."""
        with self._lock:
            return {"dataUrl": insp_api.data_url(self._require(), image_id)}

    @bridge
    def upload_inspiration(self, name: str, data_url: str, doc_id: str | None = None) -> dict:
        """Add a picture of the author's own (a `data:image/...;base64,` URL; JPG, PNG or WebP,
        at most 10 MB, checked against its bytes) to inspiration/, optionally for the item
        *doc_id*. Nothing is sent anywhere; the file name is made here, never taken from *name*."""
        with self._lock:
            project = self._require()
            return insp_api.save_upload(project, name, data_url, self._item_link(doc_id))

    @bridge
    def update_inspiration(self, image_id: str, fields: dict) -> dict:
        """Pin / unpin (`pinned`, with `for` = the id of any document to show it with),
        `title`, `notes`. (`scene` is the old name of `for`.)"""
        with self._lock:
            project = self._require()
            return {"image": insp_api.update(project, image_id, fields,
                                             lambda doc_id: self.resolve_document(doc_id)[0])}

    @bridge
    def delete_inspiration(self, image_id: str) -> dict:
        """Move the picture to the Trash (the UI confirms first)."""
        with self._lock:
            self._require().trash_inspiration(image_id)
            return {}

    @bridge
    def reveal_inspiration(self, image_id: str) -> dict:
        """Show the file in the system file manager (real window only; always returns the path)."""
        with self._lock:
            path = insp_api.get(self._require(), image_id).path
        opened = self._window is not None and insp_api.reveal(path)
        return {"path": str(path), "opened": bool(opened)}
