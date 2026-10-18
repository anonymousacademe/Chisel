"""Research bridge: figures, tables, equations (gui/research_objects_api.py). No network, no real scripts but a tiny one."""

import base64
import sys
import threading
import time

import pytest

from chisel.core import figscripts, settings
from chisel.core.project import Project
from chisel.gui import research_objects_api as roa
from chisel.gui.api import Api
from chisel.gui.research_objects_api import ResearchObjectsMixin

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"
WRITE_PNG = f"OUT.write_bytes({PNG!r})\n"
SLEEP = "import time\ntime.sleep(60)\n"


class RApi(ResearchObjectsMixin, Api):
    """The lead wires the mixin into ResearchMixin; the test composes it the same way."""


def url(data: bytes, mime="image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


@pytest.fixture(autouse=True)
def interpreter():
    settings.set(figscripts.INTERPRETER_SETTING, sys.executable)


@pytest.fixture
def rapi(tmp_path):
    project = Project.create(tmp_path / "paper", "Paper", "research")
    api = RApi()
    api._load(project)
    (project.root / "figures").mkdir(exist_ok=True)
    (project.root / "data").mkdir(exist_ok=True)
    (project.root / "data" / "flow.csv").write_text("x,y\n1,2\n", encoding="utf-8", newline="\n")
    return api, project


def make_script_figure(project, script=WRITE_PNG, label="flow"):
    f = project.root / "figures"
    (f / f"fig-{label}.py").write_text(script, encoding="utf-8", newline="\n")
    (f / f"fig-{label}.md").write_text(
        f"---\ncaption: Flow\nsource: script\nscript: fig-{label}.py\ndata: [data/flow.csv]\n---\nn\n",
        encoding="utf-8", newline="\n")
    return f"fig:{label}"


def make_table(project, label="t1", extra=""):
    (project.root / "tables").mkdir(exist_ok=True)
    p = project.root / "tables" / f"tbl-{label}.md"
    p.write_text(f"---\ncaption: Results\n---\n{extra}| a | b |\n| --- | ---: |\n| 1 | 2 |\n", encoding="utf-8", newline="\n")
    return f"tbl:{label}", p


def place(project, text):
    scene = project.list_scenes()[0] if project.list_scenes() else project.root / "manuscript" / "01-a.md"
    scene.parent.mkdir(exist_ok=True)
    scene.write_text("# A\n\n" + text, encoding="utf-8", newline="\n")


def wait(api, job, states=("done", "failed", "cancelled"), seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        r = api.figure_run_status(job)
        if r["state"] in states:
            return r
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_non_research_refused(tmp_path):
    project = Project.create(tmp_path / "story", "Story")
    api = RApi()
    api._load(project)
    for call in (lambda: api.list_objects(), lambda: api.object_numbers(), lambda: api.object_render(["fig:a"]),
                 lambda: api.insert_figure(url(PNG), "a"), lambda: api.suggest_latex("x"),
                 lambda: api.figure_trust_info("fig:a")):
        r = call()
        assert r["ok"] is False and "not a research project" in r["error"]


def test_render_batch_and_numbers(rapi):
    api, project = rapi
    assert api.insert_figure(url(PNG), "flow", "A flow")["id"] == "fig:flow"
    tid, _ = make_table(project)
    (project.root / "equations").mkdir(exist_ok=True)
    (project.root / "equations" / "eq-e1.md").write_text("---\ncaption: E\n---\nE = mc^2\n", encoding="utf-8", newline="\n")
    place(project, "![[fig:flow]]\n\n![[tbl:t1]]\n\n![[eq:e1]]\n")
    r = api.object_render(["fig:flow", tid, "eq:e1", "fig:nope"])
    assert r["ok"]
    fig, tbl, eq, bad = r["objects"]
    assert fig["number"] == "1" and fig["imageUrl"] == url(PNG) and fig["caption"] == "A flow"
    assert tbl["cells"] == [["a", "b"], ["1", "2"]] and tbl["align"] == ["default", "right"] and tbl["mtime"]
    assert eq["latex"] == "E = mc^2" and eq["kind"] == "eq"
    assert "error" in bad and bad["id"] == "fig:nope"
    nums = api.object_numbers()["numbers"]
    assert nums["fig:flow"] == {"seq": 1, "display": "1"}
    rows = {o["id"]: o for o in api.list_objects()["objects"]}
    assert set(rows) == {"fig:flow", "tbl:t1", "eq:e1"} and rows["fig:flow"]["number"]["display"] == "1"
    img = api.object_image("flow")
    assert img["dataUrl"] == url(PNG)
    assert api.object_image("../x")["ok"] is False


def test_image_cache_by_mtime(rapi):
    api, project = rapi
    api.insert_figure(url(PNG), "flow")
    a = api.object_image("flow")["dataUrl"]
    png = project.root / "figures" / "fig-flow.png"
    png.write_bytes(PNG + b"2")
    b = api.object_image("flow")["dataUrl"]
    assert a != b and b == url(PNG + b"2")


def test_save_table_and_conflict(rapi):
    api, project = rapi
    tid, path = make_table(project, extra="Intro note.\n\n")
    t = api.read_table(tid)
    assert t["ok"] and t["generated"] is False
    r = api.save_table(tid, [["a", "b"], ["1", "9"], ["x|y", ""]], ["left", "right"], t["mtime"])
    assert r["ok"] and r["mtime"]
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\ncaption: Results\n---\nIntro note.\n\n| a | b |\n| :---- | ---: |")
    assert "x\\|y" in text and "\r" not in text
    stale = api.save_table(tid, [["a", "b"]], ["default", "default"], t["mtime"])
    assert stale["ok"] is False and stale["conflict"] is True
    assert path.read_text(encoding="utf-8") == text          # untouched
    assert api.save_table(tid, [["a", "b"]], ["bogus", "default"], r["mtime"])["ok"] is False


def test_insert_figure_sniff_and_cap(rapi):
    api, project = rapi
    assert api.insert_figure(url(b"GIF89a-not-an-image"), "g")["ok"] is False
    assert api.insert_figure(url(PNG, "image/jpeg"), "j")["object"]["file"].endswith(".png")   # bytes win
    big = PNG + b"0" * (10 * 1024 * 1024)
    r = api.insert_figure(url(big), "big")
    assert r["ok"] is False and "10 MB" in r["error"]
    assert api.insert_figure("not a data url", "x")["ok"] is False
    assert api.insert_figure(url(PNG), "j")["ok"] is False      # label in use
    assert not (project.root / "figures" / "fig-big.md").exists()


def test_run_refused_until_trusted_wrong_sha(rapi):
    api, project = rapi
    fid = make_script_figure(project)
    r = api.figure_run_start(fid)
    assert r["ok"] is False and "not been confirmed" in r["error"]
    info = api.figure_trust_info(fid)
    assert info["ok"] and info["script"] == WRITE_PNG and info["interpreter"] == sys.executable
    assert info["sha"] == figscripts.script_sha(project, "flow") and info["trust"] == "untrusted"
    bad = api.trust_figure(fid, "0" * 64)
    assert bad["ok"] is False
    assert figscripts.trust_state(project, "flow") == "untrusted"
    assert api.figure_run_start(fid)["ok"] is False
    assert not (project.root / "figures" / "fig-flow.png").exists()
    assert api.trust_figure(fid, info["sha"])["trust"] == "trusted"
    # the script changes after the dialog: trust is gone
    (project.root / "figures" / "fig-flow.py").write_text(WRITE_PNG + "# x\n", encoding="utf-8", newline="\n")
    assert api.figure_run_start(fid)["ok"] is False


def test_run_done_and_cancelled(rapi):
    api, project = rapi
    fid = make_script_figure(project)
    api.trust_figure(fid, api.figure_trust_info(fid)["sha"])
    job = api.figure_run_start(fid)["job"]
    r = wait(api, job)
    assert r["state"] == "done", r.get("error")
    assert (project.root / "figures" / "fig-flow.png").read_bytes() == PNG

    fid2 = make_script_figure(project, SLEEP, "slow")
    api.trust_figure(fid2, api.figure_trust_info(fid2)["sha"])
    job2 = api.figure_run_start(fid2)["job"]
    assert api.figure_run_start(fid2)["ok"] is False        # already running
    assert api.figure_run_cancel(job2)["ok"]
    assert wait(api, job2)["state"] == "cancelled"
    assert api.figure_run_status("nope")["ok"] is False


def test_run_failed_reports_error(rapi):
    api, project = rapi
    fid = make_script_figure(project, "raise SystemExit('boom here')\n")
    api.trust_figure(fid, api.figure_trust_info(fid)["sha"])
    r = wait(api, api.figure_run_start(fid)["job"])
    assert r["state"] == "failed" and r["error"] and "boom here" in (r["error"] + r["stderr"])


def _free(api) -> bool:
    """Can ANOTHER thread take the bridge lock right now (non-blocking)?"""
    got = []

    def probe():
        ok = api._lock.acquire(blocking=False)
        got.append(ok)
        if ok:
            api._lock.release()

    t = threading.Thread(target=probe)
    t.start()
    t.join()
    return got[0]


def test_no_lock_held_during_run(rapi, monkeypatch):
    api, project = rapi
    fid = make_script_figure(project)
    api.trust_figure(fid, api.figure_trust_info(fid)["sha"])
    seen = {}

    def fake_run(proj, label, *, cancel=None, timeout=None):
        seen["free"] = _free(api)
        return figscripts.RunResult("current")

    monkeypatch.setattr(roa.figscripts, "run_figure", fake_run)
    start = api.figure_run_start(fid)
    assert start["ok"]
    r = wait(api, start["job"])
    assert r["state"] == "done", r.get("error")
    assert seen["free"] is True
    assert _free(api)


def test_build_and_apply_table(rapi):
    api, project = rapi
    (project.root / "tables").mkdir(exist_ok=True)
    p = project.root / "tables" / "tbl-d.md"
    p.write_text("---\ncaption: D\nsource: data\ndata: data/flow.csv\n---\n", encoding="utf-8", newline="\n")
    b = api.build_table("tbl:d")
    assert b["ok"] and "| x" in b["markdown"] and "latex" in b
    assert p.read_text(encoding="utf-8").endswith("---\n")        # preview wrote nothing
    a = api.apply_table("tbl:d")
    assert a["ok"] and "| x" in p.read_text(encoding="utf-8")
    assert api.save_table("tbl:d", [["a"]], ["default"], a["mtime"])["ok"] is False   # generated


def test_suggest_returns_text_only(rapi, monkeypatch):
    import chisel.gui.api as api_module

    api, project = rapi
    api._load(project)
    calls = []
    monkeypatch.setattr(api_module, "suggest_latex",
                        lambda description, *, model, cancel: calls.append(("l", description)) or "x^2", raising=False)
    monkeypatch.setattr(api_module, "suggest_plot_code",
                        lambda description, columns, *, model, cancel: calls.append(("p", columns)) or "plt.plot()",
                        raising=False)
    before = sorted(p.relative_to(project.root).as_posix() for p in project.root.rglob("*") if p.is_file())
    r = api.suggest_latex("square of x")
    assert r["ok"] and r["text"] == "x^2" and r["sent"] and "cost" in r
    r = api.suggest_plot_code("line plot", ["x"])
    assert r["ok"] and r["text"] == "plt.plot()" and calls[-1] == ("p", ["x"])
    api.suggest_plot_code("line plot")
    assert calls[-1] == ("p", None)
    after = sorted(p.relative_to(project.root).as_posix() for p in project.root.rglob("*") if p.is_file())
    assert before == after
    assert api.suggest_latex("  ")["ok"] is False
