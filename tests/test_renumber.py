"""Renumber on delete / restore (all modes): core/structure.py and the GUI bridge."""

from pathlib import Path

import pytest

from chisel.core import comments, drafts, fsutil, snapshots, structure
from chisel.core.index import Index
from chisel.core.project import Project
from chisel.gui.api import Api


def _mk(path: Path, title: str, body: str = "Some prose.") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8", newline="\n")
    return path


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.glob("*.md") if not p.name.startswith("_"))


@pytest.fixture(params=["story", "script", "research"])
def proj(request, tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "p", "P", mode=request.param)
    for f in p.manuscript_dir.glob("*.md"):
        f.unlink()
    return p


@pytest.fixture
def five(proj: Project) -> Project:
    """Front matter, two parts (a: 01-04, b: 01-02), loose Parked scene."""
    m = proj.manuscript_dir
    _mk(m / "00-front-matter" / "01-title.md", "Title")
    _mk(m / "00-front-matter" / "02-dedication.md", "Dedication")
    for n, s in enumerate("abcd", 1):
        _mk(m / "01-one" / f"{n:02d}-{s}.md", s.upper())
    _mk(m / "02-two" / "01-x.md", "X")
    _mk(m / "02-two" / "02-y.md", "Y")
    (m / "01-one" / "_part.md").write_text("# One\n", encoding="utf-8")
    (m / "02-two" / "_part.md").write_text("# Two\n", encoding="utf-8")
    _mk(m / "_unplaced" / "05-parked.md", "Parked")
    return proj


def test_delete_first_middle_last_close_the_gap(five: Project):
    one = five.manuscript_dir / "01-one"
    five.delete_scene(one / "01-a.md")
    assert _names(one) == ["01-b.md", "02-c.md", "03-d.md"]
    assert five.last_renames == {one / "02-b.md": one / "01-b.md",
                                 one / "03-c.md": one / "02-c.md",
                                 one / "04-d.md": one / "03-d.md"}
    five.delete_scene(one / "02-c.md")          # a middle one
    assert _names(one) == ["01-b.md", "02-d.md"]
    five.delete_scene(one / "02-d.md")          # the last: nothing to rename
    assert _names(one) == ["01-b.md"] and five.last_renames == {}


def test_other_folders_front_matter_and_parked_are_left_alone(five: Project):
    m = five.manuscript_dir
    five.delete_scene(m / "00-front-matter" / "01-title.md")
    assert _names(m / "00-front-matter") == ["02-dedication.md"]   # front matter: gap stays
    five.delete_scene(m / "01-one" / "01-a.md")
    assert _names(m / "02-two") == ["01-x.md", "02-y.md"]
    assert _names(m / "_unplaced") == ["05-parked.md"]
    five.delete_scene(m / "_unplaced" / "05-parked.md")
    assert five.last_renames == {}


def test_contiguous_folder_is_idempotent(five: Project):
    one = five.manuscript_dir / "01-one"
    assert five.renumber_folder(one) == {} and five.last_renames == {}
    assert _names(one) == ["01-a.md", "02-b.md", "03-c.md", "04-d.md"]


def test_delete_part_renumbers_the_parts(five: Project):
    m = five.manuscript_dir
    _mk(m / "03-three" / "01-p.md", "P")
    (m / "03-three" / "_part.md").write_text("# Three\n", encoding="utf-8")
    drafts.add_original(five.root, m / "03-three" / "01-p.md", "aaaaaa", "orig")
    comments.add(five.root, m / "03-three" / "01-p.md", "Some prose.", 0, 4, "note")
    for _ in range(4):
        five.delete_scene(sorted((m / "01-one").glob("[0-9]*.md"))[0])
    five.delete_part(m / "01-one")
    names = [p.name for p in five.list_parts()]
    assert names == ["00-front-matter", "01-two", "02-three"]
    assert (m / "01-two" / "_part.md").is_file() and (m / "02-three" / "_part.md").is_file()
    assert not (m / "03-three").exists()
    new = m / "02-three" / "01-p.md"
    assert five.last_renames[m / "03-three" / "01-p.md"] == new
    assert five.last_renames[m / "03-three"] == m / "02-three"
    assert drafts.load_originals(five.root, new) == {"aaaaaa": "orig"}
    assert [c.body for c in comments.load(five.root, new)] == ["note"]


def test_restore_goes_back_to_its_position(five: Project):
    one = five.manuscript_dir / "01-one"
    drafts.add_original(five.root, one / "02-b.md", "bbbbbb", "orig")
    five.delete_scene(one / "02-b.md")
    assert _names(one) == ["01-a.md", "02-c.md", "03-d.md"]
    item = five.list_trash()[0]
    back = five.restore_scene(item.name)
    assert back == one / "02-b.md"
    assert _names(one) == ["01-a.md", "02-b.md", "03-c.md", "04-d.md"]
    assert five.scene_title(one / "03-c.md") == "C"
    assert drafts.load_originals(five.root, back) == {"bbbbbb": "orig"}
    assert five.last_renames[one / "02-c.md"] == one / "03-c.md"


