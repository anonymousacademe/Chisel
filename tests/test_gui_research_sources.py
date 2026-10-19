"""Research bridge: Zotero sync review, sources, checks and paper export (gui/research_sources_api.py)."""

import json
import threading

import pytest

from chisel.core import entities as ent
from chisel.core.paper.types import ZItem
from chisel.core.project import Project
from chisel.core.zotero import FetchResult, Status
from chisel.gui import research_sources_api as mod
from chisel.gui.api import Api
from tests.gui_helpers import make_project

SECRET = "sekrit-zotero-key-123"
CSL = {"type": "article-journal", "title": "A Paper", "author": [{"family": "Smith", "given": "A"}],
       "issued": {"date-parts": [[2024]]}}


def research_api(tmp_path):
    root = tmp_path / "paper"
    project = Project.create(root, "Paper", "research")
    api = Api()
    api._load(project)
    return api, project


def zitem(key="A1", ckey="smith2024"):
    return ZItem(key=key, version=5, csl=dict(CSL, id=key), citation_key=ckey)


class FakeSource:
    name = "web"

    def probe(self):
        return Status(True, "", 5, None, "web:users/1")


def patch_fetch(monkeypatch, items, on_call=None):
    def fake_fetch(sources, scope, state):
        if on_call:
            on_call()
        return FetchResult("web", items, [], 5, None), ["Read items."]
    monkeypatch.setattr(mod.zotero, "chain_fetch", fake_fetch)
    monkeypatch.setattr(mod.zotero, "open_sources", lambda settings: [FakeSource()])


