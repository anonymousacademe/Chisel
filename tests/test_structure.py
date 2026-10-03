"""Parts, unplaced scenes and trash (Wave 1.1 / 1.2): core behavior."""

import json
import shutil
from pathlib import Path

import pytest

from chisel.core import drafts
from chisel.core.index import Index
from chisel.core.project import Project

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "residual"


def _mk(path: Path, title: str, body: str = "Some prose.") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body}\n")
    return path


@pytest.fixture
def proj(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "novel", "Novel")
    (p.manuscript_dir / "01-opening.md").unlink()
    return p


@pytest.fixture
def book(proj: Project) -> Project:
    """front matter + two parts, scenes in each, one unparted-free layout."""
    m = proj.manuscript_dir
    _mk(m / "00-front-matter" / "01-title.md", "Title Page", "Words " * 5)
    (m / "00-front-matter" / "_part.md").write_text("# Front Matter\n")
    _mk(m / "01-the-recall" / "01-a.md", "A")
    _mk(m / "01-the-recall" / "02-b.md", "B")
    _mk(m / "02-ghost-frequency" / "01-c.md", "C")
    return proj


# -- reading ---------------------------------------------------------------


def test_residual_example_opens_unchanged(tmp_path: Path):
    copy = tmp_path / "residual"
    shutil.copytree(EXAMPLE, copy)
    p = Project.open(copy)
    assert [s.name for s in p.list_scenes()] == sorted(
        s.name for s in (EXAMPLE / "manuscript").glob("*.md"))
    assert p.list_parts() == [] and p.list_unplaced() == [] and not p.has_parts()
    assert p.unit == "scene"
    assert [p.scene_number(s) for s in p.list_scenes()] == ["01", "02", "03", "04"]
    assert p.counted_scenes() == p.list_scenes()
    assert not (copy / ".trash").exists()


def test_reading_order_is_unparted_then_parts_and_numeric(book: Project):
    m = book.manuscript_dir
    _mk(m / "05-loose.md", "Loose")
    _mk(m / "01-the-recall" / "10-late.md", "Late")      # 10 after 02 (numeric)
    _mk(m / "01-the-recall" / "3-three.md", "Three")      # 3 before 10
    assert [p.relative_to(m).as_posix() for p in book.list_scenes()] == [
        "05-loose.md",
        "00-front-matter/01-title.md",
        "01-the-recall/01-a.md", "01-the-recall/02-b.md",
        "01-the-recall/3-three.md", "01-the-recall/10-late.md",
        "02-ghost-frequency/01-c.md",
    ]


def test_part_titles_and_helpers(book: Project):
    parts = book.list_parts()
    assert [book.part_title(p) for p in parts] == [
        "Front Matter", "Recall".replace("Recall", "The Recall"), "Ghost Frequency"]
    (parts[1] / "_part.md").write_text("# Part I - The Recall\n\nNotes for me.\n")
    assert book.part_title(parts[1]) == "Part I - The Recall"
    assert book.part_notes(parts[1]) == "Notes for me."
    a = parts[1] / "01-a.md"
    assert book.part_of(a) == parts[1] and book.is_scene_path(a)
    assert not book.is_scene_path(parts[1] / "_part.md")
    assert book.is_front_matter(parts[0] / "01-title.md")
    assert not book.is_front_matter(a)


def test_part_file_and_dot_dirs_are_not_scenes(book: Project):
    (book.manuscript_dir / ".hidden").mkdir()
    _mk(book.manuscript_dir / ".hidden" / "01-x.md", "X")
    assert all(p.name != "_part.md" for p in book.list_scenes())
    assert all(".hidden" not in str(p) for p in book.list_scenes())


def test_numbering_is_global_across_parts_and_skips_front_matter(book: Project):
    s = book.list_scenes()
    assert [book.scene_number(p) for p in s] == ["", "01", "02", "03"]


