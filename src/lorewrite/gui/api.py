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
    generate as generate_text,
)
from ..core import drafts
from ..core import settings as user_settings
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
from ..core.project import Project, write_atomic
from ..core.spans import compute_spans, from_utf16, index_to_utf16, to_utf16
from ..core.style import load_style, sample_manuscript, save_style
from ..core.recents import add_recent, load_recents
from ..core.style import style_path
from . import workspace as ws


# Errors the core raises on purpose, with a message written for the author:
# shown as-is. Anything else keeps its class name (it is a bug worth reporting).
USER_ERRORS = (ValueError, FileNotFoundError, FileExistsError, LookupError, IndexError, RuntimeError)


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
        self._baseline_words = sum(
            s["words"] for s in ws.scene_summaries(project))

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
    def new_project(self, title: str, path: str) -> dict:
        title = title.strip()
        if not title:
            raise ValueError("a project needs a title")
        root = Path(path).expanduser()
        if Project.is_project(root):
            raise FileExistsError(f"{root} already holds a project")
        with self._lock:
            self._load(Project.create(root, title))
        return {}

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
        if path.parent == project.manuscript_dir.resolve():
            return "scene"
        if path.parent.parent == project.entities_dir.resolve():
            return "entity"
        if path == style_path(project).resolve():
            return "style"
        return None

    def resolve_document(self, doc_id: str) -> tuple[Path, str]:
        """The file behind a document id (a project-relative .md path), or
        ValueError. Ids never escape the project or name non-note files."""
        project = self._require()
        path = (project.root / doc_id).resolve()
        if not path.is_relative_to(project.root.resolve()) or path.suffix != ".md":
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
            if kind == "scene":
                title = title or path.stem
                kicker, parent = ws.scene_kicker(path), "Manuscript"
            elif kind == "entity":
                title, kicker, parent = entity.name, entity.type.upper(), "Notes"
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
            }

    def _all_names(self) -> list[str]:
        return [n for e in self.entities for n in e.names]

    def _index_file(self, path: Path, kind: str, text: str) -> None:
        """Refresh derived state after *path* was written with *text*."""
        project = self._require()
        if kind == "style":
            return  # the style guide isn't part of the link index
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
                write_atomic(path, text)
                current = str(path.stat().st_mtime_ns)
            self._index_file(path, kind, text)
            _, originals = ws.read_text(project, path)
            return {"saved": True, "mtime": current,
                    "words": drafts.count_words(text, originals)}

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

    @bridge
    def new_scene(self, title: str) -> dict:
        title = " ".join(title.split())
        if not title:
            raise ValueError("a scene needs a title")
        with self._lock:
            project = self._require()
            path = project.next_scene_path(title)
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
        with self._lock:
            project = self._require()
            new_path = project.move_scene(self._scene_path(doc_id), int(delta))
            if new_path is None:
                raise ValueError("the scene is already at the edge")
            self.index.rebuild(project)  # two files changed names
            return {"id": ws.rel_id(project, new_path)}

    @bridge
    def delete_scene(self, doc_id: str) -> dict:
        with self._lock:
            project = self._require()
            path = self._scene_path(doc_id)
            rel = ws.rel_id(project, path)
            project.delete_scene(path)  # also its .drafts sidecar
            self.index.remove_file(rel)
            return {}

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
        return {"hasKey": source != "none", "keySource": source, "models": models, "editor": editor}

    @bridge
    def set_settings(self, models: dict | None = None, editor: dict | None = None) -> dict:
        """Save model choices ("" resets to the default) and GUI editor prefs."""
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
            scene_text = drafts.blank_pending(inp["text"])  # AI text isn't canon
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
            calls = LEDGER.count()
        proposal = learn_style(samples, model)
        return {"markdown": proposal.markdown, "replacing": replacing,
                "samples": len(samples), "cost": self._spent(calls)}

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
                span=(lo, hi) if hi > lo else None, originals=inp["originals"])
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
