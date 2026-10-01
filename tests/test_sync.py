"""Git sync (Wave 2.3): temp repositories and a local bare remote only.

Every test runs git with the user's and the system's git config switched off
(no signing, no hooks from ~/.gitconfig) and with an identity set locally."""

import subprocess
from datetime import date
from pathlib import Path

import pytest

from lorewrite.core import snapshots, sync
from lorewrite.core.project import Project


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Author")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Author")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "author@example.invalid")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def novel(tmp_path: Path, name: str = "novel") -> Project:
    p = Project.create(tmp_path / name, "Novel")
    (p.manuscript_dir / "02-two.md").write_text("# Two\n\nsecond\n", encoding="utf-8")
    return p


def test_not_a_repository_reports_none_and_offers_init(tmp_path):
    p = novel(tmp_path)
    assert sync.status(p.root) is None
    assert sync.can_init(p.root) is True


def test_git_missing_hides_everything(tmp_path, monkeypatch):
    p = novel(tmp_path)
    monkeypatch.setattr(sync.shutil, "which", lambda _: None)
    assert sync.status(p.root) is None
    assert sync.can_init(p.root) is False
    with pytest.raises(sync.GitError):
        sync.init(p.root)


def test_init_creates_a_repo_and_hides_only_the_cache(tmp_path):
    p = novel(tmp_path)
    (p.root / ".gitignore").write_text("*.tmp", encoding="utf-8")   # no trailing newline
    sync.init(p.root)
    assert (p.root / ".git").is_dir()
    assert (p.root / ".gitignore").read_text(encoding="utf-8").splitlines() == ["*.tmp", ".lorewrite/"]
    with pytest.raises(sync.GitError):
        sync.init(p.root)          # already a repository
    # a second init attempt never duplicates the line either
    assert (p.root / ".gitignore").read_text(encoding="utf-8").count(".lorewrite/") == 1


def test_init_on_a_bare_project_creates_gitignore(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "project.toml").write_text('title = "x"\n')
    sync.init(root)
    assert (root / ".gitignore").read_text(encoding="utf-8") == ".lorewrite/\n"


def test_status_counts_changes_and_scenes_then_commit_makes_it_synced(tmp_path):
    p = novel(tmp_path)
    sync.init(p.root)
    (p.root / ".lorewrite").mkdir()
    (p.root / ".lorewrite" / "index.sqlite").write_text("cache")   # ignored: not a change
    st = sync.status(p.root)
    assert st.state == "changes" and st.scenes == 2          # both scenes are untracked
    assert st.changes >= 4 and st.label == f"{st.changes} changes"
    assert st.remote is None and st.can_push is False
    msg = sync.default_message(st, date(2026, 10, 1))
    assert msg == "lorewrite: 2026-10-01 — 2 scenes changed"
    sync.commit(p.root, msg)                                   # first commit of a new repo
    st = sync.status(p.root)
    assert (st.state, st.label, st.changes) == ("synced", "Synced", 0)
    assert git(p.root, "log", "-1", "--format=%s") .strip() == msg
    assert ".lorewrite" not in git(p.root, "ls-files")

    (p.manuscript_dir / "02-two.md").write_text("# Two\n\nchanged\n", encoding="utf-8")
    st = sync.status(p.root)
    assert (st.state, st.label, st.scenes) == ("changes", "1 change", 1)
    assert sync.default_message(st, date(2026, 10, 2)) == "lorewrite: 2026-10-02 — 1 scene changed"


def test_nothing_to_commit_and_empty_message_are_errors(tmp_path):
    p = novel(tmp_path)
    sync.init(p.root)
    with pytest.raises(ValueError):
        sync.commit(p.root, "   ")
    sync.commit(p.root, "first")
    with pytest.raises(ValueError):
        sync.commit(p.root, "again")
    assert git(p.root, "rev-list", "--count", "HEAD").strip() == "1"


def test_multiline_messages_are_kept(tmp_path):
    p = novel(tmp_path)
    sync.init(p.root)
    sync.commit(p.root, "Subject line\n\nA longer body.")
    assert git(p.root, "log", "-1", "--format=%B").strip() == "Subject line\n\nA longer body."


def test_renames_count_once(tmp_path):
    p = novel(tmp_path)
    sync.init(p.root)
    sync.commit(p.root, "first")
    git(p.root, "mv", "manuscript/02-two.md", "manuscript/03-two.md")
    st = sync.status(p.root)
    assert st.changes == 1 and st.scenes == 1


def test_snapshots_drafts_and_trash_are_committed_not_ignored(tmp_path):
    p = novel(tmp_path)
    scene = p.manuscript_dir / "02-two.md"
    snapshots.create(p, scene, "keep")
    (p.root / ".drafts").mkdir()
    (p.root / ".drafts" / "manuscript__02-two.md.json").write_text("{}")
    (p.root / ".trash").mkdir()
    (p.root / ".trash" / "20261001-000000-manuscript__x.md").write_text("# x\n")
    sync.init(p.root)
    sync.commit(p.root, "all of it")
    tracked = git(p.root, "ls-files")
    assert ".snapshots/" in tracked and ".drafts/" in tracked and ".trash/" in tracked


