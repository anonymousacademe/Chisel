"""The bridge between the React UI and the Python core.

Every public method of Api is callable from JavaScript (pywebview's js_api, or
the devserver's POST /api/<method>). Contract: JSON in, JSON out, always
``{"ok": true, ...}`` or ``{"ok": false, "error": "..."}`` — never raise across
the bridge. No pywebview import here, so this is unit-testable.
"""

from __future__ import annotations

import inspect
import os
import re
import threading
import time
import webbrowser  # noqa: F401  (tests patch api.webbrowser)
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..ai.client import (
    MODEL_DEFAULTS,
    SETTING_LOCAL_BASE_URL,
    clear_api_key as _clear_api_key,
    get_api_key,
    list_local_models as _list_local_models,
    list_models as _list_models,
    local_base_url as _local_base_url,
    remember_context_lengths,
    resolve_model,
    set_api_key as _set_api_key,
)
from ..ai.budget import (
    SETTING as SETTING_WINDOW, Budget, Section, merge_attached, validate_window,
)
from ..ai.continuity import check_scene, plan_canon, plan_check, propose_canon_updates
from ..ai import images as image_ai
from ..ai.images import generate as generate_images, suggest_prompt as suggest_image_prompt
from ..ai.links import alias_form, plan_aliases, suggest_links
from ..ai.relationships import (
    Suggestion as RelationshipSuggestion,
    apply_suggestions,
    plan_suggestions,
    suggest_relationships,
)
from ..ai.style import learn_style
from ..ai.stream import call_ai
from ..ai.usage import LEDGER
from ..ai.writing import (
    ASK_SYSTEM_PROMPT,
    RESEARCH_SYSTEM_PROMPT,
    ask as ask_writer,
    brainstorm as brainstorm_writer,
    brainstorm_instructions,
    build_context_sections,
    build_project_context_sections,
    chat_instructions,
    fit_context,
    generate_instructions,
    research_sections,
    generate as generate_text,
    research_answer as research_writer,
)
from ..core import attach
from ..core import research as research_notes
from ..core import stats as writing_stats
from ..core import drafts, rename as renaming, scenemeta, snapshots
from ..core import fsutil
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
from . import inspiration as insp_api
from . import workspace as ws
from . import aijobs
from .aijobs import AiJobs
from .exports import ExportJobs
from ._bridge import USER_ERRORS, bridge  # noqa: F401  (re-exported)
from .annotations_api import AnnotationsMixin
from .atmosphere_api import AtmosphereMixin
from .chats_api import ChatsMixin
from .entities_api import EntitiesMixin
from .export_api import ExportMixin
from .inspiration_api import InspirationMixin
from .notebook_api import NotebookMixin
from .spelling_api import SpellingMixin
from .stats_api import StatsMixin
from .structure_api import StructureMixin
from .versions_api import VersionsMixin
from .window_api import WindowMixin