def test_restore_when_the_folder_shrank_or_came_from_parked(five: Project):
    m = five.manuscript_dir
    one = m / "01-one"
    five.delete_scene(one / "04-d.md")
    five.delete_scene(one / "01-a.md")
    five.delete_scene(one / "01-b.md")          # one is now 01-c only
    for item in five.list_trash():
        five.restore_scene(item.name)
    assert _names(one) == ["01-a.md", "02-b.md", "03-c.md", "04-d.md"]
    five.delete_scene(m / "_unplaced" / "05-parked.md")
    back = five.restore_scene(five.list_trash()[0].name)
    assert back.parent == five.unplaced_dir


def test_restore_follows_a_renumbered_part(five: Project):
    m = five.manuscript_dir
    _mk(m / "03-three" / "01-p.md", "P")
    _mk(m / "03-three" / "02-q.md", "Q")
    five.delete_scene(m / "03-three" / "02-q.md")
    for _ in range(4):
        five.delete_scene(sorted((m / "01-one").glob("[0-9]*.md"))[0])
    five.delete_part(m / "01-one")              # three is now 02-three
    q = next(i for i in five.list_trash() if i.title == "Q")
    assert five.restore_scene(q.name) == m / "02-three" / "02-q.md"


def test_snapshots_comments_and_drafts_follow_renumbered_scenes(five: Project):
    one = five.manuscript_dir / "01-one"
    old = one / "03-c.md"
    drafts.add_original(five.root, old, "cccccc", "orig")
    comments.add(five.root, old, "Some prose.", 0, 4, "remark")
    snapshots.create(five, old, label="keep")
    five.delete_scene(one / "01-a.md")
    new = one / "02-c.md"
    assert drafts.load_originals(five.root, new) == {"cccccc": "orig"}
    assert [c.body for c in comments.load(five.root, new)] == ["remark"]
    assert [s.label for s in snapshots.list_snapshots(five, new)] == ["keep"]
    assert not comments.sidecar_path(five.root, old).exists()
    assert not snapshots.scene_dir(five.root, old).exists()


