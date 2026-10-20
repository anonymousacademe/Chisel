"""The facts ledger and the continuity addendum (brief 03g). Fakes only, no network.

A project without summaries must send exactly what it always sent (tests/test_summaries_context.py holds the recorded
reference); everything here is about what is ADDED when stored summaries exist."""

import json
from types import SimpleNamespace

import pytest

from chisel.ai import continuity as cont
from chisel.ai.budget import Budget
from chisel.core import summaries as sm
from chisel.core.continuity import canon_map
from tests.gui_helpers import make_project

SCENE = "# Now\n\nMara looked at the tower. Elias said nothing.\n"


def scene_path(project, n):
    return project.manuscript_dir / f"{n:03d}-s{n}.md"


def book(tmp_path, spec):
    """A project of scenes "Scene n" (n from 1); *spec* maps n to (facts, characters) of that scene's summary."""
    project = make_project(tmp_path / "p")
    for p in project.list_scenes():
        p.unlink()
    last = max(spec) if spec else 0
    for n in range(1, last + 2):
        path = scene_path(project, n)
        path.write_text(f"# Scene {n}\n\nMara met someone. Mark {n}.\n", encoding="utf-8")
        if n in spec:
            facts, chars = spec[n]
            sm.save(project.root, path, sm.Summary(sm.current_hash(project, path), f"Event {n}.",
                                                   tuple(sm.Character(c, "here") for c in chars),
                                                   tuple(sm.Fact(t, "Mara met someone") for t in facts)))
    return project


def rel(n):
    return f"manuscript/{n:03d}-s{n}.md"


def entity(project, name):
    return next(e for e in project.load_entities() if e.name == name)


# -- the ledger -----------------------------------------------------------------------------


def test_ledger_is_in_reading_order_dedupes_and_never_looks_ahead(tmp_path):
    project = book(tmp_path, {
        1: (["Mara has green eyes.", "The tower is old."], ["Mara Vale"]),
        2: (["Mara has green eyes.", "Mara lost her key."], ["Mara Vale"]),
        3: (["Mara is in Lower Meridian."], ["Mara Vale"]),
        4: (["Mara was shot."], ["Mara Vale"]),         # the scene being checked: never included
        5: (["Mara is dead."], ["Mara Vale"]),          # later: never included
    })
    facts = sm.entity_facts(project, entity(project, "Mara Vale"), rel(4))
    assert [(f.text, f.title) for f in facts.items] == [
        ("Mara has green eyes.", "Scene 1"), ("The tower is old.", "Scene 1"),
        ("Mara lost her key.", "Scene 2"), ("Mara is in Lower Meridian.", "Scene 3")]
    assert facts.items[0].count == 2 and facts.items[1].count == 1          # the earliest is kept, the repeat counted
    assert facts.items[0].scene_id == rel(1) and facts.total == 4 and facts.omitted == 0
    assert sm.entity_facts(project, entity(project, "Mara Vale"), rel(1)).items == ()      # nothing before the first scene


def test_a_fact_belongs_to_an_entity_by_listing_or_by_name_or_alias(tmp_path):
    project = book(tmp_path, {
        1: (["The tower is old."], ["Mara Vale"]),                     # Mara is listed; the text does not name her
        2: (["Mara kept a diary."], ["Elias Vale"]),                   # an alias ("Mara") in the text; she is not listed
        3: (["Elias owns a boat.", "The mara plant blooms."], ["Elias Vale"]),   # "mara" as a word still counts: whole-word match
        4: (["The marathon began."], ["Elias Vale"]),                  # not a whole word: no match
    })
    mara = sm.entity_facts(project, entity(project, "Mara Vale"), rel(5))
    assert [f.text for f in mara.items] == ["The tower is old.", "Mara kept a diary.", "The mara plant blooms."]
    elias = sm.entity_facts(project, entity(project, "Elias Vale"), rel(5))
    assert [f.text for f in elias.items] == ["Mara kept a diary.", "Elias owns a boat.", "The mara plant blooms.", "The marathon began."]
    assert sm.entity_facts(project, entity(project, "Lower Meridian"), rel(5)).items == ()