class Api(SpellingMixin, EntitiesMixin, StructureMixin, VersionsMixin, ExportMixin,
          NotebookMixin, AnnotationsMixin, InspirationMixin, AtmosphereMixin, StatsMixin,
          ChatsMixin, WindowMixin):
    def __init__(self) -> None:
        self._lock = threading.RLock()  # guards every project write
        self._window: Any = None  # set by gui.app once the window exists
        self.project: Project | None = None
        self.index: Index | None = None
        self.entities: list[ent.Entity] = []
        self._session_start = time.time()
        self._baseline_words = 0
        self.stats: writing_stats.Tracker | None = None
        self._spell_ignores = spelling.SessionIgnores()  # in memory only
        self._exports = ExportJobs()
        self._ai_jobs = AiJobs()
        self._rename_plan: tuple[str, renaming.RenamePlan] | None = None

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
        if self.stats is not None:
            self.stats.close()
        self.project = project
        self.stats = writing_stats.Tracker(project.root)
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
            raise FileNotFoundError(f"no {root / 'project.toml'} - not a Chisel project")
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
                ai_cost=LEDGER.session_total(), stats=self._stats_brief())}

    def _stats_brief(self) -> dict | None:
        """What the status bar needs of the writing stats (the full page is `stats`)."""
        if self.stats is None:
            return None
        s = self.stats.summary()
        return {"target": s["target"], "streak": s["streak"], "todayMet": s["todayMet"],
                "todayWords": s["today"]["words"], "sprint": s["sprint"]}

    def _scene_key(self, path: Path) -> str:
        return ws.rel_id(self._require(), path)

    def _author_words(self, project: Project, path: Path, text: str) -> int:
        return drafts.count_words(text, drafts.load_originals(project.root, path))

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
                          else ws.PARKED_TITLE if project.is_unplaced(path) else "Manuscript")
                if self.stats is not None:  # baseline for the stats; nothing is counted here
                    self.stats.seen(self._scene_key(path), drafts.count_words(text, originals))
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
                kicker, parent = "NOTEBOOK", "Notebook"
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
            fsutil.ensure_utf8(path)  # never overwrite non-UTF-8 bytes with lenient text
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
            if kind == "scene" and self.stats is not None:
                self.stats.record(self._scene_key(path), drafts.count_words(text, originals))
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

    # -- Ask my notebook (the notes themselves: notebook_api.py) ----------------------------

    @bridge
    def research(self, prompt: str, history: list | None = None,
                 attachments: list | None = None) -> dict:
        """Chat: answer a question from the research notes and the project canon
        (keyword retrieval, no web). Returns the reply and the notes it was given
        (`sources`, in citation order). The manuscript is never touched."""
        with self._lock:
            project = self._require()
            entities = list(self.entities)
            sections, hits = research_sections(project, entities, canon_map(entities), prompt)
            sections, attached = self._with_attachments(project, sections, attachments)
            sources = [{"id": ws.rel_id(project, h.note.path), "title": h.note.title,
                        "score": h.score} for h in hits]
            model = resolve_model("writing", project.meta)
            context, sent = fit_context(
                [*sections, chat_instructions(RESEARCH_SYSTEM_PROMPT, prompt, history)], model, "research")
            calls = LEDGER.count()
        reply = self._stream(research_writer, prompt, context, model, history=history)
        return {"reply": reply, "sources": sources, "attached": attached, "cost": self._spent(calls),
                "sent": merge_attached(sent, attached).to_dict()}

    # -- manuscript unit label and index rebuild --------------------------------------------

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

    # -- inspiration images: the AI calls (listing, upload, edit and delete: inspiration_api.py).
    # Generation is the slow call: lock released.

    @bridge
    def describe_scene(self, doc_id: str, text: str | None = None, cursor: int = 0,
                       subject_id: str | None = None) -> dict:
        """**Describe this**: a visual prompt from the open item. For a scene, the passage around
        the cursor and the place/character notes; for an entity or notebook note, the note's
        text. The subject is *subject_id* if given, else *doc_id*. The author edits the result;
        nothing is generated or saved."""
        with self._lock:
            project = self._require()
            target = subject_id or doc_id
            _, kind = self.resolve_document(target)
            if kind == "scene":
                inp = self._scene_inputs(target, text)
                context = image_ai.scene_context(
                    inp["text"], from_utf16(inp["text"], cursor), inp["entities"],
                    canon_map(inp["entities"]), inp["originals"])
            elif kind in ("entity", "research"):
                heading, body = attach.subject(project, target)
                context = f"{heading}\n{body}"
            else:
                raise ValueError("open a scene or a note to describe it")
            model = resolve_model("fast", project.meta)
            calls = LEDGER.count()
        prompt = suggest_image_prompt(context, model)
        return {"prompt": prompt, "model": model, "cost": self._spent(calls)}

    @bridge
    def generate_inspiration(self, prompt: str, doc_id: str | None = None, pin: bool = False) -> dict:
        """Make pictures for *prompt* and save them (linked to the item *doc_id*: a scene, an
        entity note or a notebook note; pinned to it when *pin*). Costs about $0.03 per picture;
        returns the new rows."""
        with self._lock:
            project = self._require()
            scene = self._item_link(doc_id)
            model = resolve_model("image", project.meta)
            style = image_ai.style_suffix()
            calls = LEDGER.count()
        prompt = " ".join((prompt or "").split())
        if not prompt:
            raise ValueError("describe the picture first")
        pictures = generate_images(prompt, model, style=style)
        aijobs.checkpoint()   # stopped while it generated: nothing is saved
        cost = self._spent(calls)
        with self._lock:
            return insp_api.save_pictures(self._require(), pictures, prompt, model, scene,
                                          bool(pin) and bool(scene), cost)

    @bridge
    def regenerate_inspiration(self, image_id: str) -> dict:
        """Another picture from the same prompt and item (the old one stays). A picture the
        author added has no prompt and cannot be regenerated."""
        with self._lock:
            project = self._require()
            old = insp_api.get(project, image_id)
            if old.source == "upload":
                raise ValueError("a picture you added cannot be regenerated: there is no prompt")
            model = resolve_model("image", project.meta)
            style = image_ai.style_suffix()
            calls = LEDGER.count()
        pictures = generate_images(old.prompt, model, style=style)
        aijobs.checkpoint()
        cost = self._spent(calls)
        with self._lock:
            return insp_api.save_pictures(self._require(), pictures, old.prompt, model, old.link,
                                          False, cost)

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
        for kind in ("fast", "strong", "writing", "image"):
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
                "autoSnapshot": snapshots.auto_enabled(),
                "imageStyle": image_ai.style_suffix(), "imageStyleDefault": image_ai.DEFAULT_STYLE,
                "dailyTarget": writing_stats.get_target(),
                "contextWindow": user_settings.get(SETTING_WINDOW) or "",
                "localBaseUrl": user_settings.get(SETTING_LOCAL_BASE_URL) or ""}

    @bridge
    def set_settings(self, models: dict | None = None, editor: dict | None = None,
                     spellcheck: bool | None = None,
                     auto_snapshot: bool | None = None,
                     daily_target: int | None = None,
                     image_style: str | None = None,
                     context_window: int | str | None = None,
                     local_base_url: str | None = None) -> dict:
        """Save model choices ("" resets to the default), GUI editor prefs and
        the spell-check toggle (shared with the TUI). `context_window` (tokens, "" = ask the
        model list) is for models whose real window is not in the catalogue.
        `local_base_url` ("" = the default) is the OpenAI-compatible local
        server the `local:` models run on."""
        with self._lock:
            if context_window is not None:
                user_settings.set(SETTING_WINDOW,
                                  None if context_window == "" else validate_window(context_window))
            if local_base_url is not None:
                value = str(local_base_url).strip()
                if value:
                    _local_base_url(value)  # validate: raises ValueError with the reason
                user_settings.set(SETTING_LOCAL_BASE_URL, value or None)
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
            if daily_target is not None:
                writing_stats.set_target(int(daily_target))
            if image_style is not None:
                user_settings.set(image_ai.SETTING_STYLE, " ".join(str(image_style).split())[:image_ai.STYLE_MAX])
        return {}

    @bridge
    def get_project_info(self) -> dict:
        """Read the project's author and publication details."""
        if not self.project:
            raise ValueError("no project open")
        return self.project.author_info()

    @bridge
    def set_project_info(self, author: str = "", pen_name: str = "",
                        subtitle: str = "", copyright_: str = "",
                        contact: str = "", language: str = "") -> dict:
        """Save the project's author and publication details."""
        if not self.project:
            raise ValueError("no project open")
        with self._lock:
            self.project.update_author_info(
                author=author, pen_name=pen_name, subtitle=subtitle,
                copyright_=copyright_, contact=contact, language=language)
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
    def list_models(self, structured_only: bool = True, modality: str | None = None) -> dict:
        """The OpenRouter model catalog (public, needs network). Structured-output
        models only for the fast/strong pickers; the whole catalog for writing;
        `modality="image"` (with structured_only false) lists image-output models."""
        models = _list_models(structured_only=structured_only,
                              **({"output_modality": modality} if modality else {}))
        remember_context_lengths(models)   # the budget plans AI requests against these (never fetched there)
        return {"models": [{
            "id": m.id, "name": m.name, "promptPerM": m.prompt_per_m,
            "completionPerM": m.completion_per_m, "context": m.context_length,
            "imagePrice": m.image_price,
        } for m in models]}

    @bridge
    def list_local_models(self, base_url: str = "") -> dict:
        """The models installed on the author's own OpenAI-compatible server
        (Ollama by default; `base_url` overrides the setting for this call).
        The ids come back with the `local:` prefix, ready for a model field.
        Raises (-> `{ok:false}`) when the server cannot be reached."""
        models = _list_local_models(base_url=base_url or None)
        return {"models": [{
            "id": m.id, "name": m.name, "promptPerM": None,
            "completionPerM": None, "context": m.context_length,
            "imagePrice": None,
        } for m in models], "baseUrl": _local_base_url(base_url or None)}

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

    def _subject_sections(self, subject_id: str, text: str | None = None, cursor: int = 0) -> list[Section]:
        """What an AI call is *about* (call with the lock held), as context sections: for an
        entity note `SUBJECT (character|place|object|...): name` + the note body; for a notebook
        note `SUBJECT (notebook note): title` + its text (both capped like an attachment, see
        core.attach); for a scene the usual scene context around *cursor*. An id that names
        nothing, or a file that is not a subject (style guide, dictionary), is an error."""
        project = self._require()
        _, kind = self.resolve_document(subject_id)
        if kind in ("entity", "research"):
            heading, body = attach.subject(project, subject_id)
            return [Section("About: " + heading.split(": ", 1)[-1],
                            f"{heading}\n{body}" if body else heading)]
        if kind != "scene":
            raise ValueError("that item cannot be the subject of a question")
        inp = self._scene_inputs(subject_id, text)
        entities = inp["entities"]
        return build_context_sections(inp["text"], from_utf16(inp["text"], cursor), entities,
                                      canon_map(entities), load_style(project), originals=inp["originals"])

    def _chat_sections(self, scope: str, doc_id: str | None, text: str | None, cursor: int,
                       subject_id: str | None) -> list[Section]:
        """The context of a chat question or Brainstorm as sections (call with the lock held): the
        open scene (or the whole project when *scope* is "project" or no scene is open), plus the
        *subject_id* item when it is an entity or notebook note. A scene subject *is* the scene
        context (unless the whole project was asked for)."""
        project = self._require()
        entities = list(self.entities)
        canon = canon_map(entities)
        style_md = load_style(project)
        note_subject = None
        if subject_id:
            _, kind = self.resolve_document(subject_id)
            if kind in ("entity", "research"):
                note_subject = subject_id
            elif kind != "scene":
                raise ValueError("that item cannot be the subject of a question")
            elif scope != "project":
                if doc_id != subject_id:
                    doc_id, text = subject_id, (None if doc_id else text)
        if scope == "project" or not doc_id:
            sections = build_project_context_sections(
                [ws.split_title(fsutil.read_text_lenient(p))[0] or p.stem
                 for p in project.list_scenes()], entities, canon, style_md)
            if not sections:
                sections = [Section("Project", "(the project is empty)")]
        else:
            inp = self._scene_inputs(doc_id, text)
            sections = build_context_sections(
                inp["text"], from_utf16(inp["text"], cursor), entities, canon,
                style_md, originals=inp["originals"])
        if note_subject:
            sections += self._subject_sections(note_subject)
        return sections

    @staticmethod
    def _spent(calls_before: int) -> float | None:
        """Cost of the AI call made since *calls_before*, if the provider said."""
        last = LEDGER.last()
        if LEDGER.count() > calls_before and last is not None:
            return last.cost
        return None

    @staticmethod
    def _stream(fn, *args, **kwargs):
        """Call a streaming AI function. Inside an AI job its text deltas go to the
        job (and Stop closes the stream); otherwise it is the plain blocking call."""
        job = aijobs.current()
        if job is None:
            return fn(*args, **kwargs)
        return call_ai(fn, *args, on_delta=job.push, cancel=job.cancel, **kwargs)

    # Job kinds -> the synchronous bridge method each one runs (same arguments, same
    # result dict). The first four stream text; the rest are abandoned on Stop.
    AI_JOBS = {
        "ask": "ask", "research": "research", "brainstorm": "brainstorm", "generate": "generate",
        "continuity": "check_continuity", "canon": "propose_canon", "aliases": "find_aliases",
        "relationships": "suggest_relationships",
        "style": "learn_style", "image": "generate_inspiration", "describe_scene": "describe_scene",
        "image_regenerate": "regenerate_inspiration",
    }

    @bridge
    def ai_start(self, kind: str, args: dict | None = None) -> dict:
        """Start an AI action on a worker thread and return its job id. *args* are exactly the
        keyword arguments of the synchronous method for *kind* (see AI_JOBS). Poll with
        ai_poll, stop with ai_cancel. The project lock is not held during the network call."""
        name = self.AI_JOBS.get(kind)
        if name is None:
            raise ValueError(f"unknown AI action: {kind}")
        args = dict(args or {})
        method = getattr(self, name)
        try:
            inspect.signature(method).bind(**args)
        except TypeError as exc:
            raise ValueError(f"bad arguments for {kind}: {exc}") from None

        def work(job: aijobs.Job) -> dict:
            return method(**args)

        return {"job": self._ai_jobs.start(work)}

    @bridge
    def ai_poll(self, job: str, since: int = 0) -> dict:
        """State of an AI job: running | done | cancelled | error, the streamed text from
        character offset *since* (and the total `length`), `elapsed` seconds, and, when done,
        `result` (what the synchronous method returns) or, on error, `error`."""
        return self._ai_jobs.poll(job, since)

    @bridge
    def ai_cancel(self, job: str) -> dict:
        """Stop an AI job (idempotent). A stopped job inserts, saves and registers nothing."""
        return self._ai_jobs.cancel(job)

    @bridge
    def ai_status(self) -> dict:
        project = self.project
        meta = project.meta if project else None
        return {
            "hasKey": bool(get_api_key()),
            "models": {k: resolve_model(k, meta) for k in ("fast", "strong", "writing", "image")},
        }

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
            entities, sent = plan_aliases(scene_text, inp["entities"], Budget.for_model(model),
                                          details_text=drafts.blank_pending(inp["text"]))
            calls = LEDGER.count()
        suggestions = suggest_links(scene_text, entities, model)
        out = []
        for s in suggestions:
            around = lambda a, b: " ".join(scene_text[max(0, a):b].split())
            out.append({
                "entity": s.entity, "surface": s.surface, "alias": alias_form(s.surface),
                "before": around(s.start - 60, s.start), "after": around(s.end, s.end + 60),
            })
        return {"suggestions": out, "cost": self._spent(calls), "sent": sent.to_dict()}

    @bridge
    def apply_aliases(self, items: list) -> dict:
        """Add accepted suggestions ({entity, surface}) as aliases of their notes."""
        added = 0
        with self._lock:
            self._require()
            try:
                for item in items:
                    entity = ent.resolve(str(item.get("entity", "")), self.entities)
                    if entity is None:
                        continue
                    alias = alias_form(str(item.get("surface", "")))
                    if alias and all(alias.casefold() != n.casefold() for n in entity.names) \
                            and ent.alias_owner(alias, entity, self.entities) is None:
                        ent.add_alias(entity, alias)  # NotUtf8Error: the note is left alone
                        added += 1
            finally:
                if added:
                    self._entities_changed()
        return {"added": added}

    @bridge
    def suggest_relationships(self, name: str) -> dict:
        """Relationships a note's text supports, from the note's own point of
        view; accepting one rewrites its Relationships section, never the prose."""
        with self._lock:
            self._require()
            entity = ent.resolve(name, self.entities)
            if entity is None:
                raise LookupError(f"no note named {name!r}")
            model = resolve_model("fast", self.project.meta)
            entities, sent = plan_suggestions(entity, self.entities, Budget.for_model(model))
            calls = LEDGER.count()
        suggestions = suggest_relationships(entity, entities, model)
        return {"suggestions": [{"target": s.target, "label": s.label} for s in suggestions],
                "cost": self._spent(calls), "sent": sent.to_dict()}

    @bridge
    def apply_relationships(self, name: str, items: list) -> dict:
        """Add the accepted suggestions ({target, label}) to the note's
        Relationships section; targets that resolve to no other note are dropped."""
        with self._lock:
            self._require()
            entity = ent.resolve(name, self.entities)
            if entity is None:
                raise LookupError(f"no note named {name!r}")
            accepted = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                target = " ".join(str(item.get("target", "")).split())
                label = " ".join(str(item.get("label", "")).split())
                if not target or not label:
                    continue
                if ent.resolve(target, [e for e in self.entities if e is not entity]) is None:
                    continue
                accepted.append(RelationshipSuggestion(target, label))
            if accepted:
                apply_suggestions(entity, accepted, ent.save_entity)
                self._entities_changed()
        return {"applied": len(accepted)}

    @bridge
    def check_continuity(self, doc_id: str, text: str | None = None) -> dict:
        """Contradictions between the scene and the story bible (waived ones omitted)."""
        with self._lock:
            inp = self._scene_inputs(doc_id, text)
            if not inp["entities"]:
                raise ValueError("No notes yet - there is nothing to check against")
            scene_text = drafts.strip_pending(inp["text"], inp["originals"])
            model = resolve_model("strong", inp["project"].meta)
            entities, canon, sent = plan_check(scene_text, inp["entities"], canon_map(inp["entities"]),
                                               Budget.for_model(model))
            calls = LEDGER.count()
        found = check_scene(scene_text, entities, canon, model) if entities else []
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
                "cost": self._spent(calls), "sent": sent.to_dict()}

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
            entities, sent = plan_canon(scene_text, inp["entities"], Budget.for_model(model))
            calls = LEDGER.count()
        updates = propose_canon_updates(scene_text, entities, model) if entities else []
        return {"updates": [{
            "entity": u.entity, "facts": list(u.new_facts), "evidence": u.evidence,
            "existing": u.existing_canon,
        } for u in updates], "cost": self._spent(calls), "sent": sent.to_dict()}

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
            sections = build_context_sections(
                text, lo, inp["entities"], canon_map(inp["entities"]), style_md,
                span=(lo, hi) if hi > lo else None, originals=inp["originals"],
                voice_samples=select_voice_samples(
                    project, inp.get("path"), text, inp["entities"]))
            model = resolve_model("writing", project.meta)
            context, sent = fit_context(
                [*sections, generate_instructions(mode, instruction.strip(), selection)], model, mode)
            calls = LEDGER.count()
        body = self._stream(generate_text, mode, instruction.strip(), context, model,
                            selection=selection)
        with self._lock:
            draft_id = None if mode == "draft" else drafts.fresh_id(project.root, text)
            insert, a, b = drafts.prepare_draft(text, mode, body, lo, hi, draft_id)
        return {
            "mode": mode, "insert": insert, "draftId": draft_id, "original": selection,
            "from": index_to_utf16(text, a), "to": index_to_utf16(text, b),
            "noStyle": style_md is None, "model": model, "cost": self._spent(calls),
            "sent": sent.to_dict(),
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
                if accept and self.stats is not None:  # AI words, not the author's
                    self.stats.accepted(self._scene_key(path), len(insert.split()),
                                        len((originals.get(p.id) or "").split()) if p.id else 0)
                if p.id is not None:
                    drafts.drop_original(project.root, path, p.id)
            return {"edits": edits, "skipped": skipped, "found": len(chosen)}

    @bridge
    def ask(self, prompt: str, scope: str, doc_id: str | None = None,
            text: str | None = None, cursor: int = 0,
            history: list | None = None, attachments: list | None = None,
            subject_id: str | None = None) -> dict:
        """Chat: answer a question about the scene or the whole project, and about the open
        item (*subject_id*: a character / place / object note, a notebook note or a scene)
        when the author keeps it on. The reply is text for the chat only; the manuscript is
        never touched."""
        with self._lock:
            project = self._require()
            model = resolve_model("writing", project.meta)
            sections = self._chat_sections(scope, doc_id, text, cursor, subject_id)
            sections, attached = self._with_attachments(project, sections, attachments)
            context, sent = fit_context(
                [*sections, chat_instructions(ASK_SYSTEM_PROMPT, prompt, history)], model, "ask")
            calls = LEDGER.count()
        reply = self._stream(ask_writer, prompt, context, model, history=history)
        return {"reply": reply, "attached": attached, "cost": self._spent(calls),
                "sent": merge_attached(sent, attached).to_dict()}

    @bridge
    def brainstorm(self, doc_id: str | None = None, text: str | None = None, cursor: int = 0,
                   attachments: list | None = None, subject_id: str | None = None) -> dict:
        """Chat: 3-5 "unstuck" ideas for the open scene (or the project when no scene is
        open) from the scene around the cursor, the canon and the style guide, and for the
        open item (*subject_id*: a character / place / object note or a notebook note) when
        the author keeps it on. The reply is chat text (a numbered list) plus the ideas as a
        list, for per-idea actions; the manuscript is never touched."""
        with self._lock:
            project = self._require()
            model = resolve_model("writing", project.meta)
            sections = self._chat_sections("scene", doc_id, text, cursor, subject_id)
            sections, attached = self._with_attachments(project, sections, attachments)
            context, sent = fit_context([*sections, brainstorm_instructions()], model, "brainstorm")
            calls = LEDGER.count()
        ideas = self._stream(brainstorm_writer, context, model)
        reply = "\n".join(f"{i}. {idea}" for i, idea in enumerate(ideas, 1))
        return {"reply": reply, "ideas": ideas, "attached": attached, "cost": self._spent(calls),
                "sent": merge_attached(sent, attached).to_dict()}

    @staticmethod
    def _with_attachments(project: Project, sections: list[Section],
                          attachments: list | None) -> tuple[list[Section], list]:
        """Append the author's attachments (capped, core.attach) to a chat context as a section
        that is never dropped; the report (`attached`) says what was truncated or skipped and is
        merged into the sent report (`budget.merge_attached`)."""
        text, report = attach.build(project, [a for a in attachments or [] if isinstance(a, dict)])
        return ([*sections, Section("Attachments", text)] if text else list(sections)), report

    def facade(self) -> Any:
        """The object handed to pywebview as js_api: just the bridge methods.

        pywebview walks every public attribute of its js_api object, recursing
        into non-callables, so handing it the Api itself would publish
        ``project`` and ``index`` (and everything on them) to JavaScript."""
        return SimpleNamespace(**{n: getattr(self, n) for n in self.bridge_methods()})

    def bridge_methods(self) -> list[str]:
        return sorted(n for n in dir(type(self))
                      if getattr(getattr(type(self), n), "__bridge__", False))
