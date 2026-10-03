"""Comments: anchored author notes in a sidecar (Wave 3.2)."""

import json

import pytest

from chisel.core import comments as cm
from chisel.core import scenemeta
from tests.gui_helpers import make_book, make_project

PROSE = ("# Rain\n\nThe rain in the Hollow Market came down warm and tasted of copper. "
         "Rook sat at the far end of the counter, watching the koi turn.\n\n"
         "The caller ID was a row of zeros, which meant police.\n")


def fixture(tmp_path):
    project = make_project(tmp_path / "p")
    scene = project.list_scenes()[0]
    scene.write_text(PROSE, encoding="utf-8")
    return project, scene


def span(text, needle):
    i = text.index(needle)
    return i, i + len(needle)


def test_add_stores_a_plain_sidecar_and_never_touches_the_scene(tmp_path):
    project, scene = fixture(tmp_path)
    s, e = span(PROSE, "came down warm")
    c = cm.add(project.root, scene, PROSE, s, e, "  too many adjectives?  ")
    assert scene.read_text() == PROSE                      # nothing inline
    path = project.root / ".comments" / "manuscript__01-arrival.md.json"
    (row,) = json.loads(path.read_text())
    assert row["id"] == c.id and row["body"] == "too many adjectives?"
    assert row["quote"] == "came down warm" and row["resolved"] is False
    assert row["prefix"].endswith("Hollow Market ") and row["suffix"].startswith(" and tasted")
    assert set(row) == {"id", "quote", "prefix", "suffix", "body", "created", "resolved"}


def test_validation(tmp_path):
    project, scene = fixture(tmp_path)
    with pytest.raises(ValueError):
        cm.add(project.root, scene, PROSE, 5, 5, "x")
    with pytest.raises(ValueError):
        cm.add(project.root, scene, PROSE, 6, 8, "   ")   # empty body
    with pytest.raises(ValueError):
        cm.anchor("x" * 3000, 0, 3000)                  # too long to quote
    with pytest.raises(LookupError):
        cm.resolve(project.root, scene, "nope")


def test_locate_follows_edits_before_and_inside(tmp_path):
    project, scene = fixture(tmp_path)
    s, e = span(PROSE, "watching the koi turn")
    c = cm.add(project.root, scene, PROSE, s, e, "good image")
    # text inserted before moves the passage
    moved = PROSE.replace("# Rain\n\n", "# Rain\n\nA new first paragraph, quite long indeed.\n\n")
    (p,) = cm.place(moved, [c])
    assert moved[p.start:p.end] == "watching the koi turn"
    # rewrapped lines still match
    wrapped = PROSE.replace("watching the koi", "watching\nthe  koi")
    (p,) = cm.place(wrapped, [c])
    assert wrapped[p.start:p.end] == "watching\nthe  koi turn"


def test_duplicate_quote_uses_context(tmp_path):
    project, scene = fixture(tmp_path)
    text = "# T\n\nShe waited. Then he left.\n\nHe waited. Then she left.\n"
    s = text.index("waited", text.index("He waited"))
    c = cm.add(project.root, scene, text, s, s + 6, "second one")
    (p,) = cm.place(text, [c])
    assert p.start == s
    shifted = text.replace("# T", "# Title")
    (p,) = cm.place(shifted, [c])
    assert p.start == shifted.index("waited", shifted.index("He waited"))


def test_fuzzy_reanchor_when_the_middle_is_edited(tmp_path):
    project, scene = fixture(tmp_path)
    s, e = span(PROSE, "Rook sat at the far end of the counter, watching the koi turn")
    c = cm.add(project.root, scene, PROSE, s, e, "slow")
    edited = PROSE.replace("far end of the counter, watching", "far end of the long steel counter, quietly watching")
    (p,) = cm.place(edited, [c])
    assert edited[p.start:p.end].startswith("Rook sat") and edited[p.start:p.end].endswith("koi turn")
    placed = cm.reanchor(project.root, scene, edited)
    assert placed[0].start == p.start
    (stored,) = cm.load(project.root, scene)
    assert stored.quote == edited[p.start:p.end]          # refreshed: next find is exact


