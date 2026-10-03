"""Entity frontmatter round trip: keys the app does not manage (``born:``, ``tags:``...)
survive every save path (Entity.extra)."""

import datetime
from pathlib import Path

import pytest

from chisel.core import entities as ent
from chisel.core import rename, snapshots
from chisel.core.continuity import apply_canon_update
from chisel.core.project import Project
from chisel.gui.api import Api

NOTE = """\
---
name: Mara Vale
type: character
aliases:
- Mara
born: 2161-03-14
tags: [pilot, "ex-navy"]
home:
  city: Lower Meridian
  rooms: 3
motto: Ça va aller — 你好
count: 7
---

Calm. Owes [[Elias Vale]] a letter.
"""

KEYS = ["born", "tags", "home", "motto", "count"]


@pytest.fixture(autouse=True)
def _clear_daily():
    snapshots._daily_done.clear()
    yield
    snapshots._daily_done.clear()


def make(tmp_path: Path, text: str = NOTE) -> tuple[Project, Path]:
    project = Project.create(tmp_path / "book", "Book")
    (project.root / "manuscript" / "01-opening.md").unlink()
    path = project.entities_dir / "characters" / "mara-vale.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return project, path


def front(path: Path) -> dict:
    import yaml
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def assert_extra_intact(path: Path):
    meta = front(path)
    assert list(meta)[:3] == ["name", "type", "aliases"]
    assert list(meta)[3:] == KEYS
    assert meta["born"] == datetime.date(2161, 3, 14)
    assert meta["tags"] == ["pilot", "ex-navy"]
    assert meta["home"] == {"city": "Lower Meridian", "rooms": 3}
    assert meta["motto"] == "Ça va aller — 你好" and meta["count"] == 7
    assert "你好" in path.read_text(encoding="utf-8")  # allow_unicode, not escapes


def test_from_markdown_keeps_unknown_keys_in_file_order():
    e = ent.Entity.from_markdown(NOTE)
    assert list(e.extra) == KEYS
    assert e.extra["born"] == datetime.date(2161, 3, 14)
    assert e.extra["home"]["rooms"] == 3


def test_save_entity_round_trip(tmp_path):
    _, path = make(tmp_path)
    e = ent.load_entity(path)
    e.body += "\nMore.\n"
    ent.save_entity(e, path)
    assert_extra_intact(path)
    assert "More." in ent.load_entity(path).body


def test_managed_only_note_is_byte_identical_after_a_no_op_save(tmp_path):
    text = "---\nname: Elias Vale\ntype: character\naliases:\n- Elias\n---\n\nBody.\n"
    _, path = make(tmp_path, text)
    path.write_text(text, encoding="utf-8", newline="\n")
    ent.save_entity(ent.load_entity(path), path)
    assert path.read_bytes() == text.encode("utf-8")
    empty = ent.Entity(name="Wren", type="place").to_markdown()
    assert empty == "---\nname: Wren\ntype: place\naliases: []\n---\n\n"


def test_add_alias_keeps_extra(tmp_path):
    project, path = make(tmp_path)
    e = ent.resolve("Mara Vale", project.load_entities())
    ent.add_alias(e, "the pilot", project.load_entities())
    assert_extra_intact(path)
    assert "the pilot" in ent.load_entity(path).aliases


def test_apply_canon_update_keeps_extra(tmp_path):
    project, path = make(tmp_path)
    e = ent.load_entity(path)
    apply_canon_update(e, ["Has a scar on her left hand."])
    assert_extra_intact(path)
    assert "scar" in ent.load_entity(path).body


def test_rename_everywhere_plan_apply_undo_keeps_extra(tmp_path):
    project, path = make(tmp_path)
    (project.manuscript_dir / "01-a.md").write_text("# A\n\nMara Vale smiled.\n", encoding="utf-8")
    e = ent.load_entity(path)
    plan = rename.plan_rename(project, e, "Mara Okoye")
    assert path.read_text(encoding="utf-8") == NOTE  # preview writes nothing
    result = rename.apply_rename(project, plan, plan.default_ids())
    new_path = project.entities_dir / "characters" / "mara-okoye.md"
    assert new_path.is_file() and not path.exists()
    assert_extra_intact(new_path)
    assert ent.load_entity(new_path).name == "Mara Okoye"
    rename.undo_rename(project, result.undo_id)
    assert path.is_file()
    assert_extra_intact(path)
    assert ent.load_entity(path).name == "Mara Vale"


def test_gui_save_document_round_trip_and_get_entity(tmp_path):
    project, path = make(tmp_path)
    api = Api()
    assert api.open_project(str(project.root))["ok"]
    doc = api.read_document("entities/characters/mara-vale.md")
    assert doc["ok"] and doc["kind"] == "entity" and "born: 2161-03-14" in doc["text"]
    edited = doc["text"].replace("Calm.", "Very calm.")
    r = api.save_document(doc["id"], edited, doc["mtime"])
    assert r["ok"] and r["saved"] is True
    assert_extra_intact(path)
    got = api.get_entity("Mara Vale")
    assert got["ok"] and got["found"] and got["born"] == "2161-03-14"
    assert api.add_alias("Mara Vale", "Captain")["ok"]
    assert_extra_intact(path)
    r = api.apply_aliases([{"entity": "Mara Vale", "surface": "the pilot"}])
    assert r["ok"] and r["added"] == 1
    assert_extra_intact(path)


def test_unicode_and_odd_values_survive(tmp_path):
    text = ("---\nname: Zoë\ntype: character\naliases: []\n"
            "épithète: «la brave»\nlist:\n- 1\n- two\n- [3, 4]\nwhen: null\nflag: true\n"
            "long: " + "word " * 40 + "\n---\n\nBody\n")
    _, path = make(tmp_path, text)
    e = ent.load_entity(path)
    ent.save_entity(e, path)
    again = ent.load_entity(path)
    assert again.extra == e.extra
    assert list(again.extra) == ["épithète", "list", "when", "flag", "long"]


def test_malformed_frontmatter_does_not_crash_and_behaves_as_before(tmp_path):
    text = "---\nname: Mara\ntype: [unclosed\nborn: 1\n---\n\nBody\n"
    e = ent.Entity.from_markdown(text, Path("mara.md"))
    assert (e.name, e.extra, e.body) == ("mara", {}, "Body\n")
    scalar = ent.Entity.from_markdown("---\njust text\n---\n\nBody\n", Path("x.md"))
    assert scalar.extra == {} and scalar.name == "x"
    lst = ent.Entity.from_markdown("---\n- a\n- b\n---\n\nBody\n", Path("y.md"))
    assert lst.extra == {} and lst.name == "y"
    # saving such a note still works
    _, path = make(tmp_path, text)
    ent.save_entity(ent.load_entity(path), path)
    assert ent.load_entity(path).name == "mara-vale"


def test_extra_never_overrides_managed_keys():
    e = ent.Entity(name="A", extra={"name": "B", "type": "place", "born": 5})
    assert e.to_markdown() == "---\nname: A\ntype: character\naliases: []\nborn: 5\n---\n\n"
