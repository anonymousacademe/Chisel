"""Scene details stored as the scene's own YAML frontmatter (Obsidian-compatible).

    ---
    pov: Mara Vale
    place: Lower Meridian
    purpose: First contact with Elias's signal
    status: revising
    when: 2187-03-14
    target: 2400
    collections: [Needs continuity pass]
    ---
    # A City That Remembers

Only written when the author sets a field; a scene without details has no
block at all, so existing scenes are untouched. The ``# heading`` stays the
title. Unknown keys (an Obsidian ``tags:`` line, say) survive edits.

The block is *not* prose: it is excluded from word counts, spelling, mention
scanning, continuity evidence and style sampling. The one exception is that a
``pov`` / ``place`` value naming an entity counts as a mention (backlinks);
``when`` (story time) never does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

FIELDS = ("pov", "place", "purpose", "status", "when", "target", "collections")
# ``when`` is an optional story time (core/timeline.py); an invalid value is kept as text
TEXT_FIELDS = ("pov", "place", "purpose", "status", "when")
SUGGESTED_STATUS = ("idea", "draft", "revising", "done")
MENTION_FIELDS = ("pov", "place")

_BLOCK_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class Block:
    end: int      # offset just past the closing ``---`` line (and its newline)
    meta: dict    # the parsed mapping (all keys, known or not)


def find(text: str) -> Block | None:
    """The frontmatter block at the very top of *text*, or None. A leading
    ``---`` rule that is not a YAML mapping (a scene that opens with a
    horizontal rule) is not frontmatter."""
    if not text.startswith("---"):
        return None
    m = _BLOCK_RE.match(text)
    if m is None:
        return None
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    return Block(end=m.end(), meta=meta)


def body_offset(text: str) -> int:
    """Where the prose starts (0 when there is no frontmatter)."""
    block = find(text)
    return block.end if block else 0


def strip(text: str) -> str:
    """*text* without its frontmatter block."""
    return text[body_offset(text):]


def blank(text: str, keep: tuple[str, ...] = ()) -> str:
    """Replace the frontmatter with same-length whitespace (newlines kept) so
    scans skip it while offsets and rows elsewhere stay valid. The values of
    the *keep* keys (single-line ``key: value``) stay visible."""
    block = find(text)
    if block is None:
        return text
    head = text[:block.end]
    out: list[str] = []
    for line in head.splitlines(keepends=True):
        m = re.match(r"([ \t]*)([A-Za-z_][\w-]*)([ \t]*:[ \t]*)(.*?)([ \t]*)(\r?\n?)\Z", line)
        if m and m.group(2).lower() in keep:
            lead, key, colon, value, trail, nl = m.groups()
            out.append(" " * (len(lead) + len(key) + len(colon)) + value
                       + " " * len(trail) + nl)
        else:
            out.append(re.sub(r"[^\n]", " ", line))
    return "".join(out) + text[block.end:]


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value).strip()


def details(text: str) -> dict:
    """The known fields of *text*, normalized: strings (``""`` = unset), the
    ``target`` as an int or None, ``collections`` as a list of strings."""
    block = find(text)
    meta = block.meta if block else {}
    out: dict = {k: _as_text(meta.get(k)) for k in TEXT_FIELDS}
    raw = meta.get("target")
    try:
        target = int(str(raw).replace(",", "").strip()) if raw not in (None, "") else None
    except ValueError:
        target = None
    out["target"] = target if target and target > 0 else None
    coll = meta.get("collections")
    if isinstance(coll, str):
        coll = [coll]
    out["collections"] = [str(c).strip() for c in coll or [] if str(c).strip()]
    return out


def _normalize(key: str, value: object):
    """The value to store for *key*, or None to remove the key."""
    if key == "target":
        if value in (None, ""):
            return None
        n = int(str(value).replace(",", "").strip())
        if n < 0:
            raise ValueError("target must be a positive number of words")
        return n or None
    if key == "collections":
        if isinstance(value, str):
            value = [value]
        names = [str(v).strip() for v in value or [] if str(v).strip()]
        return names or None
    text = " ".join(_as_text(value).split())
    if key == "when" and text:
        from .timeline import stored_value  # (timeline imports this module)
        return stored_value(text)
    return text or None


class _Dumper(yaml.SafeDumper):
    """Block mapping, but lists of scalars stay on one line (``[a, b]``)."""


_Dumper.add_representer(list, lambda d, data: d.represent_sequence(
    "tag:yaml.org,2002:seq", data, flow_style=True))


def set_details(text: str, **fields) -> str:
    """*text* with the given details set (``""`` / None / [] clears a field).
    Other keys and the prose are kept; when no keys remain the block goes."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"unknown scene detail: {', '.join(sorted(unknown))}")
    block = find(text)
    meta = dict(block.meta) if block else {}
    for key, value in fields.items():
        new = _normalize(key, value)
        if new is None:
            meta.pop(key, None)
        else:
            meta[key] = new
    body = text[block.end:] if block else text
    if not meta:
        return body
    dumped = yaml.dump(meta, Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=10 ** 6)
    return f"---\n{dumped}---\n{body}"


def header(text: str) -> str:
    """The scene's details as a short prompt header (POV / place / purpose /
    status), or "" when none are set."""
    d = details(text)
    rows = [(label, d[key]) for label, key in (
        ("POV", "pov"), ("Place", "place"), ("Purpose", "purpose"),
        ("Status", "status")) if d[key]]
    return "\n".join(f"- {label}: {value}" for label, value in rows)
