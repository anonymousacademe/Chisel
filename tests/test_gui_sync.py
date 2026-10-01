"""Api: git sync bridge methods (Wave 2.3). Temp repos and a local bare remote only."""

import subprocess
from pathlib import Path

import pytest

from lorewrite.core import sync
from lorewrite.gui.api import Api
from tests.gui_helpers import make_project


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Test Author")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "author@example.invalid")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def open_api(tmp_path):
    root = tmp_path / "p"
    make_project(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def test_no_repository_offers_init_and_nothing_else(tmp_path):
    api, root = open_api(tmp_path)
    s = api.sync_status()["sync"]
    assert (s["repo"], s["canInit"], s["label"]) == (False, True, "Sync")
    r = api.sync_commit("nope")
    assert r["ok"] is False and "not in a git repository" in r["error"]
    assert r["error"].startswith("the project") and "GitError" not in r["error"]
    assert api.sync_push()["ok"] is False
    assert not (root / ".git").exists()           # nothing happened on its own


def test_git_missing_hides_the_item(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(sync.shutil, "which", lambda _: None)
    assert api.sync_status() == {"ok": True, "sync": None}


def test_init_commit_push_flow(tmp_path):
    api, root = open_api(tmp_path)
    r = api.sync_init()
    assert r["ok"] and r["sync"]["repo"] is True and r["sync"]["state"] == "changes"
    assert ".lorewrite/" in (root / ".gitignore").read_text(encoding="utf-8")
    assert api.sync_init()["ok"] is False          # already a repository
    s = r["sync"]
    assert s["scenes"] == 2 and s["defaultMessage"].endswith("— 2 scenes changed")
    assert s["canPush"] is False and s["remote"] is None

    c = api.sync_commit(s["defaultMessage"])
    assert c["ok"] and c["sync"]["label"] == "Synced"
    assert api.sync_commit("again")["ok"] is False  # nothing to commit

    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    s = api.sync_status()["sync"]
    assert (s["label"], s["canPush"], s["remote"], s["remoteUrl"]) == ("Ahead 1", True, "origin", str(bare))
    p = api.sync_push()
    assert p["ok"] and p["summary"].endswith("to origin") and p["sync"]["label"] == "Synced"
    assert git(bare, "rev-list", "--count", p["sync"]["branch"]).strip() == "1"


def test_saving_never_commits_or_pushes(tmp_path):
    """Autosave only writes files: git history does not move without a click."""
    api, root = open_api(tmp_path)
    api.sync_init()
    api.sync_commit("first")
    count = git(root, "rev-list", "--count", "HEAD").strip()
    doc = api.read_document("manuscript/01-arrival.md")
    assert api.save_document(doc["id"], doc["text"] + "more\n", doc["mtime"])["saved"]
    assert git(root, "rev-list", "--count", "HEAD").strip() == count
    s = api.sync_status()["sync"]
    assert s["state"] == "changes" and s["changes"] >= 1


def test_workspace_refresh_does_not_run_git(tmp_path, monkeypatch):
    """get_workspace is called after every save; it must not spawn git."""
    api, root = open_api(tmp_path)
    calls = []
    monkeypatch.setattr(sync, "status", lambda *a, **k: calls.append(1))
    api.get_workspace()
    assert calls == []
