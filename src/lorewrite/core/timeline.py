"""Optional story time (SPEC "Story time").

Time metadata is the author's choice. A scene may carry ``when:`` in its details
frontmatter and a character ``born:`` in the note's frontmatter; both are a
YEAR, optionally with a month and a day (``2187``, ``2187-03``, ``2187-03-14``;
negative and zero years are fine). With none of it, every feature here falls
back to READING ORDER and says so. Nothing in this module ever reorders the
book, and nothing guesses: a value that is not a story time is kept as text and
reported, never dropped.

A story time is deliberately not a ``datetime``: invented calendars have years
past 9999 and before 1, and a fictional "March" need not be ours. Months are
1-12 and days 1-31, nothing stricter. ``StoryTime`` compares by (year, month,
day) with a missing month/day sorting BEFORE a known one in the same year.

Pure Python, no Textual and no I/O beyond reading scene files.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from functools import total_ordering
from pathlib import Path

from . import fsutil, scenemeta

UNIT_YEAR = "year"
UNITS = (UNIT_YEAR,)
MODE_CHRONOLOGICAL = "chronological"
MODE_READING_ORDER = "reading-order"
SOURCE_EXPLICIT, SOURCE_INHERITED, SOURCE_NONE = "explicit", "inherited", "none"
NOT_A_TIME = "not a story time"

_TIME_RE = re.compile(r"^(-?\d{1,12})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$")


@total_ordering
@dataclass(frozen=True)
class StoryTime:
    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if self.month is None and self.day is not None:
            raise ValueError("a day needs a month")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError("month must be 1-12")
        if self.day is not None and not 1 <= self.day <= 31:
            raise ValueError("day must be 1-31")

    @property
    def key(self) -> tuple[int, int, int]:
        """Sort key: a missing month/day (0) sorts before every known one."""
        return (self.year, self.month or 0, self.day or 0)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, StoryTime):
            return NotImplemented
        return self.key < other.key

    @classmethod
    def parse(cls, text: object, era: str = "") -> StoryTime | None:
        return parse_story_time(text, era)

    def format(self, era: str = "") -> str:
        """``2187`` / ``2187-03`` / ``2187-03-14``, plus `` AE`` when an era is set."""
        out = str(self.year)
        if self.month is not None:
            out += f"-{self.month:02d}"
            if self.day is not None:
                out += f"-{self.day:02d}"
        return f"{out} {era}" if era else out


def parse_story_time(value: object, era: str = "") -> StoryTime | None:
    """A StoryTime from text (or a YAML int / date), else None. With *era* set,
    that label may follow the time (``2187 AE``), case-insensitively."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return StoryTime(value)
    if isinstance(value, (datetime.date, datetime.datetime)):  # YAML read `2187-03-14` as a date
        return StoryTime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if era and text.casefold().endswith(era.casefold()) and len(text) > len(era):
        head = text[: -len(era)]
        if head.endswith(" "):
            text = head.rstrip()
    m = _TIME_RE.match(text)
    if m is None:
        return None
    year, month, day = m.groups()
    try:
        return StoryTime(int(year), int(month) if month else None, int(day) if day else None)
    except ValueError:
        return None


def stored_value(text: object) -> int | str:
    """What to write in frontmatter for the *text* the author typed: a bare year
    becomes a plain YAML number (``when: 2187``), anything else stays text
    (invalid values are kept, never dropped)."""
    raw = " ".join(str(text if text is not None else "").split())
    if re.fullmatch(r"-?\d+", raw) and str(int(raw)) == raw:
        return int(raw)
    return raw


def toml_era(value: object) -> str:
    """The era label from project.toml: only a short single-line string counts."""
    if isinstance(value, str) and len(value.strip()) <= 24 and "\n" not in value:
        return value.strip()
    return ""


# -- scenes in reading order ------------------------------------------------------------


