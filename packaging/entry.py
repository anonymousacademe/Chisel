"""Entry point of the frozen apps. One bundle holds two executables built from
this script: ``Chisel`` (the desktop app, windowed) and ``chisel-tui`` (the
terminal app, console). The executable's own name picks which one starts."""

import os
import sys
from pathlib import Path


def main() -> None:
    name = Path(sys.executable).stem.lower()
    if name == "chisel-tui":
        from chisel.tui.app import main as run
    else:
        if sys.platform.startswith("linux"):
            # WebKitGTK cannot be bundled; the bundle ships the Qt (QtWebEngine) backend
            os.environ.setdefault("PYWEBVIEW_GUI", "qt")
        from chisel.gui.app import main as run
    run()


if __name__ == "__main__":
    main()
