"""Snapshots for the terminal app: take, list, compare and restore (core/snapshots.py).

A mixin for ChiselApp.
"""

from __future__ import annotations

from pathlib import Path
from ..core import snapshots
from .snapshotscreens import CompareScreen, LabelPrompt, SnapshotsScreen, label_text
from ..core import drafts
from .dialogs import ConfirmScreen


class SnapshotsMixin:
    def _refresh_snapshot_time(self) -> None:
        path = self.current_path
        self._snapshot_at = (snapshots.latest_time(self.project, path)
                             if path is not None and self._is_scene(path) else None)

    def snapshot_scene_prompt(self) -> None:
        """Scene · Snapshot scene: a verbatim copy you can compare and restore."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return

        def _take(label: str | None) -> None:
            if label is None:
                return
            snapshots.create(self.project, path, label, self.editor.text)
            self._refresh_snapshot_time()
            self.update_status()
            self.notify("Snapshot taken" + (f": {label}" if label else ""), timeout=2)

        self.push_screen(LabelPrompt("Snapshot this scene (the text as it is now)"), _take)

    def snapshot_all_prompt(self) -> None:
        """Action · Snapshot all scenes: one label for every scene."""
        if self.project is None:
            return
        self.save_current()

        def _take(label: str | None) -> None:
            if label is None:
                return
            n = snapshots.snapshot_all(self.project, label)
            self._refresh_snapshot_time()
            self.update_status()
            self.notify(f"Snapshot taken of {n} scene(s)", timeout=2)

        self.push_screen(LabelPrompt("Snapshot every scene in the project"), _take)

    def open_snapshots(self) -> None:
        """Scene · Snapshots: list, compare, restore, delete."""
        path = self._current_scene_path()
        if path is None:
            self.notify("Open a scene first", severity="warning")
            return
        self.save_current()
        text = self.editor.text
        words = drafts.count_words(text, self._originals(text))
        items = snapshots.list_snapshots(self.project, path)
        title = self.project.scene_title(path)

        def _act(result) -> None:
            if result is None:
                return
            what, name = result
            if what == "new":
                self.snapshot_scene_prompt()
            elif what == "all":
                self.snapshot_all_prompt()
            elif what == "compare":
                self._compare_snapshot(path, name)
            elif what == "restore":
                self._confirm_restore(path, name)
            elif what == "delete":
                snap = next((s for s in items if s.name == name), None)

                def _gone(ok: bool) -> None:
                    if ok:
                        snapshots.delete(self.project, path, name)
                        self._refresh_snapshot_time()
                        self.update_status()
                    self.open_snapshots()

                self.push_screen(ConfirmScreen(
                    f"Delete the snapshot '{label_text(snap.label) if snap else name}'?\n"
                    "This cannot be undone.", confirm_label="Delete"), _gone)

        self.push_screen(SnapshotsScreen(title, items, words), _act)

    def _compare_snapshot(self, path: Path, name: str) -> None:
        old = snapshots.read_text(self.project, path, name)
        segs = snapshots.diff_words(old, self.editor.text)
        snap = next((x for x in snapshots.list_snapshots(self.project, path) if x.name == name), None)
        title = (f"{label_text(snap.label)}, {snap.when.strftime('%Y-%m-%d %H:%M')} ({snapshots.ago(snap.when)})"
                 if snap else name)

        def _back(result) -> None:
            if result == "restore":
                self._confirm_restore(path, name)
            else:
                self.open_snapshots()

        self.push_screen(CompareScreen(title, segs), _back)

    def _confirm_restore(self, path: Path, name: str) -> None:
        def _go(ok: bool) -> None:
            if not ok:
                self.open_snapshots()
                return
            self.save_current()
            # the current text is snapshotted first (before-restore), then replaced
            text = snapshots.restore(self.project, path, name, self.editor.text)
            self._stats_seen(text)  # restoring is not writing
            self.editor.load_text(text)
            self.save_current()
            self.editor.refresh_links()
            self.schedule_spelling(0.05)
            self.notify("Snapshot restored; the text from before is kept as "
                        "'before a restore'", timeout=4)

        self.push_screen(ConfirmScreen(
            "Replace this scene with the snapshot?\n"
            "The text as it is now is snapshotted first, so you can come back to it.",
            confirm_label="Restore"), _go)

    # -- git sync (Wave 2.3): the status is read-only; the actions run only when asked ----
