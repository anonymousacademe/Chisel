"""Optional git sync for the terminal app (core/sync.py). Explicit only: status is the one read-only call that runs by itself.

A mixin for ChiselApp.
"""

from __future__ import annotations

import asyncio
from textual import work
from ..core import sync
from ..core.applog import log_exc
from .syncscreens import MessagePrompt
from .dialogs import ConfirmScreen


class SyncMixin:
    def _schedule_sync(self) -> None:
        """Refresh the git status 2.5 s after a save (trailing; one timer at a time)."""
        if self._sync_timer is None and self.project is not None:
            self._sync_timer = self.set_timer(2.5, self._sync_timer_fired)

    def _sync_timer_fired(self) -> None:
        self._sync_timer = None
        self.refresh_sync()

    @work(exclusive=True, group="sync-status")
    async def refresh_sync(self) -> None:
        if self.project is None:
            return
        root = self.project.root
        try:
            status = await asyncio.to_thread(sync.status, root)
        except Exception as exc:  # a failing git must never disturb writing
            log_exc("git status failed", exc)
            status = None
        self._sync = status
        self.update_status()

    def sync_visible(self, method: str) -> bool:
        """Which sync actions the palette lists: commit/push only inside a
        repository (push only with a remote), init only when there is none."""
        st = self._sync
        if method == "sync_commit_prompt":
            return st is not None
        if method == "sync_push_confirm":
            return st is not None and st.can_push
        if method == "sync_init_confirm":
            return st is None and sync.git_available() and self.project is not None \
                and not sync.in_repository(self.project.root)
        return True

    def _sync_run(self, fn, done) -> None:
        """Run a blocking git call off the UI thread; report the outcome."""
        async def go() -> None:
            try:
                result = await asyncio.to_thread(fn)
            except ValueError as exc:
                self.notify(str(exc), severity="warning", timeout=5)
            except Exception as exc:  # GitError and friends: git's own words
                self.notify(str(exc), severity="error", timeout=8)
            else:
                done(result)
            self.refresh_sync()

        self.run_worker(go(), group="sync-action")

    def sync_commit_prompt(self) -> None:
        """Action · Commit changes: message pre-filled, commits this project folder only."""
        if self.project is None or self._sync is None:
            self.notify("This project is not in a git repository", severity="warning")
            return
        if self._sync.changes == 0:
            self.notify("Nothing to commit: everything is already committed", timeout=3)
            return
        self.save_current()
        root = self.project.root
        st = self._sync

        def _go(message: str | None) -> None:
            if message is None:
                return
            self._sync_run(lambda: sync.commit(root, message),
                           lambda summary: self.notify(f"Committed: {summary}", timeout=4))

        self.push_screen(MessagePrompt(
            f"Commit {st.changes} change(s) in this project folder (enter commits, esc cancels)",
            sync.default_message(st)), _go)

    def sync_push_confirm(self) -> None:
        """Action · Push: asks first, naming the remote. Never forces."""
        st = self._sync
        if self.project is None or st is None or not st.can_push:
            self.notify("No remote is configured for this project", severity="warning")
            return
        root = self.project.root
        url = sync.remote_url(root, st.remote)
        where = f"{st.remote} ({url})" if url else st.remote

        def _go(ok: bool) -> None:
            if ok:
                self.notify("Pushing…", timeout=2)
                self._sync_run(lambda: sync.push(root), lambda s: self.notify(s, timeout=4))

        self.push_screen(ConfirmScreen(
            f"Push branch '{st.branch}' to the remote {where}?\n"
            "This sends your manuscript there. It is never forced.",
            confirm_label="Push"), _go)

    def sync_init_confirm(self) -> None:
        """Action · Initialize git for this project."""
        if self.project is None:
            return
        root = self.project.root

        def _go(ok: bool) -> None:
            if ok:
                self._sync_run(lambda: sync.init(root), lambda _: self.notify(
                    "This folder is now a git repository. Nothing is committed yet.", timeout=4))

        self.push_screen(ConfirmScreen(
            "Turn this project folder into a git repository?\n"
            "A .gitignore hides the index cache (.chisel/). Nothing is committed or pushed.",
            confirm_label="Initialize"), _go)
