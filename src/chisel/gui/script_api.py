"""Script mode bridge methods (core/fountain.py, core/fountainio.py; export is in export_api.py)."""

from __future__ import annotations

from pathlib import Path

from ..core import fountainio
from ._bridge import bridge


class ScriptMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @bridge
    def import_fountain(self, path: str | None = None) -> dict:
        """Add a ``.fountain`` file's scenes to this script project. Without a *path* the window asks for
        the file (``path`` is for the dev server and tests). New scene files only: nothing is overwritten."""
        with self._lock:
            if self._require().mode != "script":
                raise ValueError("Importing a Fountain file is for script projects: "
                                 "start a new project and choose Script.")
        if path is None:
            path = self._pick_file(False, types=("Fountain script (*.fountain;*.txt;*.md)",))
            if path is None:
                return {"imported": None}
        text = fountainio.read_file(Path(path))   # outside the lock: it reads a file the author chose
        with self._lock:
            project = self._require()
            result = fountainio.import_into(project, text, Path(path).name)
            self.index.rebuild(project)
        return {"imported": result}
