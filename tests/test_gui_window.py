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
        return 4242


class _FakeIntPtr:
    """pythonnet 3 gives System.IntPtr, which has ToInt64() but no __int__: int() raises TypeError."""

    def __init__(self, value):
        self.value = value

    def ToInt64(self):
        return self.value


class _FakeWindow:
    def __init__(self, calls, form=None):
        self.native = form or _FakeForm(calls)


def _patch_user32(monkeypatch, calls, sent, zoomed=0):
    user32 = type("U", (), {})()
    user32.ReleaseCapture = lambda: calls.append("release")
    user32.SendMessageW = lambda hwnd, msg, w, l: sent.append((hwnd, msg, w, l))
    user32.IsZoomed = lambda hwnd: zoomed
    import chisel.gui.window_api as wa

    monkeypatch.setattr(wa.ctypes, "windll", type("W", (), {"user32": user32}), raising=False)
    return wa


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


def test_begin_window_drag_accepts_an_intptr_handle(tmp_path, monkeypatch):
    """Regression: int(form.Handle) raised TypeError for a real System.IntPtr, so the drag never ran."""
    api, _ = open_api(tmp_path)
    calls, sent = [], []

    class Form:
        Handle = _FakeIntPtr(4242)

    api._window = _FakeWindow(calls, Form())
    wa = _patch_user32(monkeypatch, calls, sent)
    assert api.begin_window_drag()["ok"] is True
    assert sent == [(4242, wa.WM_NCLBUTTONDOWN, wa.HTCAPTION, 0)]


def test_begin_window_drag_runs_on_the_ui_thread_when_needed(tmp_path, monkeypatch):
    """ReleaseCapture only works on the thread that owns the capture, so a form that requires
    Invoke must have the drag run through it, not on the bridge worker thread."""
    api, _ = open_api(tmp_path)
    calls, sent = [], []
    invoked = []

    class Form:
        Handle = 4242
        InvokeRequired = True

        def Invoke(self, action):
            invoked.append(True)
            action()

    import sys as _sys
    import types

    fake_system = types.ModuleType("System")
    fake_system.Action = lambda fn: fn
    monkeypatch.setitem(_sys.modules, "System", fake_system)
    api._window = _FakeWindow(calls, Form())
    wa = _patch_user32(monkeypatch, calls, sent)
    assert api.begin_window_drag()["ok"] is True
    assert invoked == [True]
    assert sent == [(4242, wa.WM_NCLBUTTONDOWN, wa.HTCAPTION, 0)]


@pytest.mark.skipif(not sys.platform == "win32", reason="IsZoomed is Windows-only")
def test_toggle_maximize_asks_windows_not_a_stale_flag(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    calls, sent, actions = [], [], []

    class Win(_FakeWindow):
        def maximize(self):
            actions.append("maximize")

        def restore(self):
            actions.append("restore")

    api._window = Win(calls)
    api._maximized = True  # stale: a caption drag restored the window behind our back
    _patch_user32(monkeypatch, calls, sent, zoomed=0)
    assert api.toggle_maximize()["ok"] is True
    assert actions == ["maximize"]


def test_begin_window_drag_without_a_window_is_a_clean_noop(tmp_path):
    api, _ = open_api(tmp_path)
    api._window = None
    assert api.begin_window_drag()["ok"] is True
