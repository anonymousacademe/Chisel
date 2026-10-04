"""Spell check (core/spelling.py): computed outside the lock; the author's dictionary."""

from __future__ import annotations

from . import workspace as ws
from ..core import settings as user_settings, spelling
from ..core.spans import to_utf16
from ._bridge import bridge


class SpellingMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @staticmethod
    def spellcheck_enabled() -> bool:
        return bool(user_settings.get("spellcheck", True))

    @bridge
    def spelling(self, doc_id: str, text: str) -> dict:
        """Misspelled words in the editor buffer (scenes only, when the setting
        is on), offsets in UTF-16 units. Computed outside the lock: it is pure
        and can take a moment on a long scene."""
        with self._lock:
            project = self._require()
            _, kind = self.resolve_document(doc_id)
            if kind != "scene" or not self.spellcheck_enabled():
                return {"enabled": False, "spans": []}
            accepted = spelling.accepted_terms(
                project, entities=self.entities,
                ignored=self._spell_ignores.for_project(project.root))
        found = spelling.check(text, accepted)
        spans = to_utf16(text, [{"start": m.start, "end": m.end, "word": m.word}
                                for m in found])
        return {"enabled": True, "spans": spans}

    @bridge
    def spelling_suggestions(self, word: str) -> dict:
        return {"suggestions": spelling.suggestions(str(word))}

    @bridge
    def add_to_dictionary(self, term: str, scope: str = "project") -> dict:
        """Never flag *term* (a word or phrase) again: in this project's
        dictionary.txt, or in the personal one shared by all projects."""
        with self._lock:
            if scope == "project":
                path = spelling.project_dictionary_path(self._require())
            elif scope == "personal":
                path = spelling.personal_dictionary_path()
            else:
                raise ValueError("scope must be 'project' or 'personal'")
            if not " ".join(str(term).split()):
                raise ValueError("nothing to add")
            return {"added": spelling.add_to_dictionary(path, str(term))}

    @bridge
    def ignore_word(self, word: str) -> dict:
        """Ignore *word* until the app is closed (not saved anywhere)."""
        with self._lock:
            self._spell_ignores.add(self._require().root, str(word))
        return {}

    @bridge
    def open_dictionary(self) -> dict:
        """Create dictionary.txt (with a comment header) if missing; its id."""
        with self._lock:
            spelling.ensure_dictionary(spelling.project_dictionary_path(self._require()))
            return {"id": ws.DICTIONARY_ID}
