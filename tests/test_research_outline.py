"""Wave D1: the outline assistant (core/paper/scope.py + outlines.py, ai/outline.py, gui/research_outline_api.py).
The AI is mocked at the function boundary (chisel.gui.api.suggest_outline); nothing here reaches a network."""

import json
import re
from pathlib import Path

import pytest

from chisel.ai import outline as oai
from chisel.ai.budget import Budget, BudgetError
from chisel.core import snapshots
from chisel.core.paper import outlines, scope
from chisel.core.project import Project
from chisel.gui import api as api_module
from chisel.gui.api import Api
from tests.research_helpers import clear_starter


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key (network is blocked in tests)")

    monkeypatch.setattr("chisel.ai.client.make_client", boom)


def ems_project(tmp_path, journal="ems"):
    return Project.create(tmp_path / "paper", "Paper", "research", "manuscript", journal)


def open_api(project):
    api = Api()
    api._load(project)
    return api


def titles(project):
    return [s["title"] for s in outlines.current_outline(project)["sections"]]


# -- scope ---------------------------------------------------------------------------------------------

def test_scope_round_trip_and_cap(tmp_path):
    project = ems_project(tmp_path)
    assert scope.get_scope(project) == ""
    scope.set_scope(project, "Streamflow forecasting with Kalman filters.\r\nSecond line.")
    assert (project.root / "scope.md").read_bytes() == b"Streamflow forecasting with Kalman filters.\nSecond line.\n"
    assert scope.get_scope(project).startswith("Streamflow")
    with pytest.raises(ValueError):
        scope.set_scope(project, "x" * (scope.MAX_CHARS + 1))
    assert scope.get_scope(project).startswith("Streamflow")          # a refused save changes nothing
    scope.set_scope(project, "  \n")
    assert not (project.root / "scope.md").exists()


def test_scope_refuses_a_non_utf8_file(tmp_path):
    project = ems_project(tmp_path)
    (project.root / "scope.md").write_bytes(b"caf\xe9")
    with pytest.raises(ValueError):
        scope.set_scope(project, "new text")
    assert (project.root / "scope.md").read_bytes() == b"caf\xe9"


def test_scope_is_not_a_document_anywhere(tmp_path):
    project = ems_project(tmp_path)
    scope.set_scope(project, "SCOPETOKEN")
    assert all(p.name != "scope.md" for p in project.all_markdown_files())
    assert not project.is_scene_path(project.root / "scope.md")
    from chisel.core import research
    assert all(n.id != "scope.md" for n in research.list_notes(project))


def test_scope_text_never_reaches_an_existing_ai_context(tmp_path, monkeypatch):
    project = ems_project(tmp_path)
    scope.set_scope(project, "SCOPETOKEN the secret scope")
    (project.root / "notebook").mkdir(exist_ok=True)
    (project.root / "notebook" / "tides.md").write_text("# Tides\n\nThe tide floods.\n", encoding="utf-8")
    api = open_api(project)
    seen: list[str] = []

    def fake(*a, **k):
        seen.append(json.dumps([a, k], default=str))
        return "reply"

    for name in ("ask_writer", "research_writer", "brainstorm_writer", "generate_text"):
        monkeypatch.setattr(api_module, name, fake)
    first = outlines.current_outline(project)["sections"][0]["id"]
    api.ask("what next?", "project")
    api.ask("what next?", "scene", first)
    api.research("what about tides?")
    api.brainstorm("ideas?", "scene", first) if hasattr(api, "brainstorm") else None
    assert seen
    assert not any("SCOPETOKEN" in s for s in seen)
    # and no module outside the outline assistant reads the scope file
    root = Path(api_module.__file__).parents[1]
    users = {p.relative_to(root).as_posix() for p in root.rglob("*.py")
             if re.search(r"\bget_scope\b|scope_path|scope\.md", p.read_text(encoding="utf-8"))}
    assert users <= {"core/paper/scope.py", "gui/research_outline_api.py", "ai/outline.py"}, users


# -- current outline and the standard structure ------------------------------------------------------------

