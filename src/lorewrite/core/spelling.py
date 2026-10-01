"""Spell checking with accepted terms (SPEC §M6). Spelling only, never grammar.

``check(text, accepted)`` finds misspelled words in a scene; what is *accepted*
(never flagged) is the union of entity names and aliases, the project
dictionary ``<project>/dictionary.txt``, the personal dictionary
``<state dir>/dictionary.txt`` and words ignored this session. The engine
(pyspellchecker, offline) is hidden behind ``_Engine`` so it can be swapped.

Offsets are code points (Python str indexes); the GUI converts with
``core.spans``. Pending AI drafts are checked like prose (only their marker
comments are skipped): the author reviews that text, so typos in it should show.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .project import write_atomic
from .recents import default_state_dir

DICTIONARY_FILE = "dictionary.txt"
DICTIONARY_HEADER = (
    "# One word or phrase per line; these are never flagged as misspelled.\n"
    "# Lines starting with # and blank lines are ignored.\n"
)


@dataclass(frozen=True)
class Misspelling:
    start: int
    end: int
    word: str


# -- engine -----------------------------------------------------------------


class _Engine:
    """pyspellchecker behind a tiny interface: known(lowercase word) and
    ranked candidates. Loaded lazily, once (GUI calls arrive on worker threads)."""

    def __init__(self) -> None:
        from spellchecker import SpellChecker
        self._sc = SpellChecker()

    def known(self, lower: str) -> bool:
        return bool(self._sc.known([lower]))

    def candidates(self, lower: str) -> list[str]:
        found = self._sc.candidates(lower) or set()
        freq = self._sc.word_usage_frequency
        return sorted(found, key=lambda w: (-freq(w), w))


_engine: _Engine | None = None
_engine_lock = threading.Lock()


def _get_engine() -> _Engine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = _Engine()
    return _engine


# -- accepted terms -----------------------------------------------------------


def _norm(term: str) -> str:
    return " ".join(term.replace("’", "'").split())


@dataclass(frozen=True)
class AcceptedTerms:
    """Words and phrases that are never flagged.

    A lowercase entry matches any capitalisation; an entry with a capital
    (``Kessler``) matches only capitalised forms (so ``kessler`` is still
    flagged). Entries with a space are phrases: the words inside every
    occurrence of the phrase (case-insensitive, any whitespace) are accepted.
    """

    lower: frozenset[str] = frozenset()
    capitalised: frozenset[str] = frozenset()  # casefolded
    phrases: frozenset[str] = frozenset()  # normalised, casefolded

    @classmethod
    def from_terms(cls, terms: Iterable[str]) -> AcceptedTerms:
        lower: set[str] = set()
        cap: set[str] = set()
        phrases: set[str] = set()
        for term in terms:
            term = _norm(term)
            if not term:
                continue
            if " " in term:
                phrases.add(term.casefold())
            elif term == term.lower():
                lower.add(term)
            else:
                cap.add(term.casefold())
        return cls(frozenset(lower), frozenset(cap), frozenset(phrases))

    def merged(self, other: AcceptedTerms) -> AcceptedTerms:
        return AcceptedTerms(self.lower | other.lower,
                             self.capitalised | other.capitalised,
                             self.phrases | other.phrases)

    def accepts(self, word: str) -> bool:
        word = word.replace("\u2019", "'")
        folded = word.casefold()
        if folded in self.lower:
            return True
        return word[:1].isupper() and folded in self.capitalised


@lru_cache(maxsize=8)
def _phrase_re(phrases: frozenset[str]) -> re.Pattern | None:
    if not phrases:
        return None
    alts = sorted((r"\s+".join(re.escape(w) for w in p.split()) for p in phrases),
                  key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)",
                      re.IGNORECASE)


def load_dictionary(path: Path) -> list[str]:
    """Terms in a dictionary file (comments and blank lines dropped)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [t for t in (_norm(l) for l in lines) if t and not t.startswith("#")]


def add_to_dictionary(path: Path, term: str) -> bool:
    """Append *term* to a dictionary file (created if missing; comments kept).
    False when it is empty or already there (exact line)."""
    term = _norm(term)
    if not term or term.startswith("#"):
        return False
    if term in load_dictionary(path):
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = DICTIONARY_HEADER  # a new file explains itself
    if text and not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, text + term + "\n")
    return True


def remove_from_dictionary(path: Path, term: str) -> bool:
    term = _norm(term)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    kept = [l for l in lines if _norm(l) != term or term.startswith("#")]
    if len(kept) == len(lines):
        return False
    write_atomic(path, "".join(l + "\n" for l in kept))
    return True


def ensure_dictionary(path: Path) -> Path:
    """Create the file with a short comment header if it does not exist."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, DICTIONARY_HEADER)
    return path


def project_dictionary_path(project) -> Path:
    return project.root / DICTIONARY_FILE


def personal_dictionary_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / DICTIONARY_FILE


def accepted_terms(project, entities=None, ignored: Iterable[str] = (),
                   state_dir: Path | None = None) -> AcceptedTerms:
    """Everything the author has said is fine: entity names/aliases (each word
    and the whole name), both dictionaries, and this session's ignored words."""
    if entities is None:
        entities = project.load_entities()
    terms: list[str] = list(ignored)
    for e in entities:
        for name in e.names:
            terms.append(name)
            terms.extend(name.split())
    terms += load_dictionary(project_dictionary_path(project))
    terms += load_dictionary(personal_dictionary_path(state_dir))
    return AcceptedTerms.from_terms(terms)


