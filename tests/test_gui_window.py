"""The window-controls bridge (WindowMixin): the native drag hand-off."""

import sys

import pytest

from tests.test_gui_api import open_api


class _FakeIntPtr:
    """Like System.IntPtr under pythonnet: int() refuses it (that broke every drag), ToInt64() works."""

    def __init__(self, value):
        self.value = value

    def ToInt64(self):
        return self.value

    def __int__(self):
        raise TypeError("int() argument must be a string, a bytes-like object or a real number, not 'IntPtr'")


class _FakeForm:
    def __init__(self, calls):
        self.calls = calls

    @property
    def Handle(self):
        self.calls.append("handle")
        return _FakeIntPtr(4242)


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

    def cursor(ref):
        ref._obj.x, ref._obj.y = 300, 12
        return 1

    user32.GetCursorPos = cursor
    user32.PostMessageW = lambda hwnd, msg, w, l: sent.append((hwnd.value, msg, w, l.value))

    import chisel.gui.window_api as wa

    monkeypatch.setattr(wa.ctypes, "windll", type("W", (), {"user32": user32}))
    r = api.begin_window_drag()
    assert r["ok"] is True
    assert calls == ["handle", "release"]
    # posted (not sent) with the cursor's screen position, like a real title-bar press
    assert sent == [(4242, wa.WM_NCLBUTTONDOWN, wa.HTCAPTION, (12 << 16) | 300)]


def test_begin_window_drag_without_a_window_is_a_clean_noop(tmp_path):
    api, _ = open_api(tmp_path)
    api._window = None
    assert api.begin_window_drag()["ok"] is True


@pytest.mark.skipif(not sys.platform == "win32", reason="IsZoomed is Windows-only")
def test_toggle_maximize_asks_windows_not_a_stale_flag(tmp_path, monkeypatch):
    api, _ = open_api(tmp_path)
    actions = []

    class Win(_FakeWindow):
        def maximize(self):
            actions.append("maximize")

        def restore(self):
            actions.append("restore")

    api._window = Win([])
    api._maximized = True  # stale: a caption drag restored the window behind our back
    user32 = type("U", (), {})()
    user32.IsZoomed = lambda hwnd: 0

    import chisel.gui.window_api as wa

    monkeypatch.setattr(wa.ctypes, "windll", type("W", (), {"user32": user32}), raising=False)
    assert api.toggle_maximize()["ok"] is True
    assert actions == ["maximize"]
