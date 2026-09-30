"""Pending AI text: the marking mechanism for every generated span (SPEC §7 M4).

AI-written text is stored *in the scene file* between HTML comments, so it
survives saves, reopening and external editors (Obsidian hides the comments):

    <!--ai-->generated text<!--/ai-->
    <!--ai replaces="BASE64"-->generated text<!--/ai-->

``replaces`` is the urlsafe base64 (UTF-8) of the text the draft replaced (a
selection, or an ``{{expand: …}}`` marker); absent means a pure insertion.
Accept keeps the body as normal text; reject restores exactly what was there
before. Nested or malformed markers are ignored (plain text), never an error.
Pure Python, no Textual.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass

# Body may not contain another opening tag or a closing tag: an unclosed or
# nested draft never matches, so it is treated as plain text.
_PENDING_RE = re.compile(
    r'<!--ai(?: replaces="([A-Za-z0-9_=-]*)")?-->'
    r"((?:(?!<!--ai)(?!<!--/ai-->).)*)"
    r"<!--/ai-->",
    re.DOTALL,
)
_EXPAND_RE = re.compile(r"\{\{expand:\s*([^{}]*?)\s*\}\}")


@dataclass(frozen=True)
class Pending:
    start: int  # offset of the opening tag
    end: int  # offset one past the closing tag
    body_start: int
    body_end: int
    original: str | None  # text the draft replaced; None for pure insertions


@dataclass(frozen=True)
class ExpandMarker:
    start: int
    end: int
    instruction: str


def _encode(original: str) -> str:
    return base64.urlsafe_b64encode(original.encode("utf-8")).decode("ascii")


def _decode(raw: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeError, ValueError):
        return None


def wrap(body: str, original: str | None = None) -> str:
    """The marked-up form of a generated *body* (optionally replacing *original*)."""
    body = body.replace("<!--", "<!-")  # a body can never forge/close a marker
    if original is None:
        return f"<!--ai-->{body}<!--/ai-->"
    return f'<!--ai replaces="{_encode(original)}"-->{body}<!--/ai-->'


def find_pending(text: str) -> list[Pending]:
    """Every well-formed pending draft in *text*, in document order."""
    out: list[Pending] = []
    for m in _PENDING_RE.finditer(text):
        original = None
        if m.group(1) is not None:
            original = _decode(m.group(1))
            if original is None:
                continue  # corrupt replaces payload: leave as plain text
        out.append(Pending(m.start(), m.end(), m.start(2), m.end(2), original))
    return out


def pending_at(text: str, offset: int) -> Pending | None:
    """The pending draft containing *offset* (edges count), if any."""
    for p in find_pending(text):
        if p.start <= offset <= p.end:
            return p
    return None


def accept(text: str, pending: Pending) -> str:
    """Remove the markers, keep the body as normal text."""
    return text[:pending.start] + text[pending.body_start:pending.body_end] \
        + text[pending.end:]


def reject(text: str, pending: Pending) -> str:
    """Restore the original text (or remove a pure insertion)."""
    return text[:pending.start] + (pending.original or "") + text[pending.end:]


def accept_all(text: str) -> str:
    for p in reversed(find_pending(text)):
        text = accept(text, p)
    return text


def reject_all(text: str) -> str:
    for p in reversed(find_pending(text)):
        text = reject(text, p)
    return text


def strip_pending(text: str) -> str:
    """The text as if every pending draft were rejected: unaccepted AI text
    is not canon and not the author's prose."""
    return reject_all(text)


def find_expand_markers(text: str) -> list[ExpandMarker]:
    """``{{expand: instruction}}`` markers, in document order."""
    return [ExpandMarker(m.start(), m.end(), m.group(1))
            for m in _EXPAND_RE.finditer(text)]


def expand_marker_at(text: str, offset: int) -> ExpandMarker | None:
    for marker in find_expand_markers(text):
        if marker.start <= offset <= marker.end:
            return marker
    return None
