"""``lorewrite-gui --self-test``: prove that everything which needs bundled data
works, with no window and no network, and print a JSON report.

It is the main guard on the packaged apps (PyInstaller bundles lose data files
and hidden imports easily): CI runs it on every built bundle. Exit status 0 when
every required check passed, 1 otherwise.
"""

from __future__ import annotations

import importlib
import json
import platform
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable

from . import __version__


def _web() -> str:
    from .gui.webroot import find_dist
    dist = find_dist()
    if dist is None:
        raise RuntimeError("no built UI (web/index.html) found")
    assets = list((dist / "assets").glob("*.js"))
    if not assets:
        raise RuntimeError(f"{dist} has no assets/*.js")
    return str(dist)


def _fonts() -> str:
    from .core.export import pdfkit
    missing = sorted(p.name for p in (pdfkit.BUNDLED / f"{s}.ttf"
                                      for k in ("noto-serif", "liberation-mono")
                                      for s in pdfkit.FONTS[k][3]) if not p.is_file())
    if missing:
        raise RuntimeError(f"bundled fonts missing: {', '.join(missing)}")
    present = pdfkit.fonts_present()
    if not {"noto-serif", "liberation-mono"} <= present:
        raise RuntimeError(f"fonts not usable: {sorted(present)}")
    return ", ".join(sorted(present))


def _spelling() -> str:
    from .core import spelling
    flagged = [m.word for m in spelling.check("This sentense has a mispelled wrd.")]
    if "mispelled" not in flagged:
        raise RuntimeError(f"the dictionary flagged {flagged}")
    if "misspelled" not in spelling.suggestions("mispelled"):
        raise RuntimeError("no suggestion for 'mispelled'")
    return "dictionary loaded"


def _pyphen() -> str:
    import pyphen
    out = pyphen.Pyphen(lang="en_US").inserted("hyphenation")
    if "-" not in out:
        raise RuntimeError("pyphen did not hyphenate")
    return out


def _textual() -> str:
    import textual
    from textual.widgets import TextArea  # noqa: F401
    from .tui.app import LorewriteApp  # noqa: F401  (imports every screen and its CSS)
    css = Path(textual.__file__).resolve().parent / "widgets"
    if not css.is_dir():
        raise RuntimeError("textual package data missing")
    return f"textual {textual.__version__}"


def _keyring() -> str:
    import keyring
    return type(keyring.get_keyring()).__module__ + "." + type(keyring.get_keyring()).__name__


def _tls() -> str:
    import ssl
    import openai  # noqa: F401
    try:  # recent httpx uses the OS trust store; older ones the certifi bundle
        # (optional transitive dependencies: loaded by name, not declared)
        importlib.import_module("truststore").SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return "truststore (OS certificates)"
    except ImportError:
        certifi = importlib.import_module("certifi")
        path = Path(certifi.where())
        if not path.is_file():
            raise RuntimeError("certifi CA bundle missing")
        ssl.create_default_context(cafile=str(path))
        return "certifi CA bundle"


def _layouts() -> str:
    from .core.export import layouts
    names = [layout.name for layout in layouts.all_layouts()]
    if names != ["book", "manuscript", "plain"]:
        raise RuntimeError(f"layouts: {names}")
    return ", ".join(names)


def _pdf() -> str:
    from .core.export import ExportOptions, run_export
    from .core.project import Project
    with tempfile.TemporaryDirectory(prefix="lorewrite-selftest-") as tmp:
        project = Project.create(Path(tmp) / "novel", "Self Test")
        (project.manuscript_dir / "01-opening.md").write_text(
            "# Opening\n\nIt was a *quiet* morning, and nothing hyphenated itself.\n",
            encoding="utf-8", newline="\n")
        res = run_export(project, ExportOptions(format="pdf", layout="book"))
        data = res.path.read_bytes()
        if not data.startswith(b"%PDF") or len(data) < 1500:
            raise RuntimeError("the exported PDF is not valid")
        return f"{res.pages} pages, {len(data)} bytes"


def _gui_backend() -> str:
    import webview  # noqa: F401
    if sys.platform == "win32":
        mod = "webview.platforms.edgechromium"
    elif sys.platform == "darwin":
        mod = "webview.platforms.cocoa"
    else:
        mod = "webview.platforms.qt"
        try:
            importlib.import_module("qtpy")
        except ImportError:
            mod = "webview.platforms.gtk"
    importlib.import_module(mod)
    return mod


def _render() -> str:
    """Opt-in (LOREWRITE_SELFTEST_RENDER=1, Linux bundle): load the built UI in
    QtWebEngine on Qt's offscreen platform (no window, no display) and read the
    page title back. Proves the bundled Chromium starts."""
    import os
    if os.environ.get("LOREWRITE_SELFTEST_RENDER") != "1":
        return "skipped (set LOREWRITE_SELFTEST_RENDER=1)"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    QTimer = importlib.import_module("qtpy.QtCore").QTimer
    QUrl = importlib.import_module("qtpy.QtCore").QUrl
    QWebEngineView = importlib.import_module("qtpy.QtWebEngineWidgets").QWebEngineView
    QApplication = importlib.import_module("qtpy.QtWidgets").QApplication
    from .gui.webroot import find_dist
    app = QApplication.instance() or QApplication(sys.argv[:1])
    view = QWebEngineView()
    result: dict = {}
    view.loadFinished.connect(lambda ok: result.update(ok=ok, title=view.page().title()))
    view.load(QUrl.fromLocalFile(str(find_dist() / "index.html")))
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(app.quit)
    deadline.start(60000)
    view.loadFinished.connect(lambda ok: app.quit())
    app.exec()
    if not result.get("ok"):
        raise RuntimeError(f"the UI did not load in QtWebEngine: {result}")
    return f"loaded, title {result['title']!r}"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("web ui", _web),
    ("fonts", _fonts),
    ("spelling", _spelling),
    ("hyphenation", _pyphen),
    ("textual", _textual),
    ("keyring", _keyring),
    ("tls", _tls),
    ("export layouts", _layouts),
    ("pdf export", _pdf),
    ("gui backend", _gui_backend),
    ("webengine render", _render),
]


def run() -> dict:
    results = []
    for name, fn in CHECKS:
        try:
            results.append({"name": name, "ok": True, "detail": fn()})
        except BaseException as exc:  # a broken bundle can fail in any way
            results.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc(limit=4)})
    return {"version": __version__, "python": platform.python_version(),
            "platform": platform.platform(), "frozen": bool(getattr(sys, "frozen", False)),
            "ok": all(r["ok"] for r in results), "checks": results}


def main(report_path: str | None = None) -> int:
    """Run the checks, print the JSON report, return the exit status. A windowed
    Windows exe has no stdout, so the report also goes to *report_path* (default:
    ``lorewrite-selftest.json`` in the temp folder when there is no stdout)."""
    report = run()
    text = json.dumps(report, indent=2)
    if sys.stdout is not None:
        print(text)
    elif report_path is None:
        report_path = str(Path(tempfile.gettempdir()) / "lorewrite-selftest.json")
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8", newline="\n")
    return 0 if report["ok"] else 1