def test_a_failure_part_way_leaves_every_file_present(five: Project, monkeypatch):
    one = five.manuscript_dir / "01-one"
    before = {p.name: p.read_text(encoding="utf-8") for p in one.glob("*.md")}
    real, calls = fsutil.rename, {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 4:
            raise OSError("injected")
        return real(a, b)

    monkeypatch.setattr(fsutil, "rename", flaky)
    trashed = five.delete_scene(one / "01-a.md")      # the delete itself must survive
    assert trashed.is_file()
    monkeypatch.setattr(fsutil, "rename", real)
    after = {p.read_text(encoding="utf-8") for p in one.glob("[0-9]*.md")}
    assert after == {before[n] for n in ("02-b.md", "03-c.md", "04-d.md")}
    assert not list(one.glob(".mv*"))
    assert five.renumber_folder(one)                   # a later call closes the gap
    assert _names(one) == ["01-b.md", "02-c.md", "03-d.md"]


def test_index_matches_a_fresh_rebuild(tmp_path: Path):
    root = tmp_path / "p"
    p = Project.create(root, "P")
    for f in p.manuscript_dir.glob("*.md"):
        f.unlink()
    for n, s in enumerate("abc", 1):
        _mk(root / "manuscript" / "01-one" / f"{n:02d}-{s}.md", s, f"See [[Nobody{s}]].")
    api = Api()
    assert api.open_project(str(root))["ok"]
    r = api.delete_scene("manuscript/01-one/01-a.md")
    assert r["ok"] and r["remap"] == {
        "manuscript/01-one/02-b.md": "manuscript/01-one/01-b.md",
        "manuscript/01-one/03-c.md": "manuscript/01-one/02-c.md"}
    live = sorted(api.index._conn.execute("select source, target from links"))
    fresh = Index(tmp_path / "fresh.db")
    fresh.rebuild(Project.open(root))
    assert live == sorted(fresh._conn.execute("select source, target from links"))
    back = api.restore_trash(api.list_trash()["items"][0]["name"])
    assert back["id"] == "manuscript/01-one/01-a.md"
    assert back["remap"] == {"manuscript/01-one/01-b.md": "manuscript/01-one/02-b.md",
                             "manuscript/01-one/02-c.md": "manuscript/01-one/03-c.md",
                             "manuscript/01-one/01-a.md": "manuscript/01-one/01-a.md"} or \
        back["remap"].get("manuscript/01-one/02-c.md") == "manuscript/01-one/03-c.md"
    live = sorted(api.index._conn.execute("select source, target from links"))
    fresh2 = Index(tmp_path / "fresh2.db")
    fresh2.rebuild(Project.open(root))
    assert live == sorted(fresh2._conn.execute("select source, target from links"))


def test_gui_delete_part_returns_a_remap(tmp_path: Path):
    root = tmp_path / "p"
    p = Project.create(root, "P")
    for f in p.manuscript_dir.glob("*.md"):
        f.unlink()
    _mk(root / "manuscript" / "01-one" / "01-a.md", "A")
    _mk(root / "manuscript" / "02-two" / "01-b.md", "B")
    api = Api()
    assert api.open_project(str(root))["ok"]
    assert api.delete_scene("manuscript/01-one/01-a.md")["ok"]
    (root / "manuscript" / "01-one" / "_part.md").unlink(missing_ok=True)
    part_id = next(n["id"] for n in api.get_workspace()["workspace"]["binder"][0]["children"]
                   if n["kind"] == "part" and n["title"] != "Two")
    r = api.delete_part(part_id)
    assert r["ok"] and r["remap"] == {"manuscript/02-two/01-b.md": "manuscript/01-two/01-b.md",
                                      "manuscript/02-two": "manuscript/01-two"}
    assert (root / "manuscript" / "01-two" / "01-b.md").is_file()


def test_delete_part_keeps_front_matter_first(proj: Project):
    fm = proj.new_part("Front Matter")
    a = proj.new_part("Act A")
    proj.new_part("Act B")
    assert [p.name for p in proj.list_parts()] == ["01-front-matter", "02-act-a", "03-act-b"]
    proj.delete_part(a)
    assert [p.name for p in proj.list_parts()] == ["01-front-matter", "02-act-b"]
    assert proj.last_renames == {proj.manuscript_dir / "03-act-b": proj.manuscript_dir / "02-act-b"}
    assert fm.is_dir()


def test_delete_part_with_two_front_matter_parts(proj: Project):
    m = proj.manuscript_dir
    for name in ("00-front-matter", "01-front-matter-2", "02-a", "03-b", "04-c"):
        (m / name).mkdir()
        (m / name / "_part.md").write_text("# T\n", encoding="utf-8", newline="\n")
    proj.delete_part(m / "02-a")
    assert [p.name for p in proj.list_parts()] == [
        "00-front-matter", "01-front-matter-2", "02-b", "03-c"]


def test_delete_part_survives_a_locked_rename(proj: Project, monkeypatch):
    m = proj.manuscript_dir
    for name in ("01-a", "02-b", "03-c", "04-d"):
        _mk(m / name / "01-s.md", name)
    (m / "01-a" / "01-s.md").unlink()
    real, calls = fsutil.rename, {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] > 3:      # the first renumbered part goes through, a later one fails
            raise OSError("injected")
        return real(a, b)

    monkeypatch.setattr(fsutil, "rename", flaky)
    proj.delete_part(m / "01-a")                 # must not raise
    monkeypatch.setattr(fsutil, "rename", real)
    assert proj.renumber_warning
    assert proj.last_renames                     # what moved is reported
    assert not list(m.rglob(".mv*"))
    assert len(list(m.rglob("01-s.md"))) == 3    # no scene lost
    for old, new in proj.last_renames.items():
        assert not old.exists() and new.exists()


def test_gui_delete_part_reports_the_warning(tmp_path: Path, monkeypatch):
    root = tmp_path / "p"
    p = Project.create(root, "P")
    for f in p.manuscript_dir.glob("*.md"):
        f.unlink()
    for name in ("01-a", "02-b", "03-c"):
        _mk(root / "manuscript" / name / "01-s.md", name)
    (root / "manuscript" / "01-a" / "01-s.md").unlink()
    api = Api()
    assert api.open_project(str(root))["ok"]
    real = fsutil.rename

    def locked(a, b):
        raise OSError("x")

    monkeypatch.setattr(fsutil, "rename", locked)
    r = api.delete_part("manuscript/01-a")
    monkeypatch.setattr(fsutil, "rename", real)
    assert r["ok"] and r.get("warning")


def test_restore_keeps_a_three_digit_folder_width(proj: Project):
    one = proj.manuscript_dir / "01-one"
    for n, s in enumerate("abc", 1):
        _mk(one / f"{n:03d}-{s}.md", s)
    proj.delete_scene(one / "002-b.md")
    assert _names(one) == ["001-a.md", "002-c.md"]
    back = proj.restore_scene(proj.list_trash()[0].name)
    assert _names(one) == ["001-a.md", "002-b.md", "003-c.md"] and back.name == "002-b.md"


def test_helpers_unchanged_names():
    assert structure._slug_of("03-c.md") == "c"


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_renumber_failure_never_splits_a_part(proj: Project, monkeypatch, fail_at):
    m = proj.manuscript_dir
    for name in ("01-a", "02-b"):
        (m / name).mkdir()
    (m / "02-b" / "_part.md").write_text("# Title B\n", encoding="utf-8", newline="\n")
    _mk(m / "02-b" / "01-s.md", "S")
    real, calls = fsutil.rename, {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise OSError("injected")
        return real(a, b)

    monkeypatch.setattr(fsutil, "rename", flaky)
    proj.delete_part(m / "01-a")                 # must not raise
    monkeypatch.setattr(fsutil, "rename", real)
    assert proj.renumber_warning
    assert not list(m.rglob(".mv*"))
    assert (m / "02-b" / "_part.md").is_file()   # title and scene stay together
    assert (m / "02-b" / "01-s.md").is_file()
    assert not (m / "01-b").exists()
