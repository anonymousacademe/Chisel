"""Snapshots (core/snapshots.py) and optional git sync (core/sync.py; explicit actions only)."""

from __future__ import annotations

from pathlib import Path
from . import workspace as ws
from ..core import drafts, snapshots, sync
from ._bridge import bridge


class VersionsMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    @staticmethod
    def _iso(when) -> str:
        return when.isoformat(timespec="seconds")

    def _snapshot_at(self, path: Path) -> str | None:
        """ISO local time of the scene's latest snapshot (status bar), or None."""
        when = snapshots.latest_time(self._require(), path)
        return self._iso(when) if when else None

    def _snapshot_row(self, snap, current_words: int) -> dict:
        return {"id": snap.name, "label": snap.label, "when": self._iso(snap.when),
                "words": snap.words,
                "delta": current_words - snap.words}

    @bridge
    def list_snapshots(self, doc_id: str, text: str | None = None) -> dict:
        """The open scene's snapshots, newest first, with words and the change
        in words against the current text (the editor's buffer if given)."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            if text is None:
                text, originals = ws.read_text(project, path)
            else:
                originals = drafts.load_originals(project.root, path)
            now = drafts.count_words(text, originals)
            return {"items": [self._snapshot_row(s, now)
                              for s in snapshots.list_snapshots(project, path)],
                    "words": now, "snapshotAt": self._snapshot_at(path)}

    @bridge
    def create_snapshot(self, doc_id: str, label: str = "", text: str | None = None) -> dict:
        """Snapshot the scene now (the editor's buffer if given, so unsaved
        words are kept too)."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            snap = snapshots.create(project, path, label, text)
            return {"id": snap.name, "snapshotAt": self._iso(snap.when)}

    @bridge
    def compare_snapshot(self, doc_id: str, snapshot_id: str, text: str | None = None) -> dict:
        """Word-level diff of snapshot -> current text, as segments
        ``{op, old, new}`` (concatenating ``old`` gives the snapshot back,
        ``new`` the current text)."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            old = snapshots.read_text(project, path, snapshot_id)
            new = text if text is not None else path.read_text(encoding="utf-8")
            segs = snapshots.diff_words(old, new)
            added, removed = snapshots.diff_stats(segs)
            return {"segments": [{"op": s.op, "old": s.old, "new": s.new} for s in segs],
                    "added": added, "removed": removed}

    @bridge
    def restore_snapshot(self, doc_id: str, snapshot_id: str,
                         text: str | None = None) -> dict:
        """Make the scene read as the snapshot. The current text (the editor's
        buffer) is snapshotted first. Writes the file: the client must detach
        its save controller and reopen the document."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            restored = snapshots.restore(project, path, snapshot_id, text)
            self._index_file(path, "scene", restored)
            if self.stats is not None:  # restoring is not writing: new baseline
                self.stats.seen(self._scene_key(path), self._author_words(project, path, restored))
            return {"snapshotAt": self._snapshot_at(path)}

    @bridge
    def delete_snapshot(self, doc_id: str, snapshot_id: str) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            snapshots.delete(self._require(), path, snapshot_id)
            return {"snapshotAt": self._snapshot_at(path)}

    @bridge
    def snapshot_all(self, label: str = "") -> dict:
        """One snapshot per scene (book and Unplaced), all with one label."""
        with self._lock:
            return {"count": snapshots.snapshot_all(self._require(), label)}

    @bridge
    def start_new_draft(self) -> dict:
        """Snapshot every scene as ``end-of-draft-N`` and count up to the next draft."""
        with self._lock:
            project = self._require()
            previous = project.draft
            return {"draft": project.start_new_draft(), "previous": previous}

    def _project_root(self) -> Path:
        with self._lock:
            return self._require().root

    @staticmethod
    def sync_payload(root: Path) -> dict | None:
        """What the status bar needs; None when git is not installed (item hidden).
        Shared by the TUI-independent bridge methods below."""
        if not sync.git_available():
            return None
        st = sync.status(root)
        if st is None:
            return {"repo": False, "canInit": sync.can_init(root), "label": "Sync"}
        return {
            "repo": True, "canInit": False, "state": st.state, "label": st.label,
            "changes": st.changes, "scenes": st.scenes, "ahead": st.ahead, "behind": st.behind,
            "branch": st.branch, "remote": st.remote, "canPush": st.can_push,
            "remoteUrl": sync.remote_url(root, st.remote) if st.remote else "",
            "toplevel": st.toplevel,
            "defaultMessage": sync.default_message(st) if st.changes else "",
        }

    @bridge
    def sync_status(self) -> dict:
        """Git state of the project folder. Read-only; the lock is not held while git runs."""
        return {"sync": self.sync_payload(self._project_root())}

    @bridge
    def sync_commit(self, message: str) -> dict:
        """Commit the project folder (only on the author's click)."""
        root = self._project_root()
        summary = sync.commit(root, message)
        return {"summary": summary, "sync": self.sync_payload(root)}

    @bridge
    def sync_push(self) -> dict:
        """Push the current branch (only on the author's click; never forced)."""
        root = self._project_root()
        summary = sync.push(root)
        return {"summary": summary, "sync": self.sync_payload(root)}

    @bridge
    def sync_init(self) -> dict:
        """Make the project folder a git repository (only on the author's click)."""
        root = self._project_root()
        sync.init(root)
        return {"sync": self.sync_payload(root)}
