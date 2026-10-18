"""Generated figures: trust, staleness, provenance and the run (docs/dev/plan-research-mode.md 7.4).

A generated figure is ``figures/fig-<label>.md`` (YAML ``source: script``, ``script:``, ``data: [...]`` and a
``run:`` provenance record), the author's ``.py`` and the output PNG. Nothing here runs on its own: only
``run_figure`` runs code, only after ``trust_figure`` recorded the exact bytes, and never in this process.

Trust. The record lives ONLY in ``<state dir>/figure-trust/<project-id>.json`` (``recents.default_state_dir``;
``CHISEL_STATE_DIR`` honoured), keyed by project id (a hash of the resolved project path, so a cloned or moved
project arrives unconfirmed), the figure's project-relative path and the script's SHA-256. Nothing inside the
project is ever read as trust, including the ``run:`` record, which is provenance only. ``trust_figure`` is the
only writer.

Execution (all of it is the plan's contract): the hashed bytes are copied to a temp folder and the COPY runs, as
``<python> -I -X utf8 chisel_runner.py ...`` with the temp folder as working directory, a scrubbed environment
and ``NO_CONSOLE``; a timeout (or a cancel) kills the whole process tree; stdout and stderr are capped; the PNG
is checked by its bytes and replaced atomically, so a failed run leaves the old image byte-identical. The
interpreter is the per-user setting ``figure_python`` and is refused when it lives inside the project.
Chisel cannot sandbox a script's file or network access.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

from . import fsutil, objects, settings, stats
from .desktop import NO_CONSOLE
from .paper.types import ObjectStatus

INTERPRETER_SETTING = "figure_python"
DEFAULT_TIMEOUT = 120.0
OUTPUT_CAP = 64 * 1024              # bytes kept of each of stdout and stderr
ERROR_CHARS = 2000                  # error text kept in the result and the provenance record
DEFAULT_WIDTH = 6.0                 # inches; project setting [research] figure_width
SCRUBBED_PREFIXES = ("CHISEL_", "LOREWRITE_", "PYTHON")
SCRUBBED_NAMES = ("OPENROUTER_API_KEY",)

_HERE = Path(__file__).resolve().parent
RUNNER_FILE = _HERE / "chisel_runner.py"
STYLE_FILE = _HERE / "figure.mplstyle"
TEMPLATE_FILE = _HERE / "figscript_template.py.txt"

TrustState = Literal["trusted", "untrusted", "changed"]


@dataclass
class RunResult:
    status: ObjectStatus                 # "current" after a good run, "failed" otherwise
    error: str = ""                      # plain words, then the tail of stderr
    refused: bool = False                # not run at all (untrusted, no interpreter, ...)
    timed_out: bool = False
    cancelled: bool = False
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    provenance: dict = field(default_factory=dict)      # the ``run:`` record written to the figure's .md


# -- ids and files ---------------------------------------------------------------------


def starter_script() -> str:
    """The starter template (read CSV, plot, save) as text."""
    return TEMPLATE_FILE.read_text(encoding="utf-8")


def _require_research(project) -> None:
    if project.mode != "research":
        raise ValueError("generated figures are a research-project feature")


def _md_path(project, id: str) -> Path:
    """The figure's ``.md`` for a label (``flow-model``), ``fig:flow-model``, a stem (``fig-flow-model``) or
    the project-relative path. ValueError when it names nothing valid."""
    raw = (id or "").strip().replace("\\", "/")
    folder = project.root / objects.KINDS["fig"][0]
    prefix = objects.KINDS["fig"][1]
    if "/" in raw and raw.rsplit("/", 1)[0] != objects.KINDS["fig"][0]:
        raise ValueError(f"no such figure: {id}")
    name = raw.rsplit("/", 1)[-1]
    if name.endswith(".md"):
        name = name[:-3]
    candidates = []
    if raw.startswith("fig:"):
        candidates.append(raw[4:])
    elif "/" in raw or raw.endswith(".md"):
        candidates.append(name[len(prefix):] if name.startswith(prefix) else name)
    else:
        candidates += [raw, raw[len(prefix):] if raw.startswith(prefix) else raw]
    for label in candidates:
        if objects._LABEL_RE.match(label or "") and (folder / f"{prefix}{label}.md").is_file():
            return folder / f"{prefix}{label}.md"
    raise ValueError(f"no such figure: {id}")


def _rel(project, path: Path) -> str:
    return path.relative_to(project.root).as_posix()


def _read_meta(md: Path) -> tuple[dict, str]:
    return objects._split(md.read_text(encoding="utf-8"))


def _script_path(project, meta: dict) -> Path:
    script = meta.get("script")
    if meta.get("source") != "script" or not isinstance(script, str) or not script.strip():
        raise ValueError("this figure is not made by a script")
    rel = script.strip().replace("\\", "/")
    if "/" not in rel:
        rel = f"figures/{rel}"
    path = objects.safe_project_path(project, rel)
    if path.suffix != ".py":
        raise ValueError("a figure script is a .py file")
    return path


def _data_paths(project, meta: dict) -> list[Path]:
    raw = meta.get("data") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("data: must be a list of project files")
    return [objects.safe_project_path(project, str(item)) for item in raw]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _data_sha(project, paths: list[Path]) -> str:
    """One hash over the listed data files (name and bytes, in the listed order); a missing file counts as such."""
    h = hashlib.sha256()
    for p in paths:
        h.update(_rel(project, p).encode("utf-8") + b"\0")
        try:
            h.update(hashlib.sha256(p.read_bytes()).digest())
        except OSError:
            h.update(b"missing")
    return h.hexdigest()


def _width(project) -> float:
    raw = (getattr(project, "meta", None) or {}).get("research")
    try:
        w = float(raw.get("figure_width")) if isinstance(raw, dict) and raw.get("figure_width") is not None else DEFAULT_WIDTH
    except (TypeError, ValueError):
        w = DEFAULT_WIDTH
    return w if 1.0 <= w <= 20.0 else DEFAULT_WIDTH


# -- trust (per-user state folder only) ------------------------------------------------


def _trust_file(project, state_dir: Path | None = None) -> Path:
    from .recents import default_state_dir
    return (state_dir or default_state_dir()) / "figure-trust" / f"{stats.project_id(project.root)}.json"


def _load_trust(project) -> dict:
    try:
        data = json.loads(_trust_file(project).read_text(encoding="utf-8"))
        scripts = data.get("scripts") if isinstance(data, dict) else None
        return scripts if isinstance(scripts, dict) else {}
    except (OSError, ValueError):
        return {}


def script_sha(project, id: str) -> str:
    """SHA-256 of the figure's script as it is now (what the confirmation dialog shows and passes back).
    ValueError / FileNotFoundError when the figure or the script is not there."""
    _require_research(project)
    md = _md_path(project, id)
    meta, _ = _read_meta(md)
    return _sha(_script_path(project, meta).read_bytes())


def trust_state(project, id: str) -> TrustState:
    """``trusted`` when the per-user record holds this script's current hash; ``changed`` when it holds another
    hash for this figure (ask again); ``untrusted`` otherwise. Reads only the per-user state folder."""
    _require_research(project)
    md = _md_path(project, id)
    try:
        meta, _ = _read_meta(md)
        current = _sha(_script_path(project, meta).read_bytes())
    except (OSError, ValueError):
        return "untrusted"
    recorded = _load_trust(project).get(_rel(project, md))
    if not isinstance(recorded, str):
        return "untrusted"
    return "trusted" if recorded == current else "changed"


def trust_figure(project, id: str, sha: str) -> None:
    """Record that the author confirmed the script whose hash is *sha*. Called only from the confirmation
    dialog; the only writer of the trust record. ValueError when *sha* is not the script's current hash (the
    file changed after the dialog showed it, so what was confirmed is not what would run)."""
    _require_research(project)
    md = _md_path(project, id)
    meta, _ = _read_meta(md)
    current = _sha(_script_path(project, meta).read_bytes())
    if sha != current:
        raise ValueError("the script changed since it was shown; review it again")
    path = _trust_file(project)
    scripts = _load_trust(project)
    scripts[_rel(project, md)] = sha
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps({"scripts": scripts}, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


# -- status ----------------------------------------------------------------------------


def figure_status(project, id: str) -> ObjectStatus:
    """``current`` (output matches the script and data of the last good run), ``stale`` (script or data changed
    since, or the figure was never run), ``failed`` (the last run failed and nothing changed since) or
    ``missing`` (no image to show)."""
    _require_research(project)
    md = _md_path(project, id)
    meta, _ = _read_meta(md)
    png = md.with_suffix(".png")
    has_image = png.is_file() or md.with_suffix(".jpg").is_file()
    run = meta.get("run") if isinstance(meta.get("run"), dict) else None
    try:
        s_sha = _sha(_script_path(project, meta).read_bytes())
        d_sha = _data_sha(project, _data_paths(project, meta))
    except (OSError, ValueError):
        return "missing" if not has_image else "stale"
    same = run is not None and run.get("script_sha") == s_sha and run.get("data_sha") == d_sha
    if same and run.get("status") == "failed":
        return "failed"
    if not has_image:
        return "missing"
    return "current" if same else "stale"


# -- running ---------------------------------------------------------------------------


def interpreter() -> Path | None:
    value = settings.get(INTERPRETER_SETTING)
    return Path(value).expanduser() if isinstance(value, str) and value.strip() else None


def _scrubbed_env(tmp: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in SCRUBBED_NAMES and not k.upper().startswith(SCRUBBED_PREFIXES)}
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(tmp / "mpl")
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the child and everything it started (``subprocess`` timeouts only kill the direct child)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15,
                           **NO_CONSOLE)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _drain(stream, sink: bytearray) -> None:
    """Keep the first OUTPUT_CAP bytes and discard the rest, so a chatty script cannot fill memory or disk."""
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            room = OUTPUT_CAP - len(sink)
            if room > 0:
                sink.extend(chunk[:room])
    except (OSError, ValueError):
        return


def _refuse(message: str) -> RunResult:
    return RunResult("failed", error=message, refused=True)


def _write_run(md: Path, record: dict) -> None:
    """Rewrite only the figure's ``run:`` key (and ``file:`` when absent); the body is kept byte for byte."""
    text = md.read_text(encoding="utf-8")
    meta, body = objects._split(text)
    meta = dict(meta)
    meta["run"] = record
    meta.setdefault("file", f"figures/{md.stem}.png")
    head = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=10_000, default_flow_style=False)
    objects._write(md, f"---\n{head}---\n{body}")