def test_the_cap_keeps_first_appearances_and_the_newest_and_counts_the_rest(tmp_path):
    spec = {n: ([f"Mara fact {n}.{k}" for k in range(5)], ["Mara Vale"]) for n in range(1, 31)}     # 150 facts
    project = book(tmp_path, spec)
    f = sm.entity_facts(project, entity(project, "Mara Vale"), rel(31))
    assert f.total == 150 and len(f.items) == sm.FACTS_PER_ENTITY == 60 and f.omitted == 90
    texts = [i.text for i in f.items]
    assert sm.FACTS_FIRST == 10
    assert texts[:sm.FACTS_FIRST] == [f"Mara fact {n}.{k}" for n in range(1, 3) for k in range(5)]     # first appearances
    assert texts[-1] == "Mara fact 30.4" and texts[sm.FACTS_FIRST] == "Mara fact 21.0"                   # the newest 50
    assert f.omitted_scenes[0] == "Scene 3" and f.omitted_scenes[-1] == "Scene 20" and len(f.omitted_scenes) == 18
    small = sm.entity_facts(project, entity(project, "Mara Vale"), rel(31), limit=10)
    assert len(small.items) == 10 and small.omitted == 140 and [i.text for i in small.items][0] == "Mara fact 1.0"


# -- the sections, the budget, the report ---------------------------------------------------


def history_of(project, scene_rel=None, text=SCENE, mode="facts"):
    scene_rel = scene_rel or rel(max(int(p.stem[:3]) for p in project.list_scenes()))
    return cont.history_for(project, scene_rel, text, project.load_entities(), mode=mode)


def plan(project, history, budget=Budget(32_000)):
    entities = project.load_entities()
    return cont.plan_check_history(SCENE, entities, canon_map(entities), budget, history)


def test_the_ledger_section_is_compact_priced_between_canon_and_story(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes.", "Mara lost her key."], ["Mara Vale"]),
                              2: (["Mara is in Lower Meridian."], ["Mara Vale"])})
    h = history_of(project, mode="both")
    _, _, report, text = plan(project, h)
    names = [s.name for s in report.sections]
    assert names[:2] == ["Instructions and question", "Entity canon"] and names[2].startswith("Established facts about Mara Vale")
    assert names[3] == "Story so far"
    assert text.index("ESTABLISHED FACTS ABOUT MARA VALE") < text.index("STORY SO FAR")
    assert "### Mara Vale\n- Mara has green eyes. (Scene 1)\n- Mara lost her key. (Scene 1)\n- Mara is in Lower Meridian. (Scene 2)" in text
    section = next(s for s in cont._history_sections(h) if s.name.startswith("Established"))
    assert section.priority == 1 and next(s for s in cont._history_sections(h) if s.name == "Story so far").priority == 2
    assert cont.HISTORY_ADDENDUM and "ESTABLISHED FACTS" in cont.HISTORY_ADDENDUM


def test_a_repeated_fact_says_how_often_it_was_stated(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes."], ["Mara Vale"]), 2: (["Mara has green eyes."], ["Mara Vale"])})
    _, _, _, text = plan(project, history_of(project))
    assert "- Mara has green eyes. (Scene 1; stated in 2 scenes)" in text


def test_a_tight_budget_drops_the_newest_facts_first_and_the_report_names_the_scenes(tmp_path):
    spec = {n: ([f"Mara fact {n} " + "x" * 200], ["Mara Vale"]) for n in range(1, 21)}
    project = book(tmp_path, spec)
    h = history_of(project)
    _, _, full, _ = plan(project, h)
    _, _, tight, text = plan(project, h, Budget(2_200, 1_000))
    row = next(s for s in tight.sections if s.name.startswith("Established facts"))
    assert row.items_dropped == tuple(f"Mara Vale: Scene {n}" for n in range(11, 21))      # the newest go, by scene title
    assert (row.items_sent, row.items_total) == (10, 20)
    assert "(Scene 1)" in text and "(Scene 10)" in text and "(Scene 20)" not in text      # first appearances survive
    assert not any(s.items_dropped for s in full.sections if s.name.startswith("Established"))


def test_the_per_entity_cap_is_named_in_the_report(tmp_path):
    spec = {n: ([f"Mara fact {n}.{k}" for k in range(5)], ["Mara Vale"]) for n in range(1, 31)}
    project = book(tmp_path, spec)
    _, _, report, _ = plan(project, history_of(project))
    row = next(s for s in report.sections if s.name.startswith("Established facts"))
    note = row.items_dropped[-1]
    assert note.startswith("Mara Vale: 90 facts from Scene 3, Scene 4") and "over the limit of 60 for them" in note
    _, creport, _ = cont.plan_canon_history(SCENE, project.load_entities(), Budget(32_000), history_of(project))
    crow = next(s for s in creport.sections if s.name.startswith("Established facts"))
    assert "over the limit of 60 for them" in crow.items_dropped[-1]


# -- the modes ------------------------------------------------------------------------------


def test_the_three_modes(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes."], ["Mara Vale"]), 2: (["Elias owns a boat."], ["Elias Vale"])})
    summaries, facts, both = (history_of(project, mode=m) for m in ("summaries", "facts", "both"))
    assert summaries.facts == () and summaries.story.blocks and summaries.earlier
    assert facts.story is None and facts.earlier == () and sorted(n for n, _ in facts.facts) == ["Elias Vale", "Mara Vale"]
    assert both.story.blocks and both.earlier and both.facts
    assert {n for n, _ in facts.facts} == {n for n, _ in both.facts} == {n for n, _ in summaries.earlier}
    assert history_of(project, mode=cont.HISTORY_MODE).facts == ()                    # the default is "summaries" for now
    assert cont.HISTORY_MODE == "summaries"
    with pytest.raises(ValueError):
        history_of(project, mode="everything")
    assert cont.history_for(make_project(tmp_path / "q"), "manuscript/01-arrival.md", SCENE, [], mode="both") is None


def test_the_facts_mode_sends_no_story_sections(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes."], ["Mara Vale"])})
    _, _, report, text = plan(project, history_of(project, mode="facts"))
    assert [s.name for s in report.sections][2].startswith("Established facts") and "STORY SO FAR" not in text
    assert "EARLIER SCENES" not in text


# -- the addendum ---------------------------------------------------------------------------


class Capture:
    def __init__(self):
        self.messages = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.messages = kw["messages"]
        usage = SimpleNamespace(cost=0.0, prompt_tokens=1, completion_tokens=1)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"contradictions": []})))],
                               usage=usage)


