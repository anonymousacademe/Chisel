"""Optional git sync for a project folder (explicit actions only).

The status bar can show whether the project is committed and pushed; the author
can commit it, push it, or turn the folder into a git repository. Nothing here
ever runs on its own except the read-only status query: commits and pushes only
happen when a front end calls ``commit`` / ``push`` after the author asked, and
a push never forces. ``git`` is optional: without it every function reports
"not available" (``status`` returns None).

Everything runs ``git`` with the project folder as the working directory and the
path ``.`` as the pathspec, so a project inside a larger repository only ever
commits its own files. No network is touched except by ``push``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

STATUS_TIMEOUT = 5
COMMIT_TIMEOUT = 60
PUSH_TIMEOUT = 120
GITIGNORE_LINE = ".chisel/"
LEGACY_GITIGNORE_LINE = ".lorewrite/"  # projects from the LoreWriter era: also counts as "cache ignored"
CACHE_IGNORE_LINES = (GITIGNORE_LINE, LEGACY_GITIGNORE_LINE)


class GitError(RuntimeError):
    """A git command failed; the message is git's own, for the author."""


@dataclass(frozen=True)
class SyncStatus:
    state: str            # "synced" | "changes" | "ahead"
    changes: int          # uncommitted entries inside the project (incl. untracked)
    scenes: int           # how many of those are scene files
    ahead: int            # commits not pushed
    behind: int           # commits upstream has that we do not (never pulled for you)
    branch: str           # "" when HEAD is detached
    remote: str | None    # the remote a push would go to
    remotes: tuple[str, ...] = field(default_factory=tuple)
    toplevel: str = ""    # the repository the project lives in
    label: str = ""       # "Synced" | "3 changes" | "Ahead 2"

    @property
    def can_push(self) -> bool:
        return bool(self.remote) and bool(self.branch)


def git_available() -> bool:
    return shutil.which("git") is not None


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C", "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0"})
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")  # never wait on a prompt
    return env


