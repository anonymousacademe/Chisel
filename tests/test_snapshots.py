"""Core snapshots (Wave 2.1) and the manuscript draft counter (2.2)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from chisel.core import drafts, snapshots
from chisel.core.project import Project
from tests.gui_helpers import make_book, make_project


@pytest.fixture
def book(tmp_path: Path) -> Project:
    return make_book(tmp_path / "novel")


def rain(book: Project) -> Path:
    return book.manuscript_dir / "01-the-recall" / "01-rain.md"


def test_create_is_verbatim_with_label_and_listed_newest_first(book):
    scene = rain(book)
    a = snapshots.create(book, scene, "first draft", when=datetime(2026, 10, 1, 9, 0, 0))
    b = snapshots.create(book, scene, when=datetime(2026, 10, 1, 9, 5, 0))
    assert a.path.parent == book.root / ".snapshots" / "manuscript__01-the-recall__01-rain.md"
    assert a.path.name == "20261001-090000--first draft.md"
    assert a.path.read_text(encoding="utf-8") == scene.read_text(encoding="utf-8")
    listed = snapshots.list_snapshots(book, scene)
    assert [s.name for s in listed] == [b.name, a.name]
    assert listed[1].label == "first draft" and listed[0].label == ""
    assert listed[0].words == 12  # "# Rain" + ten "rain"


def test_same_second_never_overwrites(book):
    scene, when = rain(book), datetime(2026, 10, 1, 9, 0, 0)
    names = {snapshots.create(book, scene, "x", when=when).name for _ in range(3)}
    assert len(names) == 3
    assert len(snapshots.list_snapshots(book, scene)) == 3


def test_labels_are_made_safe_and_dots_survive(book):
    scene = rain(book)
    s = snapshots.create(book, scene, "a/b\\c: v1.2 ", when=datetime(2026, 10, 1, 9, 0, 0))
    assert "/" not in s.name and "\\" not in s.name
    assert s.label.endswith("v1.2")
    assert snapshots.read_text(book, scene, s.name).startswith("# Rain")
    snapshots.delete(book, scene, s.name)
    assert snapshots.list_snapshots(book, scene) == []


def test_bad_ids_are_refused(book):
    with pytest.raises(ValueError):
        snapshots.read_text(book, rain(book), "../../project")
    with pytest.raises(FileNotFoundError):
        snapshots.read_text(book, rain(book), "20261001-090000")


def test_frontmatter_and_unsaved_text_are_kept_verbatim(book):
    scene = rain(book)
    scene.write_text("---\nstatus: draft\n---\n# Rain\n\nrain rain\n", encoding="utf-8")
    s = snapshots.create(book, scene)
    assert s.path.read_text(encoding="utf-8").startswith("---\nstatus: draft\n---")
    assert s.words == 4  # "# Rain" + 2 words; frontmatter is not prose
    buffer = "# Rain\n\nunsaved edit in the editor\n"
    t = snapshots.create(book, scene, "buffer", text=buffer, when=datetime(2030, 1, 1))
    assert t.path.read_text(encoding="utf-8") == buffer


def test_draft_originals_are_copied_alongside_and_restored(book):
    scene = rain(book)
    drafts.add_original(book.root, scene, "abc123", "the original words")
    scene.write_text('# Rain\n\n<!--ai id="abc123"-->new<!--/ai-->\n', encoding="utf-8")
    snap = snapshots.create(book, scene, "with draft")
    assert snap.path.with_name(snap.path.stem + ".json").is_file()
    drafts.drop_original(book.root, scene, "abc123")  # the draft was accepted...
    scene.write_text("# Rain\n\naccepted\n", encoding="utf-8")
    text = snapshots.restore(book, scene, snap.name)
    assert "<!--ai id=" in text and scene.read_text(encoding="utf-8") == text
    assert drafts.load_originals(book.root, scene) == {"abc123": "the original words"}
    # the restore snapshotted what it replaced, so it can be undone
    labels = [s.label for s in snapshots.list_snapshots(book, scene)]
    assert "before-restore" in labels


def test_restore_snapshots_the_editor_buffer_first(book):
    scene = rain(book)
    old = snapshots.create(book, scene, "old", when=datetime(2026, 10, 1, 9, 0, 0))
    scene.write_text("# Rain\n\nmid\n", encoding="utf-8")
    snapshots.restore(book, scene, old.name, current_text="# Rain\n\nbuffer ahead of disk\n")
    safety = next(s for s in snapshots.list_snapshots(book, scene) if s.label == "before-restore")
    assert "buffer ahead of disk" in safety.path.read_text(encoding="utf-8")
    assert scene.read_text(encoding="utf-8").startswith("# Rain\n\nrain")


def test_restore_without_originals_clears_the_sidecar(book):
    scene = rain(book)
    snap = snapshots.create(book, scene)
    drafts.add_original(book.root, scene, "zzz999", "x")
    snapshots.restore(book, scene, snap.name)
    assert drafts.load_originals(book.root, scene) == {}


def test_delete_tidies_the_folder(book):
    scene = rain(book)
    s = snapshots.create(book, scene)
    snapshots.delete(book, scene, s.name)
    assert not snapshots.scene_dir(book.root, scene).exists()


def test_snapshot_all_covers_book_and_unplaced(book):
    unplaced = book.unplace_scene(book.manuscript_dir / "02-ghost" / "01-signal.md")
    n = snapshots.snapshot_all(book, "milestone")
    assert n == len(book.all_scene_files()) == 4
    assert all(snapshots.list_snapshots(book, p)[0].label == "milestone"
               for p in book.all_scene_files())
    assert snapshots.list_snapshots(book, unplaced)


def test_ensure_daily_snapshots_the_pre_edit_state_once(book):
    snapshots._daily_done.clear()
    scene = rain(book)
    original = scene.read_text(encoding="utf-8")
    assert snapshots.ensure_daily(book, scene, original) is None  # unchanged: nothing
    snap = snapshots.ensure_daily(book, scene, original + "more\n")
    assert snap is not None and snap.label == "auto"
    assert snap.path.read_text(encoding="utf-8") == original  # the state *before* the edit
    assert snapshots.ensure_daily(book, scene, original + "even more\n") is None
    assert len(snapshots.list_snapshots(book, scene)) == 1


def test_ensure_daily_skips_when_a_snapshot_from_today_exists(book):
    snapshots._daily_done.clear()
    scene = rain(book)
    snapshots.create(book, scene, "manual")
    assert snapshots.ensure_daily(book, scene, "# Rain\n\nchanged\n") is None


def test_ensure_daily_skips_when_latest_snapshot_is_identical(book):
    snapshots._daily_done.clear()
    scene = rain(book)
    snapshots.create(book, scene, "yesterday", when=datetime.now() - timedelta(days=1))
    assert snapshots.ensure_daily(book, scene, "# Rain\n\nchanged\n") is None


def test_snapshots_follow_renames_moves_and_part_swaps(book):
    cap = book.manuscript_dir / "01-the-recall" / "02-capsule.md"
    snapshots.create(book, cap, "keep me")
    swapped = book.move_scene(cap, -1)  # swaps prefixes with Rain
    assert swapped is not None and swapped != cap
    assert [s.label for s in snapshots.list_snapshots(book, swapped)] == ["keep me"]
    assert snapshots.list_snapshots(book, cap) == [] or cap.exists()  # cap is Rain now
    moved = book.move_scene_to_part(swapped, book.list_parts()[-1])
    assert [s.label for s in snapshots.list_snapshots(book, moved)] == ["keep me"]
    # whole part swapped: scene paths change under the folder
    parts = book.list_parts()
    sig = book.part_scenes(parts[-1])[0]
    snapshots.create(book, sig, "in part 2")
    book.move_part(parts[-1], -1)
    new_sig = book.part_scenes(book.list_parts()[-2])
    assert any(snapshots.list_snapshots(book, p) and
               snapshots.list_snapshots(book, p)[0].label == "in part 2" for p in new_sig)


def test_snapshots_ride_through_the_trash_and_back(book):
    scene = rain(book)
    snapshots.create(book, scene, "history")
    trashed = book.delete_scene(scene)
    assert not snapshots.scene_dir(book.root, scene).exists()
    assert trashed.with_name(trashed.name + ".snapshots").is_dir()
    restored = book.restore_scene(trashed.name)
    assert [s.label for s in snapshots.list_snapshots(book, restored)] == ["history"]
    # delete forever removes the history with it
    t2 = book.delete_scene(restored)
    book.delete_forever(t2.name)
    assert not (book.root / ".trash").exists()


def test_diff_words_roundtrips_and_marks_changes():
    old = "The rain fell.\nMara waited under the clock.\nIt was late.\n"
    new = "The rain fell.\nMara waited beneath the old clock.\nIt was late.\nShe left.\n"
    segs = snapshots.diff_words(old, new)
    assert "".join(s.old for s in segs) == old
    assert "".join(s.new for s in segs) == new
    ops = [s.op for s in segs]
    assert "equal" in ops and ("insert" in ops or "replace" in ops)
    added, removed = snapshots.diff_stats(segs)
    assert added > removed >= 1
    assert snapshots.diff_words("same\n", "same\n") == [snapshots.Segment("equal", "same\n", "same\n")]
    assert snapshots.diff_stats(snapshots.diff_words("", "a b c")) == (3, 0)


def test_diff_words_degrades_on_huge_hunks():
    a = " ".join(f"a{i}" for i in range(9000)) + "\n"
    b = " ".join(f"b{i}" for i in range(9000)) + "\n"
    segs = snapshots.diff_words(a, b)  # 81M token pairs: one replace, not minutes
    assert segs == [snapshots.Segment("replace", a, b)]


def test_ago_wording():
    now = datetime(2026, 10, 1, 12, 0, 0)
    assert snapshots.ago(now - timedelta(seconds=5), now) == "just now"
    assert snapshots.ago(now - timedelta(minutes=12), now) == "12 min ago"
    assert snapshots.ago(now - timedelta(hours=3), now) == "3 h ago"
    assert snapshots.ago(now - timedelta(days=1), now) == "1 day ago"
    assert snapshots.ago(now - timedelta(days=40), now) == "2026-08-22"


# -- 2.2 drafts -----------------------------------------------------------------


def test_draft_defaults_to_one_and_survives_reopen(tmp_path):
    project = make_project(tmp_path / "p")
    assert project.draft == 1
    n = project.start_new_draft()
    assert n == 2 and project.draft == 2
    assert Project.open(project.root).draft == 2
    assert "draft = 2" in (project.root / "project.toml").read_text(encoding="utf-8")


def test_start_new_draft_snapshots_every_scene_as_end_of_draft(tmp_path):
    project = make_project(tmp_path / "p")
    project.start_new_draft()
    project.start_new_draft()
    for scene in project.all_scene_files():
        labels = [s.label for s in snapshots.list_snapshots(project, scene)]
        assert sorted(labels) == ["end-of-draft-1", "end-of-draft-2"]
    assert project.draft == 3


def test_failed_snapshot_does_not_advance_the_draft(tmp_path, monkeypatch):
    project = make_project(tmp_path / "p")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(snapshots, "snapshot_all", boom)
    with pytest.raises(OSError):
        project.start_new_draft()
    assert project.draft == 1


def test_draft_counter_keeps_unit_and_other_settings(tmp_path):
    project = make_project(tmp_path / "p")
    project.update_manuscript_settings(unit="chapter")
    project.start_new_draft()
    reopened = Project.open(project.root)
    assert reopened.unit == "chapter" and reopened.draft == 2
    assert reopened.title == "Test Novel"


def test_bad_draft_values_fall_back_to_one(tmp_path):
    project = make_project(tmp_path / "p")
    project.meta = {"manuscript": {"draft": "two"}}
    assert project.draft == 1
    project.meta = {"manuscript": {"draft": 0}}
    assert project.draft == 1


def test_snapshots_are_not_gitignored_by_a_new_project(tmp_path):
    ignore = (Project.create(tmp_path / "n", "N").root / ".gitignore").read_text(encoding="utf-8")
    assert ".snapshots" not in ignore and ".drafts" not in ignore