def test_current_outline_of_a_fresh_ems_project(tmp_path):
    project = ems_project(tmp_path)
    out = outlines.current_outline(project)
    assert out["kind"] == "manuscript" and out["journal"] == "ems" and out["journalName"]
    rows = out["sections"]
    assert rows and all(set(r) == {"id", "title", "part", "partTitle", "frontMatter", "position", "words",
                                   "purpose"} for r in rows)
    assert rows[0]["frontMatter"] is True and rows[0]["position"] == 1
    assert any(r["purpose"] for r in rows)
    assert all(r["id"].startswith("manuscript/") and r["part"].startswith("part:manuscript/") for r in rows)
    assert all(not r["id"].startswith("manuscript/_unplaced") for r in rows)       # the parked note is excluded
    assert [r["position"] for r in rows if r["part"] == rows[1]["part"]] == \
        list(range(1, 1 + sum(r["part"] == rows[1]["part"] for r in rows)))


def test_standard_diff_adds_only_missing_sections_case_insensitively(tmp_path):
    project = ems_project(tmp_path)
    assert outlines.standard_diff(project)["items"] == []              # a fresh project has all of them
    first = outlines.current_outline(project)["sections"]
    victim = next(s for s in first if not s["frontMatter"])
    project.delete_scene(project.root / victim["id"])
    diff = outlines.standard_diff(project)
    assert [i["title"] for i in diff["items"]] == [victim["title"]]
    item = diff["items"][0]
    assert item["action"] == "add" and item["part"] == victim["partTitle"] and item["why"]
    # a differently cased title counts as present
    project2 = ems_project(tmp_path / "b")
    sec = next(s for s in outlines.current_outline(project2)["sections"] if not s["frontMatter"])
    project2.rename_scene(project2.root / sec["id"], sec["title"].upper())
    assert outlines.standard_diff(project2)["items"] == []


def test_standard_diff_without_a_journal_uses_the_generic_profile(tmp_path):
    project = Project.create(tmp_path / "g", "G", "research", "proposal")
    clear_starter(project)
    diff = outlines.standard_diff(project)
    assert diff["name"] and diff["items"]
    assert all(i["action"] == "add" for i in diff["items"])


def test_outline_standard_works_with_no_ai(tmp_path, monkeypatch):
    monkeypatch.setattr(api_module, "suggest_outline", lambda *a, **k: pytest.fail("AI called"))
    api = open_api(ems_project(tmp_path))
    r = api.outline_standard()
    assert r["ok"] and r["items"] == [] and r["name"]


def test_outline_methods_refuse_a_story_project(tmp_path):
    api = Api()
    api._load(Project.create(tmp_path / "s", "S"))
    for call in (api.outline_current, api.outline_standard, api.outline_get_scope):
        r = call()
        assert r["ok"] is False and "research" in r["error"].lower()


# -- plan_outline ----------------------------------------------------------------------------------------------

def test_plan_names_guidelines_scope_and_caps(tmp_path):
    from chisel.core.paper import guidelines
    project = ems_project(tmp_path)
    guidelines.add_text(project, "Journal rules", "Rule. " * 4000)               # ~24k characters
    guidelines.add_text(project, "Other", "Short rule.")
    context, sent = oai.plan_outline(project, "My scope.", "Make it shorter.", ["journal-rules.md", "other.md"],
                                     Budget.for_model("m"))
    names = [s.name for s in sent.sections]
    assert "Scope statement" in names and any(n.startswith("Guideline: ") for n in names) and "Current outline" in names
    assert "Journal rules" in context or "journal-rules.md" in context
    assert "journal-rules.md" in sent.truncated               # the cap is named, not silent
    assert "My scope." in context and "Make it shorter." in context
    assert sent.to_dict()["trimmed"] is True


def test_plan_without_guidelines_sends_none(tmp_path):
    project = ems_project(tmp_path)
    scope.set_scope(project, "Scope")
    from chisel.core.paper import guidelines
    guidelines.add_text(project, "Journal rules", "NOTSENTTOKEN")
    context, sent = oai.plan_outline(project, "Scope", "", [], Budget.for_model("m"))
    assert "NOTSENTTOKEN" not in context
    assert not any(s.name.startswith("Guideline") for s in sent.sections)
    assert "STANDARD STRUCTURE" in context and "CURRENT OUTLINE" in context and "JOURNAL REQUIREMENTS" in context


