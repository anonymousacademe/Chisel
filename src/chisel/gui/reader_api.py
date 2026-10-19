"""Read aloud, bridge side (core/reader.py): the list of utterances the desktop editor speaks.

Nothing here makes a sound or changes a file: Python decides what is read and in which voice, the editor plays it
with the window's speech service (docs/dev/plan-read-aloud.md). Desktop only."""

from __future__ import annotations

from ..core import fsutil, reader
from ..core.spans import to_utf16
from ._bridge import bridge


class ReaderMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @bridge
    def read_plan(self, doc_id: str, text: str | None = None, options: dict | None = None) -> dict:
        """What to read aloud in the open document: *text* is the editor buffer (default: the file). A scene is
        read as a script, a story or a research section by the project's mode; a note is read as plain text;
        the style guide and the dictionary are not read. Offsets are UTF-16, into *text*."""
        opts = reader.ReadOptions.from_dict(options)
        with self._lock:
            project = self._require()
            path, kind = self.resolve_document(doc_id)
            if kind not in ("scene", "entity", "research"):
                raise ValueError("There is nothing to read aloud in this document")
            if text is None:
                text = fsutil.read_text_lenient(path)
            mode = (project.mode if project.mode in ("script", "research") else "story") if kind == "scene" else "note"
            entities = list(self.entities)
        found = reader.plan(text, mode, entities, opts)            # outside the lock: it parses the whole text
        rows = to_utf16(text, [{
            "kind": u.kind, "voice": u.voice, "text": u.text, "say": u.say, "start": u.start, "end": u.end,
            "row": u.row, "seconds": u.seconds, "joins": u.joins} for u in found.utterances])
        return {"mode": mode, "utterances": rows, "words": found.words, "seconds": round(found.seconds(), 1),
                "voices": [{"voice": v, "count": n} for v, n in found.voices().items()]}
