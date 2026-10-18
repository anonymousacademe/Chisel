"""Research mode: Zotero settings and sync review, source rows, research checks, paper export.

Mixin of Api (the lead wires it in). Every method is ``@bridge``; project access happens under
``self._lock`` and the lock is released before any network call (Zotero probes and fetches) or export.
The Zotero Web API key is a secret: it lives in the OS keyring only (like the OpenRouter key), is never
written to settings.json or the project, never logged and never returned (only whether one is set).
"""

from __future__ import annotations

import itertools
import logging
import threading
from pathlib import Path

from . import workspace as ws
from ..ai.client import KEYRING_SERVICE
from ..core import entities as ent
from ..core import export as exporting
from ..core import settings as user_settings
from ..core import sources as src_notes
from ..core import zotero
from ..core.export import research as research_export
from ..core.export.manuscript import ExportOptions
from ..core.researchchecks import blocking, run_checks
from ._bridge import bridge
from ._research_common import require_research

log = logging.getLogger("chisel")

KEYRING_USER_ZOTERO = "zotero"
SETTING_USER_ID = "zotero_web_user_id"
SETTING_WEB_BASE = "zotero_web_base"
SETTING_LOCAL = "zotero_local"
SETTING_LOCAL_BASE = "zotero_local_base"
SETTING_FILE = "zotero_file"


def _get_zotero_key() -> str:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER_ZOTERO) or ""
    except Exception:
        return ""


