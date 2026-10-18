"""Voice checks over the desktop bridge (Api.check_voice): script-only, continuity-shaped issues, waivers."""

import pytest

from chisel.core.continuity import Contradiction
from chisel.gui import api as api_module
from chisel.gui.api import Api
from tests.gui_helpers import make_project
from tests.test_voice_ai import make


def open_script(tmp_path):
    project, cur = make(tmp_path)
    api = Api()
    assert api.open_project(str(project.root))["ok"]
    return api, project, cur.relative_to(project.root).as_posix()


def fake_check(calls):
    def check(scene_text, plan, entities, model, client=None, scene_rel=""):
        calls.append(plan)
        return [Contradiction("voice_vocabulary", "warning", "Keith", "Notwithstanding the aforementioned obligation",
                              "Nah, I'm not paying that.", scene_rel, None, "Keith never talks this formally.")]
    return check


def test_the_check_returns_continuity_shaped_issues_with_reason_and_row(tmp_path, monkeypatch):
    api, project, doc = open_script(tmp_path)
    calls = []
    monkeypatch.setattr(api_module, "voice_check", fake_check(calls))
    r = api.check_voice(doc)
    assert r["ok"], r
    [issue] = r["issues"]
    assert issue["type"] == "voice_vocabulary" and issue["entity"] == "Keith" and issue["severity"] == "warning"
    assert issue["fix"] == "Nah, I'm not paying that." and issue["reason"] == "Keith never talks this formally."
    text = (project.root / doc).read_text(encoding="utf-8")
    assert text.split("\n")[issue["row"]].startswith("Notwithstanding")
    assert len(issue["key"]) == 16
    assert r["checked"] == ["Keith"] and {s["speaker"]: s["lines"] for s in r["skipped"]} == {"Mara": 2, "Waiter": 0}
    assert r["waived"] == 0 and "sent" in r and r["sent"]["feature"] == "voice"
    assert len(calls) == 1 and calls[0].checked == ("Keith",)


def test_it_uses_the_editor_buffer_and_ignores_unaccepted_drafts(tmp_path, monkeypatch):
    api, project, doc = open_script(tmp_path)
    seen = []

    def check(scene_text, plan, entities, model, client=None, scene_rel=""):
        seen.append(scene_text)
        return []

    monkeypatch.setattr(api_module, "voice_check", check)
    text = (project.root / doc).read_text(encoding="utf-8")
    live = text + '\nKEITH\n<!--ai-->An invented line.<!--/ai-->\n'
    r = api.check_voice(doc, live)
    assert r["ok"] and "An invented line" not in seen[0]      # an unaccepted draft is not canon
    assert (project.root / doc).read_text(encoding="utf-8") == text


def test_a_waived_finding_is_not_reported_again(tmp_path, monkeypatch):
    api, project, doc = open_script(tmp_path)
    monkeypatch.setattr(api_module, "voice_check", fake_check([]))
    key = api.check_voice(doc)["issues"][0]["key"]
    assert api.waive(key, doc)["ok"]
    again = api.check_voice(doc)
    assert again["issues"] == [] and again["waived"] == 1
    assert api.restore_waivers(doc)["restored"] == 1
    assert len(api.check_voice(doc)["issues"]) == 1


def test_nothing_to_judge_makes_no_call_and_says_who_was_skipped(tmp_path, monkeypatch):
    api, project, doc = open_script(tmp_path)
    for name in project.list_scenes():
        if name.name != doc.rsplit("/", 1)[1]:
            name.unlink()
    api.open_project(str(project.root))
    monkeypatch.setattr(api_module, "voice_check", lambda *a, **k: pytest.fail("no call expected"))
    r = api.check_voice(doc)
    assert r["ok"] and r["issues"] == [] and r["checked"] == []
    assert {s["speaker"] for s in r["skipped"]} == {"Keith", "Mara", "Waiter"}


def test_a_scene_nobody_speaks_in_is_a_plain_error(tmp_path):
    api, project, doc = open_script(tmp_path)
    quiet = project.next_scene_path("Quiet", project.part_of(project.root / doc))
    quiet.write_text("# Quiet\n\nINT. A - DAY\n\nRain.\n", encoding="utf-8", newline="\n")
    api.open_project(str(project.root))
    r = api.check_voice(quiet.relative_to(project.root).as_posix())
    assert not r["ok"] and "Nobody speaks" in r["error"]


def test_stories_are_refused_before_anything_is_read(tmp_path, monkeypatch):
    make_project(tmp_path / "p")
    api = Api()
    api.open_project(str(tmp_path / "p"))
    monkeypatch.setattr(api_module, "voice_check", lambda *a, **k: pytest.fail("no call expected"))
    r = api.check_voice("manuscript/01-arrival.md")
    assert not r["ok"] and "script projects" in r["error"]


def test_it_runs_as_an_ai_job_and_is_a_bridge_method():
    assert Api.AI_JOBS["voice"] == "check_voice"
    assert hasattr(Api().facade(), "check_voice")


def test_the_dev_server_mock_flags_a_line(tmp_path, monkeypatch):
    from chisel.gui import mockai
    api, project, doc = open_script(tmp_path)
    monkeypatch.setattr(api_module, "voice_check", api_module.voice_check)
    mockai.install(api_module)
    r = api.check_voice(doc)
    assert r["ok"] and len(r["issues"]) == 1
    assert r["issues"][0]["type"] == "voice_register" and r["issues"][0]["entity"] == "Keith"
    assert r["issues"][0]["evidence"].startswith("Ain't no way")
