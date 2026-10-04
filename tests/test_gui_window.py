"""The window-controls bridge (WindowMixin): the native drag hand-off."""

import sys

import pytest

from tests.test_gui_api import open_api


class _FakeForm:
    def __init__(self, calls):
        self.calls = calls

    @property
    def Handle(self):
        self.calls.append("handle")
        return 4242  # a real System.IntPtr converts with int(); an int does too


class _FakeWindow:
    def __init__(self, calls):
        self.native = _FakeForm(calls)


@pytest.mark.skipif(not sys.platform == "win32", reason="the native drag is Windows-only")
def test_begin_window_drag_sends_the_caption_drag(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    calls = []
    api._window = _FakeWindow(calls)

    sent = []
    user32 = type("U", (), {})()
    user32.ReleaseCapture = lambda: calls.append("release")
    user32.SendMessageW = lambda hwnd, msg, w, l: sent.append((hwnd, msg, w, l))

    import chisel.gui.window_api as wa

    monkeypatch.setattr(wa.ctypes, "windll", type("W", (), {"user32": user32}))
    r = api.begin_window_drag()
    assert r["ok"] is True
    assert calls == ["handle", "release"]
    assert sent == [(4242, wa.WM_NCLBUTTONDOWN, wa.HTCAPTION, 0)]


def test_begin_window_drag_without_a_window_is_a_clean_noop(tmp_path):
    api, _ = open_api(tmp_path)
    api._window = None
    assert api.begin_window_drag()["ok"] is True
