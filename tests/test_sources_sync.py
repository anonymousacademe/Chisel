"""core/sources.py: plan_sync / apply_sync (P3)."""

import pytest

from chisel.core import entities as ent
from chisel.core import fsutil, sources
from chisel.core.paper.types import Annotation, ZItem
from chisel.core.project import Project
from chisel.core.sources import BEGIN, END, apply_sync, plan_sync
from chisel.core.zotero.base import FetchResult, Scope

CSL = {"id": "A1", "type": "book", "title": "T", "author": [{"family": "Smith", "given": "J"}],
       "issued": {"date-parts": [[2024]]}}


def item(key="A1", ckey="smith2024", version=5, **kw):
    return ZItem(key=key, version=version, csl=dict(CSL, id=key), citation_key=ckey, **kw)


def result(items, deleted=(), backend="web", version=100, server_id=None):
    return FetchResult(backend, list(items), list(deleted), version, server_id)


@pytest.fixture
def project(tmp_path):
    return Project.create(tmp_path / "p", "P", mode="research")


def sync_all(project, res, **kw):
    plan = plan_sync(project, res, **kw)
    out = apply_sync(project, plan, [r.id for r in plan.rows])
    return plan, out


def test_new_then_resync_is_clean(project):
    plan, out = sync_all(project, result([item()]), state_key="web:users/1")
    assert [r.action for r in plan.rows] == ["new"]
    assert out["changed"] == ["entities/sources/smith2024.md"] and out["recorded"]
    note = project.root / out["changed"][0]
    assert ent.load_entity(note).extra["web_version"] == 5
    assert plan_sync(project, result([item()]), state_key="web:users/1").rows == []


def test_resync_never_touches_text_outside_markers(project):
    sync_all(project, result([item(notes=["<p>one</p>"])]))
    path = project.root / "entities/sources/smith2024.md"
    raw = path.read_text(encoding="utf-8")
    mine = "\n\n## My notes\r\nI think [[Elara]]  \n\ttabbed é中 and CRLF\r\nend"
    path.write_bytes((raw + mine).encode("utf-8"))
    before = path.read_bytes().decode("utf-8")
    plan, out = sync_all(project, result([item(notes=["<p>two</p>", "<p>three</p>"],
                                               annotations=[Annotation("N1", "q", "c", "2")])]))
    assert plan.rows[0].action == "changed" and out["changed"]
    after = path.read_bytes().decode("utf-8")
    assert after != before
    b0, b1 = before.index(BEGIN), before.index(END)
    a0, a1 = after.index(BEGIN), after.index(END)
    assert before[:b0] == after[:a0]                      # frontmatter and head: byte-identical
    assert before[b1:] == after[a1:]                      # the author's text: byte-identical
    assert "two" in after and "three" in after and "one" not in after


def test_changed_csl_rewrites_frontmatter_keeps_author_keys(project):
    sync_all(project, result([item()]))
    path = project.root / "entities/sources/smith2024.md"
    note = ent.load_entity(path)
    note.extra["tags"] = ["mine"]
    note.aliases.append("Smith's book")
    note.body += "\nauthor words\n"
    ent.save_entity(note, path)
    it = ZItem("A1", 6, dict(CSL, title="Changed"), "smith2024")
    sync_all(project, result([it], version=101))
    again = ent.load_entity(path)
    assert again.extra["title"] == "Changed" and again.extra["tags"] == ["mine"]
    assert "Smith's book" in again.aliases and again.body.endswith("author words\n")
    assert again.extra["web_version"] == 6


def test_key_mismatch_is_reported_not_applied(project):
    sync_all(project, result([item()]))
    path = project.root / "entities/sources/smith2024.md"
    before = path.read_bytes()
    plan = plan_sync(project, result([item(ckey="smith2024b")]), state_key="web:users/1")
    assert [r.action for r in plan.rows] == ["key-mismatch"]
    out = apply_sync(project, plan, [plan.rows[0].id])
    assert out["changed"] == [] and out["skipped"][0]["reason"] == "key-mismatch" and not out["recorded"]
    assert path.read_bytes() == before


def test_missing_marks_and_keeps_note(project):
    sync_all(project, result([item(notes=["<p>keep</p>"])]))
    path = project.root / "entities/sources/smith2024.md"
    raw = path.read_text(encoding="utf-8")
    plan = plan_sync(project, result([], deleted=["A1"]))
    assert [r.action for r in plan.rows] == ["missing"]
    apply_sync(project, plan, [plan.rows[0].id])
    after = path.read_text(encoding="utf-8")
    assert ent.load_entity(path).extra["zotero_status"] == "missing"
    assert after.split("---\n", 2)[2] == raw.split("---\n", 2)[2]       # body untouched
    assert plan_sync(project, result([], deleted=["A1"])).rows == []   # already marked
    # back in Zotero: current again
    plan = plan_sync(project, result([item(notes=["<p>keep</p>"])]))
    assert plan.rows and "back in Zotero" in plan.rows[0].summary
    apply_sync(project, plan, [plan.rows[0].id])
    assert ent.load_entity(path).extra["zotero_status"] == "current"