def test_front_matter_is_excluded_from_counted_scenes(book: Project):
    assert [p.name for p in book.counted_scenes()] == ["01-a.md", "02-b.md", "01-c.md"]
    assert len(book.list_scenes()) == 4


def test_unit_setting_roundtrip(proj: Project):
    assert proj.unit == "scene"
    proj.update_manuscript_settings(unit="chapter")
    assert Project.open(proj.root).unit == "chapter"
    assert "[manuscript]" in (proj.root / "project.toml").read_text()
    with pytest.raises(ValueError):
        proj.update_manuscript_settings(unit="act")


# -- part operations ---------------------------------------------------------


def test_new_part_gets_next_prefix_and_part_file(book: Project):
    part = book.new_part("The Long Dark")
    assert part.name == "03-the-long-dark"
    assert book.part_title(part) == "The Long Dark"
    assert book.list_parts()[-1] == part
    with pytest.raises(ValueError):
        book.new_part("  ")


def test_rename_part_changes_title_not_folder(book: Project):
    part = book.list_parts()[1]
    (part / "_part.md").write_text("# Old\n\nMy notes.\n")
    book.rename_part(part, "Part I: Recall")
    assert book.part_title(part) == "Part I: Recall"
    assert book.part_notes(part) == "My notes."
    assert part.is_dir() and (part / "01-a.md").is_file()


def test_move_part_swaps_prefixes_and_carries_sidecars(book: Project):
    one, two = book.list_parts()[1], book.list_parts()[2]
    a = one / "01-a.md"
    c = two / "01-c.md"
    drafts.add_original(book.root, a, "aaaaaa", "from a")
    drafts.add_original(book.root, c, "cccccc", "from c")
    new_one = book.move_part(one, +1)
    assert new_one.name == "02-the-recall"
    assert [p.name for p in book.list_parts()] == [
        "00-front-matter", "01-ghost-frequency", "02-the-recall"]
    assert drafts.load_originals(book.root, new_one / "01-a.md") == {"aaaaaa": "from a"}
    assert drafts.load_originals(
        book.root, book.root / "manuscript/01-ghost-frequency/01-c.md") == {"cccccc": "from c"}
    assert sorted(p.name for p in (book.root / ".drafts").iterdir()) == [
        "manuscript__01-ghost-frequency__01-c.md.json",
        "manuscript__02-the-recall__01-a.md.json"]
    assert book.move_part(book.list_parts()[-1], +1) is None   # at the edge
    assert book.move_part(book.list_parts()[0], -1) is None


def test_delete_part_only_when_empty(book: Project):
    part = book.list_parts()[1]
    with pytest.raises(ValueError):
        book.delete_part(part)
    empty = book.new_part("Empty")
    book.delete_part(empty)
    assert not empty.exists()
    with pytest.raises(ValueError):
        book.delete_part(empty)             # no longer a part


# -- scene operations --------------------------------------------------------


def test_new_scene_path_is_per_part(book: Project):
    two = book.list_parts()[2]
    assert book.next_scene_path("Nine", two).name == "02-nine.md"
    assert book.next_scene_path("Top").parent == book.manuscript_dir
    assert book.next_scene_path("Top").name == "01-top.md"
    assert book.default_part_for_new(two / "01-c.md") == two
    assert book.default_part_for_new(None) == two          # last real part


def test_move_scene_to_part_goes_to_the_end_and_renumbers(book: Project):
    one, two = book.list_parts()[1], book.list_parts()[2]
    b = one / "02-b.md"
    drafts.add_original(book.root, b, "bbbbbb", "orig")
    new = book.move_scene_to_part(b, two)
    assert new == two / "02-b.md"
    assert not b.exists()
    assert drafts.load_originals(book.root, new) == {"bbbbbb": "orig"}
    assert drafts.load_originals(book.root, b) == {}
    assert [p.name for p in book.part_scenes(two)] == ["01-c.md", "02-b.md"]
    assert [p.name for p in book.part_scenes(one)] == ["01-a.md"]


