"""Comments: the author's notes anchored to a passage, never inline in the prose.

    .comments/manuscript__01-the-recall__01-rain.md.json

is a JSON list of ``{id, quote, prefix, suffix, body, created, resolved}`` for
one scene (keyed like the draft sidecars, ``drafts.sidecar_key``). Author data:
plain, committed with the project, travels with its scene on every move and
into the Trash. A comment is anchored by the *quoted text* plus a little
context before and after it, so it survives edits: ``locate`` finds the
passage again (exact, tolerant of re-wrapped lines, then fuzzy by the quote's
two ends or its context). A comment whose passage cannot be found is
*detached*: it stays in the list, never silently dropped, and re-attaches if
the text comes back.

Comments are not scene text: they are not spell-checked, counted or sent to
the AI unless the author attaches them to a chat (``ai/writing``).
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from . import drafts, scenemeta
from . import fsutil

COMMENTS_DIR = ".comments"
CONTEXT = 40          # characters of prefix / suffix kept around the quote
QUOTE_MAX = 2000
BODY_MAX = 5000
_END = 24             # characters at each end of the quote used for the fuzzy find


@dataclass(frozen=True)
class Comment:
    id: str
    quote: str
    prefix: str
    suffix: str
    body: str
    created: str
    resolved: bool = False

    def as_dict(self) -> dict:
        return {"id": self.id, "quote": self.quote, "prefix": self.prefix,
                "suffix": self.suffix, "body": self.body, "created": self.created,
                "resolved": self.resolved}


# -- storage ---------------------------------------------------------------------


def sidecar_path(project_root: Path, scene: Path) -> Path:
    return project_root / COMMENTS_DIR / f"{drafts.sidecar_key(project_root, scene)}.json"


def _from_dict(d: object) -> Comment | None:
    if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"]:
        return None
    text = lambda k: d[k] if isinstance(d.get(k), str) else ""  # noqa: E731
    return Comment(d["id"], text("quote"), text("prefix"), text("suffix"), text("body"),
                   text("created"), bool(d.get("resolved")))


def load(project_root: Path, scene: Path) -> list[Comment]:
    try:
        data = json.loads(sidecar_path(project_root, scene).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data if isinstance(data, list) else []
    return [c for c in map(_from_dict, items) if c is not None]


def save(project_root: Path, scene: Path, comments: list[Comment]) -> None:
    """Write the list atomically; an empty list removes the sidecar."""
    path = sidecar_path(project_root, scene)
    if not comments:
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps([c.as_dict() for c in comments], indent=2, ensure_ascii=False)
                   + "\n", encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


# -- anchoring ---------------------------------------------------------------------


def _flex(quote: str) -> re.Pattern[str]:
    """A pattern for *quote* that tolerates re-wrapped lines (any whitespace
    run matches any whitespace run)."""
    parts = [re.escape(p) for p in quote.split()]
    return re.compile(r"\s+".join(parts))


def anchor(text: str, start: int, end: int) -> tuple[str, str, str]:
    """(quote, prefix, suffix) for the passage ``text[start:end]``."""
    if not 0 <= start < end <= len(text):
        raise ValueError("select some text to comment on")
    quote = text[start:end]
    if not quote.strip():
        raise ValueError("select some text to comment on")
    if len(quote) > QUOTE_MAX:
        raise ValueError(f"select at most {QUOTE_MAX} characters to comment on")
    return quote, text[max(0, start - CONTEXT):start], text[end:end + CONTEXT]


def _common_suffix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _common_prefix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def _context_score(text: str, c: Comment, start: int, end: int) -> int:
    return (_common_suffix(text[max(0, start - len(c.prefix)):start], c.prefix)
            + _common_prefix(text[end:end + len(c.suffix)], c.suffix))


def locate(text: str, c: Comment) -> tuple[int, int] | None:
    """Where the commented passage is in *text* (code-point offsets), or None
    (detached). Never inside the scene's frontmatter."""
    base = scenemeta.body_offset(text)
    body = text[base:]
    quote = c.quote.strip()
    if not quote:
        return None
    # 1. the quote itself (exact, then tolerant of re-wrapping); several: best context
    hits = [m.span() for m in re.finditer(re.escape(c.quote), body)] or \
           [m.span() for m in _flex(quote).finditer(body)]
    if hits:
        s, e = max(hits, key=lambda h: _context_score(body, c, *h))
        return base + s, base + e
    # 2. the quote was edited in the middle: its two ends still find it
    if len(quote) >= 2 * _END:
        head, tail = _flex(quote[:_END]), _flex(quote[-_END:])
        best: tuple[int, tuple[int, int]] | None = None
        for h in head.finditer(body):
            t = next((m for m in tail.finditer(body, h.end())), None)
            if t is None:
                continue
            span = (h.start(), t.end())
            if 0.4 * len(quote) <= span[1] - span[0] <= 2.5 * len(quote):
                score = _context_score(body, c, *span)
                if best is None or score > best[0]:
                    best = (score, span)
        if best:
            return base + best[1][0], base + best[1][1]
    # 3. the passage was rewritten: whatever sits between its surroundings
    if len(c.prefix) >= 12 and len(c.suffix) >= 12:
        p, q = _flex(c.prefix.strip()), _flex(c.suffix.strip())
        for pm in p.finditer(body):
            qm = q.search(body, pm.end())
            if qm and qm.start() - pm.end() <= 3 * len(quote) + 80:
                s, e = pm.end(), qm.start()
                inner = body[s:e]
                lead = len(inner) - len(inner.lstrip())
                s, e = s + lead, e - (len(inner) - len(inner.rstrip()))
                if s < e:
                    return base + s, base + e
    return None


