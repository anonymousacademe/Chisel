"""Writing stats, focus sprints and manuscript export for the terminal app (core/stats.py, core/export/).

A mixin for ChiselApp. Stats are personal (state dir), never in the project folder.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from ..core import fsutil
from ..core import export as exporting
from ..core import stats as writing_stats
from .dialogs import NamePrompt
from .statsscreens import StatsScreen
from .exportscreen import ExportScreen
from .structurescreens import ChoiceScreen
from ..core import drafts


class StatsMixin:
    def _stats_key(self, path: Path) -> str:
        return path.relative_to(self.project.root).as_posix()

    def _stats_seen(self, text: str, path: Path | None = None) -> None:
        """A scene was opened or replaced wholesale: its baseline, nothing counted."""
        path = path or self.current_path
        if self.stats is None or not self._is_scene(path):
            return
        self.stats.seen(self._stats_key(path), drafts.count_words(text, self._originals(text, path)))

    def _stats_record(self, text: str) -> None:
        if self.stats is None or not self._is_scene(self.current_path):
            return
        try:
            self.stats.record(self._stats_key(self.current_path),
                              drafts.count_words(text, self._originals(text)))
            self._refresh_stats()
        except OSError:
            pass  # stats are a convenience; never block a save

    def _stats_accepted(self, pending, body: str) -> None:
        """An AI draft is about to become prose: AI words, not the author's."""
        if self.stats is None or not self._is_scene(self.current_path):
            return
        original = self._originals(self.editor.text).get(pending.id, "") if pending.id else ""
        self.stats.accepted(self._stats_key(self.current_path), len(body.split()),
                            len(original.split()))

    def _refresh_stats(self) -> None:
        if self.stats is None:
            self._stats_brief = None
            return
        s = self.stats.summary()
        self._stats_brief = {"target": s["target"], "streak": s["streak"],
                             "todayWords": s["today"]["words"], "sprint": s["sprint"]}

    # -- focus sprint (Wave 4.2): a countdown in the status bar, optionally in writer mode ---

    SPRINT_CHOICES = [("15 minutes", 15), ("25 minutes", 25), ("45 minutes", 45), ("Custom length…", 0)]

    def focus_sprint(self) -> None:
        """Action · Focus sprint: start a timed writing sprint, or stop the running one."""
        if self.stats is None:
            return
        if self.stats.sprint is not None:
            def _stop(choice) -> None:
                if choice == "stop":
                    self._end_sprint(cancelled=True)

            self.push_screen(ChoiceScreen(
                f"Sprint running: {writing_stats.clock(self.stats.sprint_state()['remaining'])} left",
                [("Stop the sprint (keeps what you wrote)", "stop"), ("Keep going", "keep")]), _stop)
            return

        def _length(minutes) -> None:
            if minutes is None:
                return
            if minutes == 0:
                def _custom(raw) -> None:
                    try:
                        self._ask_sprint_mode(int(raw or 0))
                    except ValueError:
                        self.notify("A sprint length is a whole number of minutes", severity="warning")

                self.push_screen(NamePrompt("Sprint length in minutes (1-240):", "30"), _custom)
            else:
                self._ask_sprint_mode(minutes)

        self.push_screen(ChoiceScreen("Focus sprint - how long?", self.SPRINT_CHOICES), _length)

    def _ask_sprint_mode(self, minutes: int) -> None:
        def _go(writer) -> None:
            if writer is not None:
                self._start_sprint(minutes, bool(writer))

        self.push_screen(ChoiceScreen(
            f"{minutes}-minute sprint", [("Start, keep the screen as it is", False),
                                         ("Start in writer mode (hides everything but the editor)", True)]), _go)

    def _start_sprint(self, minutes: int, writer: bool) -> None:
        try:
            self.stats.start_sprint(minutes)
        except ValueError as exc:
            self.notify(str(exc), severity="warning")
            return
        self._sprint_writer = writer and not self._writer_mode
        if self._sprint_writer:
            self.writer_mode()
        self._refresh_stats()
        self.update_status()
        self.notify(f"Sprint started: {minutes} minutes", timeout=2)

    def _sprint_tick(self) -> None:
        if self.stats is None or self.stats.sprint is None:
            return
        state = self.stats.sprint_state()
        if state["done"]:
            self._end_sprint(cancelled=False)
        else:
            self._refresh_stats()
            self.update_status()

    def _end_sprint(self, cancelled: bool) -> None:
        if self.stats is None or self.stats.sprint is None:
            return
        self.save_current()   # the last words count
        rec = self.stats.finish_sprint(cancelled=cancelled)
        if getattr(self, "_sprint_writer", False):
            self._sprint_writer = False
            if self._writer_mode:
                self.writer_mode()
        self._refresh_stats()
        self.update_status()
        if rec is not None:
            verb = "stopped" if cancelled else "done"
            self.notify(f"Sprint {verb}: {rec['minutes']} minutes, {writing_stats.signed(rec['words'])} words "
                        f"(today {writing_stats.signed(self._stats_brief['todayWords'])})", timeout=12)

    def export_manuscript(self) -> None:
        """Action · Export manuscript: a small form, then the file is written
        in a worker thread to exports/ and its path is shown."""
        if self.project is None:
            return
        self.save_current()
        project = self.project
        info = exporting.describe(project)
        opts = exporting.load_options(project)
        if not next((f["available"] for f in info["formats"] if f["key"] == opts.format), False):
            opts = replace(opts, format=next((f["key"] for f in info["formats"] if f["available"]), "md"))
        summary = exporting.summarize(project, opts)
        if not summary["scenes"]:
            self.notify("There is nothing to export yet: the book has no scenes", severity="warning")
            return
        notes = [m for m in summary["messages"] if "unaccepted AI drafts" not in m]
        if summary["draft_scenes"]:
            notes.insert(0, f"{summary['draft_scenes']} {project.unit}(s) have unaccepted AI drafts; "
                            "their original text is exported unless you tick the box.")
        self.push_screen(ExportScreen(info, opts, exporting.summary_line(summary, project.unit),
                                      notes[:4], project.unit), self._start_export)

    def _start_export(self, opts) -> None:
        if opts is None or self.project is None:
            return
        project = self.project
        self.notify("Exporting...", timeout=3)

        def work() -> None:
            try:
                result = exporting.run_export(project, opts)
            except (ValueError, RuntimeError, OSError) as exc:
                self.call_from_thread(self.notify, str(exc), severity="error", timeout=10)
            else:
                self.call_from_thread(self._export_done, result)

        self.run_worker(work, thread=True, exclusive=True, group="export")

    def _export_done(self, result) -> None:
        pages = f"{result.pages} pages, " if result.pages else ""
        self.notify(f"Exported to {result.rel} ({pages}{result.words:,} words)", timeout=10)
        for warning in result.warnings[:3]:
            self.notify(warning, severity="warning", timeout=10)

    def open_exports_folder(self) -> None:
        """Action · Open exports folder (hands the folder to the desktop; only when picked)."""
        if self.project is None:
            return
        try:
            exporting.open_in_desktop(exporting.resolve_export(self.project, ""))
        except (RuntimeError, OSError) as exc:
            self.notify(str(exc), severity="warning", timeout=6)

    def open_stats(self) -> None:
        """Action · Session stats: today, this session, the last 30 days, streak."""
        if self.stats is None:
            return
        self.save_current()
        summary = self.stats.summary(project_words=self._project_words)
        self.push_screen(StatsScreen(writing_stats.format_summary(summary)))

    def _recount_project_words(self) -> None:
        if self.project is None:
            self._project_words = 0
            return
        total = 0
        for path in self.project.counted_scenes():  # front matter isn't the book
            try:
                text = fsutil.read_text_lenient(path)
                total += drafts.count_words(text, self._originals(text, path))
            except OSError:
                continue
        self._project_words = total
