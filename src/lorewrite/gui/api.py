"""The bridge between the React UI and the Python core.

Every public method of Api is callable from JavaScript (pywebview's js_api, or
the devserver's POST /api/<method>). Contract: JSON in, JSON out, always
``{"ok": true, ...}`` or ``{"ok": false, "error": "..."}`` — never raise across
the bridge. No pywebview import here, so this is unit-testable.
"""

from __future__ import annotations

import functools
import os
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from ..ai.client import (
    MODEL_DEFAULTS,
    clear_api_key as _clear_api_key,
    get_api_key,
    list_models as _list_models,
    resolve_model,
    set_api_key as _set_api_key,
)
from ..ai.continuity import check_scene, propose_canon_updates
from ..ai.links import alias_form, suggest_links
from ..ai.style import learn_style
from ..ai.usage import LEDGER
from ..ai.writing import (
    ask as ask_writer,
    build_context,
    build_project_context,
    research_context,
    generate as generate_text,
    research_answer as research_writer,
)
from ..core import collections as coll
from ..core import comments
from ..core import research as research_notes
from ..core import drafts, scenemeta, snapshots, sync
from ..core import settings as user_settings
from ..core import spelling
from ..core import entities as ent
from ..core.index import Index
from ..core.continuity import (
    apply_canon_update,
    canon_map,
    clear_scene_waivers,
    filter_waived,
    load_waivers,
    locate_evidence,
    save_waiver,
)
from ..core.project import Project, default_project_path, write_atomic
from ..core.spans import compute_spans, from_utf16, index_to_utf16, to_utf16
from ..core.style import (
    ensure_style_stub, load_style, manuscript_stats, sample_manuscript, save_style,
    select_voice_samples, style_info,
)
from ..core.recents import add_recent, load_recents
from ..core.style import style_path
from . import workspace as ws


# Errors the core raises on purpose, with a message written for the author:
# shown as-is. Anything else keeps its class name (it is a bug worth reporting).
USER_ERRORS = (ValueError, FileNotFoundError, FileExistsError, LookupError, IndexError, RuntimeError,
               sync.GitError)


