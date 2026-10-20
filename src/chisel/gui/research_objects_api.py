"""Research mode: figures, tables and equations (core/objects.py, tables.py, figscripts.py, tablefmt.py).

Mixin of Api (api.py): every public method is a bridge method; shared state (``_lock``, ``_require``) is on Api.
Rules this file keeps (AGENTS.md "GUI fragile spots", docs/dev/research-mode-contracts.md):

* every method starts with ``require_research`` inside ``self._lock``;
* a figure script runs ONLY from ``figure_run_start`` (a worker thread, outside the lock) and only after
  ``trust_figure`` was called with the hash the confirmation dialog showed; nothing else here runs code;
* image bytes come out of ``objects._figure_file`` (one door), cached by mtime;
* tables are parsed and written by ``core.tables`` (atomically, stale ``base_mtime`` is a conflict);
* AI proposals (``suggest_*``) are returned as text with the sent report; nothing is inserted, saved or run.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import itertools
import logging
import re
import threading
import time

from ..ai.budget import BudgetError  # noqa: F401  (a USER_ERRORS member; listed for readers)
from ..ai.client import resolve_model
from ..ai.stream import CancelToken, call_ai
from ..ai.usage import LEDGER
from ..core import figscripts, objects, tablefmt, tables
from . import aijobs
from ._bridge import bridge
from ._research_common import require_research

log = logging.getLogger("chisel")

MAX_RENDER_IDS = 200
MAX_TABLE_ROWS = 5000
MAX_TABLE_COLS = 100
IMAGE_CACHE_ENTRIES = 24
JOB_RETENTION_SECONDS = 300
_DATA_URL = re.compile(r"^data:([\w.+-]+/[\w.+-]+)?(;[\w=.+-]+)*;base64,", re.IGNORECASE)

_setup_lock = threading.Lock()


class _FigureRuns:
    """Figure-run jobs: one worker thread each, polled by the UI. No project lock is ever taken here."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def start(self, project, fig_id: str) -> str:
        with self._lock:
            self._prune()
            if any(j["state"] == "running" and j["figure"] == fig_id for j in self._jobs.values()):
                raise RuntimeError("This figure is already running.")
            job_id = f"f{next(self._ids)}"
            cancel = threading.Event()
            job = self._jobs[job_id] = {"state": "running", "figure": fig_id, "cancel": cancel,
                                        "cancelling": False, "started": time.monotonic(), "finished": None}

        def work() -> None:
            try:
                result = figscripts.run_figure(project, fig_id, cancel=cancel)
            except Exception as exc:        # the job reports it; the thread never dies loudly
                if not isinstance(exc, (ValueError, RuntimeError, OSError)):
                    log.warning("figure run %s failed", job_id, exc_info=True)
                    message = f"{type(exc).__name__}: {exc}"
                else:
                    message = str(exc)
                update = {"state": "failed", "error": message, "stderr": ""}
            else:
                if result.cancelled:
                    state = "cancelled"
                elif result.status == "current" and not result.refused:
                    state = "done"
                else:
                    state = "failed"
                update = {"state": state, "error": result.error or "", "stderr": result.stderr or "",
                          "refused": bool(result.refused), "timedOut": bool(result.timed_out)}
            with self._lock:
                job.update(update)
                job["finished"] = time.monotonic()

        threading.Thread(target=work, name=f"figure-{job_id}", daemon=True).start()
        return job_id

    def status(self, job_id: str) -> dict:
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            if job is None:
                raise LookupError("unknown figure run (it may have expired)")
            out = {"job": job_id, "figure": job["figure"], "state": job["state"],
                   "cancelling": job["cancelling"] and job["state"] == "running"}
            if job["state"] != "running":
                out.update(error=job.get("error", ""), stderr=job.get("stderr", ""),
                           refused=job.get("refused", False), timedOut=job.get("timedOut", False))
            return out

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise LookupError("unknown figure run (it may have expired)")
            if job["state"] == "running":
                job["cancelling"] = True
                job["cancel"].set()
            return {"job": job_id, "state": job["state"], "cancelling": job["cancelling"] and job["state"] == "running"}

    def _prune(self) -> None:
        now = time.monotonic()
        for k in [k for k, j in self._jobs.items()
                  if j["finished"] is not None and now - j["finished"] > JOB_RETENTION_SECONDS]:
            del self._jobs[k]


