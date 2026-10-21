"""Summaries: storage, hashes, status, verification, rollups, and travelling with the scene."""

import json

from chisel.core import drafts, scenemeta
from chisel.core import summaries as sm
from chisel.core.entities import Entity
from tests.gui_helpers import make_book, make_project


def summary_for(project, scene, text="Things happened.", **kw):
    s = sm.Summary(source_hash=sm.current_hash(project, scene), summary=text, **kw)
    sm.save(project.root, scene, s)
    return s


def rel(project, path):
    return path.relative_to(project.root).as_posix()


# -- storage ----------------------------------------------------------------------------


def test_round_trip_and_plain_file(tmp_path):
    project = make_project(tmp_path / "p")
    scene = project.list_scenes()[0]
    s = sm.Summary("abc", "Mara arrived.", (sm.Character("Mara", "at the clock"),),
                   (sm.Fact("It rained.", "The rain had not stopped"),), ("Who is Elias?",),
                   "m/x", "2026-01-01T00:00:00", 0.02, True, False)
    sm.save(project.root, scene, s)
    path = project.root / ".summaries" / "manuscript__01-arrival.md.json"
    assert path == sm.path_for(project.root, scene)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["v"] == 1 and set(data) == {"v", "source_hash", "summary", "characters", "facts",
                                           "threads", "model", "created", "cost",
                                           "author_edited", "locked"}
    assert sm.load(project.root, scene) == s
    assert b"\r" not in path.read_bytes()
    assert not list(path.parent.glob("*.tmp"))
    sm.delete(project.root, scene)
    assert sm.load(project.root, scene) is None and not (project.root / ".summaries").exists()


def test_unreadable_or_empty_file_is_no_summary(tmp_path):
    project = make_project(tmp_path / "p")
    scene = project.list_scenes()[0]
    path = sm.path_for(project.root, scene)
    path.parent.mkdir()
    path.write_text("{ not json", encoding="utf-8")
    assert sm.load(project.root, scene) is None
    path.write_text('{"v": 1, "summary": ""}', encoding="utf-8")
    assert sm.load(project.root, scene) is None
    assert sm.status(project, scene) == "missing"


# -- hash and status --------------------------------------------------------------------


def test_hash_ignores_details_and_pending_drafts():
    prose = "# Rain\n\nIt rained all day.\n"
    base = sm.hash_of(prose)
    assert sm.hash_of(scenemeta.set_details(prose, status="draft", pov="Mara")) == base
    assert sm.hash_of(prose.replace("day.", "day.<!--ai-->An AI sentence.<!--/ai-->")) == base
    assert sm.hash_of(prose.replace("\n", "\r\n")) == base
    assert sm.hash_of(prose.replace("rained", "poured")) != base


