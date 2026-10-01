"""Api: chat history, attachments and Save to notes (Wave 3.4). AI is mocked at the function boundary."""

from lorewrite.core import comments
from lorewrite.gui import api as api_module
from tests.test_gui_api import open_api

A = "manuscript/01-arrival.md"


def U(text, i=1):
    return {"id": f"u{i}", "role": "user", "text": text}


def R(text, i=1, **kw):
    return {"id": f"a{i}", "role": "assistant", "text": text, **kw}


def test_chat_history_round_trip(tmp_path):
    api, root = open_api(tmp_path)
    assert api.list_chats() == {"ok": True, "chats": []}
    r = api.save_chat(None, [U("What if the tram never stops?"), R("Then nobody leaves.")], "project",
                      [{"kind": "scene", "id": A}])
    assert r["ok"] and r["title"] == "What if the tram never stops?"
    cid = r["id"]
    assert (root / ".assistant" / "chats" / f"{cid}.json").is_file()
    listed = api.list_chats()["chats"]
    assert listed[0]["id"] == cid and listed[0]["count"] == 2
    chat = api.open_chat(cid)["chat"]
    assert chat["scope"] == "project" and chat["attachments"] == [{"kind": "scene", "id": A}]
    assert chat["messages"][1]["text"] == "Then nobody leaves."
    assert api.save_chat(cid, [U("What if the tram never stops?"), R("Then nobody leaves."), U("And then?", 2),
                               R("A mutiny.", 2)])["ok"]
    assert api.rename_chat(cid, "Tram idea")["chats"][0]["title"] == "Tram idea"
    assert api.delete_chat(cid)["chats"] == []
    assert api.open_chat(cid)["ok"] is False
    assert api.open_chat("../../project")["ok"] is False
    assert "nothing to save" in api.save_chat(None, [])["error"]


def test_ask_and_research_get_attachments_in_their_context(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    (root / "research").mkdir()
    (root / "research" / "tides.md").write_text("# Tides\n\nThe spur floods at dusk.\n")
    scene = root / A
    comments.add(root, scene, scene.read_text(), 3, 9, "make this punchier")
    seen = {}

    def fake_ask(prompt, context, model, history=None, client=None):
        seen["ask"] = context
        return "ok"

    def fake_research(prompt, context, model, history=None, client=None):
        seen["research"] = context
        return "floods [1]"

    monkeypatch.setattr(api_module, "ask_writer", fake_ask)
    monkeypatch.setattr(api_module, "research_writer", fake_research)
    att = [{"kind": "research", "id": "research/tides.md"}, {"kind": "comments", "id": A},
           {"kind": "scene", "id": "manuscript/02-the-archive.md"}, {"kind": "scene", "id": "nope.md"}]
    r = api.ask("what next?", "project", None, None, 0, [], att)
    assert r["ok"]
    assert "ATTACHED RESEARCH NOTE: Tides" in seen["ask"] and "ATTACHED COMMENTS ON SCENE: Arrival" in seen["ask"]
    assert "make this punchier" in seen["ask"] and "ATTACHED SCENE: The Archive" in seen["ask"]
    assert "Pending AI" not in seen["ask"] and "unaccepted AI draft" not in seen["ask"]       # drafts are not canon
    skipped = [x for x in r["attached"] if x["skipped"]]
    assert len(skipped) == 1 and skipped[0]["id"] == "nope.md"
    rr = api.research("when does it flood?", [], att)
    assert rr["ok"] and "ATTACHED COMMENTS ON SCENE" in seen["research"] and "[1] Tides" in seen["research"]
    # nothing attached: the context is exactly what it was before this feature
    api.ask("again", "project")
    assert "ATTACHED" not in seen["ask"]


def test_list_attachable_and_save_to_notes(tmp_path):
    api, root = open_api(tmp_path)
    scene = root / A
    comments.add(root, scene, scene.read_text(), 3, 9, "note")
    r = api.list_attachable()
    kinds = {(i["kind"], i["title"]) for i in r["items"]}
    assert r["ok"] and ("scene", "Arrival") in kinds and ("comments", "Arrival") in kinds and ("note", "Mara Vale") in kinds
    assert r["maxWords"] > 1000

    s = api.save_reply_to_notes("Why zeros?", "Because the caller was masked.")
    assert s["ok"] and s["id"] == "research/assistant-notes.md"
    text = (root / s["id"]).read_text()
    assert "**Prompt:** Why zeros?" in text and "Because the caller was masked." in text
    assert api.save_reply_to_notes("p", "")["ok"] is False
    ws = api.get_workspace()["workspace"]
    assert [x["id"] for x in ws["research"]] == ["research/assistant-notes.md"]       # a normal research note
