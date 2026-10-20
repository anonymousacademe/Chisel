"""The requirements checklist of a research project: its journal profile's rows evaluated against the project.

``evaluate(project)`` is read-only and never raises for a bad project; a row that cannot be evaluated is
``na``. Requirements never block an export. Statuses: ``ok``, ``warn``, ``info`` (a failed row of severity
info), ``na`` (nothing to check yet), ``advice`` (a reminder, never evaluated).

Sections are the scenes of the book in reading order, front matter included (``Project.list_scenes``); a
section's title is its ``# heading`` and its text is the body without details and without pending AI drafts.
A profile pattern matches a section when it is a case-insensitive substring of the section's title.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

from .. import drafts, links, objects, scenemeta
from ..entities import resolve_key, source_key
from . import custom_requirements, journals

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WORD = {"fig": "figure", "tbl": "table", "eq": "equation"}


@dataclass
class _Section:
    title: str
    text: str            # body: no details, no pending AI drafts, no heading, no HTML comments
    words: int


def _heading_and_body(text: str, path: Path, originals: dict[str, str] | None = None) -> tuple[str, str]:
    body = scenemeta.strip(drafts.strip_pending(text, originals))
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip(), "\n".join(lines[i + 1:])
        if line.strip():
            break
    words = re.split(r"[-_\s]+", re.sub(r"^\d+-", "", path.stem))
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or path.stem, body


def _sections(project) -> list[_Section]:
    out = []
    for path in project.list_scenes():
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        originals = drafts.load_originals(project.root, path)
        title, body = _heading_and_body(raw, path, originals)
        body = _COMMENT_RE.sub("", body)
        out.append(_Section(title, body.strip(), project.count_words(body)))
    return out


def _find(sections: list[_Section], patterns: tuple[str, ...]) -> list[_Section]:
    exact = [s for s in sections if s.title.strip().casefold() in patterns]
    if exact:
        return exact
    return [s for s in sections if any(p in s.title.casefold() for p in patterns)]


def _pattern_text(patterns: tuple[str, ...]) -> str:
    return " or ".join(f'"{p}"' for p in patterns)


def _book_prose(project) -> list[str]:
    """Prose of every book scene as the checks read it: no pending AI text, no details, no research math."""
    out = []
    for path in project.list_scenes():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = drafts.reject_all(text, drafts.load_originals(project.root, path))
        out.append(objects.strip_math(scenemeta.blank(text), mode="research"))
    return out


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _list_items(section: _Section, lines_only: bool) -> list[str]:
    text = section.text
    if lines_only or any(_BULLET_RE.match(line) for line in text.splitlines()):
        items: list[str] = []
        continuing = False      # a blank line ends a bullet: text after it is not part of it
        for line in text.splitlines():
            if not line.strip():
                continuing = False
                continue
            m = _BULLET_RE.match(line)
            if m:
                items.append(m.group(1).strip())
                continuing = True
            elif lines_only and not any(_BULLET_RE.match(x) for x in text.splitlines()):
                items.append(line.strip())
            elif items and continuing:   # lazy continuation of the previous bullet
                items[-1] += " " + line.strip()
            # else: an intro line before the first bullet, or a note after the list
        return items
    return [p.strip() for p in re.split(r"[,;\n]", text) if p.strip()]


def _shorten(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "..."


def _accepted_ai_words(project) -> int:
    from ..stats import Tracker
    try:
        days = Tracker(project.root).days
        return sum(int(d.get("ai_words", 0)) for d in days.values())
    except Exception:       # stats are personal state; never let them break the checklist
        return 0


class _Context:
    def __init__(self, project) -> None:
        self.project = project
        self.sections = _sections(project)
        self._prose: list[str] | None = None
        self._entities = None

    @property
    def prose(self) -> list[str]:
        if self._prose is None:
            self._prose = _book_prose(self.project)
        return self._prose

    @property
    def entities(self):
        if self._entities is None:
            self._entities = self.project.load_entities()
        return self._entities


def _fail(req: journals.Requirement) -> str:
    return req.severity if req.severity in ("warn", "info") else "warn"


def _check(req: journals.Requirement, ctx: _Context) -> tuple[str, str]:
    kind = req.check
    pats = req.section
    if kind == "section-present":
        hit = _find(ctx.sections, pats)
        if hit:
            full = [s for s in hit if s.text]
            if full:
                return "ok", f'Found "{full[0].title}".'
            return _fail(req), f"{hit[0].title} is there but empty."
        return _fail(req), f"No section has {_pattern_text(pats)} in its title."
    if kind in ("section-words-max", "section-no-citations", "list-count"):
        hit = _find(ctx.sections, pats)
        if not hit:
            return "na", f"There is no section with {_pattern_text(pats)} in its title yet."
        sec = next((s for s in hit if s.text), hit[0])
        if not sec.text:
            # nothing written yet: a limit or a count is not met; "no citations" has nothing to look at
            return ("na" if kind == "section-no-citations" else _fail(req)), f"{sec.title} is empty."
        if kind == "section-words-max":
            limit = int(req.params.get("max", 0))
            if sec.words > limit:
                return _fail(req), f"{sec.title} is {_count(sec.words, 'word')}; the limit is {limit}."
            return "ok", f"{sec.title} is {_count(sec.words, 'word')}; the limit is {limit}."
        if kind == "section-no-citations":
            found = links.find_citations(sec.text)
            if found:
                return _fail(req), f"{sec.title} contains {_count(len(found), 'citation')}."
            return "ok", f"{sec.title} has no citations."
        return _list_count(req, sec)
    if kind == "last-section":
        hit = _find(ctx.sections, pats)
        if not hit:
            return "na", f"There is no section with {_pattern_text(pats)} in its title yet."
        if not any(s.text for s in hit):
            return "na", f"{hit[0].title} is empty."
        last = ctx.sections[-1]
        if last in hit:
            return "ok", f'"{last.title}" is the last section.'
        return _fail(req), f'"{hit[-1].title}" is followed by "{last.title}"; it should come last.'
    if kind in ("objects-captioned", "objects-referenced"):
        return _objects(req, ctx)
    if kind == "citations-resolved":
        keys = [r.key for text in ctx.prose for c in links.find_citations(text) for r in c.refs]
        if not keys:
            return "na", "There are no citations yet."
        missing = sorted({k for k in keys if resolve_key(k, ctx.entities) is None})
        if missing:
            return _fail(req), f"No source matches: {', '.join(missing)}."
        return "ok", f"All {_count(len(keys), 'citation')} match a source."
    if kind == "sources-doi":
        cited = {r.key for text in ctx.prose for c in links.find_citations(text) for r in c.refs}
        sources = [e for e in (resolve_key(k, ctx.entities) for k in sorted(cited)) if e is not None]
        if not sources:
            return "na", "No cited source to check."
        lacking = []
        for e in sources:
            csl = e.extra.get("csl") if isinstance(e.extra.get("csl"), dict) else {}
            if not str(csl.get("DOI") or csl.get("doi") or e.extra.get("doi") or e.extra.get("DOI") or "").strip():
                lacking.append(source_key(e))
        if lacking:
            return _fail(req), f"No DOI recorded for: {', '.join(lacking)}."
        return "ok", f"All {_count(len(sources), 'cited source')} have a DOI."
    if kind == "ai-declaration":
        words = _accepted_ai_words(ctx.project)
        if words <= 0:
            return "na", "No accepted AI-written words are recorded for this project."
        hit = [s for s in _find(ctx.sections, pats) if s.text]      # an empty starter section declares nothing
        if hit:
            return "ok", f'"{hit[0].title}" declares AI use ({_count(words, "AI word")} accepted).'
        return _fail(req), (f"{_count(words, 'word')} of AI-written text were accepted into this project, "
                            "and no section declares generative AI use.")
    return "na", ""


IMPLEMENTED = frozenset({
    "section-present", "section-words-max", "section-no-citations", "list-count", "last-section",
    "objects-captioned", "objects-referenced", "citations-resolved", "sources-doi", "ai-declaration"})


def _list_count(req: journals.Requirement, sec: _Section) -> tuple[str, str]:
    lo = int(req.params.get("min", 0))
    hi = req.params.get("max")
    hi = int(hi) if hi is not None else None
    cap = req.params.get("item_chars_max")
    cap = int(cap) if cap is not None else None
    items = _list_items(sec, lines_only=cap is not None)
    n = len(items)
    noun = sec.title.casefold()
    if n < lo or (hi is not None and n > hi):
        want = f"{lo} to {hi}" if hi is not None else f"at least {lo}"
        return _fail(req), f"{sec.title} has {_count(n, 'item')}; expected {want}."
    if cap is not None:
        long = [i for i in items if len(i) > cap]
        if long:
            return _fail(req), (f"{len(long)} of the {n} {noun} are longer than {cap} characters: "
                                + "; ".join(f'"{_shorten(i)}" ({len(i)})' for i in long) + ".")
    return "ok", f"{sec.title} has {_count(n, 'item')}."


def _objects(req: journals.Requirement, ctx: _Context) -> tuple[str, str]:
    okind = str(req.params.get("object", "fig"))
    word = _WORD.get(okind, okind)
    objs = [o for o in objects.list_objects(ctx.project) if o.kind == okind]
    if not objs:
        return "na", f"There are no {word}s yet."
    if req.check == "objects-captioned":
        bad = [o.label for o in objs if not o.caption.strip()]
        what = "has no caption"
    else:
        cited = {(r.kind, r.label) for text in ctx.prose for r in objects.find_refs(text)}
        bad = [o.label for o in objs if (o.kind, o.label) not in cited]
        what = "is not cited in the text"
    if bad:
        verb = what if len(bad) == 1 else what.replace("has no", "have no").replace("is not", "are not")
        return _fail(req), f"{_count(len(bad), word)} {verb}: {', '.join(bad)}."
    return "ok", f"All {_count(len(objs), word)} " + ("have captions." if req.check == "objects-captioned"
                                                       else "are cited in the text.")


def _evaluate_one(req: journals.Requirement, ctx: _Context, group: str | None = None) -> dict:
    if req.kind == "advice":
        status, message = "advice", ""
    else:
        try:
            status, message = _check(req, ctx)
        except Exception:           # a broken row must not blank the list
            status, message = "na", "This requirement could not be checked."
    return {"id": req.id, "group": group if group is not None else req.group, "title": req.title,
            "kind": req.kind, "status": status, "message": message}


def evaluate(project) -> list[dict]:
    """Result rows ``{id, group, title, kind, status, message}``: the project's profile rows in profile order,
    then the author's own rows from requirements.toml (``custom_requirements``; an id that clashes with a
    profile row gets the prefix "custom-"). ``[]`` for a project that is not research, or that has neither a
    matching profile nor own rows."""
    if getattr(project, "mode", "story") != "research":
        return []
    profile = project.research_profile()
    custom, warning = custom_requirements.load_report(project)
    if profile is None and not custom and not warning:
        return []
    ctx = _Context(project)
    out = []
    if profile is not None:
        out = [_evaluate_one(req, ctx) for req in profile.requirements]
    taken = {r["id"] for r in out}
    for row in custom:
        req = custom_requirements.as_requirement(row)
        if req.id in taken:
            new_id = "custom-" + req.id
            while new_id in taken:
                new_id = "custom-" + new_id
            req = dataclasses.replace(req, id=new_id)
        taken.add(req.id)
        out.append(_evaluate_one(req, ctx))
    if warning:
        file_id = "custom-file"
        while file_id in taken:
            file_id = "custom-" + file_id
        out.append({"id": file_id, "group": custom_requirements.DEFAULT_GROUP,
                    "title": custom_requirements.FILE_NAME, "kind": "check", "status": "warn",
                    "message": warning})
    return out
