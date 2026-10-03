"""The context budget on whole projects: a long book stays under the model's window and reports
everything it leaves out; a small project sends exactly what it sent before the budget existed.
AI is mocked at the function boundary (lorewrite.gui.api.<fn>); nothing touches the network."""

import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from lorewrite.ai import writing
from lorewrite.ai.budget import Budget, BudgetError, estimate_tokens, fit
from lorewrite.ai.continuity import (
    ACCUMULATION_SCHEMA, ACCUMULATION_SYSTEM_PROMPT, CONTRADICTION_SCHEMA, SYSTEM_PROMPT, build_check_prompt,
    _details_block, plan_canon, plan_check, propose_canon_updates,
)
from lorewrite.ai.links import SCHEMA as ALIAS_SCHEMA, SYSTEM_PROMPT as ALIAS_PROMPT, build_prompt, plan_aliases
from lorewrite.ai.usage import LEDGER
from lorewrite.core import drafts, scenemeta
from lorewrite.core import entities as ent
from lorewrite.core.continuity import add_canon_facts, canon_map, get_canon
from lorewrite.core.links import find_all_links
from lorewrite.core.project import Project
from lorewrite.gui import api as api_module
from lorewrite.gui.api import Api

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "residual"
N_ENTITIES, N_SCENES = 400, 200


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("the network is blocked in tests")

    monkeypatch.setattr("lorewrite.ai.client.make_client", boom)
    monkeypatch.setattr("lorewrite.ai.client.list_models", boom)


def zed(i: int) -> str:
    return f"Zed{i:03d} Quill"


def make_big(root: Path) -> Project:
    """400 entities (each with ~1.4k chars of managed canon, so ~140k tokens in all) and 200 scenes,
    each mentioning three of them."""
    project = Project.create(root, "Big Book")
    (root / "manuscript" / "01-opening.md").unlink()
    for i in range(N_ENTITIES):
        canon = "\n".join(f"- {zed(i)} fact {j}: he keeps a ledger of small debts." for j in range(28))
        e = ent.Entity(name=zed(i), type="place" if i % 5 == 0 else "character", aliases=[f"Z{i:03d}"],
                       body=f"{zed(i)} is person number {i}.\n\n## Canon (auto)\n\n{canon}\n")
        ent.save_entity(e, project.entity_path(e))
    filler = " ".join(["The rain went on over the spur and nobody spoke."] * 12)
    for i in range(N_SCENES):
        text = (f"# Scene {i}\n\n{zed(i)} met {zed(i + 1)} near {zed(i + 2)}. {filler}\n")
        (root / "manuscript" / f"{i + 1:03d}-scene.md").write_text(text, encoding="utf-8")
    return Project.open(root)