def test_status_missing_fresh_stale_locked(tmp_path):
    project = make_project(tmp_path / "p")
    a, b = project.list_scenes()
    assert sm.status(project, a) == "missing"
    s = summary_for(project, a)
    assert sm.status(project, a) == "fresh" and not sm.changed_since(project, a)
    a.write_text(a.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8")
    assert sm.status(project, a) == "stale" and sm.changed_since(project, a)
    # an author-edited summary whose scene changed is never offered for regeneration
    sm.save(project.root, a, sm.Summary(**{**s.__dict__, "author_edited": True}))
    assert sm.status(project, a) == "locked" and sm.changed_since(project, a)
    # edited but the scene did not change: it is simply current
    summary_for(project, b, author_edited=True)
    assert sm.status(project, b) == "fresh"
    # locked stays locked even when the scene did not change
    summary_for(project, b, locked=True)
    assert sm.status(project, b) == "locked"


def test_pending_draft_does_not_make_a_summary_stale(tmp_path):
    project = make_project(tmp_path / "p")
    scene = project.list_scenes()[1]
    summary_for(project, scene)
    text = scene.read_text(encoding="utf-8")
    scene.write_text(text + "<!--ai-->More AI.<!--/ai-->\n", encoding="utf-8")
    assert sm.status(project, scene) == "fresh"


def test_coverage_in_reading_order_without_front_matter(tmp_path):
    project = make_book(tmp_path / "p")
    scenes = project.counted_scenes()
    assert [p.name for p in scenes] == ["01-rain.md", "02-capsule.md", "01-signal.md"]
    summary_for(project, scenes[0])
    summary_for(project, scenes[1])
    scenes[1].write_text(scenes[1].read_text(encoding="utf-8") + "x\n", encoding="utf-8")
    cov = sm.coverage(project)
    assert cov.total == 3
    assert cov.counts == {"missing": 1, "fresh": 1, "stale": 1, "locked": 0}
    assert cov.ids["missing"] == [rel(project, scenes[2])]
    assert cov.percent == 67
    assert sm.coverage(make_project(tmp_path / "q")).percent == 0


# -- verify ----------------------------------------------------------------------------


SCENE = ("# Arrival\n\nMara stepped off the tram into Lower Meridian. The rain had not\n"
         "stopped for three days. Elias was waiting under the clock.\n")


def test_verify_drops_an_invented_quote_and_an_absent_name():
    s = sm.Summary("h", "Mara arrived.",
                   (sm.Character("Mara", "at the tram"), sm.Character("Rook", "somewhere")),
                   (sm.Fact("It rained.", "The rain had not stopped for three days"),   # re-wrapped: ok
                    sm.Fact("She had a gun.", "She drew a pistol from her coat"),         # invented
                    sm.Fact("Exact.", "Elias was waiting under the clock."),
                    sm.Fact("No quote.", ""),
                    sm.Fact("Too short.", "Mara")),
                   ("open",))
    clean, dropped = sm.verify(s, SCENE)
    assert [f.text for f in clean.facts] == ["It rained.", "Exact."]
    assert [c.name for c in clean.characters] == ["Mara"]
    assert [(d.kind, d.text) for d in dropped] == [
        ("fact", "She had a gun."), ("fact", "No quote."), ("fact", "Too short."), ("character", "Rook")]
    assert clean.summary == "Mara arrived." and clean.threads == ("open",)


def test_verify_ignores_details_and_pending_text():
    text = scenemeta.set_details(SCENE, pov="Rook") + "<!--ai-->Rook drew a pistol from her coat.<!--/ai-->\n"
    s = sm.Summary("h", "x", (sm.Character("Rook", ""),),
                   (sm.Fact("Armed.", "Rook drew a pistol from her coat."),))
    clean, dropped = sm.verify(s, text)
    assert not clean.facts and not clean.characters and len(dropped) == 2
    # a name must be a whole word, case-insensitively
    _, gone = sm.verify(sm.Summary("h", "x", (sm.Character("Mar", ""),)), SCENE)
    assert [d.text for d in gone] == ["Mar"]
    clean, _ = sm.verify(sm.Summary("h", "x", (sm.Character("lower meridian", ""),)), SCENE)
    assert len(clean.characters) == 1


# -- part summaries ----------------------------------------------------------------------


def test_part_summary_staleness(tmp_path):
    project = make_book(tmp_path / "p")
    part = project.list_parts()[1]
    rain, capsule = project.part_scenes(part)
    assert sm.part_status(project, part) == "missing"
    summary_for(project, rain, "Rain fell.")
    sm.save_part(project.root, part, sm.PartSummary("Part one.", inputs=sm.part_inputs(project, part)))
    assert sm.part_status(project, part) == "fresh"
    assert sm.load_part(project.root, part).inputs == (("01-rain.md", sm.part_inputs(project, part)[0][1]),)
    summary_for(project, capsule, "A capsule.")                       # a scene summary arrived
    assert sm.part_status(project, part) == "stale"
    sm.save_part(project.root, part, sm.PartSummary("Part one.", inputs=sm.part_inputs(project, part)))
    assert sm.part_status(project, part) == "fresh"
    summary_for(project, rain, "Rain fell hard.")                     # a scene summary was edited
    assert sm.part_status(project, part) == "stale"
    old = sm.load_part(project.root, part)
    sm.save_part(project.root, part, sm.PartSummary(**{**old.__dict__, "locked": True}))
    assert sm.part_status(project, part) == "locked"


# -- story so far -------------------------------------------------------------------------


def book_with_summaries(tmp_path):
    project = make_book(tmp_path / "p")
    for p in project.counted_scenes():
        summary_for(project, p, f"{p.stem} happened.",
                    characters=(sm.Character("Mara", "in the city"),), threads=("a thread",))
    return project


def test_story_so_far_reading_order_blocks_and_missing(tmp_path):
    project = book_with_summaries(tmp_path)
    rain, capsule, signal = project.counted_scenes()
    part2 = project.list_parts()[2]
    out = sm.story_so_far(project, rel(project, signal))
    assert out.mode == "reading-order" and "No story times" in out.sentence
    # the first part is a block (its scene summaries joined), newest last
    assert [b.name for b in out.blocks] == ["The Recall"] and out.blocks[0].kind == "part"
    assert "Rain: 01-rain happened." in out.text and "Capsule: 02-capsule happened." in out.text
    assert "At the end: Mara - in the city" in out.text and "Open: a thread" in out.text
    assert out.text.index("Rain:") < out.text.index("Capsule:")
    assert out.missing == () and out.dropped == ()
    # a part summary replaces its scene summaries; the current part gives scene blocks
    sm.save_part(project.root, project.list_parts()[1], sm.PartSummary("The recall, in brief."))
    out = sm.story_so_far(project, rel(project, signal))
    assert out.text == "The Recall: The recall, in brief."
    out = sm.story_so_far(project, rel(project, capsule))
    assert [(b.kind, b.name) for b in out.blocks] == [("scene", "Rain")]
    assert sm.story_so_far(project, rel(project, rain)).blocks == ()
    # a scene with no summary is named, not skipped silently
    sm.delete(project.root, rain)
    assert sm.story_so_far(project, rel(project, capsule)).missing == ("Rain",)
    assert part2.name == "02-ghost"


def test_story_so_far_cap_drops_oldest_first_by_name(tmp_path):
    project = make_project(tmp_path / "p")
    scenes = []
    for n in range(6):
        path = project.manuscript_dir / f"{n + 3:02d}-s{n}.md"
        path.write_text(f"# Scene {n}\n\nText {n}.\n", encoding="utf-8")
        summary_for(project, path, "word " * 40)
        scenes.append(path)
    last = rel(project, project.list_scenes()[-1])
    full = sm.story_so_far(project, last)
    assert len(full.blocks) == 5 and full.dropped == ()
    cap = sm._tokens(full.blocks[-1].text) * 2 + 1          # room for the two newest only
    out = sm.story_so_far(project, last, cap)
    assert [b.name for b in out.blocks] == [full.blocks[-2].name, full.blocks[-1].name]
    assert out.dropped == tuple(b.name for b in full.blocks[:3])
    assert sm.story_so_far(project, last, 1).blocks == () and len(sm.story_so_far(project, last, 1).dropped) == 5


def test_story_so_far_uses_story_time_when_the_project_has_it(tmp_path):
    project = make_project(tmp_path / "p")
    first, second = project.list_scenes()
    third = project.manuscript_dir / "03-flashback.md"
    third.write_text("# Flashback\n\nLong ago.\n", encoding="utf-8")
    first.write_text(scenemeta.set_details(first.read_text(encoding="utf-8"), when="2020"), encoding="utf-8")
    second.write_text(scenemeta.set_details(second.read_text(encoding="utf-8"), when="2021"), encoding="utf-8")
    third.write_text(scenemeta.set_details(third.read_text(encoding="utf-8"), when="1990"), encoding="utf-8")
    for p in (first, second, third):
        summary_for(project, p, f"{p.stem} summary.")
    out = sm.story_so_far(project, rel(project, second))
    assert out.mode == "chronological" and "story time" in out.sentence
    assert [b.name for b in out.blocks] == ["Arrival", "Flashback"]      # reading order kept; later events excluded
    out = sm.story_so_far(project, rel(project, third))
    assert out.blocks == ()                                              # nothing happened before 1990
    # a Parked scene is not in the book: nothing, and it says why
    parked = project.place_scene(third, unplaced=True)
    out = sm.story_so_far(project, rel(project, parked))
    assert out.blocks == () and "not in the book" in out.sentence


# -- entity history ------------------------------------------------------------------------


def test_entity_history_first_appearance_then_newest(tmp_path):
    project = make_project(tmp_path / "p")
    mara = Entity(name="Mara Vale", aliases=["Mara"])
    paths = []
    for n in range(6):
        path = project.manuscript_dir / f"{n + 3:02d}-s{n}.md"
        who = "Mara walked." if n in (0, 2, 3, 4) else "Nobody came."
        path.write_text(f"# Scene {n}\n\n{who}\n", encoding="utf-8")
        summary_for(project, path, f"Summary {n}.")
        paths.append(path)
    for p in project.list_scenes()[:2]:
        summary_for(project, p, "Early.")
    target = rel(project, project.list_scenes()[-1])
    out = sm.entity_history(project, mara, target, limit=3)
    # Arrival and The Archive name Mara, so do s0, s2, s3, s4 (s5 is the target)
    titles = [i.title for i in out.items]
    assert titles == ["Arrival", "Scene 3", "Scene 4"] and [i.rank for i in out.items] == [0, 2, 1]
    assert out.omitted == ("The Archive", "Scene 0", "Scene 2")
    assert sm.entity_history(project, mara, target, limit=10).omitted == ()
    # the first appearance has no summary: named as missing, the others still come
    sm.delete(project.root, project.list_scenes()[0])
    out = sm.entity_history(project, mara, target, limit=3)
    assert out.missing == ("Arrival",) and [i.title for i in out.items] == ["Scene 3", "Scene 4"]
    # nothing before the first scene
    assert sm.entity_history(project, mara, rel(project, project.list_scenes()[0])).items == ()


def test_entity_history_counts_pov_and_links(tmp_path):
    project = make_project(tmp_path / "p")
    first, second = project.list_scenes()
    elias = Entity(name="Elias Vale", aliases=["Elias"])
    second.write_text(scenemeta.set_details("# Two\n\nSomeone [[Elias Vale]] knew.\n", pov="Mara"),
                      encoding="utf-8")
    third = project.manuscript_dir / "03-x.md"
    third.write_text(scenemeta.set_details("# Three\n\nNothing.\n", pov="Elias"), encoding="utf-8")
    for p in (first, second, third):
        summary_for(project, p, "s")
    ids = [i.title for i in sm.entity_history(project, elias, "manuscript/04-z.md").items]
    assert ids == []                                                  # an unknown target: nothing
    fourth = project.manuscript_dir / "04-z.md"
    fourth.write_text("# Four\n", encoding="utf-8")
    assert [i.title for i in sm.entity_history(project, elias, "manuscript/04-z.md").items] == \
        ["Arrival", "Two", "Three"]


# -- the summary travels with its scene ------------------------------------------------------


def test_summaries_travel_with_the_scene(tmp_path):
    project = make_book(tmp_path / "p")
    rain = project.manuscript_dir / "01-the-recall" / "01-rain.md"
    s = summary_for(project, rain, "Rain fell.")
    # reorder inside the part (a swap renames both files)
    new = project.move_scene(rain, 1)
    assert sm.load(project.root, rain) is None and sm.load(project.root, new) == s
    assert sm.status(project, new) == "fresh"
    # swap parts (every scene inside changes folder)
    swapped = project.move_part(project.list_parts()[1], -1)
    assert swapped is not None
    here = [p for p in project.list_scenes() if sm.load(project.root, p)]
    assert len(here) == 1 and sm.load(project.root, here[0]) == s
    assert [p.name for p in (project.root / ".summaries").glob(".mv*")] == []
    # trash and restore
    gone = project.delete_scene(here[0])
    assert gone.with_name(gone.name + ".summaries.json").is_file()
    assert not (project.root / ".summaries").exists()
    back = project.restore_scene(gone.name)
    assert sm.load(project.root, back) == s
    # delete forever takes it too
    again = project.delete_scene(back)
    project.delete_forever(again.name)
    assert not list(project.root.glob(".trash/*"))
    assert not (project.root / ".summaries").exists()


def test_place_scene_into_another_part_carries_the_summary(tmp_path):
    project = make_book(tmp_path / "p")
    rain = project.manuscript_dir / "01-the-recall" / "01-rain.md"
    s = summary_for(project, rain, "Rain fell.")
    moved = project.place_scene(rain, project.list_parts()[2])
    assert sm.load(project.root, rain) is None and sm.load(project.root, moved) == s
    parked = project.unplace_scene(moved)
    assert sm.load(project.root, parked) == s


def test_part_summary_follows_a_part_move_and_goes_with_an_empty_part(tmp_path):
    project = make_book(tmp_path / "p")
    first, second = project.list_parts()[1:3]
    scene = project.part_scenes(first)[0]
    summary_for(project, scene, "Rain fell.")
    sm.save_part(project.root, first, sm.PartSummary("First.", inputs=sm.part_inputs(project, first)))
    sm.save_part(project.root, second, sm.PartSummary("Second."))
    project.move_part(first, 1)
    parts = project.list_parts()
    assert sm.load_part(project.root, parts[1]).summary == "Second."
    assert sm.load_part(project.root, parts[2]).summary == "First."
    assert sm.part_status(project, parts[2]) == "fresh"               # moving the part is not a change
    empty = project.new_part("Empty")
    sm.save_part(project.root, empty, sm.PartSummary("Nothing."))
    project.delete_part(empty)
    assert not sm.part_path_for(project.root, empty).exists()


def test_leftover_staged_summary_is_recovered(tmp_path):
    from chisel.core import structure
    project = make_project(tmp_path / "p")
    scene = project.list_scenes()[0]
    summary_for(project, scene)
    path = sm.path_for(project.root, scene)
    path.rename(path.with_name(f".mv0-{path.name}"))
    structure.recover_staged(project.root)
    assert sm.load(project.root, scene) is not None


def test_drafts_originals_are_used_for_the_hash():
    plain = "# T\n\nShe wept at the grave.\n"
    marked = "# T\n\n" + drafts.wrap("She sang at the grave.", "d1abcd") + "\n"
    assert sm.hash_of(marked, {"d1abcd": "She wept at the grave."}) == sm.hash_of(plain)
    assert sm.hash_of(marked) != sm.hash_of(plain)         # no original known: the draft text is simply gone
