from __future__ import annotations

import logging

from chisel.core import applog


def test_log_exc_writes_to_state_dir_and_scrubs(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path))
    applog.close()
    try:
        applog.log_exc("saving", ValueError("bad key sk-abcdef123456 here"), level=logging.WARNING)
        path = applog.log_path()
        assert path == tmp_path / "log" / "chisel.log"
        for h in logging.getLogger("chisel").handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        assert "saving" in text and "ValueError" in text
        assert "sk-abcdef" not in text and "[redacted]" in text
    finally:
        applog.close()


def test_log_exc_follows_state_dir_change_and_never_raises(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("CHISEL_STATE_DIR", str(a))
    applog.close()
    try:
        applog.log_exc("one")
        monkeypatch.setenv("CHISEL_STATE_DIR", str(b))
        applog.log_exc("two", RuntimeError("x" * 1000))
        for h in logging.getLogger("chisel").handlers:
            h.flush()
        assert "two" in (b / "log" / "chisel.log").read_text(encoding="utf-8")
        assert len(applog.scrub("x" * 1000)) < 300
        # an unusable state dir (a file where the folder should be) must not raise
        blocked = tmp_path / "file"
        blocked.write_text("x")
        monkeypatch.setenv("CHISEL_STATE_DIR", str(blocked))
        applog.log_exc("three", OSError("nope"))
    finally:
        applog.close()