def _mtime(path) -> str:
    return str(path.stat().st_mtime_ns)


def _key(obj) -> str:
    return f"{obj.kind}:{obj.label}"


def _status(project, obj) -> str:
    """The object's status; script figures and data tables are asked of their own modules."""
    try:
        if obj.kind == "fig" and obj.source == "script":
            return figscripts.figure_status(project, obj.label)
        if obj.kind == "tbl" and obj.source == "data":
            return tablefmt.table_status(project, obj.label)
    except (OSError, ValueError, LookupError):
        return "failed"
    return obj.status


def _row(project, obj, number: dict | None = None) -> dict:
    row = dataclasses.asdict(obj)
    row["id"] = _key(obj)
    row["status"] = _status(project, obj)
    if number is not None:
        row["number"] = number.get(row["id"])
    return row


def _find_object(project, ident: str, kind: str | None = None):
    """The RefObject named by ``fig:label`` (or its project-relative ``.md`` path)."""
    ident = (ident or "").strip().replace("\\", "/")
    for obj in objects.list_objects(project):
        if ident in (_key(obj), obj.path):
            if kind is not None and obj.kind != kind:
                break
            return obj
    names = {"fig": "figure", "tbl": "table", "eq": "equation"}
    raise ValueError(f"no such {names.get(kind or '', 'object')}: {ident}")


def _read_note(project, obj) -> tuple[str, str, str]:
    """(front matter block verbatim, body, mtime) of an object's note."""
    path = project.root / obj.path
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = objects._BLOCK_RE.match(text)
    head = text[:m.end()] if m else ""
    return head, text[len(head):], _mtime(path)


def _table_span(lines: list[str]) -> tuple[int, int] | None:
    """[start, end) line range of the first pipe table (same rule as ``tables.parse_pipe``)."""
    for i in range(len(lines) - 1):
        if "|" not in lines[i]:
            continue
        aligns = [tables._delim_align(c) for c in tables._split_row(lines[i + 1])]
        if not aligns or None in aligns or len(tables._split_row(lines[i])) != len(aligns):
            continue
        j = i + 2
        while j < len(lines) and lines[j].strip() and "|" in lines[j]:
            j += 1
        return i, j
    return None


def _data_url(mime: str, data: bytes) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


