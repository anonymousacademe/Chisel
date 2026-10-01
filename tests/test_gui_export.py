"""Api: export bridge methods (M7). Opening files is faked; nothing leaves the temp dir."""

import time

import pytest

from lorewrite.core import export as exporting
from lorewrite.gui.api import Api
from tests.export_helpers import make_structured


def open_api(tmp_path):
    root = tmp_path / "p"
    make_structured(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def wait(api, job, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        st = api.export_status(job)
        assert st["ok"]
        if st["state"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError("export did not finish")


def test_info_and_summary(tmp_path):
    api, root = open_api(tmp_path)
    info = api.export_info()
    assert info["ok"] and [f["key"] for f in info["formats"]][:1] == ["pdf"]
    assert info["options"]["format"] == "pdf" and info["layouts"]
    r = api.export_summary({"format": "md", "include_drafts": True})
    assert r["ok"] and r["summary"]["scenes"] == 4 and r["summary"]["draft_scenes"] == 1
    assert any("included as written" in m for m in r["summary"]["messages"])
    assert not api.export_summary({"format": "rtf"})["ok"]


def test_export_runs_in_a_job_and_remembers_options(tmp_path):
    api, root = open_api(tmp_path)
    job = api.export_start({"format": "md", "numbering": "numbers"})["job"]
    st = wait(api, job)
    assert st["state"] == "done" and st["result"]["name"].startswith("test-novel-md-")
    assert (root / st["result"]["rel"]).is_file()
    assert api.export_info()["options"]["numbering"] == "numbers"  # remembered in project.toml
    err = wait(api, api.export_start({"format": "pdf", "layout": "book", "font": "noto-serif"})["job"])
    assert err["state"] == "done" and err["result"]["pages"] >= 6


def test_one_export_at_a_time_and_errors(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    import threading
    gate = threading.Event()
    real = exporting.run_export

    def slow(project, options, progress=None, now=None):
        gate.wait(5)
        return real(project, options, progress)

    monkeypatch.setattr(exporting, "run_export", slow)
    job = api.export_start({"format": "md"})["job"]
    again = api.export_start({"format": "md"})
    assert not again["ok"] and "already running" in again["error"]
    assert api.export_status(job)["state"] == "running"
    gate.set()
    assert wait(api, job)["state"] == "done"
    assert not api.export_status("nope")["ok"]
    monkeypatch.setattr(exporting, "run_export", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert wait(api, api.export_start({"format": "md"})["job"]) ["error"] == "boom"


def test_open_only_inside_exports_and_only_on_request(tmp_path, monkeypatch):
    api, root = open_api(tmp_path)
    opened = []
    monkeypatch.setattr(exporting, "open_in_desktop", opened.append)
    name = wait(api, api.export_start({"format": "md"})["job"])["result"]["name"]
    assert opened == []  # exporting alone opens nothing
    assert api.export_open(name)["ok"] and opened[-1] == root / "exports" / name
    assert api.export_open(folder=True)["ok"] and opened[-1] == root / "exports"
    for bad in ("../project.toml", "manuscript/x.md", "missing.md"):
        assert not api.export_open(bad)["ok"]
    assert len(opened) == 2


def test_export_methods_are_bridge_methods():
    facade = Api().facade()
    for name in ("export_info", "export_summary", "export_start", "export_status", "export_open"):
        assert hasattr(facade, name)
