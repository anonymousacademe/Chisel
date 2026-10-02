"""core/desktop.open_path picks the right opener per platform (all faked)."""

import os
import sys

from lorewrite.core import desktop


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
