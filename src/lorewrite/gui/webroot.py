"""Where the built React UI lives.

``npm run build`` in ``gui/`` writes into ``src/lorewrite/gui/web/`` (git-ignored,
shipped as package data), so an installed package finds it next to this file.
A source checkout that was built the old way still works through ``gui/dist``.
"""

from __future__ import annotations

from pathlib import Path

PACKAGED = Path(__file__).resolve().parent / "web"
REPO_DIST = Path(__file__).resolve().parents[3] / "gui" / "dist"

MISSING = ("the UI is not built (no web/index.html in the package and no gui/dist/index.html)."
           "\nBuild it with `npm install && npm run build` in gui/ (Node 20+).")


def find_dist() -> Path | None:
    """The folder holding ``index.html``: the packaged build first, then the repo's."""
    for folder in (PACKAGED, REPO_DIST):
        if (folder / "index.html").is_file():
            return folder
    return None


def require_dist(program: str) -> Path:
    """Like :func:`find_dist` but exits with a clear message when there is no build."""
    dist = find_dist()
    if dist is None:
        raise SystemExit(f"{program}: {MISSING}")
    return dist
