"""Window controls and opening links in the system browser."""

from __future__ import annotations

import webbrowser
from urllib.parse import urlsplit

from ._bridge import bridge


class WindowMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api.

    EXTERNAL_SCHEMES = ("http", "https", "mailto")

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
            # pywebview has no "is maximized"; track it ourselves
            if getattr(self, "_maximized", False):
                w.restore()
            else:
                w.maximize()
            self._maximized = not getattr(self, "_maximized", False)
        return {}

    @bridge
    def close(self) -> dict:
        if self.stats is not None:  # flush the writing stats (a running sprint is recorded as stopped)
            self.stats.close()
        if self._window is not None:
            self._window.destroy()
        return {}
