"""The scope statement of a research project: ``scope.md`` at the project root.

Plain text the author writes to say what the paper or proposal is about. It is author data, never a scene, a
note or an indexed document, and it is sent nowhere except to an outline call (``ai/outline.py``).
"""

from __future__ import annotations

from .. import fsutil

SCOPE_FILE = "scope.md"
MAX_CHARS = 20_000


def scope_path(project):
    return project.root / SCOPE_FILE


def get_scope(project) -> str:
    """The scope text, "" when there is none (or the file cannot be read)."""
    path = scope_path(project)
    if path.is_symlink() or not path.is_file():
        return ""
    try:
        return fsutil.read_text_lenient(path)
    except OSError:
        return ""


def set_scope(project, text: str) -> None:
    """Save *text* atomically. Blank text removes the file. ``ValueError`` (plain words) when it is not text
    or longer than ``MAX_CHARS``: nothing is cut silently."""
    from ..project import write_atomic

    if not isinstance(text, str):
        raise ValueError("The scope statement must be text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > MAX_CHARS:
        raise ValueError(f"The scope statement is too long ({len(text):,} characters; the limit is "
                         f"{MAX_CHARS:,}). Shorten it and try again.")
    path = scope_path(project)
    if not text.strip():
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise ValueError("The scope statement could not be cleared.") from None
        return
    if path.is_symlink():
        raise ValueError("scope.md is a link; Chisel will not write through it.")
    write_atomic(path, text if text.endswith("\n") else text + "\n")