@dataclass(frozen=True)
class SceneTime:
    id: str                       # project-relative path (the GUI's document id)
    path: Path
    when: StoryTime | None        # explicit, else inherited, else None
    source: str                   # explicit | inherited | none
    raw: str = ""                 # the text of the scene's own `when:` ("" = none)
    invalid: bool = False         # `when:` is set but is not a story time

    def format(self, era: str = "") -> str:
        return self.when.format(era) if self.when else ""


def explicit_when(text: str, era: str = "") -> tuple[str, StoryTime | None]:
    """(raw `when:` text, its StoryTime or None) for one scene's text."""
    raw = scenemeta.details(text)["when"]
    return raw, (parse_story_time(raw, era) if raw else None)


def scene_times(project) -> list[SceneTime]:
    """Every scene of the book in READING ORDER (``list_scenes``: Parked scenes
    are not in it) with its story time: its own ``when`` (explicit) or the last
    explicit one before it (inherited); None before the first. An invalid
    ``when`` is reported (``invalid``) and does not count as explicit."""
    era = project.timeline_settings()["era"]
    out: list[SceneTime] = []
    current: StoryTime | None = None
    for path in project.list_scenes():
        try:
            text = fsutil.read_text_lenient(path)
        except OSError:
            text = ""
        raw, when = explicit_when(text, era)
        rel = path.relative_to(project.root).as_posix()
        if when is not None:
            current = when
            out.append(SceneTime(rel, path, when, SOURCE_EXPLICIT, raw))
        elif current is not None:
            out.append(SceneTime(rel, path, current, SOURCE_INHERITED, raw, invalid=bool(raw)))
        else:
            out.append(SceneTime(rel, path, None, SOURCE_NONE, raw, invalid=bool(raw)))
    return out


@dataclass(frozen=True)
class Mode:
    mode: str            # chronological | reading-order
    scenes: int          # scenes with an explicit, valid `when`
    sentence: str        # for the UI

    def to_dict(self) -> dict:
        return {"mode": self.mode, "scenes": self.scenes, "sentence": self.sentence}


def mode(project, times: list[SceneTime] | None = None) -> Mode:
    """``chronological`` when at least one scene has an explicit valid ``when``,
    else ``reading-order``, with the sentence the UI shows."""
    times = scene_times(project) if times is None else times
    return mode_for_count(sum(1 for t in times if t.source == SOURCE_EXPLICIT))


def mode_for_count(n: int) -> Mode:
    """The mode when *n* book scenes have an explicit, valid ``when``."""
    if n:
        return Mode(MODE_CHRONOLOGICAL, n,
                    f"Using story time from {n} scene{'' if n == 1 else 's'}")
    return Mode(MODE_READING_ORDER, 0, "No story times set; using reading order")


@dataclass(frozen=True)
class AsOf:
    """What ``scenes_up_to`` found. *scenes* keep READING ORDER (a subset of the
    book, never re-sorted). *undated* are the included scenes that have no story
    time yet (before the first explicit one) and were placed by reading order."""
    scenes: list[SceneTime]
    mode: str
    sentence: str
    target: SceneTime | None = None
    undated: list[str] = field(default_factory=list)


def scenes_up_to(project, scene_id: str, times: list[SceneTime] | None = None) -> AsOf:
    """The scenes at or before *scene_id*: by story time when the project has any
    (a scene counts when its time <= the target's; a scene at the same time counts
    only if it is not after the target in reading order), else by reading order.
    When the target has no story time (it comes before the first explicit one) the
    answer is by reading order, and ``mode`` says so. A scene that is not in the
    book (Parked, unknown) gives no scenes. This is the single door for "as of"
    filtering; do not re-implement it."""
    times = scene_times(project) if times is None else times
    info = mode(project, times)
    index = next((i for i, t in enumerate(times) if t.id == scene_id), None)
    if index is None:
        return AsOf([], info.mode, "This scene is not in the book's reading order")
    target = times[index]
    by_reading = times[: index + 1]
    if info.mode == MODE_READING_ORDER:
        return AsOf(by_reading, MODE_READING_ORDER, info.sentence, target)
    if target.when is None:
        return AsOf(by_reading, MODE_READING_ORDER,
                    "This scene has no story time yet; using reading order", target)
    keep: list[SceneTime] = []
    undated: list[str] = []
    for i, t in enumerate(times):
        if t.when is None:
            if i <= index:
                keep.append(t)
                undated.append(t.id)
        elif t.when < target.when or (t.when == target.when and i <= index):
            keep.append(t)
    return AsOf(keep, MODE_CHRONOLOGICAL, info.sentence, target, undated)


