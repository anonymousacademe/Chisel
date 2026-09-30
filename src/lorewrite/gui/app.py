"""lorewrite-gui: open the React UI in a native pywebview window."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .api import Api

DIST = Path(__file__).resolve().parents[3] / "gui" / "dist"
BACKGROUND = "#121318"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lorewrite-gui")
    parser.add_argument("--project", type=Path, default=None,
                        help="open this project directly")
    parser.add_argument("--dev", metavar="URL", default=None,
                        help="load the UI from a dev server (npm run dev) "
                             "instead of gui/dist")
    args = parser.parse_args(argv)

    index = DIST / "index.html"
    if args.dev is None and not index.is_file():
        sys.exit("lorewrite-gui: the UI is not built (missing gui/dist/index.html)."
                 "\nRun `npm install && npm run build` in gui/ first.")
    try:
        import webview
    except ImportError:
        sys.exit("lorewrite-gui: pywebview is not installed."
                 '\nInstall it with: pip install -e ".[gui]"')

    api = Api()
    if args.project is not None and hasattr(api, "open_project"):
        api.open_project(str(args.project))
    window = webview.create_window(
        "LoreWriter",
        url=args.dev or str(index),
        js_api=api.facade(),
        width=1600, height=1000, min_size=(1280, 760),
        frameless=True, easy_drag=False, text_select=True,
        background_color=BACKGROUND,
    )
    api._window = window
    if hasattr(api, "on_window_closing"):
        window.events.closing += api.on_window_closing
    webview.start(http_server=args.dev is None)


if __name__ == "__main__":
    main()
