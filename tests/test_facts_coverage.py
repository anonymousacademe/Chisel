"""The facts ledger covers the characters the scene is about (brief 03i). Fakes only."""

from chisel.ai import continuity as cont
from chisel.ai import relevance
from chisel.ai.budget import Budget
from chisel.core import summaries as sm
from chisel.core.continuity import canon_map
from tests.gui_helpers import make_project


def scene_path(project, n):
    return project.manuscript_dir / f"{n:03d}-s{n}.md"


def rel(n):
    return f"manuscript/{n:03d}-s{n}.md"


def cast_book(tmp_path, names, facts_each=3, scenes=12):
    """A project with characters *names*; every earlier scene lists them all and states *facts_each* facts about each."""
    project = make_project(tmp_path / "p")
    for e in names:
        project.create_entity(e, "character")
    for f in project.list_scenes():
        f.unlink()
    for n in range(1, scenes + 2):                       # the last one is the scene being checked: no summary
        path = scene_path(project, n)
        path.write_text(f"# Scene {n}\n\nSomething happens.\n", encoding="utf-8")
        if n > scenes:
            continue
        facts = tuple(sm.Fact(f"{name} fact {n}.{k}", "Something happens") for name in names for k in range(facts_each))
        sm.save(project.root, path, sm.Summary(sm.current_hash(project, path), f"Event {n}.",
                                               tuple(sm.Character(c, "here") for c in names), facts))
    return project


def plan(project, history):
    entities = project.load_entities()
    return cont.plan_check_history("# T\n\nText.\n", entities, canon_map(entities), Budget(32_000), history)


def test_characters_are_chosen_by_how_often_the_scene_names_them(tmp_path):
    project = make_project(tmp_path / "p")
    ents = project.load_entities()
    text = "---\npov: Elias Vale\nplace: Lower Meridian\n---\n# T\n\nMara spoke. Mara left. Mara Vale came back. Elias said nothing.\n"
    ranked = relevance.by_mentions(text, ents)
    assert [(r.entity.name, n) for r, n in ranked] == [("Mara Vale", 3), ("Elias Vale", 2), ("Lower Meridian", 1)]
    assert relevance.by_mentions("# T\n\nNobody here.\n", ents) == []
    tie = relevance.by_mentions("# T\n\nElias nodded. Mara nodded.\n", ents)
    assert [r.entity.name for r, _ in tie] == ["Elias Vale", "Mara Vale"]          # equal counts keep the existing ranking


def test_the_p03_case_a_character_outside_the_top_three_is_covered_with_eight(tmp_path):
    names = [f"Person{i}" for i in range(1, 8)] + ["Luzhin"]
    project = cast_book(tmp_path, names, facts_each=1)
    prose = " ".join(f"Person{i} spoke. " * (10 - i) for i in range(1, 8)) + "Luzhin bowed."      # Luzhin: mentioned once
    scene = f"# Visit\n\n{prose}\n"
    wide = cont.history_for(project, rel(13), scene, project.load_entities(), mode="facts")
    covered = [n for n, _ in wide.facts]
    assert covered[0] == "Person1" and "Luzhin" in covered and len(covered) == 8
    narrow = cont.history_for(project, rel(13), scene, project.load_entities(), mode="facts", max_entities=3)
    assert "Luzhin" not in [n for n, _ in narrow.facts] and len(narrow.facts) == 3
    assert cont.HISTORY_ENTITIES == 8 and cont.EARLIER_ENTITIES == 3
    _, _, report, text = plan(project, wide)
    assert "Luzhin fact 1.0" in text and "Luzhin" in next(s for s in report.sections if s.name.startswith("Established")).name


def test_the_total_cap_is_shared_and_named_in_the_report(tmp_path):
    names = [f"Person{i}" for i in range(1, 9)]
    project = cast_book(tmp_path, names, facts_each=5, scenes=12)            # 60 facts each, 480 in all
    scene = "# T\n\n" + " ".join(f"{n} spoke." for n in names) + "\n"
    h = cont.history_for(project, rel(13), scene, project.load_entities(), mode="facts")
    counts = [len(f.items) for _, f in h.facts]
    assert sum(counts) == cont.HISTORY_FACTS_TOTAL == 160 and counts == [20] * 8      # an equal share
    assert all(f.omitted == f.total - 20 and f.limit == 20 and f.total == 480 for _, f in h.facts)    # every scene lists all eight
    assert all(f.items[0].text.endswith("1.0") for _, f in h.facts)                    # first appearances kept
    _, _, report, text = plan(project, h)
    row = next(s for s in report.sections if s.name.startswith("Established facts"))
    notes = [d for d in row.items_dropped if "over the limit of 20 for them" in d]
    assert len(notes) == 8 and notes[0].startswith("Person1: 460 facts from Scene ")
    small = cont.history_for(project, rel(13), scene, project.load_entities(), mode="facts", max_facts=40)
    assert sum(len(f.items) for _, f in small.facts) == 40


def test_the_shares_give_what_a_character_does_not_need_to_the_others():
    assert cont._shares([10, 10, 10], 160) == [10, 10, 10]
    q = cont._shares([60, 5, 60, 60], 100)
    assert q[1] == 5 and sum(q) == 100 and q[0] >= q[2] >= q[3] and q[0] - q[3] <= 1      # the rest to the most mentioned first
    assert cont._shares([60, 60, 60], 2) == [1, 1, 0]
    assert cont._shares([], 10) == []
    assert cont._shares([0, 4], 3) == [0, 3]


def test_earlier_scenes_stay_at_three_characters_and_both_uses_the_same_top_three(tmp_path):
    names = [f"Person{i}" for i in range(1, 7)]
    project = cast_book(tmp_path, names, facts_each=1, scenes=4)
    scene = "# T\n\n" + " ".join(f"{n} spoke. " * (8 - i) for i, n in enumerate(names)) + "\n"
    ents = project.load_entities()
    both = cont.history_for(project, rel(5), scene, ents, mode="both")
    assert [n for n, _ in both.earlier] == ["Person1", "Person2", "Person3"]
    assert [n for n, _ in both.facts][:3] == ["Person1", "Person2", "Person3"] and len(both.facts) == 6
    default = cont.history_for(project, rel(5), scene, ents)
    assert [n for n, _ in default.earlier] == ["Person1", "Person2", "Person3"] and default.facts == ()
    assert cont.HISTORY_MODE == "summaries"


def test_the_ledger_still_never_looks_ahead_with_many_characters(tmp_path):
    names = [f"Person{i}" for i in range(1, 5)]
    project = cast_book(tmp_path, names, facts_each=1, scenes=6)
    scene = "# T\n\n" + " ".join(f"{n} spoke." for n in names) + "\n"
    h = cont.history_for(project, rel(3), scene, project.load_entities(), mode="facts")
    texts = [i.text for _, f in h.facts for i in f.items]
    assert texts and all(int(t.rsplit(" ", 1)[1].split(".")[0]) < 3 for t in texts)


def test_a_project_without_summaries_is_untouched(tmp_path):
    project = make_project(tmp_path / "q")
    for mode in ("summaries", "facts", "both"):
        assert cont.history_for(project, "manuscript/01-arrival.md", "# T\n\nMara spoke.\n", project.load_entities(), mode=mode) is None
