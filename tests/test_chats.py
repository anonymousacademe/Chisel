"""Saved assistant chats, attachments and Save to notes (Wave 3.4, core)."""

import json
from datetime import datetime

import pytest

from lorewrite.core import attach, chats, comments, research
from tests.gui_helpers import make_project


def U(text, i=1):
    return {"id": f"u{i}", "role": "user", "text": text}


def A(text, i=1, **kw):
    return {"id": f"a{i}", "role": "assistant", "text": text, **kw}


def test_save_creates_a_titled_plain_json_chat(tmp_path):
    project = make_project(tmp_path / "p")
    chat = chats.save(project, None, [U("How would Mara react to the news about the elevator?" + " x" * 40), A("Calmly.")],
                      "project", [{"kind": "scene", "id": "manuscript/01-arrival.md"}, {"kind": "bogus", "id": "x"}])
    assert chat.id.startswith("c") and len(chat.id) == 11
    assert len(chat.title) <= chats.TITLE_MAX and chat.title.startswith("How would Mara react")
    raw = json.loads((project.root / ".assistant" / "chats" / f"{chat.id}.json").read_text())
    assert raw["scope"] == "project" and raw["attachments"] == [{"kind": "scene", "id": "manuscript/01-arrival.md"}]
    assert [m["role"] for m in raw["messages"]] == ["user", "assistant"]
    assert raw["created"] and raw["updated"]


def test_resave_keeps_title_and_created_and_drops_errors(tmp_path):
    project = make_project(tmp_path / "p")
    first = chats.save(project, None, [U("first question"), A("answer")])
    again = chats.save(project, first.id, [U("first question"), A("answer"), U("second", 2),
                                           A("That request failed.", 2, error=True)])
    assert again.id == first.id and again.title == "first question" and again.created == first.created
    assert [m["text"] for m in again.messages] == ["first question", "answer", "second"]
    with pytest.raises(ValueError):
        chats.save(project, None, [A("only an answer, error", error=True)])
    # a regenerated answer simply replaces the old one: the client's list is the truth
    regen = chats.save(project, first.id, [U("first question"), A("better answer", 3)])
    assert [m["text"] for m in regen.messages] == ["first question", "better answer"]


def test_list_open_rename_delete_and_id_safety(tmp_path):
    project = make_project(tmp_path / "p")
    a = chats.save(project, None, [U("older"), A("x")])
    b = chats.save(project, None, [U("newer"), A("y", sources=[{"id": "research/t.md", "title": "T"}])])
    # newest activity first (touch a later)
    chats.save(project, a.id, [U("older"), A("x"), U("again", 2), A("z", 2)])
    assert [i.title for i in chats.list_chats(project)] == ["older", "newer"]
    assert chats.list_chats(project)[0].count == 4
    assert chats.load(project, b.id).messages[1]["sources"] == [{"id": "research/t.md", "title": "T"}]
    assert chats.rename(project, b.id, "  A better   name ").title == "A better name"
    assert chats.load(project, b.id).title == "A better name"
    chats.delete(project, b.id)
    assert [i.id for i in chats.list_chats(project)] == [a.id]
    for bad in ("../../project", "c12", "", "cZZZZZZZZZZ", "c0123456789/../x"):
        with pytest.raises(ValueError):
            chats.load(project, bad)
    with pytest.raises(FileNotFoundError):
        chats.load(project, "c0000000000")
    # a damaged file is skipped by the list, reported by load
    (project.root / ".assistant" / "chats" / "c1111111111.json").write_text("{nope")
    assert [i.id for i in chats.list_chats(project)] == [a.id]
    with pytest.raises(ValueError):
        chats.load(project, "c1111111111")


