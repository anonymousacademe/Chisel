"""Writing stats (core/stats.py): counting rules, streak, sprints, state dir."""

import json
from datetime import date, datetime, timedelta

from lorewrite.core import stats


class Clock:
    def __init__(self, when="2026-10-01 09:00:00"):
        self.t = datetime.fromisoformat(when).timestamp()

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def tracker(tmp_path, clock=None):
    return stats.Tracker(tmp_path / "book", state_dir=tmp_path / "state", clock=clock or Clock())


def test_first_sight_is_a_baseline_not_words(tmp_path):
    t = tracker(tmp_path)
    assert t.record("a.md", 500) == 0
    assert t.summary()["today"]["words"] == 0


def test_net_words_across_saves_and_negative(tmp_path):
    t = tracker(tmp_path)
    t.seen("a.md", 100)
    assert t.record("a.md", 130) == 30
    assert t.record("a.md", 120) == -10
    assert t.record("a.md", 120) == 0
    assert t.summary()["today"]["words"] == 20
    assert t.summary()["session"]["words"] == 20


def test_accepted_draft_counts_as_ai_words_not_author_words(tmp_path):
    t = tracker(tmp_path)
    t.seen("a.md", 100)         # pending drafts are not in this count
    t.accepted("a.md", body_words=40, replaced_words=10)
    # after accept the saved count is 100 - 0 + (40 - 10) = 130 author-countable words
    assert t.record("a.md", 130) == 0
    s = t.summary()
    assert s["today"]["aiWords"] == 40 and s["today"]["words"] == 0
    assert t.record("a.md", 135) == 5     # the author's own typing still counts


def test_active_minutes_and_sessions(tmp_path):
    c = Clock()
    t = tracker(tmp_path, c)
    t.touch()
    for _ in range(4):
        c.advance(60)
        t.touch()                # 4 minutes of continuous typing
    c.advance(10 * 60)
    t.touch()                    # a 10 minute pause: not active time, same session
    assert t.summary()["today"]["minutes"] == 4
    assert t.summary()["today"]["sessions"] == 1
    c.advance(31 * 60)
    t.touch()                    # past the session gap: a second session
    s = t.summary()
    assert s["today"]["sessions"] == 2
    assert s["session"]["words"] == 0 and s["session"]["minutes"] == 0


def test_streak_rules():
    today = date(2026, 10, 10)

    def days(*spec):
        return {(today - timedelta(days=ago)).isoformat(): {"words": w} for ago, w in spec}

    assert stats.streak(days((0, 600), (1, 500), (2, 900), (4, 900)), 500, today) == 3
    # today unfinished does not break it, but yesterday missing does
    assert stats.streak(days((0, 100), (1, 700), (2, 700)), 500, today) == 2
    assert stats.streak(days((0, 100), (2, 700)), 500, today) == 0
    # target off: any word counts
    assert stats.streak(days((0, 1), (1, 3)), 0, today) == 2
    assert stats.streak({}, 500, today) == 0


def test_sparkline():
    assert stats.sparkline([0, 0]) == "▁▁"
    line = stats.sparkline([0, 50, 100])
    assert line[0] == "▁" and line[-1] == "█" and len(line) == 3


def test_summary_aggregates(tmp_path):
    c = Clock("2026-10-01 09:00:00")
    t = tracker(tmp_path, c)
    t.seen("a", 0)
    c.advance(60)
    t.record("a", 300)
    c.advance(86400)
    t.record("a", 1000)
    s = t.summary(target=500, project_words=4200)
    assert s["bestDay"] == {"date": "2026-10-02", "words": 700}
    assert s["streak"] == 1      # day 1 missed the target, day 2 met it
    assert s["projectWords"] == 4200 and s["totalWords"] == 1000
    assert len(s["chart"]) == stats.CHART_DAYS and s["chart"][-1]["words"] == 700
    assert s["averagePerSession"] == 500       # 1000 words / 2 sessions
    assert "Streak" in stats.format_summary(s)


def test_persists_in_state_dir_keyed_by_project(tmp_path, monkeypatch):
    t = tracker(tmp_path)
    t.seen("a", 1)
    t.record("a", 11)
    t.flush()
    p = stats.stats_path(tmp_path / "book", tmp_path / "state")
    assert p.parent == tmp_path / "state" / "stats" and p.is_file()
    assert json.loads(p.read_text())["days"]["2026-10-01"]["words"] == 10
    assert tracker(tmp_path).summary()["today"]["words"] == 10     # reloaded
    assert stats.project_id(tmp_path / "book") != stats.project_id(tmp_path / "other")
    # a corrupt file is ignored, not fatal
    p.write_text("{nope")
    assert tracker(tmp_path).summary()["today"]["words"] == 0


def test_state_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LOREWRITE_STATE_DIR", str(tmp_path / "envstate"))
    t = stats.Tracker(tmp_path / "book")
    assert t.path.parent == tmp_path / "envstate" / "stats"
    assert stats.get_target() == 500
    stats.set_target(0)
    assert stats.get_target() == 0
    stats.set_target(1200)
    assert stats.get_target() == 1200
    try:
        stats.set_target(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative target accepted")


def test_sprint_words_and_record(tmp_path):
    c = Clock()
    t = tracker(tmp_path, c)
    t.seen("a", 0)
    t.record("a", 50)            # before the sprint: not counted in it
    sp = t.start_sprint(25)
    c.advance(600)
    t.record("a", 180)
    state = t.sprint_state()
    assert state["words"] == 130 and not state["done"] and state["remaining"] == 25 * 60 - 600
    c.advance(25 * 60)
    assert t.sprint_state()["done"]
    rec = t.finish_sprint()
    assert rec["words"] == 130 and rec["completed"] and rec["minutes"] == 25 and sp.minutes == 25
    assert t.sprint_state() is None and t.finish_sprint() is None
    assert t.summary()["sprints"][0]["words"] == 130


def test_cancelled_sprint_is_recorded_unfinished(tmp_path):
    c = Clock()
    t = tracker(tmp_path, c)
    t.start_sprint(15)
    c.advance(120)
    rec = t.finish_sprint(cancelled=True)
    assert rec["completed"] is False and rec["elapsed"] == 120
    for bad in (0, 241):
        try:
            t.start_sprint(bad)
        except ValueError:
            continue
        raise AssertionError("bad sprint length accepted")


def test_clock_text():
    assert stats.clock(1500) == "25:00"
    assert stats.clock(61.2) == "1:02"
    assert stats.clock(-4) == "0:00"


def test_close_records_a_running_sprint_as_stopped(tmp_path):
    c = Clock()
    t = tracker(tmp_path, c)
    t.start_sprint(25)
    t.close()                      # barely begun, nothing written: dropped
    assert tracker(tmp_path, c).summary()["sprints"] == []
    t = tracker(tmp_path, c)
    t.start_sprint(25)
    c.advance(300)
    t.close()
    s = tracker(tmp_path, c).summary()["sprints"]
    assert len(s) == 1 and s[0]["completed"] is False and s[0]["elapsed"] == 300