def _tail(text: str) -> str:
    text = text.strip()
    return text[-ERROR_CHARS:] if len(text) > ERROR_CHARS else text


def run_figure(project, id: str, *, timeout: float | None = None,
               cancel: threading.Event | None = None) -> RunResult:
    """Run the figure's script. Refuses (``refused=True``, nothing executed) unless ``trust_state`` is
    ``trusted`` and the interpreter setting names a Python outside the project. Never raises for a failed run.
    Call it from a job, never while holding the bridge lock. *timeout* (seconds) and *cancel* (an Event the
    job sets on Stop) are optional additions to the contract signature."""
    _require_research(project)
    md = _md_path(project, id)
    meta, _ = _read_meta(md)
    try:
        script = _script_path(project, meta)
        data_files = _data_paths(project, meta)
        script_bytes = script.read_bytes()        # the bytes that are hashed are the bytes that run
    except (OSError, ValueError) as exc:
        return _refuse(f"cannot run: {exc}")
    s_sha = _sha(script_bytes)
    recorded = _load_trust(project).get(_rel(project, md))
    if recorded != s_sha:
        return _refuse("this script has not been confirmed" if recorded is None
                       else "the script changed since you confirmed it; confirm it again")
    py = interpreter()
    if py is None:
        return _refuse(f"no Python is set for figure scripts; choose one in Settings ({INTERPRETER_SETTING})")
    try:
        inside = py.resolve().is_relative_to(project.root.resolve())
    except OSError:
        inside = False
    if inside:
        return _refuse("the figure Python is inside the project folder; Chisel never runs an interpreter "
                       "that came with a project")
    if not py.is_file():
        return _refuse(f"the figure Python does not exist: {py}")
    d_sha = _data_sha(project, data_files)
    seconds = DEFAULT_TIMEOUT if timeout is None else timeout
    png_final = md.with_suffix(".png")

    out_buf, err_buf = bytearray(), bytearray()
    timed_out = cancelled = False
    returncode: int | None = None
    run_meta: dict = {}
    produced: bytes | None = None
    with tempfile.TemporaryDirectory(prefix="chisel-fig-", ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        (tmp / "mpl").mkdir()
        runner = tmp / "chisel_runner.py"
        author = tmp / "figure_script.py"
        out_png = tmp / "out.png"
        meta_json = tmp / "meta.json"
        try:
            shutil.copyfile(RUNNER_FILE, runner)
            author.write_bytes(script_bytes)
        except OSError as exc:
            return _refuse(f"cannot prepare the run: {exc}")
        cmd = [str(py), "-I", "-X", "utf8", str(runner), "--script", str(author), "--out", str(out_png),
               "--data", str(project.root / "data"), "--style", str(STYLE_FILE), "--meta", str(meta_json),
               "--width", str(_width(project))]
        extra = {} if sys.platform == "win32" else {"start_new_session": True}
        try:
            proc = subprocess.Popen(cmd, cwd=str(tmp), env=_scrubbed_env(tmp), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, **NO_CONSOLE, **extra)
        except OSError as exc:
            return _refuse(f"cannot start the figure Python: {exc}")
        readers = [threading.Thread(target=_drain, args=(proc.stdout, out_buf), daemon=True),
                   threading.Thread(target=_drain, args=(proc.stderr, err_buf), daemon=True)]
        for t in readers:
            t.start()
        deadline = time.monotonic() + seconds
        while True:
            try:
                returncode = proc.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel is not None and cancel.is_set():
                cancelled = True
            elif time.monotonic() >= deadline:
                timed_out = True
            if cancelled or timed_out:
                _kill_tree(proc)
                try:
                    returncode = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    returncode = None
                break
        for t in readers:
            t.join(timeout=3)
        try:
            run_meta = json.loads(meta_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            run_meta = {}
        if returncode == 0 and not timed_out and not cancelled and out_png.is_file():
            size = out_png.stat().st_size
            if size <= objects.MAX_IMAGE_BYTES:
                produced = out_png.read_bytes()
        out_size = out_png.stat().st_size if out_png.is_file() else 0

    stdout = bytes(out_buf).decode("utf-8", "replace")
    stderr = bytes(err_buf).decode("utf-8", "replace")
    error = ""
    if cancelled:
        error = "stopped"
    elif timed_out:
        error = f"the script ran longer than {seconds:g} seconds and was stopped"
    elif returncode != 0:
        error = _tail(stderr) or f"the script failed (exit code {returncode})"
    elif produced is None:
        if out_size > objects.MAX_IMAGE_BYTES:
            error = "the script wrote an image larger than 10 MB"
        else:
            error = "the script did not write the PNG to OUT"
    elif objects.sniff_image(produced) != "png":
        error = "the script's output is not a PNG file"
        produced = None
    record = {
        "python": str(run_meta.get("python") or ""),
        "packages": run_meta.get("packages") if isinstance(run_meta.get("packages"), dict) else {},
        "script_sha": s_sha,
        "data_sha": d_sha,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok" if not error else "failed",
    }
    if error:
        record["error"] = _tail(error)
    if produced is not None and not error:
        tmp_final = png_final.with_name(f".{png_final.name}.tmp")
        try:
            tmp_final.write_bytes(produced)
            fsutil.replace(tmp_final, png_final)
        except OSError as exc:
            tmp_final.unlink(missing_ok=True)
            error = f"cannot save the image: {exc}"
            record["status"], record["error"] = "failed", error
    if not cancelled:                        # a Stop leaves the figure exactly as it was
        try:
            _write_run(md, record)
        except OSError:
            pass
    return RunResult("failed" if error else "current", error=error, timed_out=timed_out, cancelled=cancelled,
                     stdout=stdout, stderr=stderr, returncode=returncode, provenance=record)