def test_only_ticked_rows_and_version_not_recorded_when_partial(project, monkeypatch):
    res = result([item(), item("B2", "lee2023")])
    plan = plan_sync(project, res, state_key="web:users/1")
    assert len(plan.rows) == 2
    out = apply_sync(project, plan, [plan.rows[0].id])
    assert len(out["changed"]) == 1 and not out["recorded"]
    assert sources.load_sync_state(project) == {}
    out = apply_sync(project, plan_sync(project, res, state_key="web:users/1"),
                     [r.id for r in plan_sync(project, res).rows])
    assert out["recorded"] and sources.load_sync_state(project) == {"web:users/1": 100}


def test_limited_scope_and_file_backend_record_nothing(project):
    _, out = sync_all(project, result([item()]), scope=Scope(tag="x"), state_key="web:users/1")
    assert not out["recorded"]
    _, out = sync_all(project, result([item("B2", "b2")], backend="file", version=None))
    assert not out["recorded"] and sources.load_sync_state(project) == {}


def test_local_state_key_from_server_id_and_no_web_version(project):
    _, out = sync_all(project, result([item()], backend="local", version=9, server_id="srv"))
    assert out["recorded"] and sources.load_sync_state(project) == {"local:srv": 9}
    assert "web_version" not in ent.load_entity(project.root / out["changed"][0]).extra


def test_refuses_file_changed_since_plan_before_writing(project):
    sync_all(project, result([item(), item("B2", "lee2023")]))
    plan = plan_sync(project, result([item(notes=["<p>x</p>"]), item("B2", "lee2023", notes=["<p>y</p>"])]))
    assert len(plan.rows) == 2
    p1 = project.root / plan.rows[1].id
    p1.write_text(p1.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    first = (project.root / plan.rows[0].id).read_bytes()
    with pytest.raises(ValueError, match="changed since"):
        apply_sync(project, plan, [r.id for r in plan.rows])
    assert (project.root / plan.rows[0].id).read_bytes() == first    # nothing was written
    with pytest.raises(ValueError):
        apply_sync(project, plan, ["entities/sources/nope.md"])


def test_new_file_that_appeared_since_plan_is_refused(project):
    plan = plan_sync(project, result([item()]))
    (project.root / plan.rows[0].id).write_text("mine", encoding="utf-8")
    with pytest.raises(ValueError):
        apply_sync(project, plan, [plan.rows[0].id])


def test_interrupted_apply_leaves_valid_notes_and_no_version(project, monkeypatch):
    res = result([item(), item("B2", "lee2023"), item("C3", "roe2022")])
    plan = plan_sync(project, res, state_key="web:users/1")
    real = fsutil.replace
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("disk went away")
        return real(src, dst)

    monkeypatch.setattr(fsutil, "replace", flaky)
    with pytest.raises(OSError):
        apply_sync(project, plan, [r.id for r in plan.rows])
    monkeypatch.undo()
    assert sources.load_sync_state(project) == {}
    files = sorted((project.root / "entities/sources").glob("*.md"))
    assert len(files) == 1
    assert ent.load_entity(files[0]).type == "source" and ent.load_entity(files[0]).extra["csl"]
    # the leftover temp file is not a note
    assert all(p.suffix == ".md" for p in project.list_entity_files())
    # a fresh plan finishes the job
    sync_all(project, res, state_key="web:users/1")
    assert len(project.list_entity_files()) == 3


def test_damaged_markers_row_is_blocked(project):
    sync_all(project, result([item()]))
    path = project.root / "entities/sources/smith2024.md"
    path.write_text(path.read_text(encoding="utf-8").replace(END, ""), encoding="utf-8")
    plan = plan_sync(project, result([item(notes=["<p>n</p>"])]))
    assert plan.rows[0].blocked
    out = apply_sync(project, plan, [plan.rows[0].id])
    assert out["changed"] == [] and out["skipped"]


def test_filename_collision_and_adopting_a_hand_made_note(project):
    plan = plan_sync(project, result([item("A1", "Smith2024"), item("B2", "smith2024")]))
    assert sorted(r.id for r in plan.rows) == ["entities/sources/smith2024-2.md", "entities/sources/smith2024.md"]
    # a note made by hand under the key is adopted, not duplicated
    hand, path = project.create_entity("lee2023", "source")
    plan = plan_sync(project, result([item("L1", "lee2023")]))
    assert [(r.id, r.action) for r in plan.rows] == [(str(path.relative_to(project.root).as_posix()), "changed")]


def test_cached_items_roundtrip(project):
    sync_all(project, result([item()]))
    (z,) = sources.cached_items(project)
    assert z.key == "A1" and z.citation_key == "smith2024" and z.csl["title"] == "T"
    # a cache-backend result of the same notes plans nothing
    assert plan_sync(project, result([z], backend="cache", version=None)).rows == []
