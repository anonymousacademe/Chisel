"""Voice checks (ai/voice.py): the plan, the validated findings and the call; no network."""

import json
from types import SimpleNamespace

import pytest

from chisel.ai import voice
from chisel.ai.budget import Budget, BudgetError
from chisel.core import drafts
from chisel.core import entities as ent
from chisel.core import voice as dialogue
from chisel.core.continuity import canon_map
from chisel.core.project import Project

CURRENT = """\
INT. KITCHEN - DAY

KEITH
Ain't no way I'm paying that, Mara. Not a chance.

MARA
You owe him, Keith.

KEITH
Notwithstanding the aforementioned obligation, I decline.

WAITER
Anything else?
"""


def make(tmp_path, with_refs=True):
    p = Project.create(tmp_path / "s", "S", "script")
    (p.manuscript_dir / "01-opening.md").unlink()
    act = p.new_part("Act One")
    scenes = [
        ("One", "INT. A - DAY\n\nKEITH\nYeah, nah. Ain't doing it.\nNot today, mate.\n\nMARA\nPlease, Keith, think about it.\n"),
        ("Two", "INT. B - DAY\n\nKEITH\nAin't nobody asked you.\nGonna go get a pint.\n\nMARA\nI did ask, actually.\n"),
        ("Three", "INT. C - DAY\n\nKEITH\nNah. Ain't my problem.\nCome off it, Mara.\n"),
    ] if with_refs else [("One", "INT. A - DAY\n\nKEITH\nHi.\n")]
    for title, body in scenes:
        path = p.next_scene_path(title, act)
        path.write_text(f"# {title}\n\n{body}", encoding="utf-8", newline="\n")
    cur = p.next_scene_path("Current", act)
    cur.write_text(f"# Current\n\n{CURRENT}", encoding="utf-8", newline="\n")
    p.create_entity("Keith", "character")
    p.create_entity("Mara", "character")
    return Project.open(tmp_path / "s"), cur


def plan(project, cur, budget=None, style=None):
    ents = project.load_entities() if hasattr(project, "load_entities") else project.entities()
    text = drafts.strip_pending(cur.read_text(encoding="utf-8"))
    return voice.plan_voice(text, cur, project, ents, canon_map(ents), style, budget or Budget(100_000)), ents, text


def test_the_plan_judges_speakers_with_enough_reference_lines(tmp_path):
    project, cur = make(tmp_path)
    p, _ents, _ = plan(project, cur, style="## Dialogue\n- Keith is blunt and drops his g's.")
    assert p.checked == ("Keith",)                         # Mara has 2 reference lines, the Waiter none
    assert dict(p.skipped) == {"Mara": 2, "Waiter": 0}
    ctx = p.context
    assert "### Keith (speaks 2 lines in this scene)" in ctx
    assert "[Two]\n- Ain't nobody asked you." in ctx
    assert ctx.index("[Three]") < ctx.index("[Two]") < ctx.index("[One]")      # the nearest scene first
    assert "STYLE GUIDE:" in ctx and "SCENE:" in ctx and "Notwithstanding" in ctx
    assert "Please, Keith" not in ctx                       # Mara is not judged: her lines are not references
    assert p.report.feature == "voice"


def test_a_scene_is_never_its_own_reference(tmp_path):
    project, cur = make(tmp_path)
    p, _, _ = plan(project, cur)
    before_scene = p.context.split("SCENE:")[0]
    assert "Notwithstanding" not in before_scene and "Ain't no way I'm paying" not in before_scene


