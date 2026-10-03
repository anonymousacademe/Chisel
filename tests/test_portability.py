"""Portability: state dir, retrying renames, LF line endings."""

import sys
from pathlib import Path

import pytest

from chisel.core import fsutil, recents
from chisel.core.project import Project, write_atomic


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the Linux state dir")
def test_linux_state_dir_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.delenv("CHISEL_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert recents.default_state_dir() == tmp_path / ".local/state/chisel"


def test_state_dir_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path / "s"))
    assert recents.default_state_dir() == tmp_path / "s"


def test_replace_retries_a_locked_file(monkeypatch, tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x")
    real, calls = Path.replace, []

    def flaky(self, target):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("locked")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    monkeypatch.setattr(fsutil, "DELAY", 0)
    fsutil.replace(src, dst)
    assert len(calls) == 3 and dst.read_text() == "x"


def test_replace_gives_up_after_the_attempts(monkeypatch, tmp_path):
    src = tmp_path / "a"
    src.write_text("x")
    calls = []

    def locked(self, target):
        calls.append(1)
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr(fsutil, "DELAY", 0)
    with pytest.raises(PermissionError):
        fsutil.replace(src, tmp_path / "b")
    assert len(calls) == fsutil.ATTEMPTS


def test_saves_write_lf_even_when_the_platform_would_not(monkeypatch, tmp_path):
    """write_text(newline="\\n") is what keeps Windows from writing CRLF; check the
    call sites pass it by intercepting the open() mode."""
    seen = []
    real = Path.write_text

    def spy(self, data, encoding=None, errors=None, newline=None):
        seen.append(newline)
        return real(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", spy)
    write_atomic(tmp_path / "scene.md", "a\nb\n")
    Project.create(tmp_path / "book", "Book")
    assert seen and set(seen) == {"\n"}
    assert b"\r" not in (tmp_path / "scene.md").read_bytes()


def test_every_write_text_in_src_pins_the_newline():
    import ast

    root = Path(__file__).resolve().parents[1] / "src" / "chisel"
    bad = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "write_text"
                    and not any(k.arg == "newline" for k in node.keywords)):
                bad.append(f"{path.name}:{node.lineno}")
    assert not bad, bad