def test_leaving_a_part_leaves_a_gap_and_only_the_destination_is_renumbered(book: Project):
    one, two = book.list_parts()[1], book.list_parts()[2]
    book.move_scene_to_part(one / "01-a.md", two)
    assert [p.name for p in book.part_scenes(one)] == ["02-b.md"]      # a gap, like after a delete
    assert book.last_renames == {one / "01-a.md": two / "02-a.md"}     # nothing else renamed


def test_place_scene_at_index_keeps_contiguous_prefixes(book: Project):
    one, two = book.list_parts()[1], book.list_parts()[2]
    c = two / "01-c.md"
    new = book.place_scene(c, one, 0)
    assert [p.name for p in book.part_scenes(one)] == ["01-c.md", "02-a.md", "03-b.md"]
    assert new == one / "01-c.md"
    # reorder inside one part: drag B to the front
    b = one / "03-b.md"
    book.place_scene(b, one, 0)
    assert [book.scene_title(p) for p in book.part_scenes(one)] == ["B", "C", "A"]
    assert [p.name for p in book.part_scenes(one)] == ["01-b.md", "02-c.md", "03-a.md"]


def test_place_scene_clamps_index_and_rejects_non_scenes(book: Project):
    one = book.list_parts()[1]
    a = one / "01-a.md"
    book.place_scene(a, one, 99)
    assert [book.scene_title(p) for p in book.part_scenes(one)] == ["B", "A"]
    with pytest.raises(ValueError):
        book.place_scene(one / "_part.md", one)
    with pytest.raises(ValueError):
        book.place_scene(a.parent / "02-a.md", book.root / "entities")


def test_move_scene_up_down_stays_inside_the_part(book: Project):
    one = book.list_parts()[1]
    a, b = one / "01-a.md", one / "02-b.md"
    assert book.move_scene(a, -1) is None             # first of its part
    assert book.move_scene(b, +1) is None             # last of its part
    new = book.move_scene(a, +1)
    assert new.name == "02-a.md" and (one / "01-b.md").is_file()


def test_unparted_to_part_and_back(book: Project):
    m = book.manuscript_dir
    loose = _mk(m / "07-loose.md", "Loose")
    one = book.list_parts()[1]
    moved = book.move_scene_to_part(loose, one)
    assert moved.parent == one and moved.name == "03-loose.md"
    back = book.move_scene_to_part(moved, None)
    assert back.parent == m and book.part_of(back) is None


# -- unplaced ----------------------------------------------------------------


def test_unplaced_scenes_are_outside_the_book_but_indexed(book: Project):
    one = book.list_parts()[1]
    moved = book.unplace_scene(one / "02-b.md")
    assert moved.parent == book.unplaced_dir
    assert book.list_unplaced() == [moved]
    assert moved not in book.list_scenes() and moved not in book.counted_scenes()
    assert book.is_unplaced(moved) and book.is_scene_path(moved)
    assert book.scene_number(moved) == ""
    assert moved in book.all_markdown_files()
    # indexed for backlinks even though not in the book
    book.create_entity("Mara", "character")
    moved.write_text("# B\n\nMara waits.\n")
    idx = Index(book.root / ".chisel" / "index.sqlite")
    idx.rebuild(book)
    ent = book.load_entities()[0]
    assert [b.source for b in idx.backlinks(ent)] == [
        "manuscript/_unplaced/01-b.md"]
    idx.close()
    back = book.move_scene_to_part(moved, one)
    assert back.parent == one and book.list_unplaced() == []


# -- trash -------------------------------------------------------------------


def test_delete_moves_to_trash_with_sidecar_and_restores_to_the_part(book: Project):
    one = book.list_parts()[1]
    a = one / "01-a.md"
    drafts.add_original(book.root, a, "aaaaaa", "orig")
    trashed = book.delete_scene(a)
    assert not a.exists() and trashed.parent == book.root / ".trash"
    assert trashed.name.endswith("-manuscript__01-the-recall__01-a.md")
    assert (book.root / ".drafts").exists() is False or not list((book.root / ".drafts").iterdir())
    items = book.list_trash()
    assert len(items) == 1 and items[0].original == "manuscript/01-the-recall/01-a.md"
    assert items[0].title == "A"
    restored = book.restore_scene(items[0].name)
    assert restored == one / "03-a.md"                # end of its part
    assert drafts.load_originals(book.root, restored) == {"aaaaaa": "orig"}
    assert book.list_trash() == [] and not (book.root / ".trash").exists()


