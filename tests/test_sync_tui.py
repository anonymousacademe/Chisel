"""Git sync in the terminal app (Wave 2.3). Temp repos / a local bare remote only."""

import os
import subprocess
from pathlib import Path

import pytest
from textual.widgets import Input

from lorewrite.core import sync
from lorewrite.core.project import Project
from lorewrite.tui.app import ConfirmScreen, LorewriteApp
from lorewrite.tui.commands import ActionProvider
from lorewrite.tui.syncscreens import MessagePrompt


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Test Author")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "author@example.invalid")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "02-two.md").write_text("# Two\n\nsecond\n")
    return p


def _entries(app) -> set[str]:
    provider = ActionProvider(app.screen)
    return {method for _, _, cb, _ in provider._entries() for method in [cb.__name__]}


async def _settle(app, pilot):
    # an action's worker starts a status refresh as it ends; slower git (Windows) needs
    # the second wait to cover that one too
    for _ in range(3):
        await pilot.pause()
        await app.workers.wait_for_complete()
    await pilot.pause()


async def test_no_repository_only_init_is_offered(tmp_path):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        assert app._sync is None
        names = _entries(app)
        assert "sync_init_confirm" in names
        assert "sync_commit_prompt" not in names and "sync_push_confirm" not in names
        assert "Synced" not in app._status_text and "change" not in app._status_text


async def test_init_asks_first_then_creates_a_repo(tmp_path):
    p = _project(tmp_path)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        app.sync_init_confirm()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")
        await _settle(app, pilot)
        assert not (p.root / ".git").exists()
        app.sync_init_confirm()
        await pilot.pause()
        await pilot.press("y")
        await _settle(app, pilot)
        assert (p.root / ".git").is_dir()
        assert ".lorewrite/" in (p.root / ".gitignore").read_text()
        assert app._sync is not None and "changes" in app._status_text
        assert "sync_init_confirm" not in _entries(app)
        assert "sync_commit_prompt" in _entries(app)


async def test_commit_prefills_the_message_and_commits_only_on_enter(tmp_path):
    p = _project(tmp_path)
    sync.init(p.root)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        assert app._sync.state == "changes"
        app.sync_commit_prompt()
        await pilot.pause()
        assert isinstance(app.screen, MessagePrompt)
        field = app.screen.query_one(Input)
        assert field.value.startswith("lorewrite: ") and field.value.endswith("scenes changed")
        await pilot.press("escape")                 # cancel: nothing committed
        await _settle(app, pilot)
        assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=p.root,
                              capture_output=True).returncode != 0
        app.sync_commit_prompt()
        await pilot.pause()
        app.screen.query_one(Input).value = "my own message"
        await pilot.press("enter")
        await _settle(app, pilot)
        assert git(p.root, "log", "-1", "--format=%s").strip() == "my own message"
        assert app._sync.label == "Synced" and "Synced" in app._status_text


async def test_status_line_follows_saves_but_saving_never_commits(tmp_path):
    p = _project(tmp_path)
    sync.init(p.root)
    sync.commit(p.root, "first")
    scene = p.manuscript_dir / "02-two.md"
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        assert "Synced" in app._status_text
        app.open_file(scene)
        app.editor.load_text("# Two\n\nedited text\n")
        await pilot.pause()
        app.save_current()
        app._sync_timer_fired()                     # do not wait out the 2.5 s throttle
        await _settle(app, pilot)
        assert "change" in app._status_text
        assert git(p.root, "rev-list", "--count", "HEAD").strip() == "1"   # still one commit


async def test_push_names_the_remote_asks_first_and_pushes(tmp_path):
    p = _project(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    sync.init(p.root)
    sync.commit(p.root, "first")
    git(p.root, "remote", "add", "origin", str(bare))
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        assert "Ahead 1" in app._status_text
        assert "sync_push_confirm" in _entries(app)
        app.sync_push_confirm()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert "origin" in str(app.screen._message) and str(bare) in str(app.screen._message)
        await pilot.press("n")
        await _settle(app, pilot)
        assert git(bare, "branch", "--list").strip() == ""             # declined: nothing sent
        app.sync_push_confirm()
        await pilot.pause()
        await pilot.press("y")
        await _settle(app, pilot)
        assert git(bare, "rev-list", "--count", app._sync.branch).strip() == "1"
        assert "Synced" in app._status_text


async def test_push_is_not_listed_without_a_remote(tmp_path):
    p = _project(tmp_path)
    sync.init(p.root)
    sync.commit(p.root, "first")
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        assert "sync_push_confirm" not in _entries(app)
        app.sync_push_confirm()                     # called anyway: refused politely
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)


async def test_git_errors_are_reported_not_raised(tmp_path, monkeypatch):
    p = _project(tmp_path)
    sync.init(p.root)
    app = LorewriteApp(p)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(app, pilot)
        monkeypatch.setattr(sync, "commit", lambda *a: (_ for _ in ()).throw(sync.GitError("boom")))
        app.sync_commit_prompt()
        await pilot.pause()
        await pilot.press("enter")
        await _settle(app, pilot)
        assert app.is_running