def test_nobody_to_judge_is_said_plainly(tmp_path):
    project, cur = make(tmp_path, with_refs=False)
    p, _, _ = plan(project, cur)
    assert p.checked == () and p.context == "" and dict(p.skipped)["Keith"] == 1
    assert voice.check_voice("x", p, [], "m", client=object()) == []      # no call, so no client needed
    empty = project.manuscript_dir / "01-act-one" / "99-empty.md"
    empty.write_text("# Empty\n\nINT. A - DAY\n\nJust action.\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="Nobody speaks"):
        plan(project, empty)


def test_the_budget_cuts_the_farthest_scenes_first_and_reports_it(tmp_path):
    project, cur = make(tmp_path)
    ents = project.load_entities() if hasattr(project, "load_entities") else project.entities()
    big = project.next_scene_path("Long", project.part_of(cur))
    big.write_text("# Long\n\nINT. L - DAY\n\n" + "\n\n".join(f"KEITH\nLong line number {i} goes on and on and on.\n" for i in range(300)),
                   encoding="utf-8", newline="\n")
    text = drafts.strip_pending(cur.read_text(encoding="utf-8"))
    p = voice.plan_voice(text, cur, Project.open(tmp_path / "s"), ents, canon_map(ents), None, Budget(100_000))
    keith = next(s for s in p.report.sections if s.name == "Reference lines")
    assert "Keith" in keith.truncated                      # the reference list was cut, and the report names it
    assert p.context.count("Long line number") < 300
    tiny = Budget(500, 100)
    with pytest.raises(BudgetError):
        voice.plan_voice(text * 40, cur, Project.open(tmp_path / "s"), ents, canon_map(ents), None, tiny)


def finding(**kw):
    base = {"id": "1", "kind": "vocabulary", "severity": "warning", "character": "Keith",
            "evidence": "Notwithstanding the aforementioned obligation", "reason": "Keith never talks this formally.",
            "suggested_fix": "Nah, I'm not paying that."}
    return {**base, **kw}


def parse(findings, checked=("Keith",)):
    raw = json.dumps({"findings": findings})
    return voice.parse_findings(raw, CURRENT, [ent.Entity(name="Keith", type="character"), ent.Entity(name="Mara", type="character")],
                                checked, "manuscript/03-current.md")


def test_a_valid_finding_becomes_a_voice_issue_with_its_row():
    [c] = parse([finding()])
    assert (c.type, c.severity, c.entity, c.scene) == ("voice_vocabulary", "warning", "Keith", "manuscript/03-current.md")
    assert c.evidence.startswith("Notwithstanding") and c.suggested_fix == "Nah, I'm not paying that."
    assert c.reason == "Keith never talks this formally."
    assert CURRENT.split("\n")[c.row].startswith("Notwithstanding")


def test_findings_that_are_not_lines_the_character_speaks_are_dropped():
    assert parse([finding(evidence="Anything else?")]) == []                      # the Waiter's line, not Keith's
    assert parse([finding(evidence="You owe him, Keith.")]) == []                 # Mara's line
    assert parse([finding(evidence="Ain't doing it.")]) == []                     # a reference line, not in the scene
    assert parse([finding(evidence="INT. KITCHEN - DAY")]) == []                  # not dialogue
    assert parse([finding(character="Mara", evidence="You owe him, Keith.")]) == []   # Mara was not judged
    assert parse([finding(character="Nobody")]) == []
    assert parse([finding(kind="grammar")]) == [] and parse([finding(severity="fatal")]) == []
    assert parse([finding(evidence="")]) == []
    assert parse([{"kind": "vocabulary"}]) == []


def test_matching_is_tolerant_of_case_quotes_and_whitespace_but_not_of_words():
    assert len(parse([finding(character="KEITH", evidence="  “notwithstanding   the aforementioned obligation, I decline.” ")])) == 1
    assert len(parse([finding(evidence="Not a chance.")])) == 1                   # a stretch of a line
    assert parse([finding(evidence="Not a chance, mate.")]) == []


def test_duplicates_and_garbage_replies():
    assert len(parse([finding(), finding(id="2", reason="again")])) == 1
    for raw in ("", "not json", "[]", '{"findings": "x"}', '{"findings": [1, null]}'):
        assert voice.parse_findings(raw, CURRENT, [], None) == []


def test_check_voice_makes_one_structured_call_and_returns_validated_findings(tmp_path):
    project, cur = make(tmp_path)
    p, ents, text = plan(project, cur)
    seen = {}

    class Completions:
        def create(self, **kw):
            seen.update(kw)
            reply = json.dumps({"findings": [finding(), finding(id="2", evidence="made up words nobody says")]})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
                                   usage=SimpleNamespace(cost=0.002))

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    got = voice.check_voice(text, p, ents, "strong/model", client=client, scene_rel="manuscript/01-act-one/04-current.md")
    assert [c.evidence[:12] for c in got] == ["Notwithstand"] and got[0].scene.endswith("04-current.md")
    assert seen["model"] == "strong/model"
    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["response_format"]["json_schema"]["schema"] is voice.VOICE_SCHEMA
    system, user = (m["content"] for m in seen["messages"])
    assert system == voice.SYSTEM_PROMPT
    assert "Check the dialogue of: Keith" in user and "LINES EACH CHARACTER SPEAKS" in user
    from chisel.ai.usage import LEDGER
    assert LEDGER.last().feature == "voice"


