"""lorewrite-gui: open the React UI in a native pywebview window."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .api import Api
from .webroot import require_dist

BACKGROUND = "#121318"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lorewrite-gui")
    parser.add_argument("--project", type=Path, default=None,
                        help="open this project directly")
    parser.add_argument("--new", metavar="TITLE", default=None,
                        help="create a new project called TITLE and open it "
                             "(in ~/novels/<title>, or in --project PATH)")
    parser.add_argument("--report", metavar="FILE", default=None,
                        help="with --self-test: also write the JSON report to FILE")
    parser.add_argument("--self-test", action="store_true",
                        help="check the bundled data and print a JSON report "
                             "(no window, no network); exit 1 on a failure")
    parser.add_argument("--dev", metavar="URL", default=None,
                        help="load the UI from a dev server (npm run dev) "
                             "instead of the built UI")
    args = parser.parse_args(argv)
    if args.self_test:
        from ..selftest import main as self_test
        sys.exit(self_test(args.report))

    index = None if args.dev else require_dist("lorewrite-gui") / "index.html"
    try:
        import webview
    except ImportError:
        sys.exit("lorewrite-gui: pywebview is not installed."
                 '\nInstall it with: pip install -e ".[gui]"')

    api = Api()
    if args.new is not None:
        result = api.new_project(args.new, str(args.project or ""))
        if not result.get("ok"):
            sys.exit(f"lorewrite-gui: {result.get('error')}")
    elif args.project is not None and hasattr(api, "open_project"):
        api.open_project(str(args.project))
    window = webview.create_window(
        "Chisel",
        url=args.dev or str(index),
        js_api=api.facade(),
        width=1600, height=1000, min_size=(1280, 760),
        frameless=True, easy_drag=False, text_select=True,
        background_color=BACKGROUND,
    )
    api._window = window
    if hasattr(api, "on_window_closing"):
        window.events.closing += api.on_window_closing
    icon = Path(__file__).with_name("icon.ico" if sys.platform == "win32" else "icon.png")  # WinForms wants an .ico
    webview.start(http_server=args.dev is None, icon=str(icon) if icon.exists() else None)


if __name__ == "__main__":
    main()
