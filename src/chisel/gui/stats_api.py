"""Writing stats and focus sprints (core/stats.py)."""

from __future__ import annotations

from . import workspace as ws
from ..ai.usage import LEDGER
from ._bridge import bridge


class StatsMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.
    # Personal data in the user state dir, never in the project folder.

    @bridge
    def usage(self) -> dict:
        return {"cost": LEDGER.session_total(), "calls": LEDGER.count()}

    @bridge
    def stats_summary(self) -> dict:
        """The Session stats page: today, this session, the last 30 days, streak."""
        with self._lock:
            project = self._require()
            words = ws.book_words(ws.scene_summaries(project))
            return {"stats": self.stats.summary(project_words=words)}

    @bridge
    def stats_touch(self) -> dict:
        """The author is typing (the editor pings this every few seconds)."""
        with self._lock:
            self._require()
            self.stats.touch()
            return {}

    @bridge
    def sprint_start(self, minutes: int) -> dict:
        with self._lock:
            self._require()
            self.stats.start_sprint(int(minutes))
            return {"sprint": self.stats.sprint_state()}

    @bridge
    def sprint_end(self, cancelled: bool = False) -> dict:
        """End the sprint; its words are recorded in today's stats."""
        with self._lock:
            self._require()
            rec = self.stats.finish_sprint(cancelled=bool(cancelled))
            if rec is None:
                raise ValueError("no sprint is running")
            return {"sprint": rec}
