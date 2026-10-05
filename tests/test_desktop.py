"""core/desktop.open_path picks the right opener per platform (all faked)."""

import os
import sys

from chisel.core import desktop


def _popen(monkeypatch, seen, fail=False):
    def fake(cmd, **kw):
        if fail:
            raise FileNotFoundError(cmd[0])
        seen.append((cmd, kw.get("start_new_session")))
    monkeypatch.setattr(desktop.subprocess, "Popen", fake)


def test_linux_uses_xdg_open(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(sys, "platform", "linux")
    _popen(monkeypatch, seen)
    assert desktop.open_path(tmp_path) is True
    assert seen == [(["xdg-open", str(tmp_path)], True)]


def test_macos_uses_open(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(sys, "platform", "darwin")
    _popen(monkeypatch, seen)
    assert desktop.open_path(str(tmp_path)) is True
    assert seen[0][0] == ["open", str(tmp_path)]


def test_windows_uses_startfile(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", seen.append, raising=False)
    _popen(monkeypatch, seen, fail=True)  # Popen must not be used
    assert desktop.open_path(tmp_path) is True
    assert seen == [str(tmp_path)]


def test_missing_opener_is_false_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    _popen(monkeypatch, [], fail=True)
    assert desktop.open_path(tmp_path) is False


def test_no_console_hides_child_windows_on_windows():
    # the windowed Windows app has no console: without this every git status
    # flashes a console window over the app
    import subprocess
    if sys.platform == "win32":
        assert desktop.NO_CONSOLE == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert desktop.NO_CONSOLE == {}


def test_every_subprocess_call_passes_no_console():
    # a new subprocess call in the app must pass **NO_CONSOLE too
    import re
    from pathlib import Path
    src = Path(desktop.__file__).resolve().parents[1]
    missing = []
    for path in src.rglob("*.py"):
        if "tui" in path.parts:   # the terminal app has a console already
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"subprocess\.(run|Popen|call|check_output|check_call)\(", text):
            depth, i = 0, m.end() - 1
            while True:
                depth += {"(": 1, ")": -1}.get(text[i], 0)
                if depth == 0:
                    break
                i += 1
            call = text[m.start():i]
            if "NO_CONSOLE" not in call and "start_new_session" not in call:
                missing.append(f"{path.name}:{text.count(chr(10), 0, m.start()) + 1}")
    assert not missing, missing
