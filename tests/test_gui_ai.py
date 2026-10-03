"""Api AI features. AI is mocked at the function boundary (lorewrite.gui.api.<fn>);
make_client is booby-trapped so nothing can reach the network."""

import threading
from types import SimpleNamespace

import pytest

from lorewrite.ai.continuity import CanonUpdate
from lorewrite.ai.links import Suggestion
from lorewrite.core import drafts
from lorewrite.core.continuity import Contradiction
from lorewrite.gui import api as api_module
from tests.test_gui_api import open_api

SCENE = "manuscript/01-arrival.md"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("No OpenRouter API key (network is blocked in tests)")

    monkeypatch.setattr("lorewrite.ai.client.make_client", boom)
    monkeypatch.setattr("lorewrite.ai.client.list_models", boom)


def test_ai_status_and_unmocked_calls_fail_cleanly(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "get_api_key", lambda: None)
    status = api.ai_status()
    assert status["hasKey"] is False and set(status["models"]) == {"fast", "strong", "writing", "image"}
    before = (root / SCENE).read_text()
    for call in (lambda: api.find_aliases(SCENE), lambda: api.check_continuity(SCENE),
                 lambda: api.propose_canon(SCENE), lambda: api.learn_style(),
                 lambda: api.ask("hi", "scene", SCENE),
                 lambda: api.generate("draft", "x", SCENE, before, 0, 0),
                 lambda: api.describe_scene(SCENE, None, 0),
                 lambda: api.generate_inspiration("a pier", SCENE)):
        r = call()
        assert r["ok"] is False and "API key" in r["error"]
    assert (root / SCENE).read_text() == before


