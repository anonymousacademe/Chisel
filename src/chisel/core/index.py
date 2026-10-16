"""SQLite index over a project. A rebuildable cache, never the truth (SPEC §2).

Stores: entities, and every wiki-link occurrence (for backlinks). In scenes,
plain-text mentions of entity names/aliases count as links too.
Rebuild with index.rebuild(project) at any time.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from . import drafts, fsutil
from . import entities as ent
from . import scenemeta
from .links import find_all_links, find_citations

SCHEMA = """\
CREATE TABLE IF NOT EXISTS entities (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS links (
    source TEXT NOT NULL,   -- project-relative path of the file containing the link
    target TEXT NOT NULL,   -- raw link target text
    row INTEGER NOT NULL,
    line TEXT NOT NULL      -- full source line, for context display
);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source);
-- research mode: one row per cited key; TEXT without NOCASE, so keys are case-sensitive
CREATE TABLE IF NOT EXISTS citations (
    source TEXT NOT NULL,
    key TEXT NOT NULL,
    row INTEGER NOT NULL,
    line TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_key ON citations(key);
CREATE INDEX IF NOT EXISTS idx_citations_source ON citations(source);
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass(frozen=True)
class Backlink:
    source: str
    row: int  # 0-based
    line: str


class Index:
    def __init__(self, db_path: Path, check_same_thread: bool = True):
        """*check_same_thread=False* lets several threads share the index
        (the GUI serializes calls with its own lock)."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
        self._conn.executescript(SCHEMA)
        self._closed = False
        self.mode = self._get_meta("mode") or "story"   # citations are indexed in research mode only

    def _get_meta(self, name: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE name = ?", (name,)).fetchone()
        return row[0] if row else None

    def set_mode(self, mode: str) -> None:
        """Remember the project's mode; call ``rebuild`` after a change (``needs_rebuild``)."""
        self.mode = mode
        if not self._closed:
            self._conn.execute("INSERT OR REPLACE INTO meta (name, value) VALUES ('mode', ?)", (mode,))
            self._conn.commit()

    def needs_rebuild(self, project) -> bool:
        """True when the project's mode differs from the one this index was built for."""
        return (self._get_meta("mode") or "story") != project.mode

    def close(self) -> None:
        self._closed = True
        self._conn.close()

    # -- writing ----------------------------------------------------------

    def update_file(
        self, rel_path: str, text: str, names: list[str] | None = None
    ) -> None:
        """Re-index one file's links. No-op after close (teardown races).

        *names*: entity names/aliases whose plain mentions also count
        (passed for scenes, not for entity notes).

        Pending AI drafts are blanked before scanning (same-length
        whitespace, newlines kept), so unaccepted text creates no backlinks
        while rows still point at the real file lines.
        """
        if self._closed:
            return
        cur = self._conn.cursor()
        cur.execute("DELETE FROM links WHERE source = ?", (rel_path,))
        cur.execute("DELETE FROM citations WHERE source = ?", (rel_path,))
        text = drafts.blank_pending(text)
        lines = [ln.rstrip() for ln in text.split("\n")]  # "\n" only: matches line_starts
        line_starts = [0]  # offset of each line, for O(log n) offset -> row
        for i, ch in enumerate(text):
            if ch == "\n":
                line_starts.append(i + 1)
        if names is not None:
            # scene details are not prose; only pov / place values can mention
            text = scenemeta.blank(text, keep=scenemeta.MENTION_FIELDS)
        for link in find_all_links(text, names):
            row = bisect_right(line_starts, link.start) - 1
            line = lines[row] if row < len(lines) else ""
            cur.execute(
                "INSERT INTO links (source, target, row, line) VALUES (?, ?, ?, ?)",
                (rel_path, ent.fold(link.target), row, line),
            )
        if self.mode == "research":
            for cite in find_citations(text):
                row = bisect_right(line_starts, cite.start) - 1
                line = lines[row] if row < len(lines) else ""
                for key in dict.fromkeys(r.key for r in cite.refs):
                    cur.execute(
                        "INSERT INTO citations (source, key, row, line) VALUES (?, ?, ?, ?)",
                        (rel_path, key, row, line))
        self._conn.commit()

    def remove_file(self, rel_path: str) -> None:
        if self._closed:
            return
        self._conn.execute("DELETE FROM links WHERE source = ?", (rel_path,))
        self._conn.execute("DELETE FROM citations WHERE source = ?", (rel_path,))
        self._conn.commit()

    def upsert_entity(self, entity: ent.Entity, rel_path: str) -> None:
        if self._closed:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO entities (name, type, path, aliases)"
            " VALUES (?, ?, ?, ?)",
            (entity.name, entity.type, rel_path, "\n".join(entity.aliases)),
        )
        self._conn.commit()

    # -- reading ----------------------------------------------------------

    def backlinks(self, entity: ent.Entity) -> list[Backlink]:
        """Every line linking to or mentioning *entity* (by name or alias)."""
        if self._closed:
            return []
        names = [ent.fold(n) for n in entity.names]
        placeholders = ",".join("?" for _ in names)
        rows = self._conn.execute(
            f"SELECT DISTINCT source, row, line FROM links"
            f" WHERE target COLLATE NOCASE IN ({placeholders})"
            f" ORDER BY source, row",
            names,
        ).fetchall()
        return [Backlink(source=r[0], row=r[1], line=r[2]) for r in rows]

    def citers(self, key: str) -> list[Backlink]:
        """Every line citing the source *key* (exact, case-sensitive match)."""
        if self._closed:
            return []
        rows = self._conn.execute(
            "SELECT DISTINCT source, row, line FROM citations WHERE key = ? ORDER BY source, row",
            (key,)).fetchall()
        return [Backlink(source=r[0], row=r[1], line=r[2]) for r in rows]

    def rebuild(self, project) -> None:
        """Drop everything and re-index from disk. `project` is core.Project."""
        self.set_mode(project.mode)
        cur = self._conn.cursor()
        cur.execute("DELETE FROM links")
        cur.execute("DELETE FROM citations")
        cur.execute("DELETE FROM entities")
        self._conn.commit()
        names: list[str] = []
        for path in project.list_entity_files():
            entity = ent.load_entity(path)
            names.extend(entity.names)
            self.upsert_entity(entity, path.relative_to(project.root).as_posix())
        scenes = set(project.all_scene_files())
        for path in project.all_markdown_files():
            rel = path.relative_to(project.root).as_posix()
            self.update_file(rel, fsutil.read_text_lenient(path),
                             names if path in scenes else None)