def test_plan_raises_before_any_call_when_it_cannot_fit(tmp_path):
    project = ems_project(tmp_path)
    with pytest.raises(BudgetError):
        oai.plan_outline(project, "x " * 50_000, "", [], Budget(window_tokens=6_000))


def test_plan_refuses_an_unknown_guideline_and_too_many(tmp_path):
    project = ems_project(tmp_path)
    with pytest.raises(Exception):
        oai.plan_outline(project, "", "", ["nope.md"], Budget.for_model("m"))
    with pytest.raises(ValueError):
        oai.plan_outline(project, "", "", [f"g{i}.md" for i in range(20)], Budget.for_model("m"))


# -- parse_outline_items -----------------------------------------------------------------------------------

def sample_outline():
    return {"kind": "manuscript", "journal": "", "journalName": "", "sections": [
        {"id": "manuscript/01-a/01-intro.md", "title": "Introduction", "part": "part:manuscript/01-a",
         "partTitle": "Body", "frontMatter": False, "position": 1, "words": 10, "purpose": ""},
        {"id": "manuscript/01-a/02-methods.md", "title": "Methods", "part": "part:manuscript/01-a",
         "partTitle": "Body", "frontMatter": False, "position": 2, "words": 10, "purpose": ""},
    ]}


def parse(reply, outline=None):
    return oai.parse_outline_items(reply, outline or sample_outline())


def test_parse_good_reply_with_prose_fence_and_trailing_text():
    reply = ('Sure! Here is my plan:\n```json\n{"items": [\n'
             '{"id": "a", "action": "rename", "title": "Methods", "section": "manuscript/01-a/02-methods.md",'
             ' "newTitle": "Study design", "why": "Clearer."},\n'
             '{"id": "b", "action": "add", "title": "Limitations", "part": "Body",'
             ' "after": "manuscript/01-a/02-methods.md", "purpose": "What we cannot show.", "why": "Expected."},\n'
             '{"id": "c", "action": "keep", "title": "x", "section": "manuscript/01-a/01-intro.md", "why": "Fine."}\n'
             ']}\n```\nHope that helps! {not json}')
    items, dropped = parse(reply)
    assert dropped == []
    assert [i["action"] for i in items] == ["rename", "add", "keep"]
    assert items[2]["title"] == "Introduction"                  # the existing title wins over the model's
    assert set(items[0]) == {"id", "action", "title", "section", "newTitle", "part", "after", "purpose", "why"}


def test_parse_drops_invented_ids_duplicates_and_unknown_actions():
    reply = json.dumps({"items": [
        {"id": "1", "action": "rename", "title": "Ghost", "section": "manuscript/99.md", "newTitle": "X", "why": "w"},
        {"id": "2", "action": "add", "title": "introduction", "part": "Body", "why": "dup of an existing title"},
        {"id": "3", "action": "rename", "title": "Methods", "section": "manuscript/01-a/02-methods.md",
         "newTitle": "INTRODUCTION", "why": "onto an existing title"},
        {"id": "4", "action": "teleport", "title": "Methods", "why": "?"},
        {"id": "5", "action": "move", "title": "Methods", "section": "manuscript/01-a/02-methods.md",
         "part": "Body", "after": "manuscript/zzz.md", "why": "after a section that is not there"},
        {"id": "6", "action": "add", "title": "New", "part": "Appendix", "after": "manuscript/01-a/01-intro.md",
         "why": "after a section of another part"},
        "not an object",
        {"id": "7", "action": "add", "title": "Fine", "part": "Body", "why": "ok"},
        {"id": "7", "action": "add", "title": "fine", "part": "Body", "why": "same title twice in one reply"},
    ]})
    items, dropped = parse(reply)
    assert [i["title"] for i in items] == ["Fine"]
    assert len(dropped) == 8 and all(d["reason"] for d in dropped)