def test_the_prompt_asks_for_verbatim_evidence_and_restraint():
    p = voice.SYSTEM_PROMPT
    for needle in ("copied verbatim", "Never quote the reference lines", "plainly contradicted", "no reference lines",
                   "vocabulary", "register", "rhythm", "verbal_habit", "out_of_character"):
        assert needle in p, needle
    assert set(voice.KINDS) == set(voice.VOICE_SCHEMA["properties"]["findings"]["items"]["properties"]["kind"]["enum"])


# -- fixes from the independent review ---------------------------------------------------------------------


def test_a_speaker_the_budget_dropped_is_not_called_short_of_lines(tmp_path):
    project, cur = make(tmp_path)
    ents = project.load_entities()
    text = drafts.strip_pending(cur.read_text(encoding="utf-8"))
    dropped = None
    for window in range(3200, 9000, 100):
        try:
            p = voice.plan_voice(text, cur, project, ents, canon_map(ents), "## Dialogue\n- blunt " * 20, Budget(window))
        except BudgetError:
            continue
        if p.dropped:
            dropped = p
            break
    assert dropped is not None and dropped.dropped == ("Keith",) and dropped.checked == ()
    assert "Keith" not in dict(dropped.skipped)                       # not "too few lines": the window was too small
    assert "Keith" in next(s for s in dropped.report.sections if s.name == "Reference lines").items_dropped


def test_quotes_must_be_real_words_inside_one_speech():
    assert parse([finding(evidence='"')]) == [] and parse([finding(evidence="'")]) == []
    assert parse([finding(evidence="a")]) == [] and parse([finding(evidence=' "" ')]) == []
    assert parse([finding(evidence="Not a chance. You owe him, Keith.")]) == []    # joins two speeches (two speakers)
    text = "INT. A - DAY\n\nKEITH\nFirst speech here.\n\nMARA\nHm.\n\nKEITH\nSecond speech there.\n"
    raw = json.dumps({"findings": [finding(evidence="First speech here. Second speech there.")]})
    ents = [ent.Entity(name="Keith", type="character")]
    assert voice.parse_findings(raw, text, ents, ("Keith",)) == []                  # two separate speeches
    two_lines = "INT. A - DAY\n\nKEITH\nFirst line here,\nand it runs on.\n"
    raw = json.dumps({"findings": [finding(evidence="First line here, and it runs on.")]})
    [c] = voice.parse_findings(raw, two_lines, ents, ("Keith",))
    assert c.evidence == "First line here," and c.row == 3                          # across lines of ONE speech: kept


def test_the_evidence_kept_is_the_spoken_line_so_the_editor_finds_it():
    [c] = parse([finding(evidence="NOTWITHSTANDING the aforementioned obligation")])      # a different case
    assert c.evidence == "Notwithstanding the aforementioned obligation, I decline."
    assert CURRENT.split("\n")[c.row] == c.evidence
    # the same words in another character's line earlier in the scene do not move the row
    text = "INT. A - DAY\n\nMARA\nI will not say it again.\n\nKEITH\nI will not say it again.\n"
    ents = [ent.Entity(name="Keith", type="character"), ent.Entity(name="Mara", type="character")]
    raw = json.dumps({"findings": [finding(evidence="I will not say it again")]})
    [k] = voice.parse_findings(raw, text, ents, ("Keith",))
    assert text.split("\n")[k.row] == "I will not say it again." and k.row == 6


def test_a_fenced_reply_is_unwrapped():
    reply = "```json\n" + json.dumps({"findings": [finding()]}) + "\n```"
    assert len(voice.parse_findings(reply, CURRENT, [ent.Entity(name="Keith", type="character")], ("Keith",))) == 1


def test_scenes_that_never_mention_the_speaker_are_not_parsed(tmp_path, monkeypatch):
    project, cur = make(tmp_path)
    quiet = project.next_scene_path("Quiet", project.part_of(cur))
    quiet.write_text("# Quiet\n\nINT. Z - DAY\n\nZED\nNothing about the others.\n", encoding="utf-8", newline="\n")
    project = Project.open(tmp_path / "s")
    parsed = []
    real = dialogue.by_speaker
    monkeypatch.setattr(dialogue, "by_speaker", lambda t, e=(): (parsed.append(t), real(t, e))[1])
    refs = dialogue.gather_references(project, project.load_entities(), cur, {"Keith"})
    assert set(refs) == {"Keith"} and all("KEITH" in t for t in parsed) and len(parsed) == 3   # not the Quiet scene
