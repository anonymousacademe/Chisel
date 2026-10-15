"""Window controls and opening links in the system browser."""

from __future__ import annotations

import ctypes
import sys
import webbrowser
from urllib.parse import urlsplit

from ._bridge import bridge

WM_NCLBUTTONDOWN = 0xA1
HTCAPTION = 0x2


def _hwnd(form) -> int:
    """The form's window handle as an int: pythonnet 3 does not convert a System.IntPtr with int()."""
    handle = form.Handle
    return handle.ToInt64() if hasattr(handle, "ToInt64") else int(handle)


class WindowMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    EXTERNAL_SCHEMES = ("http", "https", "mailto")

    @bridge
    def begin_window_drag(self) -> dict:
        """Drag the frameless window with the native move loop (Windows): hand the
        title-bar mouse down to ``DefWindowProc`` as a caption drag, so the OS moves
        the window itself. pywebview's default (SetWindowPos on every mousemove, with
        the DPI scale applied to physical screen coordinates a second time) makes the
        window overshoot and flicker on scaled displays. Blocks until the drag ends;
        the OS answers the mouse-up.

        Both calls must run on the form's UI thread, not on this bridge worker thread:
        on mousedown the WebView2 child window captures the mouse, and that capture
        lives in the input queue the UI thread shares with it. ReleaseCapture only
        affects the calling thread's queue, so from a worker it returns success and does
        nothing, and DefWindowProc then declines to start the move loop."""
        form = getattr(self._window, "native", None) if self._window is not None else None
        if form is None:
            return {}
        hwnd = _hwnd(form)

        def drag() -> None:
            user32 = ctypes.windll.user32
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)

        if getattr(form, "InvokeRequired", False):
            from System import Action  # pythonnet: loaded by pywebview's WinForms backend
            form.Invoke(Action(drag))
        else:
            drag()
        return {}

    @bridge
    def open_external(self, url: str) -> dict:
        """Open a link from the UI in the system browser / mail app. Only http://, https:// and
        mailto: URLs are accepted; the URL goes to ``webbrowser.open`` as one argument (never a
        shell command line)."""
        url = (url or "").strip()
        if not url or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError("not a valid link")
        parts = urlsplit(url)
        if parts.scheme.lower() not in self.EXTERNAL_SCHEMES:
            raise ValueError("Only http://, https:// and mailto: links can be opened")
        if parts.scheme.lower() != "mailto" and not parts.netloc:
            raise ValueError("not a valid link")
        if parts.scheme.lower() == "mailto" and not parts.path:
            raise ValueError("not a valid link")
        return {"opened": bool(webbrowser.open(url))}

    @bridge
    def minimize(self) -> dict:
        if self._window is not None:
            self._window.minimize()
        return {}

    @bridge
    def toggle_maximize(self) -> dict:
        w = self._window
        if w is not None:
            # pywebview has no "is maximized": ask Windows (a caption drag or Win+arrow
            # restores the window behind our back); elsewhere track it ourselves
            form = getattr(w, "native", None)
            if form is not None and sys.platform == "win32":
                maximized = bool(ctypes.windll.user32.IsZoomed(_hwnd(form)))
            else:
                maximized = getattr(self, "_maximized", False)
            if maximized:
                w.restore()
            else:
                w.maximize()
            self._maximized = not maximized
        return {}

    @bridge
    def close(self) -> dict:
        if self.stats is not None:  # flush the writing stats (a running sprint is recorded as stopped)
            self.stats.close()
        if self._window is not None:
            self._window.destroy()
        return {}