def test_parse_turns_delete_and_merge_into_advice():
    reply = json.dumps({"items": [
        {"id": "1", "action": "delete", "title": "Methods", "section": "manuscript/01-a/02-methods.md", "why": "Redundant."},
        {"id": "2", "action": "Merge", "title": "Introduction", "why": "Fold into methods."}]})
    items, dropped = parse(reply)
    assert [i["action"] for i in items] == ["advice", "advice"]
    assert all(i["section"] == "" for i in items)
    assert "never" in items[0]["why"] and "Redundant." in items[0]["why"]
    assert dropped == []


def test_parse_cleans_titles_and_caps_items():
    reply = json.dumps({"items": [
        {"id": "x", "action": "add", "title": "  ../etc/passwd\\evil\n## Heading " + "w" * 300, "part": "Body",
         "why": "w" * 900}] + [
        {"id": str(n), "action": "advice", "title": f"t{n}", "why": "w"} for n in range(60)]})
    items, dropped = parse(reply)
    first = items[0]
    assert "/" not in first["title"] and "\\" not in first["title"] and "\n" not in first["title"]
    assert not first["title"].startswith("#") and len(first["title"]) <= oai.TITLE_MAX
    assert len(first["why"]) <= oai.WHY_MAX
    assert len(items) == oai.MAX_ITEMS
    assert len(dropped) == 61 - oai.MAX_ITEMS and "first 40" in dropped[0]["reason"]
    assert len({i["id"] for i in items}) == len(items)


def test_parse_survives_garbage_and_huge_text():
    for reply in ("", "no json at all", "{", "[1, 2, 3]", '{"items": "nope"}', "[" * 5000, "{" * 5000,
                  "x" * 2_000_000):
        items, dropped = parse(reply)
        assert items == [] and dropped and dropped[0]["reason"]


def test_parse_accepts_a_bare_list():
    items, _ = parse('[{"action": "advice", "title": "Tip", "why": "Because."}]')
    assert [i["action"] for i in items] == ["advice"] and items[0]["id"]


# -- suggest_outline (client faked) --------------------------------------------------------------------------

def test_suggest_outline_returns_the_reply_text_and_streams():
    class Chunk:
        def __init__(self, text):
            self.usage = None
            self.choices = [type("C", (), {"delta": type("D", (), {"content": text})()})()]

    class Stream:
        def __iter__(self):
            return iter([Chunk('{"items": '), Chunk("[]}")])

        def close(self):
            pass

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    assert kw["stream"] is True
                    return Stream()

    got = []
    out = oai.suggest_outline("ctx", "m", client=Client, on_delta=got.append)
    assert out == '{"items": []}' and got == ['{"items": ', "[]}"]


# -- the bridge: suggest -----------------------------------------------------------------------------------------

def test_outline_suggest_proposes_and_changes_nothing(tmp_path, monkeypatch):
    project = ems_project(tmp_path)
    scope.set_scope(project, "Kalman filters for streamflow.")
    api = open_api(project)
    before = {p: p.read_bytes() for p in project.root.rglob("*") if p.is_file() and ".chisel" not in p.parts}
    sec = outlines.current_outline(project)["sections"][1]
    seen = {}

    def fake(context, model, client=None, cancel=None, on_delta=None):
        seen["context"] = context
        return json.dumps({"items": [{"id": "1", "action": "rename", "title": sec["title"], "section": sec["id"],
                                      "newTitle": "Renamed by AI", "why": "Clearer."},
                                     {"id": "2", "action": "delete", "title": sec["title"], "section": sec["id"],
                                      "why": "Drop it."}]})

    monkeypatch.setattr(api_module, "suggest_outline", fake)
    r = api.outline_suggest("tighten it")
    assert r["ok"], r
    assert [i["action"] for i in r["items"]] == ["rename", "advice"]
    assert r["dropped"] == [] and r["model"] and "sections" in r["sent"]
    assert "Kalman filters" in seen["context"] and "tighten it" in seen["context"]
    after = {p: p.read_bytes() for p in project.root.rglob("*") if p.is_file() and ".chisel" not in p.parts}
    assert before == after