@pytest.fixture
def big(tmp_path):
    root = tmp_path / "big"
    make_big(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


SCENE = "manuscript/006-scene.md"      # mentions Zed005, Zed006, Zed007
NAMES = {zed(5), zed(6), zed(7)}
ALL = {zed(i) for i in range(N_ENTITIES)}


def section(sent, name):
    return next(s for s in sent["sections"] if s["name"] == name)


def window_room(sent):
    return sent["window"] - sent["reserve"]


# -- continuity / canon / aliases on a long book --------------------------------------


def test_continuity_sends_only_the_scenes_entities_and_reports_every_other_name(big, monkeypatch):
    api, root = big
    seen = {}

    def fake(scene_text, entities, canon, model):
        seen.update(entities=[e.name for e in entities], canon=canon, text=scene_text)
        return []

    monkeypatch.setattr(api_module, "check_scene", fake)
    r = api.check_continuity(SCENE)
    assert r["ok"], r
    assert set(seen["entities"]) == NAMES and set(seen["canon"]) == NAMES
    notes = section(r["sent"], "Entity canon")
    assert (notes["itemsTotal"], notes["itemsSent"]) == (N_ENTITIES, 3)
    assert set(notes["itemsDropped"]) == ALL - NAMES                   # nothing dropped without a name
    prompt = build_check_prompt(seen["text"], seen["canon"])
    assert estimate_tokens(prompt) <= r["sent"]["estTokens"] <= window_room(r["sent"])
    assert r["sent"]["feature"] == "continuity" and r["sent"]["trimmed"] is True


def test_continuity_includes_the_scenes_pov_and_place_from_its_details(big, monkeypatch):
    api, root = big
    path = root / SCENE
    path.write_text(scenemeta.set_details(path.read_text(encoding="utf-8"), pov=zed(300), place=zed(310)),
                    encoding="utf-8")
    seen = {}
    monkeypatch.setattr(api_module, "check_scene",
                        lambda t, e, c, m: seen.update(names={x.name for x in e}) or [])
    r = api.check_continuity(SCENE)
    assert seen["names"] == NAMES | {zed(300), zed(310)}
    assert section(r["sent"], "Entity canon")["itemsSent"] == 5


def test_canon_proposals_send_only_the_scenes_entities(big, monkeypatch):
    api, root = big
    seen = {}
    monkeypatch.setattr(api_module, "propose_canon_updates",
                        lambda t, e, m: seen.update(names=[x.name for x in e]) or [])
    r = api.propose_canon(SCENE)
    assert r["ok"] and set(seen["names"]) == NAMES
    notes = section(r["sent"], "Entity notes")
    assert notes["itemsSent"] == 3 and set(notes["itemsDropped"]) == ALL - NAMES
    assert set(notes["truncated"]) == NAMES                              # each canon is over its 1500-char cap
    assert r["sent"]["estTokens"] <= window_room(r["sent"])


def test_alias_roster_is_complete_when_it_fits_and_capped_by_priority_when_it_does_not(big, monkeypatch):
    api, root = big
    seen = {}
    monkeypatch.setattr(api_module, "suggest_links",
                        lambda text, entities, model: seen.update(names=[e.name for e in entities]) or [])
    r = api.find_aliases(SCENE)
    assert r["ok"] and len(seen["names"]) == N_ENTITIES                  # names only: the whole roster fits
    assert section(r["sent"], "Known entities")["itemsDropped"] == []
    assert api.set_settings(context_window=8000)["ok"]                    # a small window: the roster is capped
    r = api.find_aliases(SCENE)
    assert r["ok"], r
    roster = section(r["sent"], "Known entities")
    assert 0 < roster["itemsSent"] < N_ENTITIES
    assert NAMES <= set(seen["names"])                                    # the scene's own entities come first
    assert set(seen["names"]) | set(roster["itemsDropped"]) == ALL
    assert not set(seen["names"]) & set(roster["itemsDropped"])
    assert r["sent"]["estTokens"] <= window_room(r["sent"])


# -- chat, brainstorm, draft, research --------------------------------------------------


def chat_mocks(api, monkeypatch):
    seen = {}
    monkeypatch.setattr(api_module, "ask_writer", lambda prompt, context, model, history=None: seen.update(ask=context) or "ok")
    monkeypatch.setattr(api_module, "brainstorm_writer", lambda context, model, client=None: seen.update(brain=context) or ["Idea."])
    return seen


def test_project_scope_chat_context_stays_under_the_window_and_reports_what_it_dropped(big, monkeypatch):
    api, root = big
    seen = chat_mocks(api, monkeypatch)
    r = api.ask("what happens?", "project")
    assert r["ok"], r
    sent = r["sent"]
    notes = section(sent, "Characters and places")
    assert notes["itemsSent"] < N_ENTITIES and notes["itemsTotal"] == N_ENTITIES
    kept_in_text = {n for n in ALL if f"### {n} (" in seen["ask"]}
    assert len(kept_in_text) == notes["itemsSent"]
    assert kept_in_text | set(notes["itemsDropped"]) == ALL and not kept_in_text & set(notes["itemsDropped"])
    titles = section(sent, "Scene titles")
    assert titles["itemsTotal"] == N_SCENES and titles["itemsSent"] == N_SCENES
    assert estimate_tokens(seen["ask"]) <= sent["estTokens"] <= window_room(sent)


def test_scene_chat_and_brainstorm_report_their_context(big, monkeypatch):
    api, root = big
    seen = chat_mocks(api, monkeypatch)
    r = api.ask("who is here?", "scene", SCENE, None, 20)
    assert r["ok"] and set(re.findall(r"### (Zed\d+ Quill) \(", seen["ask"])) == NAMES
    assert section(r["sent"], "Characters and places")["itemsSent"] == 3
    assert section(r["sent"], "Scene")["itemsSent"] == 1
    r = api.brainstorm(SCENE, None, 20)
    assert r["ok"] and r["sent"]["feature"] == "brainstorm" and "### Zed006 Quill (" in seen["brain"]
    assert estimate_tokens(seen["brain"]) <= r["sent"]["estTokens"] <= window_room(r["sent"])


def test_a_crowded_scene_drafts_within_the_window_and_names_the_notes_it_could_not_send(big, monkeypatch):
    api, root = big
    crowd = "manuscript/900-crowd.md"
    (root / crowd).write_text("# Crowd\n\n" + " ".join(f"{zed(i)} came." for i in range(100, 140)) + "\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(api_module, "generate_text",
                        lambda mode, instruction, context, model, selection=None, **k: seen.update(context=context) or "He smiled.")
    text = (root / crowd).read_text(encoding="utf-8")
    r = api.generate("draft", "a smile", crowd, text, 12, 12)
    assert r["ok"], r
    notes = section(r["sent"], "Characters and places")
    crowd_names = {zed(i) for i in range(100, 140)}
    kept = set(re.findall(r"### (Zed\d+ Quill) \(", seen["context"]))
    assert notes["itemsTotal"] == 40 and kept == {n for n in crowd_names if n not in notes["itemsDropped"]}
    assert kept and set(notes["itemsDropped"]) == crowd_names - kept     # every dropped note is named
    assert len(notes["truncated"]) <= len(kept)
    assert estimate_tokens(seen["context"]) <= r["sent"]["estTokens"] <= window_room(r["sent"])


def test_research_context_reports_its_notes_and_canon(big, monkeypatch):
    api, root = big
    nb = api.new_research_note("Tide tables")["id"]
    (root / nb).write_text("# Tide tables\n\nThe spur floods at dusk. " * 3, encoding="utf-8")
    seen = {}
    monkeypatch.setattr(api_module, "research_writer",
                        lambda prompt, context, model, history=None: seen.update(context=context) or "ok [1]")
    r = api.research("tide tables")
    assert r["ok"], r
    assert section(r["sent"], "Research notes")["itemsSent"] == 1
    assert section(r["sent"], "Characters and places")["itemsDropped"]    # the 12000-char canon cap, reported
    assert "[1] Tide tables" in seen["context"]
    assert estimate_tokens(seen["context"]) <= r["sent"]["estTokens"] <= window_room(r["sent"])


def test_attachments_are_merged_into_the_sent_report_not_listed_twice(big, monkeypatch):
    api, root = big
    chat_mocks(api, monkeypatch)
    r = api.ask("q", "scene", SCENE, None, 0, [], [{"kind": "scene", "id": "manuscript/010-scene.md"},
                                                    {"kind": "scene", "id": "manuscript/missing.md"}])
    assert r["ok"] and len(r["attached"]) == 2
    att = section(r["sent"], "Attachments")
    assert att["itemsTotal"] == 2 and att["itemsSent"] == 1 and att["itemsDropped"] == [r["attached"][1]["title"]]
    assert [s["name"] for s in r["sent"]["sections"]].count("Attachments") == 1
    assert r["sent"]["attached"] == r["attached"]


# -- over the window: an actionable error before any network call, no cost ---------------


def test_a_window_too_small_for_the_request_is_refused_before_the_ai_is_called(big, monkeypatch):
    api, root = big
    calls = []

    def spy(name):
        def fake(*a, **k):
            calls.append(name)
            LEDGER.record("mock", name, 0.01)
            return []
        return fake

    for name in ("suggest_links", "check_scene", "propose_canon_updates", "generate_text", "ask_writer",
                 "brainstorm_writer", "research_writer"):
        monkeypatch.setattr(api_module, name, spy(name))
    nb = api.new_research_note("Tides")["id"]
    (root / nb).write_text("# Tides\n\nThe spur floods at dusk.\n", encoding="utf-8")
    assert api.set_settings(context_window=2000)["ok"]                    # 2k window, 4k reserved for the reply
    text = (root / SCENE).read_text(encoding="utf-8")
    spent = LEDGER.count()
    results = [
        api.find_aliases(SCENE), api.check_continuity(SCENE), api.propose_canon(SCENE),
        api.generate("draft", "x", SCENE, text, 0, 0), api.ask("q", "scene", SCENE, None, 0),
        api.brainstorm(SCENE, None, 0), api.research("tides?"),
    ]
    for r in results:
        assert r["ok"] is False, r
        assert "context window" in r["error"] and "Nothing was sent" in r["error"]
        assert "bigger context window" in r["error"] and "tokens" in r["error"]
        assert not r["error"].startswith("BudgetError")
    assert calls == [] and LEDGER.count() == spent                         # no AI call, no cost recorded
    assert "shorten the scene" in results[4]["error"]


def test_a_huge_attachment_is_named_in_the_error(big, monkeypatch):
    api, root = big
    chat_mocks(api, monkeypatch)
    api.set_settings(context_window=3000)
    r = api.ask("q", "scene", SCENE, None, 0, [], [{"kind": "scene", "id": "manuscript/010-scene.md"}])
    assert r["ok"] is False and "Attachments" in r["error"] and "remove attachments" in r["error"]


def test_the_window_comes_from_the_models_remembered_context_length(big, monkeypatch):
    from lorewrite.ai.client import remember_context_lengths, ModelInfo

    api, root = big
    chat_mocks(api, monkeypatch)
    model = api.ai_status()["models"]["writing"]
    remember_context_lengths([ModelInfo(model, "W", None, None, 123_000)])
    r = api.ask("what happens?", "project")
    assert r["ok"] and r["sent"]["window"] == 123_000
    notes = section(r["sent"], "Characters and places")                   # the fixed 12k-char cap still applies
    assert notes["itemsSent"] < N_ENTITIES


def test_the_setting_is_validated_and_shown(tmp_path):
    api, root = Api(), tmp_path / "p"
    from tests.gui_helpers import make_project

    make_project(root)
    assert api.open_project(str(root))["ok"]
    assert api.get_settings()["contextWindow"] == ""
    assert api.set_settings(context_window=64000)["ok"] and api.get_settings()["contextWindow"] == 64000
    for bad in (5, "lots", True, 10 ** 12):
        r = api.set_settings(context_window=bad)
        assert r["ok"] is False and "context window" in r["error"]
    assert api.get_settings()["contextWindow"] == 64000
    assert api.set_settings(context_window="")["ok"] and api.get_settings()["contextWindow"] == ""


# -- small projects send what they always sent --------------------------------------------


@pytest.fixture
def small(tmp_path):
    root = tmp_path / "residual"
    shutil.copytree(EXAMPLE, root)
    return Project.open(root), root


def legacy_build_context(scene_text, cursor_offset, entities, canon_by_name, style_md, span=None,
                         originals=None, voice_samples=None):
    """build_context as it was before the budget (ai/writing.py): the reference for equivalence."""
    from lorewrite.core.entities import resolve

    marked = writing._marked_scene(scene_text, cursor_offset, span, originals)
    before, _, after = marked.partition(writing.CURSOR)
    window = writing._tail_words(before, writing.CONTEXT_WORDS) + writing.CURSOR + writing._head_words(
        after, writing.CONTEXT_WORDS)
    sections = []
    if style_md and style_md.strip():
        sections.append("STYLE GUIDE:\n" + style_md.strip())
    names = [n for e in entities for n in e.names]
    mentioned = []
    for link in find_all_links(scenemeta.blank(drafts.strip_pending(scene_text, originals),
                                               keep=scenemeta.MENTION_FIELDS), names):
        entity = resolve(link.target, entities)
        if entity is not None and entity not in mentioned:
            mentioned.append(entity)
    notes, used = [], 0
    for entity in mentioned:
        note = (canon_by_name.get(entity.name) or entity.body or "").strip()[:writing.ENTITY_CHARS]
        if not note or used + len(note) > writing.ENTITY_TOTAL_CHARS:
            continue
        used += len(note)
        notes.append(f"### {entity.name} ({entity.type})\n{note}")
    if notes:
        sections.append("CHARACTERS AND PLACES:\n" + "\n\n".join(notes))
    if voice_samples:
        sections.append("THE AUTHOR'S OWN PROSE (match this voice; do not reuse its content):\n"
                        + "\n\n".join(para for _, para in voice_samples))
    details = scenemeta.header(scene_text)
    if details:
        sections.append("SCENE DETAILS (the author's plan for this scene):\n" + details)
    sections.append("SCENE (the new text goes at " + writing.CURSOR + "):\n" + window)
    return "\n\n".join(sections)


def legacy_project_context(scene_titles, entities, canon_by_name, style_md):
    sections = []
    if style_md and style_md.strip():
        sections.append("STYLE GUIDE:\n" + style_md.strip())
    if scene_titles:
        sections.append("SCENES (in order):\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(scene_titles, 1)))
    notes, used = [], 0
    for entity in entities:
        note = (canon_by_name.get(entity.name) or entity.body or "").strip()[:writing.ENTITY_CHARS]
        if used + len(note) > writing.PROJECT_CONTEXT_CHARS:
            continue
        used += len(note)
        heading = f"### {entity.name} ({entity.type})"
        notes.append(f"{heading}\n{note}" if note else heading)
    if notes:
        sections.append("CHARACTERS AND PLACES:\n" + "\n\n".join(notes))
    return "\n\n".join(sections) or "(the project is empty)"


def legacy_canon_map(entities):
    out = {}
    for e in entities:
        managed = get_canon(e.body)
        out[e.name] = managed if managed else e.body[:1500]
    return out


def legacy_roster(entities):
    roster = []
    for e in entities:
        line = f"- {e.name} ({e.type})"
        if e.aliases:
            line += f" — aliases: {', '.join(e.aliases)}"
        canon = get_canon(e.body)[:1500]
        line += f"\n  existing canon:\n{canon}" if canon else "\n  existing canon: (none)"
        roster.append(line)
    return "\n".join(roster)


def test_small_project_has_few_entities(small):
    project, root = small
    assert len(project.load_entities()) == 8


def test_small_project_draft_chat_and_brainstorm_contexts_are_unchanged(small):
    project, root = small
    entities = project.load_entities()
    canon = canon_map(entities)
    style = "## Voice\n- close third, present tense\n"
    checked = 0
    for scene in project.list_scenes():
        text = scene.read_text(encoding="utf-8")
        for offset in (0, len(text) // 2, len(text)):
            for kwargs in ({}, {"voice_samples": [("a", "Rain fell."), ("b", "Nobody spoke.")]},
                           {"span": (offset, min(len(text), offset + 30))}):
                span = kwargs.get("span")
                want = legacy_build_context(text, offset, entities, canon, style, **kwargs)
                assert writing.build_context(text, offset, entities, canon, style, **kwargs) == want
                sections = writing.build_context_sections(text, offset, entities, canon, style, **kwargs)
                context, report = writing.fit_context(
                    [*sections, writing.generate_instructions("draft", "a smile", None)], "any/model", "draft")
                assert context == want                                       # through the 32k budget as well
                assert not report.trimmed and report.dropped == () and report.truncated == ()
                checked += 1
    assert checked >= 12
    titles = [project.scene_title(p) for p in project.list_scenes()]
    want = legacy_project_context(titles, entities, canon, style)
    assert writing.build_project_context(titles, entities, canon, style) == want
    context, report = writing.fit_context(
        [*writing.build_project_context_sections(titles, entities, canon, style),
         writing.chat_instructions(writing.ASK_SYSTEM_PROMPT, "q", [])], "any/model", "ask")
    assert context == want and not report.trimmed
    assert writing.build_project_context([], [], {}, None) == "(the project is empty)"


def test_small_project_research_context_is_unchanged(small):
    project, root = small
    entities = project.load_entities()
    canon = canon_map(entities)
    (root / "notebook").mkdir(exist_ok=True)
    (root / "notebook" / "tides.md").write_text("# Tides\n\nThe spur floods at dusk when the drains fail.\n", encoding="utf-8")
    sections, hits = writing.research_sections(project, entities, canon, "tides")
    context, report = writing.fit_context(sections, "any/model", "research")
    notes = [(h.note.title, h.excerpt) for h in hits]
    head = "RESEARCH NOTES:\n" + "\n\n".join(f"[{i}] {t}\n{b.strip()}" for i, (t, b) in enumerate(notes, 1))
    assert context == head + "\n\n" + legacy_project_context([], entities, canon, None)
    assert not report.trimmed
    assert writing.research_context(project, entities, canon, "tides")[0] == context


def test_small_project_continuity_canon_and_alias_requests_are_unchanged(small):
    project, root = small
    entities = project.load_entities()
    for scene in project.list_scenes():
        text = scene.read_text(encoding="utf-8")
        legacy = legacy_canon_map(entities)
        assert canon_map(entities) == legacy                                # notes under the old cap: identical
        subset, canon, report = plan_check(text, entities, canon_map(entities), Budget(200_000))
        assert [e.name for e in subset] == [e.name for e in entities] and canon == legacy
        assert build_check_prompt(text, canon) == build_check_prompt(text, legacy)
        assert not report.trimmed and by_dropped(report) == []
        out, report = plan_canon(text, entities, Budget(200_000))
        assert out == entities and all(a is b for a, b in zip(out, entities)) and not report.trimmed
        out, report = plan_aliases(text, entities, Budget(200_000))
        assert out == entities and not report.trimmed
        assert build_prompt(text, out) == build_prompt(text, entities)
        # the same entities whatever the window is, as long as they fit (the default 32k window)
        assert [e.name for e in plan_check(text, entities, legacy, Budget.for_model("m/x", {}, {}))[0]] == \
            [e.name for e in entities]


def by_dropped(report):
    return list(report.dropped)


def test_small_project_canon_prompt_is_unchanged(small):
    project, root = small
    entities = project.load_entities()
    # one note with a long managed canon, still under the 1500-character cap: sent whole, as before
    long_note = entities[0]
    long_note.body = add_canon_facts(long_note.body, [f"fact {i} about the thing." for i in range(40)])
    assert 800 < len(get_canon(long_note.body)) < 1500
    text = project.list_scenes()[0].read_text(encoding="utf-8")
    captured = {}

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"updates": []}'))],
                                           usage=None)

    out, _ = plan_canon(text, entities, Budget(200_000))
    propose_canon_updates(text, out, "m", client=Client)
    prompt = captured["messages"][1]["content"]
    assert prompt == (f"ENTITIES:\n{legacy_roster(entities)}\n\n"
                      f"{_details_block(text)}SCENE:\n{scenemeta.strip(text)}")


def test_small_project_bridge_returns_the_report_beside_the_existing_fields(small, monkeypatch):
    project, root = small
    api = Api()
    assert api.open_project(str(root))["ok"]
    rel = "manuscript/01-rain-on-the-spur.md"
    seen = {}
    monkeypatch.setattr(api_module, "check_scene", lambda t, e, c, m: seen.update(n=len(e), canon=c) or [])
    monkeypatch.setattr(api_module, "propose_canon_updates", lambda t, e, m: seen.update(canon_n=len(e)) or [])
    monkeypatch.setattr(api_module, "suggest_links", lambda t, e, m: seen.update(alias_n=len(e)) or [])
    monkeypatch.setattr(api_module, "generate_text", lambda mode, i, c, m, selection=None, **k: "Text.")
    monkeypatch.setattr(api_module, "ask_writer", lambda p, c, m, history=None: "ok")
    monkeypatch.setattr(api_module, "brainstorm_writer", lambda c, m, client=None: ["Idea."])
    monkeypatch.setattr(api_module, "research_writer", lambda p, c, m, history=None: "ok")
    (root / "notebook").mkdir(exist_ok=True)
    (root / "notebook" / "tides.md").write_text("# Tides\n\nThe spur floods at dusk.\n", encoding="utf-8")
    text = (root / rel).read_text(encoding="utf-8")
    results = {
        "continuity": api.check_continuity(rel), "canon": api.propose_canon(rel), "aliases": api.find_aliases(rel),
        "draft": api.generate("draft", "x", rel, text, 5, 5), "ask": api.ask("q", "scene", rel, None, 0),
        "brainstorm": api.brainstorm(rel, None, 0), "research": api.research("tides?"),
    }
    assert seen["n"] == seen["canon_n"] == seen["alias_n"] == 8              # every entity, as before
    for feature, r in results.items():
        assert r["ok"], (feature, r)
        sent = r["sent"]
        json.dumps(sent)
        assert sent["feature"] == feature and sent["trimmed"] is False and not sent["overBudget"]
        assert 0 < sent["estTokens"] < sent["window"] and sent["sections"]
        assert all(s["itemsDropped"] == [] and s["truncated"] == [] for s in sent["sections"]), feature
    assert "cost" in results["ask"] and "attached" in results["ask"] and "reply" in results["ask"]


# -- the terminal app: a one-line summary after each AI call, and the same refusal ----------


async def test_tui_notification_carries_the_sent_summary_and_a_too_small_window_refuses(tmp_path, monkeypatch):
    import lorewrite.tui.app as app_mod
    from lorewrite.core import settings as user_settings
    from lorewrite.tui.app import LorewriteApp

    proj = Project.create(tmp_path / "novel", title="Budget")
    proj.create_entity("Borin")
    calls = []

    def fake_suggest(text, entities, model):
        calls.append(len(entities))
        LEDGER.record(model, "links", 0.0123)
        return []

    monkeypatch.setattr(app_mod, "suggest_links", fake_suggest)
    notified: list[str] = []
    monkeypatch.setattr(LorewriteApp, "notify", lambda self, message, **kw: notified.append(str(message)))
    app = LorewriteApp(proj)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.action_find_aliases()
        await pilot.pause(1.0)
        assert calls == [1]
        assert any("(AI $0.0123)" in m and re.search(r"sent ~\d+ tokens of 32k", m) for m in notified), notified
        notified.clear()
        user_settings.set("context_window", 2000)
        app.action_find_aliases()
        await pilot.pause(1.0)
        assert calls == [1]                                              # the second request never reached the AI
        assert any("Alias search failed" in m and "context window" in m for m in notified), notified
