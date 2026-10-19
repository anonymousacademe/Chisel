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
    out = apply_sync(project, plan, [r.id for r in plan.rows])   # the failed row is reported, the rest written
    monkeypatch.undo()
    assert len(out["skipped"]) == 1 and len(out["changed"]) == 2 and not out["recorded"]
    assert sources.load_sync_state(project) == {}
    files = sorted((project.root / "entities/sources").glob("*.md"))
    assert len(files) == 2
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


def test_crlf_note_round_trips_with_one_frontmatter(project):
    sync_all(project, result([item(notes=["<p>one</p>"])]))
    path = project.root / "entities/sources/smith2024.md"
    raw = path.read_bytes().decode("utf-8")
    mine = "\n\n## My notes\r\nmy words é\r\nend"
    crlf = raw.replace("\r\n", "\n").replace("\n", "\r\n") + mine
    path.write_bytes(crlf.encode("utf-8"))
    before = path.read_bytes().decode("utf-8")
    plan, out = sync_all(project, result([item(notes=["<p>two</p>"])]))
    assert out["changed"] and not out["skipped"]
    after = path.read_bytes().decode("utf-8")
    assert after.count("---\r\n") == 2 and after.count("zotero_key") == 1
    assert before[before.index(END):] == after[after.index(END):]
    assert "two" in after and "one" not in after
    # a changed frontmatter value is rewritten in the file's own newline style
    csl = dict(CSL, title="New title")
    sync_all(project, result([ZItem(key="A1", version=6, csl=csl, citation_key="smith2024")]))
    after2 = path.read_bytes().decode("utf-8")
    assert after2.count("zotero_key") == 1 and "New title" in after2
    assert "\n" not in after2[:after2.index(BEGIN)].replace("\r\n", "")
    assert after2[after2.index(END):] == before[before.index(END):]


def test_bom_note_is_recognised_and_bom_kept(project):
    sync_all(project, result([item()]))
    path = project.root / "entities/sources/smith2024.md"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    plan = plan_sync(project, result([item(notes=["<p>n</p>"])]))
    assert [(r.id, r.action) for r in plan.rows] == [("entities/sources/smith2024.md", "changed")]
    apply_sync(project, plan, [plan.rows[0].id])
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf---") and data.count(b"zotero_key") == 1
    assert not (project.root / "entities/sources/smith2024-2.md").exists()
    sync_all(project, result([ZItem(key="A1", version=6, csl=dict(CSL, title="Z"), citation_key="smith2024")]))
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf---") and data.count(b"zotero_key") == 1


def test_one_bad_row_does_not_abort_the_others(project):
    sync_all(project, result([item(), item("B2", "lee2023")]))
    bad = project.root / "entities/sources/smith2024.md"
    bad.write_text(bad.read_text(encoding="utf-8").replace(END, ""), encoding="utf-8")
    plan = plan_sync(project, result([], deleted=["A1", "B2"]), state_key="web:users/1")
    assert {r.action for r in plan.rows} == {"missing"} and len(plan.rows) == 2
    out = apply_sync(project, plan, [r.id for r in plan.rows])
    assert len(out["changed"]) == 2 and not out["skipped"]       # a missing row only touches frontmatter
    assert ent.load_entity(bad).extra["zotero_status"] == "missing"
    # an unreadable file is skipped and reported, the rest is written, no version recorded
    sync_all(project, result([item("C3", "roe2022"), item("D4", "kim2021")]))
    plan = plan_sync(project, result([item("C3", "roe2022", notes=["<p>x</p>"]),
                                      item("D4", "kim2021", notes=["<p>y</p>"])]), state_key="web:users/1")
    recorded_before = sources.load_sync_state(project)
    first = project.root / plan.rows[0].id
    first.write_bytes(first.read_bytes())
    real = fsutil.ensure_utf8

    def picky(path):
        if path == first:
            raise fsutil.NotUtf8Error(path)
        return real(path)

    import pytest as _pt
    mp = _pt.MonkeyPatch()
    mp.setattr(fsutil, "ensure_utf8", picky)
    try:
        out = apply_sync(project, plan, [r.id for r in plan.rows])
    finally:
        mp.undo()
    assert len(out["changed"]) == 1 and [s["id"] for s in out["skipped"]] == [plan.rows[0].id]
    assert not out["recorded"] and sources.load_sync_state(project) == recorded_before