def test_outline_suggest_runs_as_an_ai_job(tmp_path, monkeypatch):
    import time
    api = open_api(ems_project(tmp_path))
    monkeypatch.setattr(api_module, "suggest_outline",
                        lambda context, model, client=None, cancel=None, on_delta=None:
                        '{"items": [{"action": "advice", "title": "Tip", "why": "Because."}]}')
    job = api.ai_start("outline", {"instruction": "", "guidelines": []})["job"]
    for _ in range(100):
        state = api.ai_poll(job)
        if state["state"] != "running":
            break
        time.sleep(0.05)
    assert state["state"] == "done" and state["result"]["items"][0]["action"] == "advice"
    assert api.ai_start("outline", {"bogus": 1})["ok"] is False


def test_outline_suggest_with_a_guideline_names_it_in_sent(tmp_path, monkeypatch):
    project = ems_project(tmp_path)
    from chisel.core.paper import guidelines
    guidelines.add_text(project, "Journal rules", "GUIDELINETOKEN: abstracts under 250 words.")
    api = open_api(project)
    seen = {}
    monkeypatch.setattr(api_module, "suggest_outline",
                        lambda context, model, client=None, cancel=None, on_delta=None:
                        seen.setdefault("c", context) and '{"items": []}')
    r = api.outline_suggest("", ["journal-rules.md"])
    assert r["ok"] and "GUIDELINETOKEN" in seen["c"]
    assert any(s["name"] == "Guideline: journal-rules.md" for s in r["sent"]["sections"])
    assert api.outline_suggest("", ["missing.md"])["ok"] is False


# -- apply -------------------------------------------------------------------------------------------------------

def never_ai(monkeypatch):
    monkeypatch.setattr(api_module, "suggest_outline", lambda *a, **k: pytest.fail("AI called by apply"))
    monkeypatch.setattr("chisel.ai.client.make_client", lambda *a, **k: pytest.fail("client made by apply"))