def test_restore_goes_to_unplaced_when_the_part_is_gone(book: Project):
    two = book.list_parts()[2]
    book.delete_scene(two / "01-c.md")
    book.delete_part(two)
    item = book.list_trash()[0]
    restored = book.restore_scene(item.name)
    assert restored.parent == book.unplaced_dir and book.scene_title(restored) == "C"


def test_restore_unparted_and_unplaced_origins(book: Project):
    m = book.manuscript_dir
    loose = _mk(m / "07-loose.md", "Loose")
    un = book.unplace_scene(_mk(m / "08-draft.md", "Draft"))
    book.delete_scene(loose)
    book.delete_scene(un)
    by_title = {i.title: i for i in book.list_trash()}
    assert book.restore_scene(by_title["Loose"].name).parent == m
    assert book.restore_scene(by_title["Draft"].name).parent == book.unplaced_dir


def test_trash_names_never_collide_and_list_newest_first(book: Project):
    one = book.list_parts()[1]
    a = one / "01-a.md"
    first = book.delete_scene(a)
    _mk(a, "A again")
    second = book.delete_scene(a)
    assert first != second and first.exists() and second.exists()
    assert len(book.list_trash()) == 2


def test_delete_forever_and_empty_trash(book: Project):
    one = book.list_parts()[1]
    book.delete_scene(one / "01-a.md")
    drafts.add_original(book.root, one / "02-b.md", "bbbbbb", "x")
    book.delete_scene(one / "02-b.md")
    first, second = book.list_trash()
    book.delete_forever(first.name)
    assert [i.name for i in book.list_trash()] == [second.name]
    assert book.empty_trash() == 1
    assert not (book.root / ".trash").exists()
    with pytest.raises(FileNotFoundError):
        book.restore_scene("nope.md")


def test_trash_is_not_gitignored(proj: Project):
    gi = (proj.root / ".gitignore").read_text()
    assert ".trash" not in gi and "_unplaced" not in gi and ".drafts" not in gi


# -- sidecars ----------------------------------------------------------------


def test_sidecar_keys_are_project_relative(book: Project):
    one = book.list_parts()[1]
    assert drafts.sidecar_path(book.root, one / "01-a.md").name == \
        "manuscript__01-the-recall__01-a.md.json"
    # the same filename in two parts no longer collides
    drafts.add_original(book.root, one / "01-a.md", "aaaaaa", "one")
    other = _mk(book.list_parts()[2] / "01-a.md", "Other A")
    drafts.add_original(book.root, other, "zzzzzz", "two")
    assert drafts.load_originals(book.root, one / "01-a.md") == {"aaaaaa": "one"}
    assert drafts.load_originals(book.root, other) == {"zzzzzz": "two"}


def test_old_sidecars_migrate_on_open(tmp_path: Path):
    p = Project.create(tmp_path / "n", "N")
    scene = p.manuscript_dir / "01-opening.md"
    old = p.root / ".drafts" / "01-opening.md.json"
    old.parent.mkdir()
    old.write_text(json.dumps({"abcdef": "was this"}))
    orphan = p.root / ".drafts" / "99-gone.md.json"        # scene missing: left alone
    orphan.write_text(json.dumps({"qqqqqq": "x"}))
    reopened = Project.open(p.root)
    assert not old.exists()
    assert drafts.load_originals(reopened.root, scene) == {"abcdef": "was this"}
    assert orphan.exists()
    Project.open(p.root)                                  # idempotent
    assert drafts.load_originals(reopened.root, scene) == {"abcdef": "was this"}