def test_duplicate_keys_are_blocked_not_duplicated(project):
    plan = plan_sync(project, result([item("A1", "dup"), item("B2", "dup")]))
    assert [r.action for r in plan.rows] == ["new", "key-mismatch"]
    assert plan.rows[1].blocked and "share the key" in plan.rows[1].summary
    out = apply_sync(project, plan, [r.id for r in plan.rows])
    assert len(out["changed"]) == 1 and len(out["skipped"]) == 1
    assert len(list((project.root / "entities/sources").glob("dup*.md"))) == 1
    # two items with one key and a hand-made note: only one adopts it, rows keep distinct ids
    project.create_entity("lee2023", "source")
    plan = plan_sync(project, result([item("L1", "lee2023"), item("L2", "lee2023")]))
    assert len({r.id for r in plan.rows}) == len(plan.rows) == 2
    assert sorted(r.action for r in plan.rows) == ["changed", "key-mismatch"]


def test_file_appearing_or_changing_after_digest_check_is_skipped(project, monkeypatch):
    plan = plan_sync(project, result([item(), item("B2", "lee2023")]))
    target = project.root / plan.rows[0].id
    real = sources._digest_bytes
    calls = {"n": 0}

    def late(path):
        # the up-front check sees the planned state; the re-check before the write sees a new file
        calls["n"] += 1
        if path == target and calls["n"] > 2:
            target.write_text("mine", encoding="utf-8")
        return real(path)

    monkeypatch.setattr(sources, "_digest_bytes", late)
    out = apply_sync(project, plan, [r.id for r in plan.rows])
    assert target.read_text(encoding="utf-8") == "mine"
    assert [s["id"] for s in out["skipped"]] == [plan.rows[0].id] and len(out["changed"]) == 1
    assert not out["recorded"]
    # exclusive create: a file that exists is never replaced
    with pytest.raises(FileExistsError):
        sources._atomic_write(target, "x", exclusive=True)
    assert target.read_text(encoding="utf-8") == "mine"


def test_block_is_readable_markdown_in_order():
    csl = dict(CSL, abstract="<p>First para.</p><p>Second &amp; last.</p>", DOI="10.1/x",
               URL="https://example.org/p", **{"container-title": "Water Research"})
    it = ZItem(key="A1", version=5, csl=csl, citation_key="smith2024", notes=["<p>My note</p>"],
               annotations=[Annotation(id="AN1", text="quoted", comment="c", page="3")])
    md = sources.block_markdown(it)
    assert md.startswith("## From Zotero\n\n**T**\n\nSmith, J\n\n*Water Research* · 2024 · [DOI](https://doi.org/10.1/x)"
                         " · [URL](https://example.org/p)\n\n### Abstract\n\nFirst para.\n\nSecond & last.")
    assert md.index("### Abstract") < md.index("### Notes") < md.index("### Highlights")
    assert md.count("<!--zotero-ann:AN1-->") == 1
    bad = ZItem(key="K", version=1, csl=dict(CSL, URL="javascript:alert(1)"), citation_key="k")
    assert "javascript:" not in sources.block_markdown(bad)


def test_old_format_note_is_reformatted_once(project):
    it = item(notes=["<p>keep</p>"])
    old = sources.item_to_note(it, None)
    old.body = sources.replace_block("", sources.legacy_block_markdown(it)) + "\n\n## My notes\nmine\n"
    path = project.root / "entities" / "sources" / "smith2024.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(old.to_markdown(), encoding="utf-8", newline="\n")
    plan = plan_sync(project, result([it]))
    assert [(r.action, "reformatted" in r.summary) for r in plan.rows] == [("changed", True)]
    assert path.read_text(encoding="utf-8") == old.to_markdown()   # nothing written until ticked
    out = apply_sync(project, plan, [plan.rows[0].id])
    text = path.read_text(encoding="utf-8")
    assert out["changed"] and "**T**" in text and text.endswith("## My notes\nmine\n")
    assert plan_sync(project, result([it])).rows == []
