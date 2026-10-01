"""Writing stats: words, active minutes, sessions, streak, focus sprints.

Personal data, not book content, so it lives in the user state dir
(``<state>/stats/<project-id>.json``, ``LOREWRITE_STATE_DIR`` honoured), never in
the project folder. ``project-id`` is a hash of the resolved project path.

Counting rules:

* *Words* are the net change of the author's own prose in scenes (pending AI
  drafts are not prose, ``drafts.count_words``). It can be negative for a day of
  cutting. The front ends call :meth:`Tracker.seen` when a scene is opened (a
  baseline, nothing is counted) and :meth:`Tracker.record` when it is saved.
* An accepted AI draft is counted as *AI words* instead; the baseline moves with
  it so the same words are not also the author's (:meth:`Tracker.accepted`).
* *Active time*: each activity ping (typing) adds the gap since the previous one
  if it is at most two minutes. A *session* starts at the first activity after
  thirty idle minutes (or at the first activity of the process).
* *Streak*: consecutive days that met the daily target (or wrote at least one
  word when the target is off), counted back from today; today only breaks the
  streak once the day is over.

File format (version 1)::

    {"version": 1, "project": "/path", "days": {"2026-10-01": {"words": 420,
     "ai_words": 60, "seconds": 3100, "sessions": 2,
     "sprints": [{"at": "...", "minutes": 25, "words": 310, "completed": true}]}}}
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import settings as user_settings
from .recents import default_state_dir

DEFAULT_TARGET = 500
ACTIVE_WINDOW = 120        # seconds: typing this recently counts as active time
SESSION_GAP = 30 * 60      # seconds idle that end a session
MAX_TARGET = 100_000
MAX_SPRINT_MINUTES = 240
CHART_DAYS = 30
_FLUSH_EVERY = 30          # seconds between writes caused by activity pings alone


def stats_dir(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "stats"


def project_id(root: Path) -> str:
    return hashlib.sha1(str(Path(root).expanduser().resolve()).encode("utf-8")).hexdigest()[:16]


def stats_path(root: Path, state_dir: Path | None = None) -> Path:
    return stats_dir(state_dir) / f"{project_id(root)}.json"


# -- the daily target (a user setting) ----------------------------------------------


def get_target(state_dir: Path | None = None) -> int:
    """The daily word target; 0 = off. Default 500."""
    raw = user_settings.get("daily_target", DEFAULT_TARGET, state_dir)
    try:
        return max(0, min(MAX_TARGET, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_TARGET


def set_target(value: int, state_dir: Path | None = None) -> int:
    value = int(value)
    if not 0 <= value <= MAX_TARGET:
        raise ValueError(f"the daily target must be between 0 and {MAX_TARGET:,} words")
    user_settings.set("daily_target", value, state_dir)
    return value


# -- pure helpers --------------------------------------------------------------------


def day_met(words: int, target: int) -> bool:
    return words >= target if target > 0 else words >= 1


def streak(days: dict[str, dict], target: int, today: date) -> int:
    """Consecutive days meeting the target ending today (or yesterday, while
    today is still open)."""
    def met(d: date) -> bool:
        return day_met(int(days.get(d.isoformat(), {}).get("words", 0)), target)

    d = today if met(today) else today - timedelta(days=1)
    n = 0
    while met(d):
        n += 1
        d -= timedelta(days=1)
    return n


def clock(seconds: float) -> str:
    """``24:05`` for a countdown (whole seconds, rounded up)."""
    s = max(0, int(-(-seconds // 1)))
    return f"{s // 60}:{s % 60:02d}"


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    """A one-line bar chart (``▁▃█``); zero or less is the lowest bar."""
    top = max([v for v in values if v > 0], default=0)
    if top <= 0:
        return SPARK[0] * len(values)
    return "".join(SPARK[0] if v <= 0 else SPARK[min(len(SPARK) - 1, max(0, round(v / top * (len(SPARK) - 1))))]
                   for v in values)


@dataclass
class Sprint:
    minutes: int
    started: float          # epoch seconds
    words_at_start: int     # tracker.session_words when it began
    ai_at_start: int = 0

    @property
    def ends(self) -> float:
        return self.started + self.minutes * 60


# -- the tracker ------------------------------------------------------------------------


class Tracker:
    """Stats for one open project. Thread-safe (the GUI calls from workers)."""

    def __init__(self, root: Path, state_dir: Path | None = None, clock=time.time) -> None:
        self.root = Path(root)
        self.state_dir = state_dir
        self.path = stats_path(self.root, state_dir)
        self._clock = clock
        self._lock = threading.RLock()
        self._baseline: dict[str, int] = {}
        self._last_activity: float | None = None
        self._last_flush = 0.0
        self._dirty = False
        self.session_started = self._clock()
        self.session_words = 0
        self.session_ai_words = 0
        self.session_seconds = 0.0
        self.sprint: Sprint | None = None
        self.days: dict[str, dict] = self._load()
        # what this process added since the last write: flush merges it into whatever is on
        # disk, so the terminal app and the desktop app open on one project do not overwrite
        # each other's numbers
        self._unsaved: dict[str, dict] = {}

    # persistence

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            days = data.get("days") if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return {}
        out: dict[str, dict] = {}
        for key, d in (days or {}).items():
            try:
                date.fromisoformat(key)
                out[key] = {
                    "words": int(d.get("words", 0)), "ai_words": int(d.get("ai_words", 0)),
                    "seconds": int(d.get("seconds", 0)), "sessions": int(d.get("sessions", 0)),
                    "sprints": [s for s in d.get("sprints", []) if isinstance(s, dict)],
                }
            except (AttributeError, TypeError, ValueError):
                continue
        return out

    def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            disk = self._load()
            for key, add in self._unsaved.items():
                d = disk.setdefault(key, self._blank())
                for field in ("words", "ai_words", "seconds", "sessions"):
                    d[field] += add[field]
                d["sprints"].extend(add["sprints"])
            self._unsaved.clear()
            self.days = disk
            payload = {"version": 1, "project": str(self.root.expanduser().resolve()), "days": self.days}
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            tmp.replace(self.path)
            self._dirty = False
            self._last_flush = self._clock()

    def _touch_file(self, force: bool) -> None:
        self._dirty = True
        if force or self._clock() - self._last_flush >= _FLUSH_EVERY:
            self.flush()

    # days

    def _today(self, now: float | None = None) -> date:
        return datetime.fromtimestamp(self._clock() if now is None else now).date()

    @staticmethod
    def _blank() -> dict:
        return {"words": 0, "ai_words": 0, "seconds": 0, "sessions": 0, "sprints": []}

    def _bump(self, field: str, n: int, now: float | None = None) -> None:
        """Add *n* to today's *field* (and remember it as unsaved)."""
        key = self._today(now).isoformat()
        self.days.setdefault(key, self._blank())[field] += n
        self._unsaved.setdefault(key, self._blank())[field] += n

    def _add_sprint(self, rec: dict, now: float) -> None:
        key = self._today(now).isoformat()
        self.days.setdefault(key, self._blank())["sprints"].append(rec)
        self._unsaved.setdefault(key, self._blank())["sprints"].append(rec)

    # activity

    def _activity(self, now: float) -> None:
        last = self._last_activity
        if last is None or now - last > SESSION_GAP:
            self._bump("sessions", 1, now)
            if last is not None:           # a new session after a long pause
                self.session_started = now
                self.session_words = self.session_ai_words = 0
                self.session_seconds = 0.0
        elif now - last <= ACTIVE_WINDOW and now > last:
            self._bump("seconds", int(round(now - last)), now)
            self.session_seconds += now - last
        self._last_activity = now

    def touch(self) -> None:
        """The author is typing (call at most every few seconds)."""
        with self._lock:
            self._activity(self._clock())
            self._touch_file(force=False)

    # words

    def seen(self, key: str, words: int) -> None:
        """A scene was opened or replaced from disk: this is its baseline."""
        with self._lock:
            self._baseline[key] = int(words)

    def forget(self, key: str) -> None:
        with self._lock:
            self._baseline.pop(key, None)

    def record(self, key: str, words: int) -> int:
        """A scene was saved with *words* of the author's prose; returns the
        change counted (0 for the first sight of a scene)."""
        with self._lock:
            words = int(words)
            old = self._baseline.get(key)
            self._baseline[key] = words
            if old is None or old == words:
                return 0
            delta = words - old
            now = self._clock()
            self._activity(now)
            self._bump("words", delta, now)
            self.session_words += delta
            self._touch_file(force=True)
            return delta

    def accepted(self, key: str, body_words: int, replaced_words: int = 0) -> None:
        """An AI draft became prose: count its words as AI words and move the
        baseline so they are not also the author's."""
        with self._lock:
            body_words, replaced_words = max(0, int(body_words)), max(0, int(replaced_words))
            now = self._clock()
            self._activity(now)
            self._bump("ai_words", body_words, now)
            self.session_ai_words += body_words
            if key in self._baseline:
                self._baseline[key] += body_words - replaced_words
            self._touch_file(force=True)

    # sprints

    def start_sprint(self, minutes: int) -> Sprint:
        minutes = int(minutes)
        if not 1 <= minutes <= MAX_SPRINT_MINUTES:
            raise ValueError(f"a sprint is 1 to {MAX_SPRINT_MINUTES} minutes")
        with self._lock:
            self.sprint = Sprint(minutes, self._clock(), self.session_words, self.session_ai_words)
            return self.sprint

    def sprint_words(self) -> int:
        with self._lock:
            return 0 if self.sprint is None else self.session_words - self.sprint.words_at_start

    def finish_sprint(self, cancelled: bool = False) -> dict | None:
        """End the sprint and record it in today's stats; returns the record
        (``minutes`` is the planned length, ``elapsed`` seconds actually run)."""
        with self._lock:
            sp = self.sprint
            if sp is None:
                return None
            self.sprint = None
            now = self._clock()
            rec = {"at": datetime.fromtimestamp(sp.started).isoformat(timespec="seconds"),
                   "minutes": sp.minutes, "elapsed": int(min(now, sp.ends) - sp.started),
                   "words": self.session_words - sp.words_at_start,
                   "completed": not cancelled and now >= sp.ends - 1}
            self._add_sprint(rec, now)
            self._touch_file(force=True)
            return rec

    def sprint_state(self) -> dict | None:
        with self._lock:
            sp = self.sprint
            if sp is None:
                return None
            now = self._clock()
            return {"minutes": sp.minutes, "startedAt": sp.started, "endsAt": sp.ends,
                    "remaining": max(0, int(round(sp.ends - now))), "words": self.sprint_words(),
                    "done": now >= sp.ends}

    # reading

    def summary(self, target: int | None = None, project_words: int = 0) -> dict:
        with self._lock:
            target = get_target(self.state_dir) if target is None else target
            today = self._today()
            tday = self.days.get(today.isoformat(), {})
            chart = []
            for i in range(CHART_DAYS - 1, -1, -1):
                d = today - timedelta(days=i)
                chart.append({"date": d.isoformat(),
                              "words": int(self.days.get(d.isoformat(), {}).get("words", 0))})
            total_words = sum(max(0, int(d["words"])) for d in self.days.values())
            total_sessions = sum(int(d["sessions"]) for d in self.days.values())
            best = max(((k, int(d["words"])) for k, d in self.days.items()),
                       key=lambda kv: kv[1], default=None)
            words_today = int(tday.get("words", 0))
            return {
                "target": target,
                "streak": streak(self.days, target, today),
                "todayMet": day_met(words_today, target),
                "today": {"words": words_today, "aiWords": int(tday.get("ai_words", 0)),
                          "minutes": int(tday.get("seconds", 0)) // 60,
                          "sessions": int(tday.get("sessions", 0))},
                "session": {"words": self.session_words, "aiWords": self.session_ai_words,
                            "minutes": int(self.session_seconds // 60),
                            "startedAt": self.session_started},
                "chart": chart,
                "averagePerSession": round(total_words / total_sessions) if total_sessions else 0,
                "bestDay": {"date": best[0], "words": best[1]} if best and best[1] > 0 else None,
                "daysWritten": sum(1 for d in self.days.values() if int(d["words"]) > 0),
                "totalWords": total_words,
                "projectWords": int(project_words),
                "sprints": list(tday.get("sprints", [])),
                "sprint": self.sprint_state(),
            }

    def close(self) -> None:
        """Flush. A sprint still running (the app is closing) is recorded as
        stopped early, unless it has barely begun and written nothing."""
        with self._lock:
            sp = self.sprint
            if sp is not None and (self._clock() - sp.started >= 60 or self.sprint_words()):
                self.finish_sprint(cancelled=True)
            self.sprint = None
            self.flush()


def signed(n: int) -> str:
    """A net word change in one form everywhere: ``+1,240``, ``−35`` (real minus), ``±0``."""
    return f"+{n:,}" if n > 0 else f"\u2212{-n:,}" if n < 0 else "\u00b10"


def format_summary(s: dict) -> str:
    """Plain-text version of :meth:`Tracker.summary` for the terminal page."""
    t, ses = s["today"], s["session"]
    target = s["target"]
    goal = f" of {target:,}" if target else ""
    best = s["bestDay"]
    lines = [
        f"Today          {signed(t['words'])} words{goal}  ·  {t['minutes']} min  ·  {t['sessions']} session(s)"
        + (f"  ·  {t['aiWords']:,} AI words accepted" if t["aiWords"] else ""),
        f"This session   {signed(ses['words'])} words  ·  {ses['minutes']} min",
        f"Streak         {s['streak']} day(s)" + ("  (today met)" if s["todayMet"] and s["streak"] else ""),
        f"Best day       {best['words']:,} words on {best['date']}" if best else "Best day       none yet",
        f"Per session    {s['averagePerSession']:,} words on average",
        f"Project        {s['projectWords']:,} words in the book  ·  {s['totalWords']:,} written with lorewrite",
        "",
        f"Last {CHART_DAYS} days  {sparkline([c['words'] for c in s['chart']])}",
    ]
    done = [sp for sp in s["sprints"]]
    if done:
        lines += ["", "Sprints today  " + ", ".join(
            f"{sp['minutes']} min: {signed(sp['words'])} words" + ("" if sp.get("completed") else " (stopped)")
            for sp in done)]
    return "\n".join(lines)