def test_find_aliases_review_then_apply(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    seen = {}

    def fake(scene_text, entities, model):
        seen.update(text=scene_text, model=model)
        i = scene_text.index("the archivist")
        return [Suggestion("Mara Vale", i, i + len("the archivist"), "the archivist")]

    monkeypatch.setattr(api_module, "suggest_links", fake)
    text = "Then the archivist left. <!--ai-->the archivist again<!--/ai-->"
    r = api.find_aliases(SCENE, text)
    assert r["suggestions"][0]["entity"] == "Mara Vale"
    assert r["suggestions"][0]["alias"] == "the archivist"
    assert "again" not in seen["text"]  # pending AI text is blanked before the model sees it
    assert len(seen["text"]) == len(text)
    # nothing changed until the author accepts
    assert "the archivist" not in api.get_entity("Mara Vale")["aliases"]
    assert api.apply_aliases([{"entity": "Mara Vale", "surface": "The archivist"}])["added"] == 1
    assert "the archivist" in api.get_entity("Mara Vale")["aliases"]  # alias_form lowercases the article
    assert api.apply_aliases([{"entity": "Mara Vale", "surface": "the archivist"}])["added"] == 0
    assert api.apply_aliases([{"entity": "Nobody", "surface": "x"}])["added"] == 0


def test_check_continuity_waive_and_restore(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    issue = Contradiction("physical_attribute", "error", "Mara Vale",
                          "Elias was waiting under the clock.", "Use green eyes", "", None)
    captured = {}

    def fake(scene_text, entities, canon, model):
        captured.update(text=scene_text, canon=canon)
        return [issue]

    monkeypatch.setattr(api_module, "check_scene", fake)
    text = (root / SCENE).read_text() + "\n<!--ai-->AI only<!--/ai-->\n"
    r = api.check_continuity(SCENE, text)
    assert len(r["issues"]) == 1 and r["waived"] == 0
    got = r["issues"][0]
    assert got["row"] == 3 and got["entity"] == "Mara Vale" and got["fix"] == "Use green eyes"
    assert "AI only" not in captured["text"] and "Mara Vale" in captured["canon"]
    assert api.waive(got["key"], SCENE)["ok"]
    again = api.check_continuity(SCENE, text)
    assert again["issues"] == [] and again["waived"] == 1
    assert api.restore_waivers(SCENE)["restored"] == 1
    assert len(api.check_continuity(SCENE, text)["issues"]) == 1


def test_propose_and_apply_canon_adds_only(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "propose_canon_updates", lambda t, e, m: [
        CanonUpdate("Mara Vale", ("Has a scar on her left hand", "Drinks tea"), "she rubbed the scar", "")])
    r = api.propose_canon(SCENE)
    assert r["updates"][0]["facts"] == ["Has a scar on her left hand", "Drinks tea"]
    note = root / "entities/characters/mara-vale.md"
    before = note.read_text()
    assert api.apply_canon([{"entity": "Mara Vale", "facts": ["Has a scar on her left hand"]}])["applied"] == 1
    after = note.read_text()
    assert "Has a scar on her left hand" in after and "Drinks tea" not in after
    assert after.startswith(before.rstrip("\n")[:40])
    assert api.get_entity("Mara Vale")["canon"].count("scar") == 1
    assert api.apply_canon([{"entity": "Mara Vale", "facts": []}])["applied"] == 0


def test_learn_style_then_save_with_backup(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    monkeypatch.setattr(api_module, "learn_style",
                        lambda samples, model, **kw: SimpleNamespace(markdown="# Style guide\n\nDry.\n"))
    r = api.learn_style()
    assert r["markdown"].startswith("# Style guide") and r["replacing"] is False
    assert not (root / "style.md").exists()  # proposal only
    assert api.save_style(r["markdown"])["id"] == "style.md"
    assert api.get_workspace()["workspace"]["status"]["hasStyle"] is True
    assert api.learn_style()["replacing"] is True
    api.save_style("# Style guide\n\nWarm.\n")
    assert (root / "style.md.bak").read_text().startswith("# Style guide\n\nDry.")
    assert api.read_document("style.md")["kind"] == "style"


def gen(api, monkeypatch, body, mode, instruction, text, start, end):
    monkeypatch.setattr(api_module, "generate_text", lambda m, i, c, model, selection=None, **k: body)
    return api.generate(mode, instruction, SCENE, text, start, end)


def test_generate_draft_returns_wrapped_text_and_inserts_nothing(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    text = (root / SCENE).read_text()
    at = text.index("Elias") + 5
    r = gen(api, monkeypatch, "He smiled.", "draft", "a smile", text, at, at)
    assert r["insert"] == "<!--ai--> He smiled.<!--/ai-->"  # glued to "Elias": a space is added
    assert (r["from"], r["to"]) == (at, at) and r["draftId"] is None
    assert (root / SCENE).read_text() == text  # the file is untouched
    assert drafts.load_originals(root, root / SCENE) == {}


def test_generate_rewrite_register_then_accept_or_reject(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    text = (root / SCENE).read_text()
    a = text.index("The rain")
    b = text.index("three days") + len("three days")
    r = gen(api, monkeypatch, "It poured.", "rewrite", "shorter", text, a, b)
    original = text[a:b]
    assert r["original"] == original and len(r["draftId"]) == 6
    assert r["insert"].startswith(f'<!--ai id="{r["draftId"]}"-->')
    # the marker needs its original first
    assert api.register_draft(SCENE, r["draftId"], r["original"])["ok"]
    new_text = text[:r["from"]] + r["insert"] + text[r["to"]:]
    # reject restores the original
    rej = api.resolve_drafts(SCENE, new_text, accept=False, index=0)
    e = rej["edits"][0]
    assert new_text[:e["from"]] + e["insert"] + new_text[e["to"]:] == text
    assert drafts.load_originals(root, root / SCENE) == {}  # sidecar entry dropped
    # accept keeps the body
    api.register_draft(SCENE, r["draftId"], r["original"])
    acc = api.resolve_drafts(SCENE, new_text, accept=True)
    e = acc["edits"][0]
    assert (new_text[:e["from"]] + e["insert"] + new_text[e["to"]:]).count("It poured.") == 1
    assert "<!--" not in new_text[:e["from"]] + e["insert"] + new_text[e["to"]:]


def test_reject_refuses_when_the_original_is_missing(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    text = 'Before <!--ai id="abc123"-->new prose<!--/ai--> after'
    r = api.resolve_drafts(SCENE, text, accept=False)
    assert r["edits"] == [] and r["skipped"] == 1  # never delete prose on a failed lookup
    acc = api.resolve_drafts(SCENE, text, accept=True)
    assert acc["edits"][0]["insert"] == "new prose"
    assert api.resolve_drafts(SCENE, text, accept=True, index=5)["ok"] is False
    assert api.resolve_drafts(SCENE, "no drafts here", accept=True)["edits"] == []


def test_resolve_all_edits_are_back_to_front_and_utf16(tmp_path):
    api, root = open_api(tmp_path)
    text = "\U0001F600 <!--ai-->one<!--/ai--> mid <!--ai-->two<!--/ai-->"
    r = api.resolve_drafts(SCENE, text, accept=True)
    assert [e["insert"] for e in r["edits"]] == ["two", "one"]  # last first
    units = text.encode("utf-16-le")
    first = r["edits"][1]
    assert first["from"] == 3  # the emoji is two UTF-16 units, then a space
    js_text = units.decode("utf-16-le")
    out = js_text
    for e in r["edits"]:
        raw = out.encode("utf-16-le")
        out = (raw[:e["from"] * 2] + e["insert"].encode("utf-16-le") + raw[e["to"] * 2:]).decode("utf-16-le")
    assert out == "\U0001F600 one mid two"


def test_register_draft_validates_and_draft_from_reply(tmp_path):
    api, root = open_api(tmp_path)
    assert api.register_draft(SCENE, "NOT-OK", "x")["ok"] is False
    assert api.register_draft("entities/characters/mara-vale.md", "abc123", "x")["ok"] is False
    r = api.draft_from_reply(SCENE, "Hello", "World", 5)
    assert r["insert"] == "<!--ai--> World<!--/ai-->" and (r["from"], r["to"]) == (5, 5)


def test_ask_scene_and_project_scope_never_touch_the_manuscript(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    seen = []
    monkeypatch.setattr(api_module, "ask_writer",
                        lambda prompt, context, model, history=None: seen.append((prompt, context, history)) or "An answer.")
    before = {p.name: p.read_text() for p in (root / "manuscript").glob("*.md")}
    r = api.ask("who is Mara?", "scene", SCENE, None, 10, [{"role": "user", "text": "earlier"}])
    assert r["reply"] == "An answer."
    prompt, context, history = seen[-1]
    assert "<<CURSOR>>" in context and "Arrival" not in context.split("SCENE")[0] and history == [{"role": "user", "text": "earlier"}]
    api.ask("outline?", "project", None)
    context = seen[-1][1]
    assert "SCENES (in order)" in context and "1. Arrival" in context and "Mara Vale" in context
    assert before == {p.name: p.read_text() for p in (root / "manuscript").glob("*.md")}


def test_a_slow_ai_call_does_not_block_saves(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    started, release = threading.Event(), threading.Event()

    def slow(scene_text, entities, canon, model):
        started.set()
        assert release.wait(10)
        return []

    monkeypatch.setattr(api_module, "check_scene", slow)
    result = {}
    t = threading.Thread(target=lambda: result.update(api.check_continuity(SCENE)))
    t.start()
    assert started.wait(5)
    saved = {}
    t2 = threading.Thread(target=lambda: saved.update(api.save_document(SCENE, "# Arrival\n\nEdited.\n", None, force=True)))
    t2.start()
    t2.join(3)
    assert not t2.is_alive() and saved["saved"] is True  # the lock was not held during the call
    release.set()
    t.join(5)
    assert result["ok"] and result["issues"] == []


def test_ensure_style_creates_the_stub_once(tmp_path):
    api, root = open_api(tmp_path)
    assert not (root / "style.md").exists()
    assert api.ensure_style()["id"] == "style.md"
    stub = (root / "style.md").read_text()
    assert stub.startswith("# Style guide") and "## Voice" in stub
    (root / "style.md").write_text("# Style guide\n\nMine.\n")
    api.ensure_style()  # never overwrites
    assert "Mine." in (root / "style.md").read_text()
    binder = {n["id"]: n for n in api.get_workspace()["workspace"]["binder"]}
    assert "meta" not in binder["style.md"]


# -- the open item as the subject of a question (subject_id) -------------------------------------

MARA = "entities/characters/mara-vale.md"
MARA_NOTE = ("---\nname: Mara Vale\ntype: character\naliases: [Mara]\n---\n\n"
             "Left-handed archivist; hums when she lies.\n")


def _subject_api(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    (root / MARA).write_text(MARA_NOTE, encoding="utf-8")
    api.reload_entities()
    nb = api.new_research_note("Tide tables")["id"]
    (root / nb).write_text("# Tide tables\n\nThe spur floods at dusk.\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(api_module, "ask_writer",
                        lambda prompt, context, model, history=None: seen.update(ask=context) or "ok")
    monkeypatch.setattr(api_module, "brainstorm_writer",
                        lambda context, model, client=None: seen.update(brain=context) or ["Idea."])
    return api, root, nb, seen


def test_subject_entity_note_goes_into_ask_and_brainstorm_context(tmp_path, monkeypatch):
    api, root, nb, seen = _subject_api(tmp_path, monkeypatch)
    # no scene open, the whole project, plus the subject
    assert api.ask("who?", "scene", None, None, 0, [], [], MARA)["ok"]
    ctx = seen["ask"]
    assert "SCENES (in order)" in ctx and "SUBJECT (character): Mara Vale" in ctx
    assert ctx.endswith("Left-handed archivist; hums when she lies.")
    assert "aliases: [Mara]" not in ctx.split("SUBJECT")[1]            # frontmatter is not part of it
    # a scene is open as well: the scene context stays, the subject is appended
    assert api.ask("who?", "scene", SCENE, None, 10, [], [], MARA)["ok"]
    ctx = seen["ask"]
    assert "<<CURSOR>>" in ctx and ctx.index("<<CURSOR>>") < ctx.index("SUBJECT (character): Mara Vale")
    assert api.brainstorm(None, None, 0, [], MARA)["ok"]
    assert "SUBJECT (character): Mara Vale" in seen["brain"] and "SCENES (in order)" in seen["brain"]
    assert api.brainstorm(SCENE, None, 5, [], MARA)["ok"]
    assert "<<CURSOR>>" in seen["brain"] and "Left-handed archivist" in seen["brain"]


def test_subject_notebook_note_and_scene_subject(tmp_path, monkeypatch):
    api, root, nb, seen = _subject_api(tmp_path, monkeypatch)
    assert api.ask("tides?", "scene", None, None, 0, [], [], nb)["ok"]
    assert "SUBJECT (notebook note): Tide tables" in seen["ask"] and "floods at dusk" in seen["ask"]
    assert api.brainstorm(None, None, 0, [], nb)["ok"] and "floods at dusk" in seen["brain"]
    # a scene as the subject is simply the scene context (the editor text is honoured)
    assert api.ask("scene?", "scene", None, "Mara waits.", 0, [], [], SCENE)["ok"]
    assert "<<CURSOR>>Mara waits." in seen["ask"] and "SUBJECT" not in seen["ask"] and "<<CURSOR>>" in seen["ask"]
    # ... unless the author asked for the whole project: then no scene text goes
    assert api.ask("scene?", "project", None, None, 0, [], [], SCENE)["ok"]
    assert "SCENES (in order)" in seen["ask"] and "<<CURSOR>>" not in seen["ask"]


def test_subject_text_is_capped_like_an_attachment(tmp_path, monkeypatch):
    from lorewrite.core import attach

    api, root, nb, seen = _subject_api(tmp_path, monkeypatch)
    (root / nb).write_text("# Tide tables\n\n" + "tide " * 5000, encoding="utf-8")
    assert api.ask("tides?", "scene", None, None, 0, [], [], nb)["ok"]
    sent = seen["ask"].split("SUBJECT (notebook note): Tide tables\n", 1)[1]
    assert 0 < len(sent) <= attach.ITEM_CHARS and sent.endswith("…")


def test_without_a_subject_the_context_is_unchanged_and_no_note_text_is_sent(tmp_path, monkeypatch):
    api, root, nb, seen = _subject_api(tmp_path, monkeypatch)
    api.ask("q", "scene", SCENE, None, 10)
    plain = seen["ask"]
    assert api.ask("q", "scene", SCENE, None, 10, None, None, None)["ok"] and seen["ask"] == plain
    assert "SUBJECT" not in plain and "floods at dusk" not in plain           # the notebook is not canon
    api.ask("q", "project", None)
    assert "SUBJECT" not in seen["ask"] and "floods at dusk" not in seen["ask"]
    api.brainstorm(None)
    assert "SUBJECT" not in seen["brain"] and "floods at dusk" not in seen["brain"]
    # an empty / null subject is "off"
    api.ask("q", "scene", SCENE, None, 10, [], [], "")
    assert seen["ask"] == plain


def test_unknown_or_unsuitable_subject_fails_cleanly_without_an_ai_call(tmp_path, monkeypatch):
    api, root, nb, seen = _subject_api(tmp_path, monkeypatch)
    for bad in ("entities/characters/nobody.md", "../x.md", "notebook/none.md", "style.md", "dictionary.txt", "nope"):
        r = api.ask("q", "scene", None, None, 0, [], [], bad)
        assert r["ok"] is False, bad
        assert api.brainstorm(None, None, 0, [], bad)["ok"] is False, bad
    assert seen == {}                                                   # nothing was sent


def test_subject_goes_through_the_job_runner_and_chat_context_has_no_images(tmp_path, monkeypatch):
    from lorewrite.core import inspiration as store

    api, root, nb, seen = _subject_api(tmp_path, monkeypatch)
    store.save(api.project, b"\xff\xd8\xff\xe0IMAGEBYTES", "jpg", {"prompt": "A tall woman", "for": MARA})
    assert api.ask("who?", "scene", None, None, 0, [], [], MARA)["ok"]
    assert "IMAGEBYTES" not in seen["ask"] and "A tall woman" not in seen["ask"] and "inspiration" not in seen["ask"]
    assert api.brainstorm(None, None, 0, [], MARA)["ok"]
    assert "IMAGEBYTES" not in seen["brain"] and "A tall woman" not in seen["brain"]
    assert api.AI_JOBS["ask"] == "ask" and api.AI_JOBS["brainstorm"] == "brainstorm"
