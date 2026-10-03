"""Migration from the LoreWriter-era names (lorewrite -> chisel): non-destructive,
one-time, and never fatal. The old names appear here on purpose."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from chisel.ai import client
from chisel.core import continuity, envvars, migrate, recents, rename, soundpacks, sync
from chisel.core import entities as ent
from chisel.core.project import Project

ROOT = Path(__file__).resolve().parents[1]


# -- per-user folders ---------------------------------------------------------

def make_old(base: Path) -> Path:
    old = base / "old"
    (old / "stats").mkdir(parents=True)
    (old / "recent.json").write_text('[{"path": "x"}]', encoding="utf-8")
    (old / "stats" / "p.json").write_text("{}", encoding="utf-8")
    return old


def test_state_dir_copied_when_new_absent(tmp_path):
    old, new = make_old(tmp_path), tmp_path / "new"
    assert migrate.copy_tree_once(old, new) == "copied"
    assert (new / "recent.json").read_text(encoding="utf-8") == '[{"path": "x"}]'
    assert (new / "stats" / "p.json").is_file()
    assert (new / migrate.MARKER).is_file()
    assert (old / "recent.json").is_file() and (old / "stats" / "p.json").is_file()  # old kept
    assert not (tmp_path / "new.migrating").exists()


def test_existing_new_dir_is_untouched(tmp_path):
    old, new = make_old(tmp_path), tmp_path / "new"
    new.mkdir()
    (new / "mine.txt").write_text("keep", encoding="utf-8")
    assert migrate.copy_tree_once(old, new) == "exists"
    assert sorted(p.name for p in new.iterdir()) == ["mine.txt"]


def test_nothing_to_copy(tmp_path):
    assert migrate.copy_tree_once(tmp_path / "none", tmp_path / "new") == "missing"
    assert not (tmp_path / "new").exists()


def test_copy_is_idempotent(tmp_path):
    old, new = make_old(tmp_path), tmp_path / "new"
    assert migrate.copy_tree_once(old, new) == "copied"
    (new / "recent.json").write_text("[]", encoding="utf-8")        # the user moves on
    assert migrate.copy_tree_once(old, new) == "exists"
    assert (new / "recent.json").read_text(encoding="utf-8") == "[]"


def test_copy_failure_leaves_no_half_folder(tmp_path, monkeypatch):
    old, new = make_old(tmp_path), tmp_path / "new"

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(migrate.shutil, "copytree", boom)
    assert migrate.copy_tree_once(old, new) == "failed"
    assert not new.exists()


def test_user_dirs_state_and_data(tmp_path, monkeypatch):
    monkeypatch.delenv("CHISEL_STATE_DIR", raising=False)
    monkeypatch.delenv("CHISEL_DATA_DIR", raising=False)
    old_state, old_data = make_old(tmp_path), tmp_path / "old-data"
    (old_data / "sounds" / "pack").mkdir(parents=True)
    (old_data / "sounds" / "pack" / "key-1.wav").write_bytes(b"RIFF")
    new_state, new_data = tmp_path / "s", tmp_path / "d"
    report = migrate.migrate_user_dirs(new_state, new_data, old_state, old_data)
    assert (report.state, report.data) == ("copied", "copied")
    assert (new_data / "sounds" / "pack" / "key-1.wav").read_bytes() == b"RIFF"
    assert (old_data / "sounds" / "pack" / "key-1.wav").is_file()
    again = migrate.migrate_user_dirs(new_state, new_data, old_state, old_data)
    assert (again.state, again.data) == ("exists", "exists")


@pytest.mark.parametrize("name", ["CHISEL_STATE_DIR", "LOREWRITE_STATE_DIR"])
def test_state_env_override_leaves_platform_dirs_alone(tmp_path, monkeypatch, name):
    monkeypatch.setenv(name, str(tmp_path / "forced"))
    monkeypatch.setenv("CHISEL_DATA_DIR", str(tmp_path / "forced-data"))
    calls = []
    monkeypatch.setattr(migrate, "copy_tree_once", lambda o, n: calls.append((o, n)) or "copied")
    report = migrate.migrate_user_dirs()
    assert (report.state, report.data) == ("override", "override")
    assert calls == []


def test_run_startup_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("anything")

    monkeypatch.setattr(migrate, "migrate_user_dirs", boom)
    assert migrate.run_startup() is None


def test_run_startup_with_overrides_is_a_noop(tmp_path):
    report = migrate.run_startup()   # conftest sets CHISEL_STATE_DIR / CHISEL_DATA_DIR
    assert report.state == "override" and report.data == "override"


# -- environment aliases ------------------------------------------------------

def test_env_new_name_wins(monkeypatch):
    monkeypatch.setenv("CHISEL_STATE_DIR", "new")
    monkeypatch.setenv("LOREWRITE_STATE_DIR", "old")
    assert envvars.get_env("STATE_DIR") == "new"


def test_env_old_name_is_a_deprecated_alias(monkeypatch):
    monkeypatch.delenv("CHISEL_STATE_DIR")
    monkeypatch.setenv("LOREWRITE_STATE_DIR", "old")
    assert envvars.get_env("STATE_DIR") == "old"
    monkeypatch.setenv("CHISEL_STATE_DIR", "")          # empty counts as unset
    assert envvars.get_env("STATE_DIR") == "old"
    monkeypatch.delenv("LOREWRITE_STATE_DIR")
    monkeypatch.delenv("CHISEL_STATE_DIR")
    assert envvars.get_env("STATE_DIR") is None
    assert envvars.get_env("STATE_DIR", "dflt") == "dflt"


def test_state_and_data_dirs_honour_both_names(tmp_path, monkeypatch):
    monkeypatch.delenv("CHISEL_STATE_DIR")
    monkeypatch.delenv("CHISEL_DATA_DIR")
    monkeypatch.setenv("LOREWRITE_STATE_DIR", str(tmp_path / "old-s"))
    monkeypatch.setenv("LOREWRITE_DATA_DIR", str(tmp_path / "old-d"))
    assert recents.default_state_dir() == tmp_path / "old-s"
    assert soundpacks.data_dir() == tmp_path / "old-d"
    monkeypatch.setenv("CHISEL_STATE_DIR", str(tmp_path / "new-s"))
    monkeypatch.setenv("CHISEL_DATA_DIR", str(tmp_path / "new-d"))
    assert recents.default_state_dir() == tmp_path / "new-s"
    assert soundpacks.data_dir() == tmp_path / "new-d"


def test_platform_dirs_use_the_new_app_name(monkeypatch):
    monkeypatch.delenv("CHISEL_STATE_DIR")
    monkeypatch.delenv("CHISEL_DATA_DIR")
    assert recents.default_state_dir().name == "chisel"
    assert soundpacks.data_dir().name == "chisel"


# -- keyring (an in-memory fake; the real keyring is never touched) -----------

def test_key_from_old_service_is_copied_to_the_new_one(fake_keyring, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake_keyring.set_password("lorewrite", "openrouter", "sk-old")
    assert client.get_api_key() == "sk-old"
    assert fake_keyring.get_password("chisel", "openrouter") == "sk-old"
    assert fake_keyring.get_password("lorewrite", "openrouter") == "sk-old"   # old entry stays


def test_no_key_anywhere(fake_keyring, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert client.get_api_key() is None
    assert fake_keyring.store == {}


def test_new_key_wins_over_old(fake_keyring, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake_keyring.set_password("chisel", "openrouter", "sk-new")
    fake_keyring.set_password("lorewrite", "openrouter", "sk-old")
    assert client.get_api_key() == "sk-new"
    assert fake_keyring.get_password("lorewrite", "openrouter") == "sk-old"


def test_env_key_still_first(fake_keyring, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")
    fake_keyring.set_password("lorewrite", "openrouter", "sk-old")
    assert client.get_api_key() == "sk-env"
    assert fake_keyring.get_password("chisel", "openrouter") is None


def test_set_and_clear_use_the_new_service(fake_keyring):
    client.set_api_key("sk-x")
    assert fake_keyring.store == {("chisel", "openrouter"): "sk-x"}
    client.clear_api_key()
    assert fake_keyring.store == {}


def test_failed_copy_still_returns_the_old_key(fake_keyring, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake_keyring.set_password("lorewrite", "openrouter", "sk-old")

    def boom(*a):
        raise RuntimeError("locked")

    monkeypatch.setattr(fake_keyring, "set_password", boom)
    assert migrate.migrate_api_key(fake_keyring, "chisel", "lorewrite", "openrouter") == "sk-old"


# -- projects ------------------------------------------------------------------

def old_project(tmp_path: Path, name: str = "book") -> Project:
    """A project as the LoreWriter-era app left it: cache in .lorewrite/."""
    p = Project.create(tmp_path / name, "Book")
    (p.root / ".gitignore").write_text(".lorewrite/\n", encoding="utf-8")
    old = p.root / ".lorewrite"
    (old / "rename-undo").mkdir(parents=True)
    (old / "index.sqlite").write_text("cache", encoding="utf-8")
    (old / "waivers.json").write_text(json.dumps({"waived": ["k1"], "scenes": {"k1": "manuscript/01-opening.md"}}),
                                      encoding="utf-8")
    (old / "rename-undo" / "abc.json").write_text('{"id": "abc"}', encoding="utf-8")
    return p


def test_open_renames_the_cache_folder_and_keeps_its_files(tmp_path):
    p = old_project(tmp_path)
    Project.open(p.root)
    assert not (p.root / ".lorewrite").exists()
    new = p.root / ".chisel"
    assert (new / "index.sqlite").read_text(encoding="utf-8") == "cache"
    assert (new / "rename-undo" / "abc.json").read_text(encoding="utf-8") == '{"id": "abc"}'
    assert continuity.load_waivers(p.root) == {"k1"}              # waivers.json survived


def test_gitignore_gets_the_new_line_once(tmp_path):
    p = old_project(tmp_path)
    Project.open(p.root)
    Project.open(p.root)
    lines = (p.root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines == [".lorewrite/", ".chisel/"]


def test_gitignore_without_trailing_newline(tmp_path):
    p = old_project(tmp_path)
    (p.root / ".gitignore").write_text("*.tmp\n.lorewrite/", encoding="utf-8")
    assert migrate.migrate_gitignore(p.root) is True
    assert (p.root / ".gitignore").read_text(encoding="utf-8").splitlines() == ["*.tmp", ".lorewrite/", ".chisel/"]


def test_gitignore_untouched_when_it_never_listed_the_old_cache(tmp_path):
    p = old_project(tmp_path)
    (p.root / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    Project.open(p.root)
    assert (p.root / ".gitignore").read_text(encoding="utf-8") == "*.tmp\n"
    assert not (p.root / ".lorewrite").exists()           # the folder is still renamed


def test_open_with_chisel_folder_already_present(tmp_path):
    p = old_project(tmp_path)
    (p.root / ".chisel").mkdir()
    (p.root / ".chisel" / "index.sqlite").write_text("new cache", encoding="utf-8")
    assert migrate.migrate_project(p.root) == "present"
    assert (p.root / ".chisel" / "index.sqlite").read_text(encoding="utf-8") == "new cache"
    assert (p.root / ".lorewrite" / "index.sqlite").is_file()          # never deleted
    Project.open(p.root)                                                # and the app still opens it


def test_open_a_project_that_never_had_a_cache(tmp_path):
    p = Project.create(tmp_path / "fresh", "Fresh")
    assert migrate.migrate_project(p.root) == "none"
    assert not (p.root / ".lorewrite").exists() and not (p.root / ".chisel").exists()


def test_rename_failure_falls_back_to_a_fresh_cache(tmp_path, monkeypatch):
    p = old_project(tmp_path)

    def locked(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(migrate.fsutil, "rename", locked)
    project = Project.open(p.root)                           # must not raise
    assert project.title == "Book"
    assert (p.root / ".chisel").is_dir() and not (p.root / ".chisel" / "index.sqlite").exists()
    assert (p.root / ".lorewrite" / "index.sqlite").is_file()   # old folder untouched
    assert ".chisel/" in (p.root / ".gitignore").read_text(encoding="utf-8")


def test_rename_undo_journal_survives_the_move(tmp_path):
    p = Project.create(tmp_path / "book", "Book")
    (p.root / "manuscript" / "01-opening.md").unlink()
    e, _ = p.create_entity("Mara", "character")
    scene = p.manuscript_dir / "01-a.md"
    scene.write_text("Mara one.\n", encoding="utf-8")
    plan = rename.plan_rename(p, ent.resolve("Mara", p.load_entities()), "Nia")
    result = rename.apply_rename(p, plan, plan.default_ids())
    # make it look like the old app wrote the journal
    shutil.move(str(p.root / ".chisel"), str(p.root / ".lorewrite"))
    reopened = Project.open(p.root)
    assert (reopened.root / ".chisel" / "rename-undo").is_dir()
    undone = rename.undo_rename(reopened, result.undo_id)
    assert undone.skipped == []
    assert scene.read_text(encoding="utf-8") == "Mara one.\n"


def test_example_project_copy_migrates(tmp_path):
    copy = tmp_path / "residual"
    shutil.copytree(ROOT / "examples" / "residual", copy)
    (copy / ".gitignore").write_text(".lorewrite/\n", encoding="utf-8")
    (copy / ".lorewrite").mkdir()
    (copy / ".lorewrite" / "index.sqlite").write_text("c", encoding="utf-8")
    project = Project.open(copy)
    assert project.title == "Residual"
    assert (copy / ".chisel" / "index.sqlite").is_file() and not (copy / ".lorewrite").exists()
    assert (copy / ".gitignore").read_text(encoding="utf-8").splitlines() == [".lorewrite/", ".chisel/"]


def test_bundled_example_ignores_the_new_cache_folder():
    assert (ROOT / "examples" / "residual" / ".gitignore").read_text(encoding="utf-8").split() == [".chisel/"]


# -- git sync: both ignore lines count as "cache ignored" ----------------------

@pytest.fixture
def isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "T")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@example.invalid")


def test_cache_ignored_accepts_either_line():
    assert sync.cache_ignored([".chisel/"]) and sync.cache_ignored(["x", " .lorewrite/ "])
    assert not sync.cache_ignored(["*.tmp"])
    assert sync.GITIGNORE_LINE == ".chisel/"


@pytest.mark.skipif(not sync.git_available(), reason="git not installed")
@pytest.mark.parametrize("existing", [".lorewrite/\n", ".chisel/\n", ".lorewrite/\n.chisel/\n"])
def test_sync_init_does_not_duplicate_either_line(tmp_path, isolated_git, existing):
    p = Project.create(tmp_path / "n", "N")
    (p.root / ".gitignore").write_text(existing, encoding="utf-8")
    sync.init(p.root)
    assert (p.root / ".gitignore").read_text(encoding="utf-8") == existing


@pytest.mark.skipif(not sync.git_available(), reason="git not installed")
def test_sync_init_writes_the_new_line_for_new_projects(tmp_path, isolated_git):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "project.toml").write_text('title = "x"\n')
    sync.init(root)
    assert (root / ".gitignore").read_text(encoding="utf-8") == ".chisel/\n"


@pytest.mark.skipif(not sync.git_available(), reason="git not installed")
def test_migrated_git_project_does_not_show_the_cache_as_changes(tmp_path, isolated_git):
    p = old_project(tmp_path)
    subprocess.run(["git", "init"], cwd=p.root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=p.root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "x"], cwd=p.root, check=True, capture_output=True)
    Project.open(p.root)                                  # .lorewrite/ -> .chisel/, .gitignore updated
    st = sync.status(p.root)
    assert st.changes == 1                                # only the .gitignore edit, not the cache
