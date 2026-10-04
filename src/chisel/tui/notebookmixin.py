"""Notebook notes for the terminal app (core/research.py; the code keeps the name research).

A mixin for ChiselApp.
"""

from __future__ import annotations

from ..core import research as research_notes
from .dialogs import ConfirmScreen, NamePrompt


class NotebookMixin:
    def new_research_note_prompt(self) -> None:
        def _create(title: str | None) -> None:
            if not title:
                return
            try:
                path = research_notes.new_note(self.project, title)
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                return
            self.open_file(path)

        self.push_screen(NamePrompt("New note title:"), _create)

    def new_research_from_link_prompt(self) -> None:
        def _create(url: str | None) -> None:
            if not url:
                return
            try:
                path = research_notes.note_from_url(self.project, url)
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                return
            self.open_file(path)
            self.notify("Saved the link as a notebook note (the page is not downloaded)", timeout=3)

        self.push_screen(NamePrompt("Link (https://...):"), _create)

    def send_selection_to_notebook(self) -> None:
        """Copy the selected passage into notebook/clippings.md (the scene is not touched)."""
        if not self.editor.selected_text.strip():
            self.notify("Select the passage to send first", severity="warning")
            return
        path = self._current_scene_path()
        source = self.project.scene_title(path) if path is not None else ""
        try:
            research_notes.append_clipping(self.project, self.editor.selected_text, source)
        except (ValueError, OSError) as exc:
            self.notify(str(exc), severity="warning")
            return
        self.notify("Sent to notebook/clippings.md", timeout=3)

    def delete_research_note_confirm(self) -> None:
        path = self.current_path
        if path is None or not research_notes.is_research_path(self.project, path):
            self.notify("Open a notebook note first", severity="warning")
            return

        def _go(ok: bool) -> None:
            if not ok:
                return
            self._dirty = False          # a pending autosave must not bring the file back
            self.current_path = None
            research_notes.delete_note(self.project, path)   # to the Trash
            scenes = self.project.list_scenes()
            if scenes:
                self.open_file(scenes[0])
            self.notify("Note moved to the Trash (Action · Open Trash restores it)", timeout=3)

        self.push_screen(ConfirmScreen(
            f"Move the notebook note '{research_notes.title_of(path)}' to the Trash?\n"
            "You can restore it from Action · Open Trash.", confirm_label="Move to Trash"), _go)

    # -- the assistant (chat + research), Wave 3.3 / 3.4 -------------------------------------