# -- tokenizing ---------------------------------------------------------------

_SKIP_RES = [re.compile(p, re.DOTALL | re.MULTILINE | re.IGNORECASE) for p in (
    r"^```.*?(?:^```[^\n]*$|\Z)",  # fenced code (to the end if unclosed)
    r"^~~~.*?(?:^~~~[^\n]*$|\Z)",
    r"<!--.*?-->",  # draft markers, style.md provenance
    r"\{\{expand:.*?\}\}",
    r"`[^`\n]*`",
    r"(?:https?://|www\.)[^\s<>)\]]+",
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
)]
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")
_TOKEN_RE = re.compile(r"\w+(?:['’-]\w+)*")
_CONTRACTION_SUFFIXES = ("'d", "'ll", "'ve", "'re", "'m", "'em", "'s", "'t")


def _skip_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    m = _FRONTMATTER_RE.match(text)
    if m:
        ranges.append((0, m.end()))
    for rx in _SKIP_RES:
        ranges.extend((m.start(), m.end()) for m in rx.finditer(text))
    for m in _WIKILINK_RE.finditer(text):
        if m.group(2):  # [[Target|shown]]: shown text is prose, target is not
            ranges.append((m.start(), m.start(2)))
        else:  # [[Name]] names an entity, not prose
            ranges.append((m.start(), m.end()))
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for s, e in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _latin(token: str) -> bool:
    return token.isascii() or all(
        ord(c) < 0x250 or 0x1E00 <= ord(c) <= 0x1EFF for c in token)


def check(text: str, accepted: AcceptedTerms | None = None) -> list[Misspelling]:
    """Misspelled words in *text*, in document order."""
    accepted = accepted or AcceptedTerms()
    engine = _get_engine()
    skips = _skip_ranges(text)
    pr = _phrase_re(accepted.phrases)
    if pr is not None:
        skips = sorted(skips + [(m.start(), m.end()) for m in pr.finditer(text)])
    memo: dict[str, bool] = {}

    def ok(word: str) -> bool:
        """Is this single word (no hyphen, possessive already stripped) fine?"""
        hit = memo.get(word)
        if hit is None:
            word_n = word.replace("’", "'")
            hit = (len(word_n.replace("'", "")) < 2
                   or accepted.accepts(word_n)
                   or engine.known(word_n.lower())
                   or (not word_n.isascii() and engine.known(_deaccent(word_n.lower())))
                   or (word_n.upper() == word_n
                       and len(word_n.replace("'", "")) <= 5)
                   or _contraction_ok(word_n, engine, accepted))
            memo[word] = hit
        return hit

    out: list[Misspelling] = []
    si = 0
    for m in _TOKEN_RE.finditer(text):
        start, end = m.span()
        while si < len(skips) and skips[si][1] <= start:
            si += 1
        if si < len(skips) and skips[si][0] < end:
            continue  # overlaps a skipped range
        token = m.group()
        if any(c.isdigit() or c == "_" for c in token) or not _latin(token):
            continue
        # a plural possessive (dogs') leaves a bare "dogs" before the quote
        plural_poss = end < len(text) and text[end] in "'’" and token[-1:] in "sS"
        if "-" in token:
            if all(p == "" or ok(p) for p in _strip_poss(token).split("-")) \
                    or ok(token) or accepted.accepts(token):
                continue
            pos = start
            body = _strip_poss(token)
            for part in body.split("-"):
                if part and not ok(part) and not _upper_acronym(body):
                    out.append(Misspelling(pos, pos + len(part), part))
                pos += len(part) + 1
            continue
        base = _strip_poss(token)
        if ok(base) or (plural_poss and len(base) > 2 and ok(base[:-1])):
            continue
        out.append(Misspelling(start, start + len(base), base))
    return out


def _deaccent(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", word)
                   if not unicodedata.combining(c))


def _upper_acronym(token: str) -> bool:
    letters = [c for c in token if c.isalpha()]
    return bool(letters) and len(letters) <= 5 and all(c.isupper() for c in letters)


def _strip_poss(token: str) -> str:
    """Rook's -> Rook (not str.strip, which eats letters)."""
    if token[-2:] in ("'s", "'S", "’s", "’S") and len(token) > 2:
        return token[:-2]
    return token


def _contraction_ok(word: str, engine: _Engine, accepted: AcceptedTerms) -> bool:
    for suffix in _CONTRACTION_SUFFIXES:
        if word.lower().endswith(suffix) and len(word) > len(suffix):
            base = word[: -len(suffix)]
            if engine.known(base.lower()) or accepted.accepts(base):
                return True
    return False


# -- suggestions ----------------------------------------------------------------


def suggestions(word: str, n: int = 5) -> list[str]:
    """Up to *n* corrections, most probable first, in the word's capitalisation."""
    word = word.replace("’", "'")
    if not word:
        return []
    found = _get_engine().candidates(word.lower())
    found = [w for w in found if w != word.lower()][:n]
    if len(word) > 1 and word.isupper():
        return [w.upper() for w in found]
    if word[0].isupper():
        return [w[:1].upper() + w[1:] for w in found]
    return found


@dataclass
class SessionIgnores:
    """Words ignored for this session only, per project (never persisted)."""

    words: dict[str, set[str]] = field(default_factory=dict)

    def add(self, project_root: Path, word: str) -> None:
        self.words.setdefault(str(project_root), set()).add(_norm(word))

    def for_project(self, project_root: Path) -> set[str]:
        return self.words.get(str(project_root), set())
