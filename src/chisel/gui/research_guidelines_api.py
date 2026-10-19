"""Research mode: guideline documents (PDF, Word, text) kept in the project's guidelines/ folder.

Mixin of Api (the lead wires it in). They are the author's reference only and never reach an AI.
"""

from __future__ import annotations

from pathlib import Path

from ..core.paper import guidelines
from ._bridge import bridge
from ._research_common import require_research


class ResearchGuidelinesMixin:
    # Mixin of Api: shared state (_require, _lock, _window) is on Api.

    def _guidelines_project(self):
        project = self._require()
        require_research(project)
        return project

    def _pick_files(self) -> list[str]:
        """Native open dialog with several files (only in the real window; none otherwise)."""
        if getattr(self, "_window", None) is None:
            return []
        import webview

        kind = getattr(webview, "FileDialog", None)
        mode = getattr(kind, "OPEN", None) or webview.OPEN_DIALOG
        picked = self._window.create_file_dialog(
            mode, allow_multiple=True, file_types=("Guidelines (*.pdf;*.docx;*.md;*.txt)",))
        if not picked:
            return []
        return [str(p) for p in ([picked] if isinstance(picked, str) else picked)]

    @bridge
    def guidelines_list(self) -> dict:
        with self._lock:
            project = self._guidelines_project()
            return {"files": guidelines.list_files(project)}

    @bridge
    def guidelines_add(self, paths: list | None = None) -> dict:
        """Pick files in the native dialog (``paths`` is for tests and the dev server) and add them."""
        with self._lock:
            self._guidelines_project()
        picked = [str(p) for p in paths] if paths is not None else self._pick_files()   # dialog: no lock
        added: list[str] = []
        skipped: list[dict] = []
        with self._lock:
            project = self._guidelines_project()
            for p in picked:
                try:
                    added.append(guidelines.add_file(project, p))
                except (guidelines.GuidelineError, FileNotFoundError) as exc:
                    skipped.append({"name": Path(p).name, "reason": str(exc)})
                except OSError:
                    skipped.append({"name": Path(p).name, "reason": "The file could not be read."})
        return {"added": added, "skipped": skipped}

    @bridge
    def guidelines_add_text(self, title: str, text: str) -> dict:
        with self._lock:
            project = self._guidelines_project()
            return {"name": guidelines.add_text(project, title, text)}

    @bridge
    def guidelines_read(self, name: str, limit: int = 20000) -> dict:
        with self._lock:
            project = self._guidelines_project()
            return guidelines.read_text(project, name, limit)

    @bridge
    def guidelines_remove(self, name: str) -> dict:
        with self._lock:
            project = self._guidelines_project()
            guidelines.remove(project, name)
        return {}
