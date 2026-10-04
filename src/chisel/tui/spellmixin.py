"""Spell check for the terminal app (core/spelling.py): spelling only, off the UI thread, debounced.

A mixin for ChiselApp.
"""

from __future__ import annotations

from ..core import settings as user_settings
from ..core import spelling
from ..core.applog import log_exc
from ..core.links import offset_to_rowcol, rowcol_to_offset
from .spellscreen import SpellScreen


class SpellMixin:
    def _spell_active(self) -> bool:
        """Spelling applies to scenes only (not notes, style.md, dictionary)."""
        return (self.project is not None and self._editor is not None
                and self._is_scene(self.current_path))

    def _spell_on(self) -> bool:
        return bool(user_settings.get("spellcheck", True)) and self._spell_active()

    def _accepted(self) -> spelling.AcceptedTerms:
        return spelling.accepted_terms(
            self.project, entities=self.entities,
            ignored=self._spell_ignores.for_project(self.project.root))

    def _spelling_edited(self) -> None:
        """Keep underlines honest between checks: a line-count change shifts
        every later row, so clear; otherwise the edited row is dropped."""
        if not self._spell_on():
            return
        lines = self.editor.document.line_count
        if lines != self._spell_lines:
            self.editor.set_misspellings(None)
        else:
            row = self.editor.cursor_location[0]
            self.editor._spelling.pop(row, None)
        self.schedule_spelling()

    def schedule_spelling(self, delay: float = 0.6) -> None:
        if self._spell_timer is not None:
            self._spell_timer.stop()
        self._spell_timer = self.set_timer(delay, self._spell_start)

    def _spell_start(self) -> None:
        if self._editor is None:
            return
        if not self._spell_on():
            self.editor.set_misspellings(None)
            return
        text = self.editor.text
        accepted = self._accepted()
        self._spell_lines = self.editor.document.line_count

        def work() -> None:
            found = spelling.check(text, accepted)
            try:
                self.call_from_thread(self._spell_apply, text, found)
            except Exception as exc:  # app shutting down
                log_exc("spell result dropped", exc)

        self.run_worker(work, thread=True, exclusive=True, group="spell")

    def _spell_apply(self, text: str, found) -> None:
        if self._editor is not None and self._editor.text == text \
                and self._spell_on():
            self.editor.set_misspellings(found)

    def refresh_spelling(self) -> None:
        """Re-check right now (after a dictionary change)."""
        if self._editor is None:
            return
        if not self._spell_on():
            self.editor.set_misspellings(None)
            return
        self._spell_lines = self.editor.document.line_count
        self.editor.set_misspellings(
            spelling.check(self.editor.text, self._accepted()))

    def toggle_spellcheck(self) -> None:
        on = not user_settings.get("spellcheck", True)
        user_settings.set("spellcheck", on)
        self.refresh_spelling()
        self.notify(f"Spell check {'on' if on else 'off'}", timeout=2)

    def action_spell_next(self) -> None:
        """f6: jump to the next misspelling after the cursor and fix it."""
        if not self._spell_active():
            self.notify("Spell check applies to scenes", timeout=2)
            return
        text = self.editor.text
        found = spelling.check(text, self._accepted())
        if not found:
            self.notify("No misspellings", timeout=2)
            return
        offset = rowcol_to_offset(text, *self.editor.cursor_location)
        m = next((m for m in found if m.start >= offset), found[0])
        self.editor.move_cursor(offset_to_rowcol(text, m.end))
        word = text[m.start:m.end]

        def _done(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            kind, value = result
            self._spell_resolve(m, word, kind, value)

        self.push_screen(SpellScreen(word, spelling.suggestions(word)), _done)

    def _spell_resolve(self, m, word: str, kind: str, value: str) -> None:
        if kind == "replace":
            if self.editor.text[m.start:m.end] == word:
                self.editor.replace_offsets(m.start, m.end, value)
            return
        if kind == "project":
            spelling.add_to_dictionary(
                spelling.project_dictionary_path(self.project), word)
            self.notify(f'Added "{word}" to the project dictionary', timeout=2)
        elif kind == "personal":
            spelling.add_to_dictionary(spelling.personal_dictionary_path(), word)
            self.notify(f'Added "{word}" to your dictionary', timeout=2)
        elif kind == "ignore":
            self._spell_ignores.add(self.project.root, word)
        self.refresh_spelling()

    def add_selection_to_dictionary(self) -> None:
        """Palette: selected word or phrase -> project dictionary."""
        if self.project is None or self._editor is None:
            return
        term = " ".join(self.editor.selected_text.split())
        if not term:
            self.notify("Select a word or phrase first", timeout=2)
            return
        added = spelling.add_to_dictionary(
            spelling.project_dictionary_path(self.project), term)
        self.notify(f'Added "{term}" to the project dictionary' if added
                    else f'"{term}" is already in the dictionary', timeout=2)
        self.refresh_spelling()

    def open_project_dictionary(self) -> None:
        if self.project is None:
            return
        self.save_current()
        self.open_file(spelling.ensure_dictionary(
            spelling.project_dictionary_path(self.project)))

    # -- actions ---------------------------------------------------------------------