def test_rewritten_passage_found_by_its_surroundings_else_detached_and_kept(tmp_path):
    project, scene = fixture(tmp_path)
    old = "Rook sat at the far end of the counter, watching the koi turn"
    c = cm.add(project.root, scene, PROSE, *span(PROSE, old), "cliche")
    rewritten = PROSE.replace(old, "Rook stared at nothing")
    # rewritten between the same surroundings: found by that context, not detached
    (p,) = cm.place(rewritten, [c])
    assert rewritten[p.start:p.end] == "Rook stared at nothing"
    # the whole sentence is removed: detached, not dropped
    gone = PROSE.replace(old + ".", "").replace(" The caller", "The caller")
    (p,) = cm.reanchor(project.root, scene, gone)
    assert p.detached and p.start is None
    assert [x.id for x in cm.load(project.root, scene)] == [c.id]     # still on disk, unchanged
    assert cm.load(project.root, scene)[0].quote == c.quote
    # undo: the text returns and the comment re-attaches
    (p,) = cm.reanchor(project.root, scene, PROSE)
    assert not p.detached


def test_detached_sort_first_then_by_position(tmp_path):
    project, scene = fixture(tmp_path)
    a = cm.add(project.root, scene, PROSE, *span(PROSE, "copper"), "late")
    b = cm.add(project.root, scene, PROSE, *span(PROSE, "Hollow Market"), "early")
    lost = cm.add(project.root, scene, PROSE, *span(PROSE, "row of zeros"), "lost")
    text = PROSE.replace("The caller ID was a row of zeros, which meant police.", "Gone.")
    assert [p.comment.id for p in cm.place(text, cm.load(project.root, scene))] == [lost.id, b.id, a.id]


def test_frontmatter_is_not_commentable_or_searched(tmp_path):
    project, scene = fixture(tmp_path)
    text = scenemeta.set_details(PROSE, status="draft")
    with pytest.raises(ValueError):
        cm.add(project.root, scene, text, 0, 5, "no")
    c = cm.add(project.root, scene, text, *span(text, "copper"), "ok")
    (p,) = cm.place(text, [c])
    assert text[p.start:p.end] == "copper"


def test_edit_resolve_delete(tmp_path):
    project, scene = fixture(tmp_path)
    c = cm.add(project.root, scene, PROSE, *span(PROSE, "copper"), "one")
    assert cm.edit(project.root, scene, c.id, "two").body == "two"
    assert cm.resolve(project.root, scene, c.id).resolved is True
    assert cm.open_count(project.root, scene) == 0
    assert cm.resolve(project.root, scene, c.id, False).resolved is False
    cm.delete(project.root, scene, c.id)
    assert cm.load(project.root, scene) == []
    assert not (project.root / ".comments").exists()      # no empty leftovers


def test_comments_travel_with_the_scene(tmp_path):
    project = make_book(tmp_path / "p")
    rain = project.manuscript_dir / "01-the-recall" / "01-rain.md"
    text = rain.read_text()
    c = cm.add(project.root, rain, text, 2, 6, "note")
    # reorder inside the part
    new = project.move_scene(rain, 1)
    assert cm.load(project.root, rain) == [] and [x.id for x in cm.load(project.root, new)] == [c.id]
    # swap parts (every scene inside changes folder)
    part = project.list_parts()[1]
    swapped = project.move_part(part, -1)
    assert swapped is not None
    here = [p for p in project.list_scenes() if cm.load(project.root, p)]
    assert len(here) == 1
    # trash and restore
    gone = project.delete_scene(here[0])
    assert (gone.with_name(gone.name + ".comments.json")).is_file()
    assert not (project.root / ".comments").exists()
    back = project.restore_scene(gone.name)
    assert [x.id for x in cm.load(project.root, back)] == [c.id]
    # delete forever takes them too
    again = project.delete_scene(back)
    project.delete_forever(again.name)
    assert not list(project.root.glob(".trash/*"))
    assert not (project.root / ".comments").exists() or not list((project.root / ".comments").glob("*.json"))
