"""One-time, non-destructive migration from the LoreWriter-era names (``lorewrite``).

Pure Python, no Textual. Nothing here deletes or moves user data, with one exception:
a project's ``.lorewrite/`` folder (a disposable cache plus small waiver and undo files)
is renamed to ``.chisel/``. Every function tolerates failure: start-up must never
be blocked by a migration problem.

- ``migrate_user_dirs``: copy the old per-user state and data folders to the new names.
- ``migrate_api_key``: the keyring entry (service ``lorewrite`` -> ``chisel``).
- ``migrate_project``: ``.lorewrite/`` -> ``.chisel/`` in a project, plus ``.gitignore``.
- ``run_startup``: what both apps call once, early.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

from . import fsutil
from .envvars import get_env

log = logging.getLogger(__name__)

OLD_APP = "lorewrite"
NEW_APP = "chisel"
OLD_CACHE_DIR = ".lorewrite"
NEW_CACHE_DIR = ".chisel"
MARKER = "migrated-from-lorewrite.json"


@dataclass
class MigrationReport:
    state: str = "skipped"   # copied | exists | missing | override | failed | skipped
    data: str = "skipped"
    errors: list[str] = field(default_factory=list)


# -- per-user folders -------------------------------------------------------

def copy_tree_once(old: Path, new: Path) -> str:
    """Copy *old* to *new* when *old* exists and *new* does not. The old tree is left
    in place. The copy lands in a sibling folder first and is renamed into place, so a
    half-finished copy never looks like a finished one. Returns "copied", "exists"
    (new is already there: untouched), "missing" (nothing to copy) or "failed"."""
    try:
        if new.exists():
            return "exists"
        if not old.is_dir():
            return "missing"
        new.parent.mkdir(parents=True, exist_ok=True)
        tmp = new.with_name(new.name + ".migrating")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)  # our own leftover from an earlier crash
        try:
            shutil.copytree(old, tmp)
            (tmp / MARKER).write_text(json.dumps({"copied_from": str(old), "at": time.time()}, indent=2),
                                      encoding="utf-8", newline="\n")
            fsutil.rename(tmp, new)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return "copied"
    except OSError as exc:
        log.warning("could not copy %s to %s: %s", old, new, exc)
        return "failed"


def migrate_user_dirs(state_dir: Path | None = None, data_dir: Path | None = None,
                      old_state_dir: Path | None = None, old_data_dir: Path | None = None) -> MigrationReport:
    """Copy the old state and data folders to the new names (the arguments are for tests).
    An environment override (CHISEL_/LOREWRITE_ STATE_DIR / DATA_DIR) means the platform
    folders are not used at all, so they are not touched."""
    report = MigrationReport()
    if get_env("STATE_DIR") and state_dir is None:
        report.state = "override"
    else:
        report.state = copy_tree_once(
            old_state_dir or Path(platformdirs.user_state_dir(OLD_APP, appauthor=False)),
            state_dir or Path(platformdirs.user_state_dir(NEW_APP, appauthor=False)))
    if get_env("DATA_DIR") and data_dir is None:
        report.data = "override"
    else:
        report.data = copy_tree_once(
            old_data_dir or Path(platformdirs.user_data_dir(OLD_APP, appauthor=False)),
            data_dir or Path(platformdirs.user_data_dir(NEW_APP, appauthor=False)))
    for what, status in (("state", report.state), ("data", report.data)):
        if status == "failed":
            report.errors.append(what)
    return report


# -- keyring ----------------------------------------------------------------

def migrate_api_key(keyring_module, new_service: str, old_service: str, username: str) -> str | None:
    """The stored key: the new service first; else the old one, copied to the new service
    (the old entry stays). None when neither has one."""
    key = keyring_module.get_password(new_service, username)
    if key:
        return key
    old = keyring_module.get_password(old_service, username)
    if not old:
        return None
    try:
        keyring_module.set_password(new_service, username, old)
    except Exception as exc:  # still usable this run
        log.warning("could not copy the API key to the new keyring entry: %s", exc)
    return old


# -- projects ---------------------------------------------------------------

def _lists_line(text: str, name: str) -> bool:
    bare = name.strip("/")
    return any(ln.strip().strip("/") == bare for ln in text.splitlines()
               if ln.strip() and not ln.lstrip().startswith("#"))


def migrate_gitignore(root: Path) -> bool:
    """Append ``.chisel/`` to the project's .gitignore when it lists ``.lorewrite/`` and
    not yet ``.chisel/``. True when the file changed."""
    path = root / ".gitignore"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not _lists_line(text, OLD_CACHE_DIR) or _lists_line(text, NEW_CACHE_DIR):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    try:
        path.write_text(text + NEW_CACHE_DIR + "/\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        log.warning("could not update %s: %s", path, exc)
        return False
    return True


def migrate_project(root: Path) -> str:
    """Rename ``.lorewrite/`` to ``.chisel/`` in a project folder (called when it opens).
    Returns "renamed", "none" (nothing to do), "present" (``.chisel/`` already exists;
    the old folder is left alone) or "fallback" (the rename failed: a fresh ``.chisel/``
    was created and the old folder stays). Never raises, never deletes."""
    old, new = root / OLD_CACHE_DIR, root / NEW_CACHE_DIR
    result = "none"
    try:
        if old.is_dir():
            if new.exists():
                result = "present"
            else:
                try:
                    fsutil.rename(old, new)
                    result = "renamed"
                except OSError as exc:
                    log.warning("could not rename %s to %s: %s", old, new, exc)
                    new.mkdir(exist_ok=True)
                    result = "fallback"
        migrate_gitignore(root)
    except OSError as exc:
        log.warning("project migration failed for %s: %s", root, exc)
    return result


# -- start-up ---------------------------------------------------------------

def run_startup() -> MigrationReport | None:
    """Called once, early, by both apps. Never raises."""
    try:
        report = migrate_user_dirs()
        if report.state == "copied" or report.data == "copied":
            log.info("copied your Chisel settings from the old lorewrite folders (state: %s, data: %s)",
                     report.state, report.data)
        return report
    except Exception:
        log.exception("migration from the old lorewrite folders failed")
        return None