def test_push_to_a_local_bare_remote_and_ahead_label(tmp_path):
    p = novel(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    sync.init(p.root)
    sync.commit(p.root, "first")
    st = sync.status(p.root)
    assert st.remote is None and st.state == "synced"          # no remote: nothing to push
    with pytest.raises(sync.GitError):
        sync.push(p.root)
    git(p.root, "remote", "add", "origin", str(bare))
    st = sync.status(p.root)
    assert (st.remote, st.state, st.ahead, st.label) == ("origin", "ahead", 1, "Ahead 1")
    assert st.can_push is True
    assert sync.remote_url(p.root, "origin") == str(bare)
    out = sync.push(p.root)                                    # first push sets the upstream
    assert out.endswith("to origin")
    st = sync.status(p.root)
    assert (st.state, st.ahead) == ("synced", 0)
    assert git(bare, "rev-list", "--count", st.branch).strip() == "1"

    (p.manuscript_dir / "02-two.md").write_text("# Two\n\nmore\n", encoding="utf-8")
    sync.commit(p.root, "second")
    st = sync.status(p.root)
    assert (st.state, st.ahead) == ("ahead", 1)
    sync.push(p.root)
    assert sync.status(p.root).state == "synced"
    assert git(bare, "rev-list", "--count", st.branch).strip() == "2"


def test_changes_win_over_ahead_in_the_label(tmp_path):
    p = novel(tmp_path)
    bare = tmp_path / "r.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    sync.init(p.root)
    sync.commit(p.root, "first")
    git(p.root, "remote", "add", "origin", str(bare))
    (p.manuscript_dir / "02-two.md").write_text("# Two\n\nedit\n", encoding="utf-8")
    st = sync.status(p.root)
    assert st.state == "changes" and st.ahead == 1


def test_push_never_forces(tmp_path):
    """Remote history diverged: the push is refused and the remote is untouched."""
    p = novel(tmp_path)
    bare = tmp_path / "r.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    sync.init(p.root)
    sync.commit(p.root, "first")
    git(p.root, "remote", "add", "origin", str(bare))
    sync.push(p.root)
    branch = sync.status(p.root).branch
    # someone else pushes a commit
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(bare), str(other))
    (other / "note.txt").write_text("theirs")
    git(other, "add", "-A")
    git(other, "commit", "-qm", "theirs")
    git(other, "push", "-q")
    theirs = git(bare, "rev-parse", branch).strip()
    # we commit on top of the old state
    (p.manuscript_dir / "02-two.md").write_text("# Two\n\nmine\n", encoding="utf-8")
    sync.commit(p.root, "mine")
    with pytest.raises(sync.GitError):
        sync.push(p.root)
    assert git(bare, "rev-parse", branch).strip() == theirs


def test_detached_head_cannot_push(tmp_path):
    p = novel(tmp_path)
    bare = tmp_path / "r.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    sync.init(p.root)
    sync.commit(p.root, "first")
    git(p.root, "remote", "add", "origin", str(bare))
    git(p.root, "checkout", "-q", "--detach")
    assert sync.status(p.root).branch == ""
    with pytest.raises(sync.GitError, match="detached"):
        sync.push(p.root)


def test_a_project_inside_a_bigger_repo_commits_only_its_own_folder(tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q")
    (outer / "other.txt").write_text("not mine")
    p = Project.create(outer / "books" / "novel", "Novel")
    st = sync.status(p.root)
    assert st is not None and st.toplevel == str(outer.resolve())
    assert st.scenes == 1                       # the prefix is stripped: manuscript/01-opening.md
    sync.commit(p.root, "novel only")
    names = git(outer, "show", "--name-only", "--format=").split()
    assert names and all(n.startswith("books/novel/") for n in names)
    assert "other.txt" not in names
    assert git(outer, "status", "--porcelain").strip() == "?? other.txt"
    assert sync.status(p.root).state == "synced"


def test_unrelated_staged_files_are_left_staged(tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q")
    (outer / "seed.txt").write_text("x")
    git(outer, "add", "-A")
    git(outer, "commit", "-qm", "seed")
    (outer / "staged.txt").write_text("staged by someone else")
    git(outer, "add", "staged.txt")
    p = Project.create(outer / "novel", "Novel")
    sync.commit(p.root, "novel")
    assert "staged.txt" not in git(outer, "show", "--name-only", "--format=")
    assert git(outer, "diff", "--cached", "--name-only").strip() == "staged.txt"


def test_a_timeout_becomes_a_clear_error(tmp_path, monkeypatch):
    p = novel(tmp_path)
    sync.init(p.root)

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(sync.subprocess, "run", slow)
    with pytest.raises(sync.GitError, match="took longer"):
        sync._run(p.root, "status", timeout=1)
    assert sync.status(p.root) is None          # a hung status hides the item, never freezes


def test_status_is_read_only(tmp_path):
    p = novel(tmp_path)
    sync.init(p.root)
    before = sorted(x.name for x in (p.root / ".git").iterdir())
    sync.status(p.root)
    sync.status(p.root)
    assert sorted(x.name for x in (p.root / ".git").iterdir()) == before