@dataclass(frozen=True)
class Placed:
    comment: Comment
    start: int | None      # None = detached
    end: int | None

    @property
    def detached(self) -> bool:
        return self.start is None


def place(text: str, comments: list[Comment]) -> list[Placed]:
    """Each comment with its position in *text* (detached ones have None).
    Detached first, then by position, so the list reads top to bottom."""
    placed = []
    for c in comments:
        pos = locate(text, c)
        placed.append(Placed(c, *(pos if pos else (None, None))))
    return sorted(placed, key=lambda p: (p.start is not None, p.start or 0, p.comment.created))


def reanchor(project_root: Path, scene: Path, text: str) -> list[Placed]:
    """``place`` plus: a comment found by the fuzzy rules gets its stored quote and
    context refreshed to what is there now (so the next find is exact). A detached
    comment is left exactly as it was."""
    comments = load(project_root, scene)
    placed = place(text, comments)
    changed = False
    out: list[Placed] = []
    for p in placed:
        c = p.comment
        if p.start is not None:
            quote, prefix, suffix = anchor(text, p.start, p.end)
            if (quote, prefix, suffix) != (c.quote, c.prefix, c.suffix):
                c = replace(c, quote=quote, prefix=prefix, suffix=suffix)
                changed = True
        out.append(Placed(c, p.start, p.end))
    if changed:
        by_id = {p.comment.id: p.comment for p in out}
        save(project_root, scene, [by_id[c.id] for c in comments])
    return out


# -- operations ----------------------------------------------------------------------


def _body(body: str) -> str:
    body = (body or "").strip()
    if not body:
        raise ValueError("a comment needs some text")
    if len(body) > BODY_MAX:
        raise ValueError(f"a comment is at most {BODY_MAX} characters")
    return body


def add(project_root: Path, scene: Path, text: str, start: int, end: int, body: str) -> Comment:
    """Comment on ``text[start:end]`` (the editor's buffer)."""
    quote, prefix, suffix = anchor(text, start, end)
    if start < scenemeta.body_offset(text):
        raise ValueError("comments go on the prose, not the scene details")
    comments = load(project_root, scene)
    taken = {c.id for c in comments}
    cid = next(i for i in (secrets.token_hex(4) for _ in range(1000)) if i not in taken)
    c = Comment(cid, quote, prefix, suffix, _body(body),
                datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    save(project_root, scene, comments + [c])
    return c


def _update(project_root: Path, scene: Path, cid: str, **changes) -> Comment:
    comments = load(project_root, scene)
    for i, c in enumerate(comments):
        if c.id == cid:
            comments[i] = replace(c, **changes)
            save(project_root, scene, comments)
            return comments[i]
    raise LookupError("no such comment")


def edit(project_root: Path, scene: Path, cid: str, body: str) -> Comment:
    return _update(project_root, scene, cid, body=_body(body))


def resolve(project_root: Path, scene: Path, cid: str, resolved: bool = True) -> Comment:
    return _update(project_root, scene, cid, resolved=bool(resolved))


def delete(project_root: Path, scene: Path, cid: str) -> None:
    comments = load(project_root, scene)
    kept = [c for c in comments if c.id != cid]
    if len(kept) == len(comments):
        raise LookupError("no such comment")
    save(project_root, scene, kept)


def open_count(project_root: Path, scene: Path) -> int:
    return sum(1 for c in load(project_root, scene) if not c.resolved)


# -- moves with the scene (same pattern as snapshots / draft sidecars) -----------------


def stage(project_root: Path, scene: Path, tag: str) -> Path | None:
    old = sidecar_path(project_root, scene)
    if not old.is_file():
        return None
    tmp = old.with_name(f".mv{tag}-{old.name}")
    fsutil.replace(old, tmp)
    return tmp


def unstage(project_root: Path, staged: Path, new_scene: Path) -> None:
    new = sidecar_path(project_root, new_scene)
    new.parent.mkdir(parents=True, exist_ok=True)
    fsutil.replace(staged, new)


def archive(project_root: Path, scene: Path, dest: Path) -> None:
    """Move the sidecar to *dest* (the Trash keeps a deleted scene's comments)."""
    old = sidecar_path(project_root, scene)
    if old.is_file():
        fsutil.replace(old, dest)
        try:
            old.parent.rmdir()
        except OSError:
            pass


def unarchive(project_root: Path, src: Path, scene: Path) -> None:
    if src.is_file():
        new = sidecar_path(project_root, scene)
        new.parent.mkdir(parents=True, exist_ok=True)
        fsutil.replace(src, new)