class ResearchObjectsMixin:
    # -- lazily created per-Api state (the Api constructor is not edited) --------------------------------

    def _fig_runs(self) -> _FigureRuns:
        with _setup_lock:
            runs = getattr(self, "_figure_runs", None)
            if runs is None:
                runs = self._figure_runs = _FigureRuns()
            return runs

    def _image_cache(self) -> dict:
        with _setup_lock:
            cache = getattr(self, "_object_image_cache", None)
            if cache is None:
                cache = self._object_image_cache = {}
            return cache

    def _figure_data_url(self, project, label: str) -> str:
        """Through ``objects._figure_file`` only; cached by (path, mtime, size)."""
        path = objects._figure_file(project, label)
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
        cache = self._image_cache()
        key = str(path)
        hit = cache.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        url = _data_url(objects.MIME[path.suffix.lstrip(".")], path.read_bytes())
        cache.pop(key, None)
        cache[key] = (stamp, url)
        while len(cache) > IMAGE_CACHE_ENTRIES:
            cache.pop(next(iter(cache)))
        return url

    # -- listing and rendering ---------------------------------------------------------------------------

    @bridge
    def list_objects(self) -> dict:
        """Binder rows: every figure, table and equation (``id`` is ``fig:label``)."""
        with self._lock:
            project = self._require()
            require_research(project)
            numbers = {k: {"seq": n.seq, "display": n.display} for k, n in objects.numbering(project).items()}
            return {"objects": [_row(project, o, numbers) for o in objects.list_objects(project)]}

    @bridge
    def object_numbers(self) -> dict:
        """``{key: {seq, display}}`` in reading order; an object that is never placed has no entry."""
        with self._lock:
            project = self._require()
            require_research(project)
            numbers = objects.numbering(project)
            return {"numbers": {k: {"seq": n.seq, "display": n.display} for k, n in numbers.items()}}

    @bridge
    def object_render(self, ids: list) -> dict:
        """Batch for the editor widgets. One entry per id (same order): kind, number, caption, status and, by
        kind, ``imageUrl`` (figure), ``cells`` / ``align`` (table), ``latex`` (equation). A bad id gets an
        ``error`` entry; it never fails the batch."""
        if not isinstance(ids, (list, tuple)):
            raise ValueError("ids must be a list")
        if len(ids) > MAX_RENDER_IDS:
            raise ValueError(f"at most {MAX_RENDER_IDS} objects per request")
        with self._lock:
            project = self._require()
            require_research(project)
            numbers = objects.numbering(project)
            out = []
            for ident in ids:
                try:
                    out.append(self._render_one(project, str(ident), numbers))
                except (ValueError, OSError, LookupError) as exc:
                    out.append({"id": str(ident), "error": str(exc)})
            return {"objects": out}

    def _render_one(self, project, ident: str, numbers) -> dict:
        obj = _find_object(project, ident)
        key = _key(obj)
        num = numbers.get(key)
        entry = {"id": key, "kind": obj.kind, "label": obj.label, "caption": obj.caption,
                 "number": num.display if num else None, "seq": num.seq if num else None,
                 "status": _status(project, obj), "source": obj.source, "path": obj.path}
        if obj.kind == "fig":
            entry.update(width=obj.width, alt=obj.alt, imageUrl=None)
            try:
                entry["imageUrl"] = self._figure_data_url(project, obj.label)
            except FileNotFoundError:
                pass
        elif obj.kind == "tbl":
            _head, body, mtime = _read_note(project, obj)
            entry.update(cells=None, align=None, mtime=mtime, generated=obj.source == "data")
            try:
                t = tables.parse_pipe(body)
                entry.update(cells=t.cells, align=t.align)
            except ValueError:
                pass
        else:
            _head, body, _mtime_ = _read_note(project, obj)
            entry["latex"] = body.strip()
        return entry

    @bridge
    def object_image(self, label: str) -> dict:
        """A figure's image as a data URL (``figures/`` through the one core door, cached by mtime)."""
        with self._lock:
            project = self._require()
            require_research(project)
            return {"label": label, "dataUrl": self._figure_data_url(project, label)}

    # -- tables ------------------------------------------------------------------------------------------

    @bridge
    def read_table(self, id: str) -> dict:
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "tbl")
            _head, body, mtime = _read_note(project, obj)
            t = tables.parse_pipe(body)
            return {"id": _key(obj), "caption": obj.caption, "cells": t.cells, "align": t.align,
                    "mtime": mtime, "generated": obj.source == "data"}

    @bridge
    def save_table(self, id: str, cells: list, align: list, base_mtime: str) -> dict:
        """Write the grid back (only the table lines of the body change). A *base_mtime* that is not the file's
        current one is a conflict: nothing is written and ``conflict: true`` comes back."""
        if (not isinstance(cells, list) or not cells or not all(isinstance(r, list) for r in cells)
                or not isinstance(align, list) or not align):
            raise ValueError("a table needs a header row and at least one column")
        if len(cells) > MAX_TABLE_ROWS or len(align) > MAX_TABLE_COLS:
            raise ValueError("that table is too large")
        table = tables.Table([[str(c) for c in r] for r in cells], [str(a) for a in align])
        text = tables.to_pipe(table)         # validates the alignments
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "tbl")
            if obj.source == "data":
                raise ValueError("this table is built from data; edit the data or its format instead")
            path = project.root / obj.path
            head, body, mtime = _read_note(project, obj)
            if str(base_mtime) != mtime:
                return {"ok": False, "conflict": True, "mtime": mtime,
                        "error": "This table changed on disk since you opened it. Reload it before saving."}
            lines = body.split("\n")
            span = _table_span(lines)
            if span is None:
                new_body = text + "\n" + (("\n" + body.lstrip("\n")) if body.strip() else "")
            else:
                new_body = "\n".join(lines[:span[0]] + text.split("\n") + lines[span[1]:])
                if not new_body.endswith("\n"):
                    new_body += "\n"
            objects.write_atomic(path, (head + new_body).encode("utf-8"))
            return {"id": _key(obj), "mtime": _mtime(path)}

    @bridge
    def build_table(self, id: str) -> dict:
        """Preview of a data-built table (read-only)."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "tbl")
            return {"id": _key(obj), **_built(tablefmt.build_table(project, obj.label))}

    @bridge
    def apply_table(self, id: str) -> dict:
        """Write the built table into the note (generated body replaced)."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "tbl")
            built = tablefmt.apply_table(project, obj.label)
            return {"id": _key(obj), "mtime": _mtime(project.root / obj.path), **_built(built)}

    # -- figures -----------------------------------------------------------------------------------------

    @bridge
    def insert_figure(self, data_url: str, label: str, caption: str = "") -> dict:
        """Add a figure from a data URL (PNG or JPG decided from the bytes, 10 MB cap)."""
        if not isinstance(data_url, str):
            raise ValueError("the image is empty")
        m = _DATA_URL.match(data_url)
        if m is None:
            raise ValueError("the image must be sent as a base64 data URL")
        payload = data_url[m.end():]
        if len(payload) > (objects.MAX_IMAGE_BYTES * 4) // 3 + 8:
            raise ValueError("the image is larger than 10 MB")
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("the image data is not valid") from None
        with self._lock:
            project = self._require()
            require_research(project)
            obj = objects.create_figure(project, data, label, caption)
            return {"id": _key(obj), "object": _row(project, obj)}

    # -- creating, editing and removing objects (F0) -----------------------------------------------------

    @bridge
    def create_table(self, label: str, caption: str, cells: list, align: list | None = None) -> dict:
        """Add a table note from a grid (canonical pipe table; caps in core.objects)."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = objects.create_table(project, label, caption, cells, align)
            return {"id": _key(obj), "object": _row(project, obj)}

    @bridge
    def create_equation(self, label: str, latex: str, caption: str = "") -> dict:
        """Add an equation note (the LaTeX is its body)."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = objects.create_equation(project, label, latex, caption)
            return {"id": _key(obj), "object": _row(project, obj)}

    @bridge
    def update_object(self, id: str, caption: str | None = None, alt: str | None = None,
                      width: float | None = None, latex: str | None = None) -> dict:
        """Change a figure's caption / alt / width, an equation's latex / caption or a table's caption. Other
        frontmatter keys are kept; the write is atomic."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id)
            new = objects.update_object(project, obj.kind, obj.label, caption=caption, alt=alt,
                                        width=width, latex=latex)
            return {"object": _row(project, new)}

    @bridge
    def trash_object(self, id: str) -> dict:
        """Move an object (note plus image / CSV) to the project Trash. A placement of it in a section is left
        as it is and shows as unresolved; restoring from the Trash brings the object back."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id)
            project.trash_object(obj.path)
            return {"trashed": True, "name": obj.caption or obj.label}

    @bridge
    def object_references(self, id: str) -> dict:
        """Where an object is placed (``![[id]]``) and referenced (``[[id]]``) in the book's sections, as
        ``{doc, title, row}`` (0-based row). Parked sections are not in the book."""
        from . import workspace as ws
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id)
            found = objects.references(project, obj.kind, obj.label)

            def rows(items):
                return [{"doc": ws.rel_id(project, p), "title": project.scene_title(p), "row": r}
                        for p, r in items]
            return {"placements": rows(found["placements"]), "refs": rows(found["refs"])}

    @bridge
    def object_suggest_label(self, kind: str, caption: str = "") -> dict:
        """A unique plain label for a new figure, table or equation (no AI)."""
        with self._lock:
            project = self._require()
            require_research(project)
            return {"label": objects.suggest_label(project, kind, caption)}

    # -- generated figures: trust and run ----------------------------------------------------------------

    @bridge
    def figure_trust_info(self, id: str) -> dict:
        """What the confirmation dialog shows: the script text, its SHA-256, its path and the interpreter."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "fig")
            md = figscripts._md_path(project, obj.label)
            meta, _ = figscripts._read_meta(md)
            script = figscripts._script_path(project, meta)
            raw = script.read_bytes()
            sha = figscripts.script_sha(project, obj.label)
            if sha != figscripts._sha(raw):
                raise RuntimeError("the script changed while it was read; try again")
            py = figscripts.interpreter()
            return {"id": _key(obj), "script": raw.decode("utf-8", errors="replace"), "sha": sha,
                    "path": figscripts._rel(project, script),
                    "interpreter": str(py) if py is not None else None,
                    "data": [figscripts._rel(project, p) for p in figscripts._data_paths(project, meta)],
                    "trust": figscripts.trust_state(project, obj.label)}

    @bridge
    def trust_figure(self, id: str, sha: str) -> dict:
        """Record the author's confirmation of the script whose hash the dialog showed (never automatic)."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "fig")
            figscripts.trust_figure(project, obj.label, str(sha))
            return {"id": _key(obj), "trust": figscripts.trust_state(project, obj.label)}

    @bridge
    def figure_run_start(self, id: str) -> dict:
        """Start the script on a worker thread (the only place a script ever starts). Refused with a plain
        message unless the script is trusted. Poll with figure_run_status."""
        with self._lock:
            project = self._require()
            require_research(project)
            obj = _find_object(project, id, "fig")
            state = figscripts.trust_state(project, obj.label)
        if state == "untrusted":
            raise ValueError("this script has not been confirmed; review and confirm it first")
        if state == "changed":
            raise ValueError("the script changed since you confirmed it; confirm it again")
        return {"job": self._fig_runs().start(project, obj.label), "id": _key(obj)}

    @bridge
    def figure_run_status(self, job: str) -> dict:
        """``state`` is running | done | failed | cancelled; failed carries ``error`` and the ``stderr`` tail."""
        return self._fig_runs().status(job)

    @bridge
    def figure_run_cancel(self, job: str) -> dict:
        """Stop a run (idempotent); the process tree is killed and the old image is left as it was."""
        return self._fig_runs().cancel(job)

    # -- AI proposals (text only) ------------------------------------------------------------------------

    def _spent(self, calls_before: int):
        last = LEDGER.last()
        return last.cost if LEDGER.count() > calls_before and last is not None else None

    @bridge
    def suggest_latex(self, description: str) -> dict:
        """A LaTeX equation proposed from *description*. Text only: nothing is inserted or saved. Runs inside
        ai_start when the lead lists it in Api.AI_JOBS; also fine as a plain synchronous call."""
        from . import api as api_module        # looked up at CALL time so tests can patch it

        description = (description or "").strip()
        if not description:
            raise ValueError("describe the equation first")
        with self._lock:
            project = self._require()
            require_research(project)
            model = resolve_model("fast", project.meta)
            from ..ai import paper
            sent = paper.plan_latex(description, model=model)
            calls = LEDGER.count()
        fn = getattr(api_module, "suggest_latex", None) or paper.suggest_latex
        job = aijobs.current()
        text = call_ai(fn, description, model=model, cancel=job.cancel if job else CancelToken())
        return {"text": text, "model": model, "cost": self._spent(calls), "sent": sent.to_dict()}

    @bridge
    def suggest_plot_code(self, description: str, columns_ticked: list | None = None) -> dict:
        """A matplotlib script proposed from *description*. *columns_ticked* is the list of column names the
        author ticked to share (omit or empty: no column names are sent). Text only: never saved or run."""
        from . import api as api_module

        description = (description or "").strip()
        if not description:
            raise ValueError("describe the figure first")
        columns = [str(c) for c in columns_ticked] if columns_ticked else None
        with self._lock:
            project = self._require()
            require_research(project)
            model = resolve_model("fast", project.meta)
            from ..ai import paper
            sent = paper.plan_plot_code(description, columns, model=model)
            calls = LEDGER.count()
        fn = getattr(api_module, "suggest_plot_code", None) or paper.suggest_plot_code
        job = aijobs.current()
        text = call_ai(fn, description, columns, model=model, cancel=job.cancel if job else CancelToken())
        return {"text": text, "model": model, "cost": self._spent(calls), "sent": sent.to_dict()}


def _built(b) -> dict:
    return {"markdown": b.markdown, "grid": b.grid, "latex": b.latex, "warnings": list(b.warnings),
            "caption": b.caption, "footnotes": list(b.footnotes)}
