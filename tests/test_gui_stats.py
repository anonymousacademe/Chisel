"""Api: writing stats (Wave 4.1) - counted on save, kept in the state dir."""

from tests.gui_helpers import make_book
from chisel.core import stats as writing_stats
from chisel.gui.api import Api

RAIN = "manuscript/01-the-recall/01-rain.md"


def open_book(tmp_path):
    root = tmp_path / "p"
    make_book(root)
    api = Api()
    assert api.open_project(str(root))["ok"]
    return api, root


def save(api, root, text, mtime=None):
    doc = api.read_document(RAIN)
    r = api.save_document(RAIN, text, doc["mtime"] if mtime is None else mtime)
    assert r["ok"] and r["saved"], r
    return r


def test_saving_counts_net_author_words_and_ignores_pending(tmp_path):
    api, root = open_book(tmp_path)
    before = api.stats_summary()["stats"]
    assert before["today"]["words"] == 0 and before["target"] == 500
    base = (root / RAIN).read_text(encoding="utf-8")
    save(api, root, base + "\nfive new words right here\n")
    save(api, root, base + "\nfive new words right here\n<!--ai-->a long pending draft that is not prose<!--/ai-->\n")
    s = api.stats_summary()["stats"]
    assert s["today"]["words"] == 5 and s["session"]["words"] == 5 and s["today"]["aiWords"] == 0


def test_accepting_a_draft_counts_ai_words_not_author_words(tmp_path):
    api, root = open_book(tmp_path)
    base = (root / RAIN).read_text(encoding="utf-8")
    draft = base + '\n<!--ai-->one two three four<!--/ai-->\n'
    mtime = save(api, root, draft)["mtime"]
    res = api.resolve_drafts(RAIN, draft, True, 0)       # the editor stays open: no re-read
    assert res["ok"] and res["found"] == 1
    accepted = draft.replace("<!--ai-->", "").replace("<!--/ai-->", "")
    assert api.save_document(RAIN, accepted, mtime)["ok"]
    s = api.stats_summary()["stats"]
    assert s["today"]["aiWords"] == 4 and s["today"]["words"] == 0


def test_first_save_of_an_unopened_scene_is_a_baseline(tmp_path):
    api, root = open_book(tmp_path)
    mtime = str((root / RAIN).stat().st_mtime_ns)
    r = api.save_document(RAIN, "# Rain\n\n" + "word " * 500, mtime)
    assert r["ok"] and api.stats_summary()["stats"]["today"]["words"] == 0


def test_stats_live_in_the_state_dir_not_the_project(tmp_path):
    api, root = open_book(tmp_path)
    save(api, root, (root / RAIN).read_text(encoding="utf-8") + "\nmore words\n")
    state = tmp_path / "state" / "stats"
    files = list(state.glob("*.json"))
    assert len(files) == 1 and files[0].name == writing_stats.project_id(root) + ".json"
    assert not [p for p in root.rglob("*") if "stats" in p.name.lower()]


def test_workspace_status_carries_the_brief_and_target_setting(tmp_path):
    api, root = open_book(tmp_path)
    brief = api.get_workspace()["workspace"]["status"]["stats"]
    assert brief["target"] == 500 and brief["streak"] == 0 and brief["sprint"] is None
    assert api.set_settings(daily_target=0)["ok"]
    assert api.get_settings()["dailyTarget"] == 0
    assert api.get_workspace()["workspace"]["status"]["stats"]["target"] == 0
    assert not api.set_settings(daily_target=-5)["ok"]


def test_touch_and_sprint_round_trip(tmp_path):
    api, root = open_book(tmp_path)
    assert api.stats_touch()["ok"]
    assert not api.sprint_end()["ok"]            # none running
    assert not api.sprint_start(0)["ok"]
    r = api.sprint_start(25)
    assert r["ok"] and r["sprint"]["minutes"] == 25
    assert api.get_workspace()["workspace"]["status"]["stats"]["sprint"]["minutes"] == 25
    save(api, root, (root / RAIN).read_text(encoding="utf-8") + "\nthree sprint words\n")
    end = api.sprint_end(cancelled=True)
    assert end["ok"] and end["sprint"]["words"] == 3 and end["sprint"]["completed"] is False
    assert api.stats_summary()["stats"]["sprints"][0]["words"] == 3