def _http_url(value, label: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(f"The {label} address must start with http:// or https://")
    return value


class _ResearchExportJobs:
    """At most one paper export at a time; finished jobs are kept for polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def start(self, project, options, kwargs: dict) -> str:
        with self._lock:
            if any(j["state"] == "running" for j in self._jobs.values()):
                raise RuntimeError("An export is already running.")
            job_id = f"r{next(self._ids)}"
            job = self._jobs[job_id] = {"state": "running", "stage": "Exporting", "fraction": 0.0}

        def work() -> None:
            try:
                result = research_export.run_research_export(project, options, **kwargs)
            except Exception as exc:
                user = isinstance(exc, (ValueError, RuntimeError, OSError))
                if not user:
                    log.warning("research export %s failed", job_id, exc_info=True)
                job.update(state="error", error=str(exc) if user else f"{type(exc).__name__}: {exc}")
            else:
                to_dict = getattr(result, "to_dict", None)
                job.update(state="done", result=to_dict() if to_dict else {})

        threading.Thread(target=work, name=f"research-export-{job_id}", daemon=True).start()
        return job_id

    def status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError("unknown export")
        return dict(job)


class ResearchSourcesMixin:
    # Mixin of Api: shared state (project, _lock, entities, index) is on Api. The pending sync plan and the
    # export jobs are created on first use so Api.__init__ needs no change.

    # -- Zotero settings (non-secret in settings.json, the key in the keyring) ---------------------------

    def _zotero_settings(self, cache=None) -> dict:
        """The mapping core.zotero.open_sources reads. Holds the secret key: never return it."""
        s = user_settings.load_settings()
        out = {
            "zotero_web_key": _get_zotero_key(),
            "zotero_web_user_id": str(s.get(SETTING_USER_ID) or ""),
            "zotero_local": bool(s.get(SETTING_LOCAL, True)),
            "zotero_file": str(s.get(SETTING_FILE) or ""),
        }
        if s.get(SETTING_WEB_BASE):
            out["zotero_web_base"] = str(s[SETTING_WEB_BASE])
        if s.get(SETTING_LOCAL_BASE):
            out["zotero_local_base"] = str(s[SETTING_LOCAL_BASE])
        if cache is not None:
            out["zotero_cache"] = cache
        return out

    def _research_project(self):
        project = self._require()
        require_research(project)
        return project

    @bridge
    def zotero_get_settings(self) -> dict:
        s = user_settings.load_settings()
        return {"userId": str(s.get(SETTING_USER_ID) or ""), "webBase": str(s.get(SETTING_WEB_BASE) or ""),
                "local": bool(s.get(SETTING_LOCAL, True)), "localBase": str(s.get(SETTING_LOCAL_BASE) or ""),
                "file": str(s.get(SETTING_FILE) or ""), "keySet": bool(_get_zotero_key())}

    @bridge
    def zotero_set_settings(self, user_id: str = "", web_base: str = "", local: bool = True,
                            local_base: str = "", file: str = "") -> dict:
        user_id = str(user_id or "").strip()
        if user_id and not user_id.isdigit():
            raise ValueError("The Zotero user id is a number (see your Zotero account's API page).")
        web_base = _http_url(web_base, "Zotero web")
        local_base = _http_url(local_base, "Zotero local")
        file = str(file or "").strip()
        if file and not Path(file).expanduser().is_file():
            raise FileNotFoundError(f"The export file {file} does not exist.")
        s = user_settings.load_settings()
        s.update({SETTING_USER_ID: user_id, SETTING_WEB_BASE: web_base, SETTING_LOCAL: bool(local),
                  SETTING_LOCAL_BASE: local_base,
                  SETTING_FILE: str(Path(file).expanduser()) if file else ""})
        user_settings.save_settings(s)
        return self.zotero_get_settings()

    @bridge
    def zotero_set_key(self, key: str) -> dict:
        key = str(key or "").strip()
        if not key:
            raise ValueError("The key is empty.")
        try:
            import keyring
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER_ZOTERO, key)
        except Exception as exc:
            raise RuntimeError("The system keyring is unavailable, so the Zotero key was not saved "
                               f"({type(exc).__name__}).") from None
        return {"keySet": True}

    @bridge
    def zotero_clear_key(self) -> dict:
        try:
            import keyring
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER_ZOTERO)
        except Exception:
            pass
        return {"keySet": bool(_get_zotero_key())}

    # -- status, plan, apply ------------------------------------------------------------------------------

    @bridge
    def zotero_status(self) -> dict:
        with self._lock:
            project = self._research_project()
            cache = src_notes.cached_items(project)
        sources = zotero.open_sources(self._zotero_settings(cache))   # network below: no lock
        rows = []
        for source in sources:
            try:
                st = source.probe()
                rows.append({"backend": source.name, "ok": bool(st.ok), "message": st.message or ""})
            except Exception as exc:   # a dead backend never throws out of here
                rows.append({"backend": source.name, "ok": False, "message": str(exc) or type(exc).__name__})
        return {"backends": rows, "keySet": bool(_get_zotero_key())}

    @bridge
    def zotero_collections(self) -> dict:
        with self._lock:
            project = self._research_project()
            cache = src_notes.cached_items(project)
        sources = zotero.open_sources(self._zotero_settings(cache))   # network below: no lock
        problems: list[str] = []
        for source in sources:
            lister = getattr(source, "collections", None)
            if lister is None:       # file and cache backends have no collections
                continue
            try:
                st = source.probe()
                if not st.ok:
                    problems.append(st.message)
                    continue
                return {"collections": list(lister())}
            except zotero.ZoteroError as exc:
                problems.append(str(exc))
        raise RuntimeError(problems[0] if problems else "No Zotero source that lists collections is set up.")

    @bridge
    def zotero_sync_plan(self, scope: dict | None = None) -> dict:
        scope = scope or {}
        sc = zotero.Scope(collection=str(scope.get("collection") or "") or None,
                          tag=str(scope.get("tag") or "") or None)
        with self._lock:
            project = self._research_project()
            state = src_notes.load_sync_state(project)
            cache = src_notes.cached_items(project)
        sources = zotero.open_sources(self._zotero_settings(cache))
        result, report = zotero.chain_fetch(sources, sc, state)     # network: no lock held
        state_key = ""
        for source in sources:
            if source.name == result.backend:
                try:
                    state_key = source.probe().state_key or ""
                except Exception:
                    state_key = ""
                break
        with self._lock:
            project = self._research_project()
            plan = src_notes.plan_sync(project, result, scope=sc, state_key=state_key)
            self._zotero_plan = (project.root, plan)
            rows = [{"id": r.id, "key": r.key, "action": r.action, "summary": r.summary,
                     "blocked": r.blocked} for r in plan.rows]
        return {"rows": rows, "report": list(report) + [str(w) for w in plan.warnings],
                "backend": plan.backend}

    @bridge
    def zotero_sync_apply(self, ticked: list) -> dict:
        with self._lock:
            project = self._research_project()
            held = getattr(self, "_zotero_plan", None)
            if held is None or held[0] != project.root:
                raise ValueError("There is no sync preview to apply; preview again.")
            ids = [str(i) for i in (ticked or [])]
            outcome = src_notes.apply_sync(project, held[1], ids)
            self._zotero_plan = None
            if outcome["changed"]:
                self._entities_changed()    # reload entities and rebuild the index
        return {"changed": outcome["changed"], "skipped": outcome["skipped"],
                "recorded": outcome["recorded"]}

    # -- sources, checks, export ------------------------------------------------------------------------

    @bridge
    def list_sources(self) -> dict:
        with self._lock:
            project = self._research_project()
            rows = []
            for e in project.load_entities():
                if not e.is_source or e.path is None:
                    continue
                rows.append({"id": ws.rel_id(project, e.path), "name": e.name,
                             "title": str(e.extra.get("title") or e.name),
                             "key": ent.source_key(e),
                             "status": str(e.extra.get("zotero_status") or "")})
            rows.sort(key=lambda r: r["key"].casefold())
        return {"sources": rows}

    @bridge
    def research_checks(self) -> dict:
        with self._lock:
            flags = run_checks(self._research_project())
        return {"flags": [{"kind": f.kind, "path": f.path, "row": f.row, "message": f.message,
                           "blocking": bool(f.blocking)} for f in flags],
                "blocking": blocking(flags)}

    def _research_jobs(self) -> _ResearchExportJobs:
        jobs = getattr(self, "_research_exports", None)
        if jobs is None:
            jobs = self._research_exports = _ResearchExportJobs()
        return jobs

    @bridge
    def export_research_start(self, opts: dict | None = None) -> dict:
        opts = dict(opts or {})
        override = opts.pop("override", False) is True
        tex_install = opts.pop("allow_tex_install", False) is True
        with self._lock:
            project = self._research_project()
            if not override and blocking(run_checks(project)):
                raise ValueError("The paper has problems that block export (unresolved citations or missing "
                                 "references). Fix them, or export anyway.")
            options = ExportOptions.from_dict(opts)
        kwargs = {"allow_unresolved": override, "allow_tex_install": tex_install}
        return {"job": self._research_jobs().start(project, options, kwargs)}

    @bridge
    def export_research_status(self, job: str) -> dict:
        return self._research_jobs().status(job)

    @bridge
    def export_research_open(self, name: str = "", folder: bool = False) -> dict:
        with self._lock:
            path = exporting.resolve_export(self._research_project(), "" if folder else name)
        exporting.open_in_desktop(path)
        return {}