def walk(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from walk(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from walk(v)
    else:
        yield value


def test_non_research_project_refused(tmp_path):
    root = tmp_path / "p"
    make_project(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    for call in (api.zotero_status, api.zotero_sync_plan, api.list_sources, api.research_checks,
                 api.export_research_start):
        r = call()
        assert r["ok"] is False and "not a research project" in r["error"]
    assert api.zotero_sync_apply([])["ok"] is False


def test_plan_then_apply_only_ticked(tmp_path, monkeypatch):
    api, project = research_api(tmp_path)
    patch_fetch(monkeypatch, [zitem("A1", "smith2024"), zitem("B2", "jones2023")])
    plan = api.zotero_sync_plan({})
    assert plan["ok"] and len(plan["rows"]) == 2
    assert {"id", "key", "action", "summary"} <= set(plan["rows"][0])
    assert plan["report"]
    by_key = {r["key"]: r for r in plan["rows"]}
    out = api.zotero_sync_apply([by_key["smith2024"]["id"]])
    assert out["ok"] and out["changed"] == [by_key["smith2024"]["id"]] and out["skipped"] == []
    assert (project.root / by_key["smith2024"]["id"]).is_file()
    assert not (project.root / by_key["jones2023"]["id"]).exists()
    assert any(e.is_source for e in api.entities)       # reloaded
    rows = api.list_sources()["sources"]
    assert [r["key"] for r in rows] == ["smith2024"]
    assert set(rows[0]) >= {"id", "title", "key", "status"}
    # the plan is spent
    again = api.zotero_sync_apply([by_key["jones2023"]["id"]])
    assert again["ok"] is False


def test_apply_without_plan(tmp_path):
    api, _ = research_api(tmp_path)
    r = api.zotero_sync_apply(["x.md"])
    assert r["ok"] is False and "preview" in r["error"]


def test_apply_unknown_id_refused(tmp_path, monkeypatch):
    api, _ = research_api(tmp_path)
    patch_fetch(monkeypatch, [zitem()])
    api.zotero_sync_plan({})
    r = api.zotero_sync_apply(["../elsewhere.md"])
    assert r["ok"] is False


def test_key_never_returned_or_stored(tmp_path, monkeypatch, fake_keyring):
    api, _ = research_api(tmp_path)
    results = [api.zotero_set_key(SECRET), api.zotero_get_settings(), api.zotero_status(),
               api.zotero_set_settings(user_id="42", local=False)]
    seen = {}
    monkeypatch.setattr(mod.zotero, "open_sources", lambda s: seen.update(s) or [FakeSource()])
    results.append(api.zotero_status())
    for r in results:
        assert r["ok"], r
        assert SECRET not in json.dumps(r)
    assert results[1]["keySet"] is True
    assert seen["zotero_web_key"] == SECRET and seen["zotero_web_user_id"] == "42"
    assert seen["zotero_local"] is False
    from chisel.core import settings as user_settings
    assert SECRET not in json.dumps(user_settings.load_settings())
    assert SECRET in fake_keyring.store.values()
    assert api.zotero_clear_key()["keySet"] is False
    assert api.zotero_get_settings()["keySet"] is False


def test_settings_validation(tmp_path):
    api, _ = research_api(tmp_path)
    assert api.zotero_set_settings(user_id="abc")["ok"] is False
    assert api.zotero_set_settings(web_base="ftp://x")["ok"] is False
    assert api.zotero_set_settings(file=str(tmp_path / "missing.json"))["ok"] is False
    good = tmp_path / "lib.json"
    good.write_text("[]", encoding="utf-8")
    r = api.zotero_set_settings(file=str(good), local_base="http://127.0.0.1:23119/api/")
    assert r["ok"] and r["file"] == str(good) and r["localBase"] == "http://127.0.0.1:23119/api"
    assert api.zotero_set_key("")["ok"] is False


def test_status_survives_dead_backend(tmp_path, monkeypatch):
    api, _ = research_api(tmp_path)

    class Dead:
        name = "local"

        def probe(self):
            raise OSError("connection refused")

    monkeypatch.setattr(mod.zotero, "open_sources", lambda s: [Dead(), FakeSource()])
    r = api.zotero_status()
    assert r["ok"] and r["backends"][0] == {"backend": "local", "ok": False, "message": "connection refused"}
    assert r["backends"][1]["ok"] is True


def test_lock_not_held_during_network(tmp_path, monkeypatch):
    api, _ = research_api(tmp_path)
    held = []

    def probe_lock():
        got = []

        def try_lock():     # the lock is re-entrant: try it from another thread
            ok = api._lock.acquire(blocking=False)
            got.append(ok)
            if ok:
                api._lock.release()
        t = threading.Thread(target=try_lock)
        t.start()
        t.join()
        held.append(not got[0])

    patch_fetch(monkeypatch, [zitem()], on_call=probe_lock)
    orig_probe = FakeSource.probe

    def probing(self):
        probe_lock()
        return orig_probe(self)

    monkeypatch.setattr(FakeSource, "probe", probing)
    assert api.zotero_status()["ok"]
    assert api.zotero_sync_plan({})["ok"]
    assert held and not any(held)


def write_scene(project, text):
    (project.manuscript_dir / "01-intro.md").write_text(text, encoding="utf-8", newline="\n")


def test_checks_and_export_gate(tmp_path, monkeypatch):
    api, project = research_api(tmp_path)
    write_scene(project, "Intro\n\nAs shown [[@ghost2020]].\n")
    checks = api.research_checks()
    assert checks["ok"] and checks["blocking"] is True
    assert checks["flags"][0]["kind"] == "citation-unresolved"
    assert set(checks["flags"][0]) == {"kind", "path", "row", "message", "blocking"}

    calls = []

    class Res:
        def to_dict(self):
            return {"rel": "exports/x.docx"}

    def fake_export(project, options, **kw):
        calls.append((options.format, kw))
        return Res()

    monkeypatch.setattr(mod.research_export, "run_research_export", fake_export)
    refused = api.export_research_start({"format": "docx"})
    assert refused["ok"] is False and "block export" in refused["error"] and not calls

    r = api.export_research_start({"format": "docx", "override": True})
    assert r["ok"]
    for _ in range(200):
        st = api.export_research_status(r["job"])
        if st["state"] != "running":
            break
        threading.Event().wait(0.01)
    assert st["state"] == "done" and st["result"] == {"rel": "exports/x.docx"}
    assert calls == [("docx", {"allow_unresolved": True, "allow_tex_install": False})]


def test_export_clean_paper_no_override_and_tex_install_explicit(tmp_path, monkeypatch):
    api, project = research_api(tmp_path)
    ent.save_entity(ent.Entity(name="smith2024", type="source", extra={"key": "smith2024"}),
                    project.entity_path(ent.Entity(name="smith2024", type="source",
                                                   extra={"key": "smith2024"})))
    write_scene(project, "Intro\n\nAs [[@smith2024]] says.\n")
    calls = []

    def fake_export(project, options, **kw):
        calls.append(kw)
        return object()

    monkeypatch.setattr(mod.research_export, "run_research_export", fake_export)

    def run(opts):
        r = api.export_research_start(opts)
        assert r["ok"], r
        for _ in range(200):
            st = api.export_research_status(r["job"])
            if st["state"] != "running":
                return st
            threading.Event().wait(0.01)

    assert run({"format": "pdf"})["state"] == "done"
    assert run({"format": "pdf", "allow_tex_install": "yes"})["state"] == "done"
    assert run({"format": "pdf", "allow_tex_install": True})["state"] == "done"
    assert [c["allow_tex_install"] for c in calls] == [False, False, True]
    assert all(c["allow_unresolved"] is False for c in calls)
    assert api.export_research_status("nope")["ok"] is False


def test_plan_scope_multi_and_legacy(tmp_path, monkeypatch):
    api, _ = research_api(tmp_path)
    seen = []
    patch_fetch(monkeypatch, [zitem()])
    real = mod.zotero.chain_fetch
    monkeypatch.setattr(mod.zotero, "chain_fetch",
                        lambda sources, scope, state: seen.append(scope) or real(sources, scope, state))
    assert api.zotero_sync_plan({"collections": ["C1", "C2"], "includeSubcollections": False})["ok"]
    assert seen[-1].collection_keys == ("C1", "C2") and seen[-1].include_subcollections is False
    assert api.zotero_sync_plan({"collection": "OLD"})["ok"]
    assert seen[-1].collection_keys == ("OLD",) and seen[-1].include_subcollections is True


def test_saved_collections_round_trip_keeps_other_research_keys(tmp_path, monkeypatch):
    import tomllib
    api, project = research_api(tmp_path)
    assert api.zotero_saved_collections() == {"ok": True, "keys": []}
    path = project.root / "project.toml"
    text = path.read_text(encoding="utf-8").rstrip("\n")
    path.write_text(text + '\n\n[research]\nfigure_width = 5.5\nnumbering = "by-section"\n'
                    'flag = true\n', encoding="utf-8", newline="\n")
    project.meta = tomllib.loads(path.read_text(encoding="utf-8"))
    patch_fetch(monkeypatch, [zitem()])
    plan = api.zotero_sync_plan({"collections": ["C1", 'we"ird']})
    assert api.zotero_sync_apply([plan["rows"][0]["id"]])["ok"]
    assert api.zotero_saved_collections()["keys"] == ["C1", 'we"ird']
    r = Project.open(project.root).research_settings()
    assert r["figure_width"] == 5.5 and r["numbering"] == "by-section" and r["flag"] is True
    assert r["zotero_collections"] == ["C1", 'we"ird']


def test_departed_paper_is_never_marked_missing(tmp_path, monkeypatch):
    api, project = research_api(tmp_path)
    patch_fetch(monkeypatch, [zitem("A1", "smith2024"), zitem("B2", "jones2023")])
    plan = api.zotero_sync_plan({})
    assert api.zotero_sync_apply([r["id"] for r in plan["rows"]])["ok"]
    patch_fetch(monkeypatch, [zitem("A1", "smith2024")])      # B2 left the ticked collection
    plan = api.zotero_sync_plan({"collections": ["C1"]})
    assert not [r for r in plan["rows"] if r["action"] == "missing"]