def test_save_reply_to_notes_appends_with_date_and_prompt(tmp_path):
    project = make_project(tmp_path / "p")
    when = datetime(2026, 10, 1, 9, 30)
    path = research.append_assistant_note(project, "Why does the spur flood?", "Because of the tide table.", when)
    assert path == project.root / "research" / "assistant-notes.md"
    research.append_assistant_note(project, "Second?\n  with   spaces", "Second reply.", when)
    text = path.read_text()
    assert text.startswith("# Assistant notes\n")
    assert "## 2026-10-01 - Why does the spur flood?\n\n**Prompt:** Why does the spur flood?\n\nBecause of the tide table.\n" in text
    assert text.index("Because of the tide") < text.index("Second reply.")
    assert text.count("# Assistant notes") == 1
    assert [n.rel for n in research.list_notes(project)] == ["assistant-notes.md"]      # an ordinary research note
    assert research.search(project, "tide table")[0].note.rel == "assistant-notes.md"
    with pytest.raises(ValueError):
        research.append_assistant_note(project, "p", "  ")


def test_attachments_resolve_clean_and_cap(tmp_path):
    project = make_project(tmp_path / "p")
    arrival = "manuscript/01-arrival.md"
    archive = project.root / "manuscript" / "02-the-archive.md"
    archive.write_text("---\nstatus: draft\n---\n# The Archive\n\nReal prose.<!--ai-->Pending.<!--/ai-->\n")
    (project.root / "research").mkdir()
    (project.root / "research" / "tides.md").write_text("# Tides\n\n" + "tide " * 3000)
    comments.add(project.root, archive, archive.read_text(), 40, 50, "check this")
    text, report = attach.build(project, [
        {"kind": "scene", "id": "manuscript/02-the-archive.md"},
        {"kind": "comments", "id": "manuscript/02-the-archive.md"},
        {"kind": "note", "id": "entities/characters/mara-vale.md"},
        {"kind": "research", "id": "research/tides.md"},
        {"kind": "scene", "id": "manuscript/02-the-archive.md"},                  # duplicate: once
        {"kind": "scene", "id": "../../etc/passwd"},                              # unsafe
        {"kind": "comments", "id": arrival},                                       # no comments
        {"kind": "research", "id": "manuscript/01-arrival.md"},                    # wrong kind for the path
    ])
    assert "ATTACHED SCENE: The Archive\n# The Archive\n\nReal prose." in text
    assert "Pending" not in text and "status: draft" not in text            # drafts and details are not prose
    assert "ATTACHED COMMENTS ON SCENE: The Archive\n- On “" in text and "check this" in text
    assert "ATTACHED NOTE: Mara Vale" in text
    research_row = next(r for r in report if r["kind"] == "research" and not r["skipped"])
    assert research_row["truncated"] and research_row["chars"] <= attach.ITEM_CHARS + 2
    skipped = [r for r in report if r["skipped"]]
    assert len(skipped) == 3 and all(r["reason"] for r in skipped)
    assert len(text) <= attach.TOTAL_CHARS + 500
    # the total cap: later items are reported, not silently dropped
    big = [{"kind": "research", "id": f"research/n{i}.md"} for i in range(5)]
    for i in range(5):
        (project.root / "research" / f"n{i}.md").write_text("# N\n\n" + "word " * 3000)
    _, rep = attach.build(project, big)
    assert sum(r["chars"] for r in rep) <= attach.TOTAL_CHARS
    assert any(r["skipped"] and "already" in r["reason"] for r in rep)


def test_attachable_lists_everything_with_sizes(tmp_path):
    project = make_project(tmp_path / "p")
    (project.root / "research").mkdir()
    (project.root / "research" / "tides.md").write_text("# Tides\n\nfour words right here\n")
    scene = project.list_scenes()[0]
    comments.add(project.root, scene, scene.read_text(), 3, 9, "note")
    items = attach.attachable(project, project.load_entities())
    kinds = {(i["kind"], i["title"]) for i in items}
    assert ("scene", "Arrival") in kinds and ("comments", "Arrival") in kinds
    assert ("note", "Mara Vale") in kinds and ("research", "Tides") in kinds
    assert all(i["words"] >= 0 and i["id"] for i in items)