def test_apply_nothing_ticked_changes_nothing(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    snap = {p: p.read_bytes() for p in project.root.rglob("*") if p.is_file()}
    r = api.outline_apply([])
    assert r == {"ok": True, "changed": [], "remap": {}, "skipped": [], "created": [], "createdParts": []}
    assert snap == {p: p.read_bytes() for p in project.root.rglob("*") if p.is_file()}


def test_apply_rename_snapshots_first_and_keeps_the_id(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    sec = outlines.current_outline(project)["sections"][3]
    path = project.root / sec["id"]
    r = api.outline_apply([{"id": "1", "action": "rename", "title": sec["title"], "section": sec["id"],
                            "newTitle": "A Better Title", "why": "w"}])
    assert r["ok"] and r["changed"] == [sec["id"]] and r["skipped"] == [] and r["remap"] == {}
    assert project.scene_title(path) == "A Better Title"
    snaps = snapshots.list_snapshots(project, path)
    assert len(snaps) == 1 and "before-outline" in snaps[0].name
    assert sec["title"] in snaps[0].path.read_text(encoding="utf-8")        # the snapshot has the old title


def test_apply_add_creates_a_section_with_the_purpose_in_place(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    rows = outlines.current_outline(project)["sections"]
    anchor = next(s for s in rows if not s["frontMatter"])
    r = api.outline_apply([{"id": "1", "action": "add", "title": "Limitations", "part": anchor["partTitle"],
                            "after": anchor["id"], "purpose": "What the study cannot show.", "why": "w"}])
    assert r["ok"] and len(r["created"]) == 1 and r["skipped"] == []
    new = project.root / r["created"][0]
    assert new.is_file() and "purpose: What the study cannot show." in new.read_text(encoding="utf-8")
    after = outlines.current_outline(project)["sections"]
    names = [s["title"] for s in after if s["part"] == anchor["part"]]
    assert names.index("Limitations") == names.index(anchor["title"]) + 1
    assert after[[s["id"] for s in after].index(r["created"][0])]["purpose"] == "What the study cannot show."


def test_apply_two_adds_after_the_same_section_keep_their_order(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    anchor = next(s for s in outlines.current_outline(project)["sections"] if not s["frontMatter"])
    mk = lambda i, t: {"id": i, "action": "add", "title": t, "part": anchor["partTitle"], "after": anchor["id"],
                       "purpose": "p", "why": "w"}
    r = api.outline_apply([mk("1", "First new"), mk("2", "Second new")])
    assert len(r["created"]) == 2
    names = [s["title"] for s in outlines.current_outline(project)["sections"] if s["part"] == anchor["part"]]
    i = names.index(anchor["title"])
    assert names[i + 1:i + 3] == ["First new", "Second new"]


def test_apply_move_snapshots_and_returns_the_remap(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    rows = [s for s in outlines.current_outline(project)["sections"] if not s["frontMatter"]]
    same = [s for s in rows if s["part"] == rows[0]["part"]]
    assert len(same) >= 3
    moving, target = same[0], same[2]
    r = api.outline_apply([{"id": "1", "action": "move", "title": moving["title"], "section": moving["id"],
                            "part": moving["partTitle"], "after": target["id"], "why": "w"}])
    assert r["ok"] and r["skipped"] == []
    names = [s["title"] for s in outlines.current_outline(project)["sections"] if s["part"] == moving["part"]]
    assert names.index(moving["title"]) == names.index(target["title"]) + 1
    new_id = r["remap"][moving["id"]]
    assert (project.root / new_id).is_file() and not (project.root / moving["id"]).exists()
    assert new_id in r["changed"]
    assert all((project.root / v).is_file() for v in r["remap"].values())
    assert snapshots.list_snapshots(project, project.root / new_id)          # carried to the new name


def test_apply_skips_an_item_whose_section_vanished(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    sec = next(s for s in outlines.current_outline(project)["sections"] if not s["frontMatter"])
    project.delete_scene(project.root / sec["id"])
    keep = outlines.current_outline(project)["sections"][-1]
    r = api.outline_apply([
        {"id": "gone", "action": "rename", "title": sec["title"], "section": sec["id"], "newTitle": "X", "why": "w"},
        {"id": "ok", "action": "rename", "title": keep["title"], "section": keep["id"], "newTitle": "Fine", "why": "w"},
        {"id": "adv", "action": "advice", "title": "Tip", "why": "w"},
        {"id": "del", "action": "delete", "title": keep["title"], "section": keep["id"], "why": "w"},
    ])
    assert r["changed"] == [keep["id"]]
    skipped = {s["id"]: s["reason"] for s in r["skipped"]}
    assert set(skipped) == {"gone", "adv", "del"} and all(skipped.values())
    assert project.scene_title(project.root / keep["id"]) == "Fine"


def test_apply_after_a_move_follows_renumbered_ids(tmp_path, monkeypatch):
    """A later item names an id that an earlier item renumbered: the remap carries it."""
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    rows = [s for s in outlines.current_outline(project)["sections"] if not s["frontMatter"]]
    same = [s for s in rows if s["part"] == rows[0]["part"]]
    a, b, c = same[0], same[1], same[2]
    r = api.outline_apply([
        {"id": "1", "action": "move", "title": a["title"], "section": a["id"], "part": a["partTitle"],
         "after": c["id"], "why": "w"},
        {"id": "2", "action": "rename", "title": b["title"], "section": b["id"], "newTitle": "Renamed b", "why": "w"},
    ])
    assert r["skipped"] == [], r
    titles_now = [s["title"] for s in outlines.current_outline(project)["sections"]]
    assert "Renamed b" in titles_now and a["title"] in titles_now


def test_apply_add_into_a_missing_part_creates_it(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    r = api.outline_apply([{"id": "1", "action": "add", "title": "Data availability", "part": "Back matter",
                            "after": "", "purpose": "Where the data is.", "why": "w"}])
    assert r["ok"] and r["createdParts"] == ["Back matter"] and len(r["created"]) == 1
    assert project.root.joinpath(r["created"][0]).is_file()


def test_apply_refuses_hostile_ids(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    r = api.outline_apply([{"id": "1", "action": "rename", "title": "Outside", "section": "../outside.md",
                            "newTitle": "Hacked", "why": "w"},
                           {"id": "2", "action": "add", "title": "Ok", "part": "Body", "after": "../outside.md",
                            "why": "w"}, 5, None, "x"])
    assert r["ok"] and r["changed"] == [] and r["created"] == []
    assert outside.read_text(encoding="utf-8") == "# Outside\n"
    assert len(r["skipped"]) == 5 and all(s["reason"] for s in r["skipped"])
    assert api.outline_apply("nonsense")["changed"] == []


# -- review fixes (D1) ---------------------------------------------------------------------------------------

def _sec(project, title):
    return next(s for s in outlines.current_outline(project)["sections"] if s["title"] == title)


def test_apply_skips_a_rename_when_the_title_changed_since_the_suggestion(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    intro = _sec(project, "Introduction")
    suggested = {"id": "1", "action": "rename", "title": "Introduction", "section": intro["id"],
                 "newTitle": "Introduction and aims", "why": "w"}
    project.rename_scene(project.root / intro["id"], "Background")          # the author retitles it meanwhile
    r = api.outline_apply([suggested, {**suggested, "id": "2", "action": "move", "part": "Article", "after": ""}])
    assert r["changed"] == [] and [s["id"] for s in r["skipped"]] == ["1", "2"]
    assert all(s["reason"] == "This section has changed since the suggestion." for s in r["skipped"])
    assert project.scene_title(project.root / intro["id"]) == "Background"
    assert not snapshots.list_snapshots(project, project.root / intro["id"])


def test_apply_ids_of_created_sections_stay_apart_from_original_ids(tmp_path, monkeypatch):
    never_ai(monkeypatch)
    project = ems_project(tmp_path)
    api = open_api(project)
    methods, intro = _sec(project, "Methods"), _sec(project, "Introduction")
    first_decl = _sec(project, "Software and data availability")
    mk = lambda i, t: {"id": i, "action": "add", "title": t, "part": "Article", "after": intro["id"],
                       "purpose": "p", "why": "w"}
    r = api.outline_apply([
        {"id": "1", "action": "rename", "title": "Methods", "section": methods["id"], "newTitle": "Approach", "why": "w"},
        {"id": "2", "action": "move", "title": "Methods", "section": methods["id"],
         "part": "Declarations and availability", "after": first_decl["id"], "why": "w"},
        mk("3", "Methods"), mk("4", "Scope"), mk("5", "Limits")])
    assert r["skipped"] == [], r
    assert len(r["created"]) == 3 and all((project.root / c).is_file() for c in r["created"])
    rows = outlines.current_outline(project)["sections"]
    article = [s["title"] for s in rows if s["partTitle"] == "Article"]
    assert article[article.index("Introduction") + 1:article.index("Introduction") + 4] == ["Methods", "Scope", "Limits"]
    by_id = {s["id"]: s["title"] for s in rows}
    assert [by_id[c] for c in r["created"]] == ["Methods", "Scope", "Limits"]
    assert by_id[r["remap"][methods["id"]]] == "Approach"
    assert r["remap"][methods["id"]] not in r["created"]
    decl = [s["title"] for s in rows if s["partTitle"] == "Declarations and availability"]
    assert decl.index("Approach") == 1


def test_clean_title_removes_comment_and_marker_fragments():
    for hostile in ('<!--ai id="x"-->Intro', "{{expand}}", "<!<!---- -->x", "{{{expand}}}"):
        out = oai.clean_title(hostile)
        assert not any(f in out for f in ("<!--", "-->", "{{", "}}")), out
    assert oai.clean_title('<!--ai id="x"-->Intro') == 'ai id="x"Intro'
    assert oai.clean_title("{{expand}}") == "expand"


def test_parse_caps_the_dropped_list():
    reply = json.dumps({"items": [{"action": "bogus"} for _ in range(5000)]})
    items, dropped = parse(reply)
    assert items == [] and len(dropped) == oai.MAX_DROPPED + 1
    assert dropped[-1]["reason"] == f"{5000 - oai.MAX_DROPPED} more items were dropped."


def test_parse_finds_json_after_lots_of_bracketed_prose():
    prose = "see [1] and $\alpha_{i}$ " * 500
    reply = prose + '\n{"items": [{"id": "1", "action": "advice", "title": "Tip", "why": "w"}]}'
    items, dropped = parse(reply)
    assert [i["title"] for i in items] == ["Tip"] and dropped == []