def test_the_addendum_is_sent_only_with_history_and_is_short(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes."], ["Mara Vale"])})
    entities = project.load_entities()
    canon = {"Mara Vale": "Tall."}
    plain, withh = Capture(), Capture()
    cont.check_scene(SCENE, entities, canon, "m/x", client=plain)
    assert plain.messages[0]["content"] == cont.SYSTEM_PROMPT                    # exactly today's instructions
    _, _, _, text = plan(project, history_of(project, mode="both"))
    cont.check_scene(SCENE, entities, canon, "m/x", client=withh, history=text)
    assert withh.messages[0]["content"] == cont.SYSTEM_PROMPT + cont.HISTORY_ADDENDUM
    for must in ("count as established canon", "earlier: ", "exact text", "do not flag a change", "When unsure, do not flag"):
        assert must in cont.HISTORY_ADDENDUM
    assert len(cont.HISTORY_ADDENDUM.split()) < 150
    assert withh.messages[1]["content"].startswith("ENTITY CANON:") and "ESTABLISHED FACTS ABOUT" in withh.messages[1]["content"]


def test_the_addendum_counts_in_the_budget_and_only_when_history_is_present(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes."], ["Mara Vale"])})
    base = plan(project, None)[2]
    empty = plan(project, cont.History())[2]
    with_h = plan(project, history_of(project, mode="both"))[2]
    tokens = lambda r: next(s.est_tokens for s in r.sections if s.name == "Instructions and question")
    assert tokens(base) == tokens(empty) < tokens(with_h)
    assert [s.name for s in base.sections] == [s.name for s in empty.sections]
    assert base.to_dict() == empty.to_dict()


def test_canon_proposal_instructions_are_left_alone(tmp_path):
    project = book(tmp_path, {1: (["Mara has green eyes."], ["Mara Vale"])})
    entities = project.load_entities()
    _, report, text = cont.plan_canon_history(SCENE, entities, Budget(32_000), history_of(project, mode="both"))
    base = cont.plan_canon_history(SCENE, entities, Budget(32_000), None)[1]
    tokens = lambda r: next(s.est_tokens for s in r.sections if s.name == "Instructions and question")
    assert tokens(report) == tokens(base) and "ESTABLISHED FACTS" in text
    cap = Capture()
    cont.propose_canon_updates(SCENE, entities, "m/x", client=cap, history=text)
    assert cap.messages[0]["content"] == cont.ACCUMULATION_SYSTEM_PROMPT


# -- a long book ----------------------------------------------------------------------------


def test_a_200_scene_book_stays_within_budget(tmp_path):
    spec = {n: ([f"Mara fact {n}.{k} about the long road." for k in range(3)], ["Mara Vale", "Elias Vale"]) for n in range(1, 201)}
    project = book(tmp_path, spec)
    h = history_of(project, scene_rel=rel(201), mode="both")
    entities = project.load_entities()
    budget = Budget(32_000)
    _, _, report, text = cont.plan_check_history(SCENE, entities, canon_map(entities), budget, h)
    assert report.est_tokens <= budget.available and not report.over_budget
    row = next(s for s in report.sections if s.name.startswith("Established facts"))
    assert row.items_sent > 0 and "(Scene 1)" in text            # first appearances survive; the report names the rest
    assert len(next(s for s in cont._history_sections(h) if s.name.startswith("Established")).items) <= 2 * (
        sm.FACTS_PER_ENTITY)