def bridge(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Wrap an Api method: exceptions become ``{"ok": False, "error": ...}``."""

    @functools.wraps(fn)
    def wrapper(self: "Api", *args: Any, **kwargs: Any) -> dict:
        try:
            result = fn(self, *args, **kwargs)
        except Exception as exc:  # the bridge never raises
            message = str(exc) if type(exc) in USER_ERRORS else f"{type(exc).__name__}: {exc}"
            return {"ok": False, "error": message}
        if not isinstance(result, dict):
            result = {"value": result}
        result.setdefault("ok", True)
        return result

    wrapper.__bridge__ = True  # type: ignore[attr-defined]
    return wrapper


class Api:
    def __init__(self) -> None:
        self._lock = threading.RLock()  # guards every project write
        self._window: Any = None  # set by gui.app once the window exists
        self.project: Project | None = None
        self.index: Index | None = None
        self.entities: list[ent.Entity] = []
        self._session_start = time.time()
        self._baseline_words = 0
        self._spell_ignores = spelling.SessionIgnores()  # in memory only

    @bridge
    def ping(self) -> dict:
        return {"pong": True}

    # -- project --------------------------------------------------------------

    def _require(self) -> Project:
        if self.project is None:
            raise RuntimeError("no project is open")
        return self.project

    def _load(self, project: Project) -> None:
        """Make *project* the open project: index, entities, session baseline."""
        if self.index is not None:
            self.index.close()
        self.project = project
        self.index = Index(project.index_path, check_same_thread=False)
        self.index.rebuild(project)
        self.reload_entities()
        add_recent(project.root, project.title)
        self._session_start = time.time()
        self._baseline_words = ws.book_words(ws.scene_summaries(project))

    def reload_entities(self) -> None:
        self.entities = self._require().load_entities()

    @bridge
    def open_project(self, path: str) -> dict:
        root = Path(path).expanduser()
        if not Project.is_project(root):
            raise FileNotFoundError(f"no {root / 'project.toml'} - not a lorewrite project")
        with self._lock:
            self._load(Project.open(root))
        return {}

    @bridge
    def new_project(self, title: str, path: str = "") -> dict:
        title = title.strip()
        if not title:
            raise ValueError("a project needs a title")
        root = Path(path).expanduser() if path.strip() else default_project_path(title)
        if Project.is_project(root):
            raise FileExistsError(f"{root} already holds a project")
        with self._lock:
            self._load(Project.create(root, title))
        return {}

    @bridge
    def suggest_project_path(self, title: str) -> dict:
        """Default folder for a new project with this title (~/novels/<slug>)."""
        path = default_project_path(title)
        return {"path": str(path) if path else ""}

    @bridge
    def recent_projects(self) -> dict:
        return {"recents": [
            {"path": str(r.path), "title": r.title, "openedAt": r.opened_at,
             "exists": Project.is_project(r.path)}
            for r in load_recents()]}

    @bridge
    def choose_folder(self) -> dict:
        """Native folder picker (only in the real window)."""
        if self._window is None:
            return {"path": None}
        import webview

        folder = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        picked = self._window.create_file_dialog(
            folder if folder is not None else webview.FOLDER_DIALOG)
        return {"path": str(picked[0]) if picked else None}

    @bridge
    def get_workspace(self) -> dict:
        with self._lock:
            if self.project is None:
                return {"workspace": None}
            return {"workspace": ws.build_workspace(
                self.project, self.entities,
                baseline_words=self._baseline_words,
                session_minutes=int((time.time() - self._session_start) // 60),
                ai_cost=LEDGER.session_total())}

    # -- documents ------------------------------------------------------------

    def _doc_kind(self, path: Path) -> str | None:
        project = self._require()
        if project.is_scene_path(path):
            return "scene"
        if path.parent.parent == project.entities_dir.resolve():
            return "entity"
        if path == style_path(project).resolve():
            return "style"
        if path == spelling.project_dictionary_path(project).resolve():
            return "dictionary"
        if research_notes.is_research_path(project, path):
            return "research"
        return None

    def resolve_document(self, doc_id: str) -> tuple[Path, str]:
        """The file behind a document id (a project-relative .md path), or
        ValueError. Ids never escape the project or name non-note files."""
        project = self._require()
        path = (project.root / doc_id).resolve()
        if not path.is_relative_to(project.root.resolve()) or (
                path.suffix != ".md" and doc_id != ws.DICTIONARY_ID):
            raise ValueError("invalid document id")
        kind = self._doc_kind(path)
        if kind is None or not path.is_file():
            raise FileNotFoundError(f"no such document: {doc_id}")
        return path, kind

    @bridge
    def read_document(self, doc_id: str) -> dict:
        with self._lock:
            project = self._require()
            path, kind = self.resolve_document(doc_id)
            text, originals = ws.read_text(project, path)
            entity = ent.load_entity(path) if kind == "entity" else None
            title, _ = ws.split_title(text)
            extra: dict = {}
            if kind == "scene":
                title = title or path.stem
                kicker = ws.scene_kicker(project, path)
                part = project.part_of(path)
                parent = (project.part_title(part) if part
                          else "Unplaced Scenes" if project.is_unplaced(path) else "Manuscript")
                extra = {
                    "details": scenemeta.details(text),
                    "bodyStart": index_to_utf16(text, scenemeta.body_offset(text)),
                    "partId": ws.part_id(project, part) if part else None,
                    "frontMatter": project.is_front_matter(path),
                    "unplaced": project.is_unplaced(path),
                    "snapshotAt": self._snapshot_at(path),
                }
            elif kind == "entity":
                title, kicker, parent = entity.name, entity.type.upper(), "Notes"
            elif kind == "dictionary":
                title, kicker, parent = "Dictionary", "DICTIONARY", "Project"
            elif kind == "research":
                title = research_notes.title_of(path, text)
                kicker, parent = "RESEARCH", "Research"
            else:
                title, kicker, parent = "Style guide", "STYLE GUIDE", "Project"
            mentions = (ws.scene_context(text, self.entities, self.index)
                        if kind == "scene" else [])
            return {
                "id": doc_id, "kind": kind, "title": title, "kicker": kicker,
                "parent": parent, "text": text,
                "mtime": str(path.stat().st_mtime_ns),
                "words": drafts.count_words(text, originals),
                "mentions": mentions,
                **extra,
            }

    def _all_names(self) -> list[str]:
        return [n for e in self.entities for n in e.names]

    def _index_file(self, path: Path, kind: str, text: str) -> None:
        """Refresh derived state after *path* was written with *text*."""
        project = self._require()
        if kind in ("style", "dictionary", "research"):
            return  # not part of the link index
        self.index.update_file(ws.rel_id(project, path), text,
                               self._all_names() if kind == "scene" else None)
        if kind == "entity":
            before = self._all_names()
            self.reload_entities()
            if self._all_names() != before:  # aliases edited in a note:
                self.index.rebuild(project)   # earlier scenes may mention them

    @bridge
    def document_mtime(self, doc_id: str) -> dict:
        with self._lock:
            path, _ = self.resolve_document(doc_id)
            return {"mtime": str(path.stat().st_mtime_ns)}

    @bridge
    def save_document(self, doc_id: str, text: str, base_mtime: str | None,
                      force: bool = False) -> dict:
        """Write *text* atomically and re-index. If the file changed on disk
        since *base_mtime* (the TUI may be open on the same project) nothing is
        written and ``conflict`` is returned, unless *force* (keep mine) or the
        disk text already equals *text*. A deleted document is never recreated.
        """
        with self._lock:
            project = self._require()
            path, kind = self.resolve_document(doc_id)  # FileNotFoundError if gone
            current = str(path.stat().st_mtime_ns)
            if not force and base_mtime is not None and current != str(base_mtime):
                if path.read_text(encoding="utf-8") != text:
                    return {"saved": False, "conflict": True, "mtime": current}
            else:
                if kind == "scene" and snapshots.auto_enabled():
                    snapshots.ensure_daily(project, path, text)
                write_atomic(path, text)
                current = str(path.stat().st_mtime_ns)
            self._index_file(path, kind, text)
            _, originals = ws.read_text(project, path)
            return {"saved": True, "mtime": current,
                    "words": drafts.count_words(text, originals),
                    **({"snapshotAt": self._snapshot_at(path)} if kind == "scene" else {})}

    @bridge
    def link_spans(self, doc_id: str, text: str) -> dict:
        """Mentions, links, pending drafts and expand markers of *text* (the
        editor's unsaved buffer), offsets in UTF-16 units."""
        with self._lock:
            _, kind = self.resolve_document(doc_id)
            spans = compute_spans(text, self.entities, mentions=kind == "scene")
            return {"spans": to_utf16(text, spans)}

    @bridge
    def scene_context(self, doc_id: str, text: str | None = None) -> dict:
        """Entities a scene mentions (count here, backlinks project-wide). *text*
        is the editor buffer; default the file on disk."""
        with self._lock:
            project = self._require()
            path, kind = self.resolve_document(doc_id)
            if kind != "scene":
                return {"mentions": []}
            if text is None:
                text, _ = ws.read_text(project, path)
            return {"mentions": ws.scene_context(text, self.entities, self.index)}

    # -- spelling ---------------------------------------------------------------

    @staticmethod
    def spellcheck_enabled() -> bool:
        return bool(user_settings.get("spellcheck", True))

    @bridge
    def spelling(self, doc_id: str, text: str) -> dict:
        """Misspelled words in the editor buffer (scenes only, when the setting
        is on), offsets in UTF-16 units. Computed outside the lock: it is pure
        and can take a moment on a long scene."""
        with self._lock:
            project = self._require()
            _, kind = self.resolve_document(doc_id)
            if kind != "scene" or not self.spellcheck_enabled():
                return {"enabled": False, "spans": []}
            accepted = spelling.accepted_terms(
                project, entities=self.entities,
                ignored=self._spell_ignores.for_project(project.root))
        found = spelling.check(text, accepted)
        spans = to_utf16(text, [{"start": m.start, "end": m.end, "word": m.word}
                                for m in found])
        return {"enabled": True, "spans": spans}

    @bridge
    def spelling_suggestions(self, word: str) -> dict:
        return {"suggestions": spelling.suggestions(str(word))}

    @bridge
    def add_to_dictionary(self, term: str, scope: str = "project") -> dict:
        """Never flag *term* (a word or phrase) again: in this project's
        dictionary.txt, or in the personal one shared by all projects."""
        with self._lock:
            if scope == "project":
                path = spelling.project_dictionary_path(self._require())
            elif scope == "personal":
                path = spelling.personal_dictionary_path()
            else:
                raise ValueError("scope must be 'project' or 'personal'")
            if not " ".join(str(term).split()):
                raise ValueError("nothing to add")
            return {"added": spelling.add_to_dictionary(path, str(term))}

    @bridge
    def ignore_word(self, word: str) -> dict:
        """Ignore *word* until the app is closed (not saved anywhere)."""
        with self._lock:
            self._spell_ignores.add(self._require().root, str(word))
        return {}

    @bridge
    def open_dictionary(self) -> dict:
        """Create dictionary.txt (with a comment header) if missing; its id."""
        with self._lock:
            spelling.ensure_dictionary(spelling.project_dictionary_path(self._require()))
            return {"id": ws.DICTIONARY_ID}

    # -- entities -------------------------------------------------------------

    @bridge
    def list_entities(self) -> dict:
        with self._lock:
            return {"entities": ws.entity_summaries(self._require(), self.entities)}

    @bridge
    def get_entity(self, name: str) -> dict:
        """The note behind a link target (name or alias), or found=false."""
        with self._lock:
            project = self._require()
            entity = ent.resolve(name, self.entities)
            if entity is None or entity.path is None:
                return {"found": False, "name": name}
            return {"found": True, **ws.entity_payload(project, entity, self.index)}

    def _entities_changed(self) -> None:
        """Names/aliases changed: earlier scenes may now mention them."""
        self.reload_entities()
        self.index.rebuild(self._require())

    @bridge
    def create_entity(self, name: str, etype: str) -> dict:
        name = " ".join(name.split())
        if not name or "/" in name or "\\" in name:
            raise ValueError("a note needs a simple name")
        if etype not in ent.VALID_TYPES:
            raise ValueError(f"type must be one of {', '.join(ent.VALID_TYPES)}")
        with self._lock:
            project = self._require()
            existing = ent.resolve(name, self.entities)
            if existing is not None and existing.path is not None:
                return {"id": ws.rel_id(project, existing.path),
                        "name": existing.name, "existed": True}
            entity, path = project.create_entity(name, etype)
            self._entities_changed()
            return {"id": ws.rel_id(project, path), "name": entity.name,
                    "existed": False}

    @bridge
    def add_alias(self, name: str, alias: str) -> dict:
        alias = " ".join(alias.split())
        if not alias:
            raise ValueError("an alias can't be empty")
        with self._lock:
            entity = ent.resolve(name, self.entities)
            if entity is None:
                raise LookupError(f"no note named {name!r}")
            ent.add_alias(entity, alias)
            self._entities_changed()
            return {}

    # -- scenes ---------------------------------------------------------------

    def _scene_path(self, doc_id: str) -> Path:
        path, kind = self.resolve_document(doc_id)
        if kind != "scene":
            raise ValueError("not a scene")
        return path

    def _rel_map(self) -> dict[str, str]:
        """{old id: new id} of what the last renaming operation moved, so a UI
        can follow the file it has open (renumbering renames neighbours too)."""
        project = self._require()
        out = {}
        for old, new in project.last_renames.items():
            try:
                out[ws.rel_id(project, old)] = ws.rel_id(project, new)
            except ValueError:
                continue
        return out

    @bridge
    def new_scene(self, title: str, part_id: str | None = None,
                  near_id: str | None = None) -> dict:
        """Create a scene at the end of *part_id* (a "part:..." id); without
        one, in the part of *near_id* (the open scene), else the last part."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("a scene needs a title")
        with self._lock:
            project = self._require()
            if part_id:
                part = ws.part_for_id(project, part_id)
            else:
                near = None
                if near_id:
                    try:
                        near = self._scene_path(near_id)
                    except (ValueError, FileNotFoundError):
                        near = None
                part = project.default_part_for_new(near)
            path = project.next_scene_path(title, part)
            path.parent.mkdir(parents=True, exist_ok=True)
            text = f"# {title}\n\n"
            write_atomic(path, text)
            self._index_file(path, "scene", text)
            return {"id": ws.rel_id(project, path)}

    @bridge
    def rename_scene(self, doc_id: str, title: str) -> dict:
        """Retitle the scene's file on disk. Callers flush their own unsaved
        edits first and reload the document afterwards."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("a scene needs a title")
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            project.rename_scene(path, title)
            self._index_file(path, "scene", path.read_text(encoding="utf-8"))
            return {"id": doc_id}

    @bridge
    def move_scene(self, doc_id: str, delta: int) -> dict:
        """Swap with the neighbouring scene inside the same part."""
        with self._lock:
            project = self._require()
            new_path = project.move_scene(self._scene_path(doc_id), int(delta))
            if new_path is None:
                raise ValueError("the scene is already at the edge of its part")
            self.index.rebuild(project)  # two files changed names
            return {"id": ws.rel_id(project, new_path), "remap": self._rel_map()}

    @bridge
    def place_scene(self, doc_id: str, part_id: str | None = None,
                    index: int | None = None, unplaced: bool = False) -> dict:
        """Move a scene into *part_id* (None = the unparted top level) at the
        0-based *index* (default the end), or into Unplaced Scenes. Used by
        "Move to part", drag-to-reorder and Place in the book."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            part = None if unplaced else ws.part_for_id(project, part_id)
            new = project.place_scene(path, part, None if index is None else int(index),
                                      unplaced=bool(unplaced))
            self.index.rebuild(project)
            remap = self._rel_map()
            return {"id": ws.rel_id(project, new), "remap": remap}

    @bridge
    def delete_scene(self, doc_id: str) -> dict:
        """Move the scene (and its draft sidecar) to the Trash."""
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            rel = ws.rel_id(project, path)
            project.delete_scene(path)
            self.index.remove_file(rel)
            return {}

    # -- parts ----------------------------------------------------------------

    @bridge
    def new_part(self, title: str) -> dict:
        with self._lock:
            part = self._require().new_part(title)
            return {"id": ws.part_id(self.project, part)}

    @bridge
    def rename_part(self, part_id: str, title: str) -> dict:
        with self._lock:
            project = self._require()
            project.rename_part(ws.part_for_id(project, part_id), title)
            return {"id": part_id}

    @bridge
    def move_part(self, part_id: str, delta: int) -> dict:
        with self._lock:
            project = self._require()
            new = project.move_part(ws.part_for_id(project, part_id), int(delta))
            if new is None:
                raise ValueError("the part is already at the edge")
            self.index.rebuild(project)
            return {"id": ws.part_id(project, new), "remap": self._rel_map()}

    @bridge
    def delete_part(self, part_id: str) -> dict:
        """Delete an empty part (move or trash its scenes first)."""
        with self._lock:
            project = self._require()
            project.delete_part(ws.part_for_id(project, part_id))
            return {}

    # -- trash ------------------------------------------------------------------

    @bridge
    def list_trash(self) -> dict:
        with self._lock:
            project = self._require()
            return {"items": [{
                "name": i.name, "title": i.title,
                "original": i.original.removeprefix("manuscript/"),
                "deleted": i.deleted.strftime("%Y-%m-%d %H:%M"),
            } for i in project.list_trash()]}

    @bridge
    def restore_trash(self, name: str) -> dict:
        """Back to the end of its original part (Unplaced if the part is gone)."""
        with self._lock:
            project = self._require()
            path = project.restore_scene(name)
            self.index.rebuild(project)
            return {"id": ws.rel_id(project, path),
                    "unplaced": project.is_unplaced(path)}

    @bridge
    def delete_forever(self, name: str) -> dict:
        with self._lock:
            self._require().delete_forever(name)
            return {}

    @bridge
    def empty_trash(self) -> dict:
        with self._lock:
            return {"deleted": self._require().empty_trash()}

    # -- snapshots and drafts -----------------------------------------------------

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

    # -- sync (git, explicit actions only) ----------------------------------------

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

    # -- scene details ----------------------------------------------------------

    @bridge
    def set_scene_details(self, doc_id: str, text: str, fields: dict) -> dict:
        """Apply detail fields (pov, place, purpose, status, target, collections)
        to the editor's *text*. Returns the edit that replaces the frontmatter
        block (UTF-16 offsets) for the editor to dispatch; nothing is written
        here, the normal autosave persists it."""
        with self._lock:
            self._scene_path(doc_id)
            new = scenemeta.set_details(text, **fields)
            old_end, new_end = scenemeta.body_offset(text), scenemeta.body_offset(new)
            return {
                "edit": {"from": 0, "to": index_to_utf16(text, old_end),
                         "insert": new[:new_end]},
                "details": scenemeta.details(new),
                "bodyStart": index_to_utf16(new, new_end),
            }

    # -- research ---------------------------------------------------------------------
    # Plain Markdown notes in research/ (core.research): not scenes, not entities, not indexed.

    def _research_payload(self) -> dict:
        project = self._require()
        return {"research": ws.research_summaries(project)}

    @bridge
    def new_research_note(self, title: str) -> dict:
        with self._lock:
            path = research_notes.new_note(self._require(), title)
            return {"id": ws.rel_id(self._require(), path)}

    @bridge
    def new_research_from_url(self, url: str, title: str = "") -> dict:
        """A note holding just the link and a title; the page is never fetched."""
        with self._lock:
            project = self._require()
            path = research_notes.note_from_url(project, url, title)
            return {"id": ws.rel_id(project, path), "title": research_notes.title_of(path)}

    @bridge
    def delete_research_note(self, doc_id: str) -> dict:
        """Delete a research note for good (the UI confirms first)."""
        with self._lock:
            path, kind = self.resolve_document(doc_id)
            if kind != "research":
                raise ValueError("not a research note")
            research_notes.delete_note(self._require(), path)
            return {}

    @bridge
    def research(self, prompt: str, history: list | None = None) -> dict:
        """Chat: answer a question from the research notes and the project canon
        (keyword retrieval, no web). Returns the reply and the notes it was given
        (`sources`, in citation order). The manuscript is never touched."""
        with self._lock:
            project = self._require()
            entities = list(self.entities)
            context, hits = research_context(project, entities, canon_map(entities), prompt)
            sources = [{"id": ws.rel_id(project, h.note.path), "title": h.note.title,
                        "score": h.score} for h in hits]
            model = resolve_model("writing", project.meta)
            calls = LEDGER.count()
        reply = research_writer(prompt, context, model, history=history)
        return {"reply": reply, "sources": sources, "cost": self._spent(calls)}

    # -- comments ---------------------------------------------------------------------
    # Author notes anchored to a passage (core.comments), in .comments/<scene>.json - never in the
    # prose. Positions are computed against the editor's text (UTF-16 for CodeMirror).

    def _comment_rows(self, path: Path, text: str) -> list[dict]:
        project = self._require()
        rows = []
        for p in comments.reanchor(project.root, path, text):
            c = p.comment
            rows.append({
                **c.as_dict(), "detached": p.detached,
                "start": None if p.start is None else index_to_utf16(text, p.start),
                "end": None if p.end is None else index_to_utf16(text, p.end),
                "row": None if p.start is None else text.count("\n", 0, p.start),
            })
        return rows

    def _comment_text(self, path: Path, text: str | None) -> str:
        return text if text is not None else path.read_text(encoding="utf-8")

    @bridge
    def list_comments(self, doc_id: str, text: str | None = None) -> dict:
        """The scene's comments, detached ones first, then top to bottom."""
        with self._lock:
            path = self._scene_path(doc_id)
            text = self._comment_text(path, text)
            return {"comments": self._comment_rows(path, text)}

    @bridge
    def add_comment(self, doc_id: str, text: str, start: int, end: int, body: str) -> dict:
        """Comment on text[start:end] (UTF-16 offsets into the editor's *text*)."""
        with self._lock:
            path = self._scene_path(doc_id)
            c = comments.add(self._require().root, path, text,
                             from_utf16(text, start), from_utf16(text, end), body)
            return {"id": c.id, "comments": self._comment_rows(path, text)}

    @bridge
    def edit_comment(self, doc_id: str, comment_id: str, body: str, text: str | None = None) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            comments.edit(self._require().root, path, comment_id, body)
            return {"comments": self._comment_rows(path, self._comment_text(path, text))}

    @bridge
    def resolve_comment(self, doc_id: str, comment_id: str, resolved: bool = True,
                        text: str | None = None) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            comments.resolve(self._require().root, path, comment_id, resolved)
            return {"comments": self._comment_rows(path, self._comment_text(path, text))}

    @bridge
    def delete_comment(self, doc_id: str, comment_id: str, text: str | None = None) -> dict:
        with self._lock:
            path = self._scene_path(doc_id)
            comments.delete(self._require().root, path, comment_id)
            return {"comments": self._comment_rows(path, self._comment_text(path, text))}

    # -- collections ----------------------------------------------------------------
    # Definitions: project.toml [collections]. Membership: each scene's frontmatter, which a
    # scene's own editor changes through set_scene_details (fields={"collections": [...]}); the
    # calls below rewrite the other scenes' files, so the client flushes first and reopens after.

    def _collections_payload(self) -> dict:
        project = self._require()
        return {"collections": ws.collection_summaries(project, ws.scene_summaries(project))}

    def _ids(self, paths) -> list[str]:
        project = self._require()
        return [ws.rel_id(project, p) for p in paths]

    @bridge
    def list_collections(self) -> dict:
        with self._lock:
            return self._collections_payload()

    @bridge
    def create_collection(self, name: str, color: str = "violet") -> dict:
        with self._lock:
            coll.create(self._require(), name, color)
            return self._collections_payload()

    @bridge
    def recolor_collection(self, name: str, color: str) -> dict:
        with self._lock:
            coll.recolor(self._require(), name, color)
            return self._collections_payload()

    @bridge
    def rename_collection(self, name: str, new_name: str) -> dict:
        with self._lock:
            changed = coll.rename(self._require(), name, new_name)
            return {**self._collections_payload(), "changed": self._ids(changed)}

    @bridge
    def delete_collection(self, name: str) -> dict:
        """Remove the collection and its membership from every scene (no scene is deleted)."""
        with self._lock:
            changed = coll.delete(self._require(), name)
            return {**self._collections_payload(), "changed": self._ids(changed)}

    @bridge
    def set_unit(self, unit: str) -> dict:
        """Call the manuscript's units "scene" or "chapter" (labels only)."""
        with self._lock:
            self._require().update_manuscript_settings(unit=unit)
            return {"unit": unit}

    @bridge
    def rebuild_index(self) -> dict:
        with self._lock:
            project = self._require()
            self.index.rebuild(project)
            self.reload_entities()
            return {}

    # -- settings ---------------------------------------------------------------

    EDITOR_DEFAULTS = {"zoom": 100, "reflow": True}
    ZOOMS = (90, 100, 110, 125)

    @bridge
    def get_settings(self) -> dict:
        """Everything the settings dialog shows. The API key itself is never sent."""
        project = self.project
        meta = project.meta if project else None
        overrides = (meta or {}).get("ai") or {}
        source = "none"
        if os.environ.get("OPENROUTER_API_KEY"):
            source = "environment"
        elif get_api_key():
            source = "keyring"
        models = {}
        for kind in ("fast", "strong", "writing"):
            key = f"{kind}_model"
            models[kind] = {
                "value": user_settings.get(key) or "",       # what the user chose ("" = default)
                "default": MODEL_DEFAULTS[kind],
                "effective": resolve_model(kind, meta),
                "projectOverride": str(overrides.get(key) or ""),
            }
        editor = {k: user_settings.get(f"gui_{k}", v) for k, v in self.EDITOR_DEFAULTS.items()}
        return {"hasKey": source != "none", "keySource": source, "models": models, "editor": editor,
                "spellcheck": self.spellcheck_enabled(),
                "autoSnapshot": snapshots.auto_enabled()}

    @bridge
    def set_settings(self, models: dict | None = None, editor: dict | None = None,
                     spellcheck: bool | None = None,
                     auto_snapshot: bool | None = None) -> dict:
        """Save model choices ("" resets to the default), GUI editor prefs and
        the spell-check toggle (shared with the TUI)."""
        with self._lock:
            for kind, value in (models or {}).items():
                if kind not in MODEL_DEFAULTS:
                    raise ValueError(f"unknown model kind: {kind}")
                value = str(value or "").strip()
                user_settings.set(f"{kind}_model", value or None)
            for key, value in (editor or {}).items():
                if key == "zoom":
                    value = int(value)
                    if value not in self.ZOOMS:
                        raise ValueError(f"zoom must be one of {self.ZOOMS}")
                elif key == "reflow":
                    value = bool(value)
                else:
                    raise ValueError(f"unknown editor setting: {key}")
                user_settings.set(f"gui_{key}", value)
            if spellcheck is not None:
                user_settings.set("spellcheck", bool(spellcheck))
            if auto_snapshot is not None:
                user_settings.set("auto_snapshot", bool(auto_snapshot))
        return {}

    @bridge
    def set_api_key(self, key: str) -> dict:
        key = (key or "").strip()
        if not key:
            raise ValueError("paste your OpenRouter API key first")
        try:
            _set_api_key(key)
        except Exception as exc:
            raise RuntimeError(
                f"The system keyring is unavailable ({exc}). Set the "
                "OPENROUTER_API_KEY environment variable instead.") from exc
        return {}

    @bridge
    def clear_api_key(self) -> dict:
        _clear_api_key()
        env = bool(os.environ.get("OPENROUTER_API_KEY"))
        return {"stillSet": env, "note": (
            "The key stored in the keyring was removed, but OPENROUTER_API_KEY is "
            "still set in the environment." if env else "")}

    @bridge
    def list_models(self, structured_only: bool = True) -> dict:
        """The OpenRouter model catalog (public, needs network). Structured-output
        models only for the fast/strong pickers; the whole catalog for writing."""
        models = _list_models(structured_only=structured_only)
        return {"models": [{
            "id": m.id, "name": m.name, "promptPerM": m.prompt_per_m,
            "completionPerM": m.completion_per_m, "context": m.context_length,
        } for m in models]}

    # -- AI ---------------------------------------------------------------------
    # Every AI call gathers its inputs under the lock, releases it for the slow
    # network round trip (so saves and reads stay responsive), and re-locks only
    # to write. Nothing here edits prose: results are suggestions the UI must
    # confirm, and generated text only ever comes back wrapped as a draft.

    def _scene_inputs(self, doc_id: str, text: str | None) -> dict:
        """Snapshot what an AI call over one scene needs (call with the lock held)."""
        project = self._require()
        path, kind = self.resolve_document(doc_id)
        if kind != "scene":
            raise ValueError("open a scene first")
        disk, originals = ws.read_text(project, path)
        text = disk if text is None else text
        if '<!--ai id="' in text and not originals:
            originals = drafts.load_originals(project.root, path)
        return {
            "project": project, "path": path, "text": text, "originals": originals,
            "entities": list(self.entities), "rel": ws.rel_id(project, path),
        }

    @staticmethod
    def _spent(calls_before: int) -> float | None:
        """Cost of the AI call made since *calls_before*, if the provider said."""
        last = LEDGER.last()
        if LEDGER.count() > calls_before and last is not None:
            return last.cost
        return None

    @bridge
    def ai_status(self) -> dict:
        project = self.project
        meta = project.meta if project else None
        return {
            "hasKey": bool(get_api_key()),
            "models": {k: resolve_model(k, meta) for k in ("fast", "strong", "writing")},
        }

    @bridge
    def usage(self) -> dict:
        return {"cost": LEDGER.session_total(), "calls": LEDGER.count()}

    @bridge
    def find_aliases(self, doc_id: str, text: str | None = None) -> dict:
        """Descriptive references to known entities ("the old smith") the prose
        makes; accepting one adds an alias to the note, never touches the text."""
        with self._lock:
            inp = self._scene_inputs(doc_id, text)
            if not inp["entities"]:
                raise ValueError("No notes yet - create some notes first")
            scene_text = scenemeta.blank(  # AI text and the details block aren't prose
                drafts.blank_pending(inp["text"]))
            model = resolve_model("fast", inp["project"].meta)
            calls = LEDGER.count()
        suggestions = suggest_links(scene_text, inp["entities"], model)
        out = []
        for s in suggestions:
            around = lambda a, b: " ".join(scene_text[max(0, a):b].split())
            out.append({
                "entity": s.entity, "surface": s.surface, "alias": alias_form(s.surface),
                "before": around(s.start - 60, s.start), "after": around(s.end, s.end + 60),
            })
        return {"suggestions": out, "cost": self._spent(calls)}

    @bridge
    def apply_aliases(self, items: list) -> dict:
        """Add accepted suggestions ({entity, surface}) as aliases of their notes."""
        added = 0
        with self._lock:
            self._require()
            for item in items:
                entity = ent.resolve(str(item.get("entity", "")), self.entities)
                if entity is None:
                    continue
                alias = alias_form(str(item.get("surface", "")))
                if alias and all(alias.casefold() != n.casefold() for n in entity.names):
                    ent.add_alias(entity, alias)
                    added += 1
            if added:
                self._entities_changed()
        return {"added": added}

    @bridge
    def check_continuity(self, doc_id: str, text: str | None = None) -> dict:
        """Contradictions between the scene and the story bible (waived ones omitted)."""
        with self._lock:
            inp = self._scene_inputs(doc_id, text)
            if not inp["entities"]:
                raise ValueError("No notes yet - there is nothing to check against")
            scene_text = drafts.strip_pending(inp["text"], inp["originals"])
            canon = canon_map(inp["entities"])
            model = resolve_model("strong", inp["project"].meta)
            calls = LEDGER.count()
        found = check_scene(scene_text, inp["entities"], canon, model)
        with self._lock:
            waived = load_waivers(inp["project"].root)
        shown = filter_waived(found, waived)
        issues = [{
            "key": c.waiver_key(), "type": c.type, "severity": c.severity,
            "entity": c.entity, "evidence": c.evidence, "fix": c.suggested_fix,
            # locate in the text the author sees (drafts included), not the stripped copy
            "row": locate_evidence(inp["text"], c.evidence),
        } for c in shown]
        return {"issues": issues, "waived": len(found) - len(shown),
                "cost": self._spent(calls)}

    @bridge
    def waive(self, key: str, doc_id: str) -> dict:
        with self._lock:
            project = self._require()
            path, _ = self.resolve_document(doc_id)
            save_waiver(project.root, key, ws.rel_id(project, path))
        return {}

    @bridge
    def restore_waivers(self, doc_id: str) -> dict:
        with self._lock:
            project = self._require()
            path, _ = self.resolve_document(doc_id)
            return {"restored": clear_scene_waivers(project.root, ws.rel_id(project, path))}

    @bridge
    def propose_canon(self, doc_id: str, text: str | None = None) -> dict:
        """New facts this scene establishes about each note (additions only)."""
        with self._lock:
            inp = self._scene_inputs(doc_id, text)
            if not inp["entities"]:
                raise ValueError("No notes yet - create some notes first")
            scene_text = drafts.strip_pending(inp["text"], inp["originals"])
            model = resolve_model("strong", inp["project"].meta)
            calls = LEDGER.count()
        updates = propose_canon_updates(scene_text, inp["entities"], model)
        return {"updates": [{
            "entity": u.entity, "facts": list(u.new_facts), "evidence": u.evidence,
            "existing": u.existing_canon,
        } for u in updates], "cost": self._spent(calls)}

    @bridge
    def apply_canon(self, updates: list) -> dict:
        """Append the accepted facts ({entity, facts}) to each note's canon section."""
        applied = 0
        with self._lock:
            self._require()
            for update in updates:
                entity = ent.resolve(str(update.get("entity", "")), self.entities)
                facts = [str(f) for f in update.get("facts", []) if str(f).strip()]
                if entity is not None and facts:
                    apply_canon_update(entity, facts)
                    applied += 1
            if applied:
                self._entities_changed()
        return {"applied": applied}

    @bridge
    def learn_style(self) -> dict:
        """Propose a style guide from the manuscript; saved only by save_style()."""
        with self._lock:
            project = self._require()
            samples = sample_manuscript(project)
            if not samples:
                raise ValueError("Nothing to learn from yet - write some scenes first")
            model = resolve_model("writing", project.meta)
            replacing = style_path(project).is_file()
            manuscript = manuscript_stats(project)
            calls = LEDGER.count()
        proposal = learn_style(samples, model, manuscript=manuscript)
        return {"markdown": proposal.markdown, "replacing": replacing,
                "samples": len(samples), "cost": self._spent(calls)}

    @bridge
    def style_status(self) -> dict:
        """For the "Your style" card: is there a guide, when was it learned
        and from how much prose, and has the manuscript grown since."""
        with self._lock:
            return style_info(self._require())

    @bridge
    def ensure_style(self) -> dict:
        """Create style.md from the stub template if missing (opening the Style Guide)."""
        with self._lock:
            ensure_style_stub(self._require())
            return {"id": ws.STYLE_ID}

    @bridge
    def save_style(self, text: str) -> dict:
        """Write style.md (an existing guide is first copied to style.md.bak)."""
        with self._lock:
            path = save_style(self._require(), text)
            return {"id": ws.STYLE_ID, "path": str(path)}

    @bridge
    def generate(self, mode: str, instruction: str, doc_id: str, text: str,
                 start: int, end: int) -> dict:
        """Draft at the cursor, expand a marker, or rewrite [start, end).
        Offsets are UTF-16 in *text* (the editor buffer). Inserts nothing: the
        reply is the wrapped draft and the range it replaces; register_draft()
        must store `original` before the editor writes the marker."""
        if mode not in ("draft", "expand", "rewrite"):
            raise ValueError(f"unknown mode: {mode}")
        if not instruction.strip():
            raise ValueError("say what should be written")
        with self._lock:
            inp = self._scene_inputs(doc_id, text)
            project = inp["project"]
            lo, hi = from_utf16(text, start), from_utf16(text, end)
            selection = text[lo:hi] if hi > lo else None
            style_md = load_style(project)
            context = build_context(
                text, lo, inp["entities"], canon_map(inp["entities"]), style_md,
                span=(lo, hi) if hi > lo else None, originals=inp["originals"],
                voice_samples=select_voice_samples(
                    project, inp.get("path"), text, inp["entities"]))
            model = resolve_model("writing", project.meta)
            calls = LEDGER.count()
        body = generate_text(mode, instruction.strip(), context, model, selection=selection)
        with self._lock:
            draft_id = None if mode == "draft" else drafts.fresh_id(project.root, text)
            insert, a, b = drafts.prepare_draft(text, mode, body, lo, hi, draft_id)
        return {
            "mode": mode, "insert": insert, "draftId": draft_id, "original": selection,
            "from": index_to_utf16(text, a), "to": index_to_utf16(text, b),
            "noStyle": style_md is None, "model": model, "cost": self._spent(calls),
        }

    @bridge
    def draft_from_reply(self, doc_id: str, text: str, body: str, at: int) -> dict:
        """A chat reply inserted at *at* (UTF-16) as a pending draft (no network)."""
        with self._lock:
            self._scene_inputs(doc_id, text)
            pos = from_utf16(text, at)
            insert, a, b = drafts.prepare_draft(text, "draft", body.strip(), pos, pos)
        return {"insert": insert, "from": index_to_utf16(text, a), "to": index_to_utf16(text, b)}

    @bridge
    def register_draft(self, doc_id: str, draft_id: str, original: str) -> dict:
        """Store what a draft replaces in the sidecar. Call before writing the
        marker: a marker must never exist without its original."""
        if not re.fullmatch(r"[a-z0-9]{6}", draft_id or ""):
            raise ValueError("bad draft id")
        with self._lock:
            project = self._require()
            path, kind = self.resolve_document(doc_id)
            if kind != "scene":
                raise ValueError("not a scene")
            drafts.add_original(project.root, path, draft_id, original)
        return {}

    @bridge
    def resolve_drafts(self, doc_id: str, text: str, accept: bool,
                       index: int | None = None) -> dict:
        """Accept or reject pending drafts in *text*: the one at *index* (in
        document order) or all. Returns the edits for the editor, newest
        position first, in UTF-16 offsets. A reject whose original is missing
        is skipped (prose is never deleted on a failed lookup)."""
        with self._lock:
            project = self._require()
            path, kind = self.resolve_document(doc_id)
            if kind != "scene":
                raise ValueError("not a scene")
            found = drafts.find_pending(text)
            if index is not None:
                if not 0 <= index < len(found):
                    raise IndexError("no such draft")
                chosen = [found[index]]
            else:
                chosen = found
            if index is None and chosen:  # whole-scene operation: keep a way back
                snapshots.create(project, path,
                                 "before-accept-all" if accept else "before-reject-all", text)
            originals = drafts.load_originals(project.root, path)
            edits, skipped = [], 0
            for p in reversed(chosen):  # back to front so offsets hold
                if accept:
                    insert = text[p.body_start:p.body_end]
                elif p.id is None:
                    insert = ""
                elif p.id in originals:
                    insert = originals[p.id]
                else:
                    skipped += 1
                    continue
                edits.append({"from": index_to_utf16(text, p.start),
                              "to": index_to_utf16(text, p.end), "insert": insert})
                if p.id is not None:
                    drafts.drop_original(project.root, path, p.id)
            return {"edits": edits, "skipped": skipped, "found": len(chosen)}

    @bridge
    def ask(self, prompt: str, scope: str, doc_id: str | None = None,
            text: str | None = None, cursor: int = 0,
            history: list | None = None) -> dict:
        """Chat: answer a question about the scene or the whole project. The
        reply is text for the chat only; the manuscript is never touched."""
        with self._lock:
            project = self._require()
            entities = list(self.entities)
            canon = canon_map(entities)
            style_md = load_style(project)
            model = resolve_model("writing", project.meta)
            if scope == "project" or not doc_id:
                context = build_project_context(
                    [ws.split_title(p.read_text(encoding="utf-8"))[0] or p.stem
                     for p in project.list_scenes()], entities, canon, style_md)
            else:
                inp = self._scene_inputs(doc_id, text)
                context = build_context(
                    inp["text"], from_utf16(inp["text"], cursor), entities, canon,
                    style_md, originals=inp["originals"])
            calls = LEDGER.count()
        reply = ask_writer(prompt, context, model, history=history)
        return {"reply": reply, "cost": self._spent(calls)}

    # -- window ---------------------------------------------------------------

    @bridge
    def minimize(self) -> dict:
        if self._window is not None:
            self._window.minimize()
        return {}

    @bridge
    def toggle_maximize(self) -> dict:
        w = self._window
        if w is not None:
            # pywebview has no "is maximized"; track it ourselves
            if getattr(self, "_maximized", False):
                w.restore()
            else:
                w.maximize()
            self._maximized = not getattr(self, "_maximized", False)
        return {}

    @bridge
    def close(self) -> dict:
        if self._window is not None:
            self._window.destroy()
        return {}

    def facade(self) -> Any:
        """The object handed to pywebview as js_api: just the bridge methods.

        pywebview walks every public attribute of its js_api object, recursing
        into non-callables, so handing it the Api itself would publish
        ``project`` and ``index`` (and everything on them) to JavaScript."""
        return SimpleNamespace(**{n: getattr(self, n) for n in self.bridge_methods()})

    def bridge_methods(self) -> list[str]:
        return sorted(n for n in dir(type(self))
                      if getattr(getattr(type(self), n), "__bridge__", False))