def _run(root: Path, *args: str, timeout: float, check: bool = True,
         input_text: str | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(["git", *args], cwd=root, env=_env(), timeout=timeout,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", input=input_text)
    except FileNotFoundError as exc:
        raise GitError("git is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} took longer than {int(timeout)} s and was stopped") from exc
    if check and proc.returncode != 0:
        raise GitError((proc.stderr or proc.stdout).strip() or f"git {args[0]} failed")
    return proc


def in_repository(root: Path) -> bool:
    if not git_available():
        return False
    try:
        proc = _run(root, "rev-parse", "--is-inside-work-tree", timeout=STATUS_TIMEOUT, check=False)
    except GitError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def can_init(root: Path) -> bool:
    """git is installed and the folder is not (inside) a repository yet."""
    return git_available() and not in_repository(root)


def _is_scene(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (rel.startswith("manuscript/") and name.endswith(".md")
            and not name.startswith((".", "_")))


def _remotes(root: Path) -> tuple[str, ...]:
    out = _run(root, "remote", timeout=STATUS_TIMEOUT, check=False).stdout
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def _push_remote(root: Path, branch: str, remotes: tuple[str, ...]) -> str | None:
    if not remotes:
        return None
    if branch:
        cfg = _run(root, "config", f"branch.{branch}.remote", timeout=STATUS_TIMEOUT, check=False)
        name = cfg.stdout.strip()
        if cfg.returncode == 0 and name in remotes:
            return name
    if len(remotes) == 1:
        return remotes[0]
    return "origin" if "origin" in remotes else remotes[0]


def status(root: Path) -> SyncStatus | None:
    """The project's git state, or None when git is missing or the folder is
    not in a repository. One ``git status`` call (plus a few cheap ones)."""
    if not git_available():
        return None
    try:
        proc = _run(root, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all", "--", ".",
                    timeout=STATUS_TIMEOUT, check=False)
    except GitError:
        return None
    if proc.returncode != 0:
        return None  # not a repository
    prefix = _run(root, "rev-parse", "--show-prefix", timeout=STATUS_TIMEOUT,
                  check=False).stdout.strip()
    toplevel = _run(root, "rev-parse", "--show-toplevel", timeout=STATUS_TIMEOUT,
                    check=False).stdout.strip()
    if toplevel:
        toplevel = str(Path(toplevel))  # git prints C:/x on Windows; the OS spelling is C:\x
    branch, ahead, behind, has_upstream, has_head = "", 0, 0, False, True
    changes = scenes = 0
    parts = proc.stdout.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        if entry.startswith("# branch.head "):
            head = entry.removeprefix("# branch.head ")
            branch = "" if head == "(detached)" else head
        elif entry.startswith("# branch.oid "):
            has_head = entry.removeprefix("# branch.oid ") != "(initial)"
        elif entry.startswith("# branch.upstream "):
            has_upstream = True
        elif entry.startswith("# branch.ab "):
            plus, minus = entry.removeprefix("# branch.ab ").split()
            ahead, behind = int(plus), -int(minus)
        elif entry.startswith("#") or entry.startswith("! "):
            continue
        else:
            kind = entry[0]
            if kind == "?":
                path = entry[2:]
            elif kind in "12u":
                path = entry.split(" ", 9 if kind == "2" else 8 if kind == "1" else 10)[-1]
                if kind == "2":
                    i += 1  # the original path follows as its own entry
            else:
                continue
            changes += 1
            rel = path[len(prefix):] if prefix and path.startswith(prefix) else path
            if _is_scene(rel):
                scenes += 1
    remotes = _remotes(root)
    if not has_upstream and remotes and has_head:
        # never pushed: everything not yet on any remote counts as ahead
        count = _run(root, "rev-list", "--count", "HEAD", "--not", "--remotes",
                     timeout=STATUS_TIMEOUT, check=False)
        ahead = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
    state = "changes" if changes else "ahead" if ahead else "synced"
    label = {"changes": f"{changes} change{'s' if changes != 1 else ''}",
             "ahead": f"Ahead {ahead}", "synced": "Synced"}[state]
    return SyncStatus(state, changes, scenes, ahead, behind, branch,
                      _push_remote(root, branch, remotes), remotes, toplevel, label)


def default_message(st: SyncStatus, today: date | None = None) -> str:
    """``chisel: 2026-10-01 — 3 scenes changed`` (files when no scene changed)."""
    day = (today or date.today()).isoformat()
    if st.scenes:
        n, what = st.scenes, "scene"
    else:
        n, what = st.changes, "file"
    return f"chisel: {day} — {n} {what}{'s' if n != 1 else ''} changed"


def init(root: Path) -> None:
    """``git init`` the project folder and make sure ``.gitignore`` hides the
    index cache (``.chisel/``). Refuses if the folder is already in a repository."""
    if not git_available():
        raise GitError("git is not installed")
    if in_repository(root):
        raise GitError("this folder is already in a git repository")
    _run(root, "init", timeout=COMMIT_TIMEOUT)
    ignore = root / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    if not cache_ignored(lines):
        lines.append(GITIGNORE_LINE)
        ignore.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def cache_ignored(lines) -> bool:
    """True when .gitignore *lines* already hide the cache folder (either name)."""
    return any(ln.strip() in CACHE_IGNORE_LINES for ln in lines)


def commit(root: Path, message: str) -> str:
    """Stage everything inside the project folder and commit just that folder.
    Returns git's one-line summary. ValueError when there is nothing to commit."""
    message = (message or "").strip()
    if not message:
        raise ValueError("a commit needs a message")
    st = status(root)
    if st is None:
        raise GitError("the project folder is not in a git repository")
    if st.changes == 0:
        raise ValueError("nothing to commit: every change is already committed")
    _run(root, "add", "-A", "--", ".", timeout=COMMIT_TIMEOUT)
    # The message goes in on stdin as UTF-8 (not argv: Windows code pages mangle the
    # em dash of the default message) and is stored as UTF-8.
    proc = _run(root, "-c", "i18n.commitEncoding=utf-8", "commit", "-F", "-", "--", ".",
                timeout=COMMIT_TIMEOUT, check=False, input_text=message + "\n")
    if proc.returncode != 0:
        text = (proc.stdout + proc.stderr).strip()
        if "nothing to commit" in text or "no changes added" in text:
            raise ValueError("nothing to commit: every change is already committed")
        raise GitError(text or "git commit failed")
    return (proc.stdout.strip().splitlines() or ["Committed"])[0]


def push(root: Path) -> str:
    """Push the current branch to its remote. Never forces. Sets the upstream
    the first time. Returns a short description of where it went."""
    st = status(root)
    if st is None:
        raise GitError("the project folder is not in a git repository")
    if not st.remote:
        raise GitError("no remote is configured for this repository")
    if not st.branch:
        raise GitError("HEAD is detached: switch to a branch before pushing")
    cfg = _run(root, "config", f"branch.{st.branch}.remote", timeout=STATUS_TIMEOUT, check=False)
    args = ["push"] if cfg.returncode == 0 and cfg.stdout.strip() else \
        ["push", "-u", st.remote, st.branch]
    _run(root, *args, timeout=PUSH_TIMEOUT)
    return f"Pushed {st.branch} to {st.remote}"


def remote_url(root: Path, name: str) -> str:
    out = _run(root, "remote", "get-url", name, timeout=STATUS_TIMEOUT, check=False)
    return out.stdout.strip() if out.returncode == 0 else ""
