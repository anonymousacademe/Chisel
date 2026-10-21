"""Continuity and canon context with summaries (Wave A).

``test_without_summaries_is_byte_identical`` compares plan_check / plan_canon / the prompts actually
sent against ``fixtures/context_no_summaries.json``, recorded from the code BEFORE summaries existed
(regenerate only on purpose: ``CHISEL_REGEN_FIXTURE=1``). A project with no summaries must send what it sent.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from chisel.ai import continuity as cont
from chisel.ai.budget import Budget, BudgetError
from chisel.core import summaries as sm
from chisel.core.continuity import get_canon, set_canon
from chisel.core.entities import Entity
from tests.gui_helpers import make_project

FIXTURE = Path(__file__).parent / "fixtures" / "context_no_summaries.json"

SCENE = ("---\npov: Mara Vale\nplace: Lower Meridian\n---\n# Arrival\n\n"
         "Mara stepped off the tram into Lower Meridian. Elias was waiting under the clock, "
         "and Dr. Okafor had not come.\n")


def cast(n):
    out = []
    for i in range(n):
        name = ["Mara Vale", "Elias Vale", "Lower Meridian", "Dr. Okafor"][i] if i < 4 else f"Extra {i}"
        canon = f"- {name} fact one.\n- {name} fact two. " + "word " * (60 if i % 2 else 5)
        out.append(Entity(name=name, type="place" if name == "Lower Meridian" else "character",
                          aliases=[name.split()[0]] if i < 2 else [], body=set_canon("", canon)))
    return out


class FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw["messages"])
        reply = '{"contradictions": []}' if "contradictions" in kw["messages"][0]["content"] or True else ""
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


def report_dict(report):
    return json.loads(json.dumps(report.to_dict()))


def snapshot():
    out = {}
    for label, n, window in (("small", 4, 32_000), ("large", 50, 32_000), ("tight", 12, 4_700)):
        entities = cast(n)
        canon = {e.name: get_canon(e.body) for e in entities}
        budget = Budget(window)
        ents, kept, report = cont.plan_check(SCENE, entities, canon, budget)
        client = FakeClient()
        cont.check_scene(SCENE, ents, kept, "m/x", client=client)
        cents, creport = cont.plan_canon(SCENE, entities, budget)
        cont.propose_canon_updates(SCENE, cents, "m/x", client=client)
        out[label] = {"check": {"entities": [e.name for e in ents], "canon": kept,
                                "report": report_dict(report), "messages": client.calls[0]},
                      "canon": {"entities": [(e.name, e.body) for e in cents],
                                "report": report_dict(creport), "messages": client.calls[1]}}
    return out


def test_without_summaries_is_byte_identical():
    got = snapshot()
    if os.environ.get("CHISEL_REGEN_FIXTURE"):
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                           encoding="utf-8", newline="\n")
    assert json.loads(json.dumps(got, sort_keys=True)) == json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_empty_history_is_the_same_as_none():
    """History objects with nothing in them must not add a section or change a byte."""
    entities = cast(4)
    canon = {e.name: get_canon(e.body) for e in entities}
    base = cont.plan_check(SCENE, entities, canon, Budget(32_000))
    same = cont.plan_check_history(SCENE, entities, canon, Budget(32_000), cont.History())
    assert same[3] == "" and base[0] == same[0] and base[1] == same[1] and base[2] == same[2]


# -- with summaries -------------------------------------------------------------------------


def story_project(tmp_path, scenes=8, words=60):
    project = make_project(tmp_path / "p")
    for p in project.list_scenes():
        p.unlink()
    for n in range(scenes):
        path = project.manuscript_dir / f"{n + 1:02d}-s{n}.md"
        path.write_text(f"# Scene {n}\n\nMara met someone. Mark {n}.\n", encoding="utf-8")
        sm.save(project.root, path, sm.Summary(
            sm.current_hash(project, path), f"Event {n}. " + "filler " * words,
            (sm.Character("Mara", f"state {n}"),)))
    return project


def history_for(project, scene_rel, mara):
    return cont.History(sm.story_so_far(project, scene_rel),
                        (("Mara Vale", sm.entity_history(project, mara, scene_rel, limit=3)),))


def test_summaries_add_droppable_sections_and_reach_the_prompt(tmp_path):
    project = story_project(tmp_path, scenes=4, words=5)
    entities = cast(4)
    canon = {e.name: get_canon(e.body) for e in entities}
    scene_rel = project.root.joinpath("manuscript", "04-s3.md").relative_to(project.root).as_posix()
    history = history_for(project, scene_rel, entities[0])
    ents, kept, report, text = cont.plan_check_history(SCENE, entities, canon, Budget(32_000), history)
    names = [s.name for s in report.sections]
    assert names == ["Instructions and question", "Entity canon", "Story so far",
                     "Earlier scenes involving Mara Vale", "Scene details", "Scene"]
    assert text.startswith("STORY SO FAR") and "Event 0." in text and "Event 2." in text
    assert "EARLIER SCENES INVOLVING MARA VALE" in text and "### Mara Vale - Scene 0" in text
    assert not report.dropped
    # the same entities and canon as without summaries; only the history text is new
    base = cont.plan_check(SCENE, entities, canon, Budget(32_000))
    assert (ents, kept) == (base[0], base[1])
    client = FakeClient()
    cont.check_scene(SCENE, ents, kept, "m/x", client=client, history=text)
    prompt = client.calls[0][1]["content"]
    assert prompt.index("ENTITY CANON:") < prompt.index("STORY SO FAR") < prompt.index("SCENE DETAILS") \
        < prompt.rindex("SCENE:")
    cents, creport, ctext = cont.plan_canon_history(SCENE, entities, Budget(32_000), history)
    assert ctext == text and "Story so far" in [s.name for s in creport.sections]
    client = FakeClient()
    cont.propose_canon_updates(SCENE, cents, "m/x", client=client, history=ctext)
    assert "STORY SO FAR" in client.calls[0][1]["content"]


def test_every_drop_is_in_the_report_newest_summaries_kept(tmp_path):
    project = story_project(tmp_path, scenes=8, words=120)
    entities = cast(4)
    canon = {e.name: get_canon(e.body) for e in entities}
    scene_rel = "manuscript/08-s7.md"
    history = history_for(project, scene_rel, entities[0])
    ents, kept, report, text = cont.plan_check_history(SCENE, entities, canon, Budget(2_800, 1_000), history)
    story = next(s for s in report.sections if s.name == "Story so far")
    assert story.items_dropped and story.items_sent + len(story.items_dropped) == story.items_total == 7
    sent = [f"Scene {n}" for n in range(7)][len(story.items_dropped):]
    assert all(title in text for title in sent) and not any(t in text for t in story.items_dropped)
    assert story.items_dropped == tuple(f"Scene {n}" for n in range(len(story.items_dropped)))   # oldest go first
    assert set(story.items_dropped) <= set(report.dropped)
    # the entity canon was filled before any summary was
    assert next(s for s in report.sections if s.name == "Entity canon").items_sent == len(ents)
    cents, creport, ctext = cont.plan_canon_history(SCENE, entities, Budget(2_800, 1_000), history)
    assert [n for n in creport.dropped if n.startswith("Scene")]


def test_summaries_never_make_the_fixed_parts_overflow(tmp_path):
    project = story_project(tmp_path, scenes=3, words=400)
    entities = cast(2)
    canon = {e.name: get_canon(e.body) for e in entities}
    history = history_for(project, "manuscript/03-s2.md", entities[0])
    tiny = Budget(900, 200)
    ents, kept, report, text = cont.plan_check_history(SCENE, entities, canon, tiny, history)
    assert not report.over_budget and report.est_tokens <= tiny.available
    with pytest.raises(BudgetError):
        cont.plan_check_history(SCENE * 40, entities, canon, tiny, history)


def test_a_big_project_stays_within_budget(tmp_path):
    project = story_project(tmp_path, scenes=200, words=120)
    entities = cast(4) + [Entity(name=f"Person {i}", body=set_canon("", "- a fact")) for i in range(396)]
    assert len(entities) == 400
    canon = {e.name: get_canon(e.body) for e in entities}
    scene_rel = "manuscript/200-s199.md"
    story = sm.story_so_far(project, scene_rel)
    assert len(story.blocks) == 199
    history = cont.History(story, (("Mara Vale", sm.entity_history(project, entities[0], scene_rel, limit=5)),))
    budget = Budget(32_000)
    ents, kept, report, text = cont.plan_check_history(SCENE, entities, canon, budget, history)
    assert not report.over_budget and report.est_tokens <= budget.available
    assert len(ents) < 40                                              # the relevance cut still applies
    story_row = next(s for s in report.sections if s.name == "Story so far")
    assert story_row.items_sent + len(story_row.items_dropped) == 199 and story_row.items_dropped
    cents, creport, ctext = cont.plan_canon_history(SCENE, entities, budget, history)
    assert not creport.over_budget and creport.est_tokens <= budget.available


# -- the pieces wave B1 wires into the desktop app ------------------------------------------


def test_history_for_reads_nothing_without_summaries_and_names_the_main_characters(tmp_path):
    project = make_project(tmp_path / "p")
    entities = project.load_entities()
    scene = "# T\n\nMara spoke to Elias at the clock.\n"
    assert not sm.has_any(project.root)
    assert cont.history_for(project, "manuscript/02-the-archive.md", scene, entities) is None
    first = project.root / "manuscript" / "01-arrival.md"
    sm.save(project.root, first, sm.Summary(sm.current_hash(project, first),
                                            "Mara arrived and Elias waited.", (), ()))
    assert sm.has_any(project.root)
    history = cont.history_for(project, "manuscript/02-the-archive.md", scene, entities)
    assert [b.name for b in history.story.blocks] == ["Arrival"]
    assert sorted(name for name, _ in history.earlier) == ["Elias Vale", "Mara Vale"]
    assert cont.history_for(project, "manuscript/02-the-archive.md", "# T\n\nNobody here.\n", entities).earlier == ()


def test_story_so_far_through_includes_the_last_scene(tmp_path):
    project = story_project(tmp_path, scenes=3, words=3)
    last = "manuscript/03-s2.md"
    assert [b.name for b in sm.story_so_far(project, last).blocks] == ["Scene 0", "Scene 1"]
    assert [b.name for b in sm.story_so_far(project, last, through=True).blocks] == ["Scene 0", "Scene 1", "Scene 2"]


def test_story_section_is_droppable_newest_kept_and_empty_means_no_section(tmp_path):
    from chisel.ai import writing

    project = story_project(tmp_path, scenes=3, words=3)
    story = sm.story_so_far(project, "manuscript/03-s2.md")
    section = writing.story_section(story)
    assert section.name == "Story so far" and section.droppable and section.priority == writing.STORY_PRIORITY
    assert [it.name for it in section.items] == ["Scene 0", "Scene 1"]
    assert [it.priority for it in section.items] == [1, 0]                # the newest scene is kept longest
    assert section.head.startswith("STORY SO FAR") and "reading order" in section.head
    assert writing.story_section(None) is None and writing.story_section(sm.StorySoFar()) is None
    assert writing.story_section(story, writing.STORY_PROJECT_PRIORITY).priority == 1


def test_context_builders_are_unchanged_without_a_story_and_add_one_section_with_it(tmp_path):
    from chisel.ai import writing

    project = story_project(tmp_path, scenes=3, words=3)
    story = sm.story_so_far(project, "manuscript/03-s2.md")
    entities = cast(3)
    text = "# T\n\nMara walked.\n"
    plain = writing.build_context_sections(text, 0, entities, {}, None)
    assert plain == writing.build_context_sections(text, 0, entities, {}, None, story=None)
    withs = writing.build_context_sections(text, 0, entities, {}, None, story=story)
    assert [s.name for s in withs if s not in plain] == ["Story so far"]
    assert [s.name for s in withs].index("Story so far") < [s.name for s in withs].index("Scene")
    pplain = writing.build_project_context_sections(["A", "B"], entities, {}, None)
    pwith = writing.build_project_context_sections(["A", "B"], entities, {}, None, story=story)
    assert [s.name for s in pwith if s not in pplain] == ["Story so far"]
    assert pplain == writing.build_project_context_sections(["A", "B"], entities, {}, None, story=None)


def test_dismissal_is_kept_in_project_toml_ui_and_nothing_else_changes(tmp_path):
    from chisel.core.project import Project

    project = make_project(tmp_path / "p")
    before = (project.root / "project.toml").read_text(encoding="utf-8")
    assert project.scale_hint_dismissed() == ""
    project.set_scale_hint_dismissed("strong")
    text = (project.root / "project.toml").read_text(encoding="utf-8")
    assert text.startswith(before.rstrip("\n")) and text.rstrip().endswith('[ui]\nscale_hint_dismissed = "strong"')
    assert Project.open(project.root).scale_hint_dismissed() == "strong"
    project.set_scale_hint_dismissed("notice")
    assert text.count("[ui]") == 1 and (project.root / "project.toml").read_text(encoding="utf-8").count("[ui]") == 1
    project.set_scale_hint_dismissed("")
    assert Project.open(project.root).scale_hint_dismissed() == ""
    with pytest.raises(ValueError):
        project.set_scale_hint_dismissed("loud")
    project.meta["ui"] = {"scale_hint_dismissed": 7}
    assert project.scale_hint_dismissed() == ""
