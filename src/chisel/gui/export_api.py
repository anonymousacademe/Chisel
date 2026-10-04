"""Export (core/export; the file work runs in a worker thread)."""

from __future__ import annotations

from ..core import export as exporting
from ..core.export.manuscript import ExportOptions
from ._bridge import bridge


class ExportMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @bridge
    def export_info(self) -> dict:
        """Formats (and whether each can run), layouts and the remembered options."""
        with self._lock:
            return exporting.describe(self._require())

    @bridge
    def export_summary(self, options: dict) -> dict:
        """The live line in the dialog: scenes, words, parts, unaccepted drafts, warnings."""
        with self._lock:
            return {"summary": exporting.summarize(self._require(), ExportOptions.from_dict(options))}

    @bridge
    def export_start(self, options: dict) -> dict:
        """Start an export in a worker thread; poll with export_status. The client
        saves the open scene first so the file has the latest words."""
        with self._lock:
            project = self._require()
        return {"job": self._exports.start(project, ExportOptions.from_dict(options))}

    @bridge
    def export_status(self, job: str) -> dict:
        return self._exports.status(job)

    @bridge
    def export_open(self, name: str = "", folder: bool = False) -> dict:
        """Open an export (or the exports folder) with the desktop; only on the author's click."""
        with self._lock:
            path = exporting.resolve_export(self._require(), "" if folder else name)
        exporting.open_in_desktop(path)
        return {}