# -- ages -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Age:
    years: int | None
    reason: str = ""       # why there is no age: no born | invalid born | no story time | before birth
    born: StoryTime | None = None

    def __bool__(self) -> bool:
        return self.years is not None


def born_of(entity, era: str = "") -> tuple[str, StoryTime | None]:
    """(raw `born:` text, StoryTime or None) of a note ("" when it has none)."""
    value = entity.extra.get("born") if getattr(entity, "extra", None) else None
    if value is None or value == "":
        return "", None
    if isinstance(value, (datetime.date, datetime.datetime)):
        raw = value.date().isoformat() if isinstance(value, datetime.datetime) else value.isoformat()
    else:
        raw = " ".join(str(value).split())
    return raw, parse_story_time(value, era)


def age_at(entity, when: StoryTime | None, era: str = "") -> Age:
    """Whole years from the entity's ``born`` to *when*. Month and day count only
    when both sides know them, else it is the year difference. Before the birth
    there is no age (``years`` None, reason ``before birth``)."""
    raw, born = born_of(entity, era)
    if not raw:
        return Age(None, "no born")
    if born is None:
        return Age(None, "invalid born")
    if when is None:
        return Age(None, "no story time", born)
    years = when.year - born.year
    if born.month is not None and when.month is not None:
        if when.month < born.month or (when.month == born.month and born.day is not None
                                       and when.day is not None and when.day < born.day):
            years -= 1
    if years < 0:
        return Age(None, "before birth", born)
    return Age(years, "", born)


def age_label(entity, when: StoryTime | None, era: str = "") -> str:
    """``age 24 at 2189 AE`` for the UI, or "" when there is no age to show."""
    age = age_at(entity, when, era)
    return f"age {age.years} at {when.format(era)}" if age and when else ""


# -- fact tags (not wired into any AI yet) ---------------------------------------------------


@dataclass(frozen=True)
class FactTag:
    kind: str                    # at (age N) | from | until
    age: int | None = None       # (age 12), (from age 15), (until age 20)
    time: StoryTime | None = None  # (from 2185), (until 2190-06)


_TAIL_RE = re.compile(r"^(?P<text>.*?)[ \t]*\((?P<tag>[^()]*)\)[ \t]*$", re.DOTALL)
_AGE_RE = re.compile(r"^(?:(?P<kind>from|until)\s+)?age\s+(?P<n>\d{1,4})$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^(?P<kind>from|until)\s+(?P<when>\S.*)$", re.IGNORECASE)


def parse_fact_tags(line: str) -> tuple[str, FactTag | None]:
    """Split a trailing tag off a canon line: ``- Plays the cello (from age 15)``
    -> (``- Plays the cello``, FactTag). Recognised: ``(age 12)``, ``(from age 15)``,
    ``(until age 20)``, ``(from 2185)``, ``(until 2190-06)``. A malformed tag (or
    none) returns the line unchanged and None; the tag must be at the end."""
    m = _TAIL_RE.match(line)
    if m is None:
        return line, None
    tag_text = " ".join(m.group("tag").split())
    tag: FactTag | None = None
    a = _AGE_RE.match(tag_text)
    if a:
        tag = FactTag(a.group("kind").lower() if a.group("kind") else "at", age=int(a.group("n")))
    else:
        r = _RANGE_RE.match(tag_text)
        if r:
            when = parse_story_time(r.group("when"))
            if when is not None:
                tag = FactTag(r.group("kind").lower(), time=when)
    if tag is None or not m.group("text").strip(" \t-*•"):
        return line, None
    return m.group("text").rstrip(), tag
