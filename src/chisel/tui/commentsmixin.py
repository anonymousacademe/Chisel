"""Comments and collections for the terminal app (core/comments.py, core/collections.py).

A mixin for ChiselApp.
"""

from __future__ import annotations

from pathlib import Path
from textual.widgets.text_area import Selection
from ..core import fsutil
from ..core import collections as coll
from ..core import comments
from ..core import scenemeta
from ..core.links import offset_to_rowcol, rowcol_to_offset
from .collectionscreens import CollectionsScreen
from .commentscreens import CommentsScreen
from .dialogs import ConfirmScreen, NamePrompt


class CommentsCollectionsMixin:
    def refresh_comments(self, reload: bool = False) -> None:
        """Underline the open scene's open comments (faintly) in the editor."""
        if self._editor is None:
            return
        path = self._current_scene_path()
        if path is None:
            self._comment_list, self._comment_scene = [], None
            self._editor.set_comments([])
            return
        if reload or self._comment_scene != path:
            self._comment_list = comments.load(self.project.root, path)
            self._comment_scene = path
        if not self._comment_list:
            self._editor.set_comments([])
            return
        live = [c for c in self._comment_list if not c.resolved]
        self._editor.set_comments([(p.start, p.end) for p in comments.place(
            self._editor.text, live) if not p.detached])

    def add_comment_prompt(self) -> None:
        """Scene · Add comment on selection."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        if not self.editor.selected_text.strip():
            self.notify("Select the passage to comment on first", severity="warning")
            return
        text = self.editor.text
        a, b = self.editor.selection
        lo = min(rowcol_to_offset(text, *a), rowcol_to_offset(text, *b))
        hi = max(rowcol_to_offset(text, *a), rowcol_to_offset(text, *b))

        def _add(body: str | None) -> None:
            if not body:
                return
            try:
                comments.add(self.project.root, path, text, lo, hi, body)
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                return
            self.refresh_comments(reload=True)
            self.notify("Comment added (it is kept beside the scene, not in the text)", timeout=3)

        self.push_screen(NamePrompt("Comment:"), _add)

    def open_comments(self, focus: str | None = None) -> None:
        """Scene · Comments: list, jump, resolve, edit, delete."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self.save_current()
        text = self.editor.text
        placed = comments.place(text, comments.load(self.project.root, path))
        lines = {p.comment.id: (None if p.start is None else text.count("\n", 0, p.start))
                 for p in placed}
        index = next((i for i, p in enumerate(placed) if p.comment.id == focus), 0)
        by_id = {p.comment.id: p for p in placed}

        def _act(result) -> None:
            if result is None:
                self.refresh_comments(reload=True)
                return
            what, cid = result
            root = self.project.root
            if what == "jump":
                p = by_id[cid]
                self.refresh_comments(reload=True)
                self.editor.selection = Selection(offset_to_rowcol(text, p.start),
                                                  offset_to_rowcol(text, p.end))
                self.editor.focus()
            elif what == "resolve":
                comments.resolve(root, path, cid, not by_id[cid].comment.resolved)
                self.open_comments(cid)
            elif what == "edit":
                def _edit(body: str | None) -> None:
                    if body:
                        comments.edit(root, path, cid, body)
                    self.open_comments(cid)

                self.push_screen(NamePrompt("Comment:", by_id[cid].comment.body), _edit)
            elif what == "delete":
                def _gone(ok: bool) -> None:
                    if ok:
                        comments.delete(root, path, cid)
                    self.open_comments(None if ok else cid)

                self.push_screen(ConfirmScreen(
                    "Delete this comment?\nThe text it was about is not touched.",
                    confirm_label="Delete comment"), _gone)

        self.push_screen(CommentsScreen(placed, lines, self.project.scene_title(path), index),
                         _act)

    def _scene_collection_names(self) -> dict[Path, list[str]]:
        """{scene: its collection names}, for the sidebar's #collection filter."""
        out: dict[Path, list[str]] = {}
        for c in coll.list_collections(self.project):
            for p in c.scenes:
                out.setdefault(p, []).append(c.name)
        return out

    def open_collections(self, focus: str | None = None) -> None:
        """Scene · Collections: tick the open scene's collections; add, rename,
        recolour or delete them. (Sidebar filter: type #name.)"""
        self.save_current()
        path = self._current_scene_path()
        members = (set(scenemeta.details(self.editor.text)["collections"])
                   if path is not None else None)
        items = coll.list_collections(self.project)
        index = next((i for i, c in enumerate(items) if c.name == focus), 0)
        title = self.project.scene_title(path) if path is not None else None

        def _act(result) -> None:
            if result is None:
                return
            what, name = result
            if what == "new":
                def _create(new: str | None) -> None:
                    if new:
                        try:
                            name = coll.create(self.project, new)
                        except ValueError as exc:
                            self.notify(str(exc), severity="warning")
                            name = None
                        self.refresh_sidebar()
                        self.open_collections(name)
                    else:
                        self.open_collections()

                self.push_screen(NamePrompt("New collection name:"), _create)
            elif what == "toggle":
                names = [n for n in (members or ()) if n != name]
                if name not in (members or ()):
                    names.append(name)
                new = scenemeta.set_details(self.editor.text, collections=names)
                if new != self.editor.text:
                    self.editor.load_text(new)  # the buffer owns the file: edit it, then save
                    self.save_current()
                    self.editor.refresh_links()
                self.open_collections(name)
            elif what == "recolor":
                found = coll.find(self.project, name)
                at = coll.COLORS.index(found.color) if found and found.color in coll.COLORS else -1
                coll.recolor(self.project, name, coll.COLORS[(at + 1) % len(coll.COLORS)])
                self.open_collections(name)
            elif what == "rename":
                def _rename(new: str | None) -> None:
                    if new:
                        try:
                            self._collection_op(lambda: coll.rename(self.project, name, new))
                            name_after = new
                        except (ValueError, LookupError) as exc:
                            self.notify(str(exc), severity="warning")
                            name_after = name
                        self.open_collections(name_after)
                    else:
                        self.open_collections(name)

                self.push_screen(NamePrompt(f"Rename '{name}' to:"), _rename)
            elif what == "delete":
                found = coll.find(self.project, name)
                count = len(found.scenes) if found else 0

                def _gone(ok: bool) -> None:
                    if ok:
                        self._collection_op(lambda: coll.delete(self.project, name))
                    self.open_collections()

                self.push_screen(ConfirmScreen(
                    f"Delete the collection '{name}'?\nIt is taken off its {count} "
                    f"scene{'' if count == 1 else 's'}; no scene is deleted.",
                    confirm_label="Delete collection"), _gone)

        self.push_screen(CollectionsScreen(items, members, title, index, self.project.unit),
                         _act)

    def _collection_op(self, run) -> None:
        """Rename / delete rewrite member scenes on disk: the open one is
        saved first and re-read afterwards."""
        self.save_current()
        changed = run()
        if self.current_path in changed:  # re-read it; open_file would save the stale buffer over it
            self.editor.load_text(fsutil.read_text_lenient(self.current_path))
            self._dirty = False
            self.editor.refresh_links()
        self.refresh_sidebar()
