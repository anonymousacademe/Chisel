"""Journal and funder profiles of research mode: starter outline, requirements and citation style.

A profile is a TOML file in ``core/paper/journals/`` (package data), our own restatement of a journal's rules.
``list_profiles`` and ``load_profile`` never raise anything but ``ValueError``; a missing or malformed profile
is a clean error and must never stop a project from opening (callers catch it and fall back to "no profile").
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("manuscript", "proposal")
DEFAULT_KIND = "manuscript"
CITATION_STYLES = ("apa", "harvard")
DEFAULT_STYLE = "apa"
GENERIC_ID = {"manuscript": "manuscript", "proposal": "proposal"}
FIRST = "ems"                       # listed first, then the generic profiles, then the rest by name

# every check kind core/paper/requirements.py implements (a profile may use only these, plus "advice" rows)
CHECK_KINDS = (
    "section-present", "section-words-max", "section-no-citations", "list-count", "last-section",
    "objects-captioned", "objects-referenced", "citations-resolved", "sources-doi", "ai-declaration",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class OutlineSection:
    title: str
    purpose: str = ""


@dataclass(frozen=True)
class OutlinePart:
    part: str
    sections: tuple[OutlineSection, ...] = ()
    front_matter: bool = False


@dataclass(frozen=True)
class Requirement:
    id: str
    group: str
    title: str
    kind: str                                   # "check" | "advice"
    check: str = ""
    section: tuple[str, ...] = ()
    severity: str = "warn"                      # "warn" | "info"
    params: dict = field(default_factory=dict)  # every other key (max, min, item_chars_max, object, ...)


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    publisher: str
    kind: str
    source: str
    read_on: str
    citation_style: str
    outline: tuple[OutlinePart, ...] = ()
    requirements: tuple[Requirement, ...] = ()


def journals_dir() -> Path:
    return Path(__file__).parent / "journals"


def is_plain_id(profile_id: object) -> bool:
    return isinstance(profile_id, str) and bool(_ID_RE.match(profile_id))


def _text(table: dict, key: str, default: str = "") -> str:
    value = table.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _parse(profile_id: str, data: dict) -> Profile:
    if _text(data, "id") != profile_id:
        raise ValueError(f"The profile file for {profile_id} does not carry that id.")
    kind = _text(data, "kind")
    if kind not in KINDS:
        raise ValueError(f"The profile {profile_id} has an unknown kind.")
    style = _text(data, "citation_style", DEFAULT_STYLE) or DEFAULT_STYLE
    if style not in CITATION_STYLES:
        style = DEFAULT_STYLE
    parts = []
    for raw in data.get("outline") or []:
        if not isinstance(raw, dict) or not _text(raw, "part"):
            raise ValueError(f"The profile {profile_id} has an outline part without a name.")
        sections = []
        for s in raw.get("sections") or []:
            if not isinstance(s, dict) or not _text(s, "title"):
                raise ValueError(f"The profile {profile_id} has an outline section without a title.")
            sections.append(OutlineSection(_text(s, "title"), _text(s, "purpose")))
        parts.append(OutlinePart(_text(raw, "part"), tuple(sections), bool(raw.get("front_matter"))))
    reqs = []
    seen: set[str] = set()
    for raw in data.get("requirement") or []:
        if not isinstance(raw, dict):
            raise ValueError(f"The profile {profile_id} has a malformed requirement.")
        rid, rkind = _text(raw, "id"), _text(raw, "kind")
        if not rid or rid in seen or rkind not in ("check", "advice") or not _text(raw, "title"):
            raise ValueError(f"The profile {profile_id} has a malformed requirement ({rid or '?'}).")
        seen.add(rid)
        check = _text(raw, "check")
        if rkind == "check" and check not in CHECK_KINDS:
            raise ValueError(f"The profile {profile_id} uses an unknown check ({check or '?'}).")
        severity = _text(raw, "severity", "warn")
        section = raw.get("section") or []
        if not isinstance(section, list) or not all(isinstance(x, str) for x in section):
            raise ValueError(f"The requirement {rid} has a malformed section list.")
        known = {"id", "group", "title", "kind", "check", "section", "severity"}
        reqs.append(Requirement(rid, _text(raw, "group") or "Other", _text(raw, "title"), rkind, check,
                                tuple(x.strip().casefold() for x in section if x.strip()),
                                severity if severity in ("warn", "info") else "warn",
                                {k: v for k, v in raw.items() if k not in known}))
    return Profile(profile_id, _text(data, "name") or profile_id, _text(data, "publisher"), kind,
                   _text(data, "source"), _text(data, "read_on"), style, tuple(parts), tuple(reqs))


def load_profile(profile_id: str) -> Profile:
    """The profile called *profile_id*. ``ValueError`` (plain words) when the id is not a plain name, the file
    is missing, or it does not parse."""
    if not is_plain_id(profile_id):
        raise ValueError("That is not a journal profile name.")
    path = journals_dir() / f"{profile_id}.toml"
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ValueError(f"There is no journal profile called {profile_id}.") from None
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"The journal profile {profile_id} could not be read.") from exc
    return _parse(profile_id, data)


def list_profiles() -> list[Profile]:
    """Every profile that loads, ordered: "ems", the generic ones, then the rest by name. Broken files are
    skipped (listing must never fail)."""
    found: list[Profile] = []
    try:
        names = sorted(p.stem for p in journals_dir().glob("*.toml"))
    except OSError:
        return []
    for name in names:
        try:
            found.append(load_profile(name))
        except ValueError:
            continue
    generic = list(GENERIC_ID.values())

    def rank(p: Profile) -> tuple[int, str]:
        if p.id == FIRST:
            return (0, "")
        if p.id in generic:
            return (1, str(generic.index(p.id)))
        return (2, p.name.casefold())
    return sorted(found, key=rank)


def profile_for(kind: str, journal: str = "") -> Profile | None:
    """The profile that applies to a project of *kind* with *journal* chosen: the journal's profile when it
    loads and its kind matches, else None."""
    if not journal:
        return None
    try:
        p = load_profile(journal)
    except ValueError:
        return None
    return p if p.kind == kind else None


def starter_profile(kind: str, journal: str = "") -> Profile | None:
    """The profile a new project's starter outline comes from: the journal's when it applies, else the generic
    profile of the kind."""
    p = profile_for(kind, journal)
    if p is not None:
        return p
    try:
        return load_profile(GENERIC_ID.get(kind, GENERIC_ID[DEFAULT_KIND]))
    except ValueError:
        return None
