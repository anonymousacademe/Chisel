"""The reading model: what is read aloud, in what voice, from where in the text (docs/dev/plan-read-aloud.md).

Pure Python, no audio. ``plan`` turns a document into an ordered list of ``Utterance`` s, one adapter per kind of
text: a script (Fountain: who speaks is exact), story prose (quoted speech split from narration), a research
section (citations dropped, math and figure references spoken as words) and any other note. The desktop editor
plays the list with the window's speech service; nothing here speaks, and nothing is changed or stored.

Offsets are code points of the text given (the bridge converts to UTF-16). Skipped everywhere: the scene's
details block, notes and boneyard, pending AI drafts (not accepted, so not canon), ``{{expand}}`` markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields

from . import drafts, fountain, links, objects, scenemeta
from . import entities as ent
from . import voice as dialogue

NARRATOR = "narrator"
QUOTE = "quote"                      # spoken lines in story prose: one voice, whoever says them

WORDS_PER_MINUTE = 160
PAUSE = {"title": 1.0, "heading": 0.8, "scene-heading": 0.7, "narration": 0.5, "quote": 0.35,
         "dialogue": 0.35, "direction": 0.25, "transition": 0.4}
KINDS = tuple(PAUSE)


@dataclass(frozen=True)
class ReadOptions:
    titles: bool = True              # the scene / document title
    headings: bool = True            # headings inside the text, and (script) scene headings
    directions: bool = False         # script: parentheticals "(softly)"
    transitions: bool = False        # script: "CUT TO:"
    citations: bool = False          # research: say "citation" where one stands

    @classmethod
    def from_dict(cls, raw: dict | None) -> ReadOptions:
        """Options from untrusted input (the bridge): unknown keys are ignored, a non-boolean raises ValueError."""
        kw = {}
        for f in fields(cls):
            if raw and f.name in raw:
                if not isinstance(raw[f.name], bool):
                    raise ValueError(f"{f.name} must be true or false")
                kw[f.name] = raw[f.name]
        return cls(**kw)


@dataclass(frozen=True)
class Utterance:
    kind: str                        # one of KINDS
    voice: str                       # NARRATOR, QUOTE, or a script speaker's name
    text: str                        # as shown
    say: str                         # as spoken: markup removed, names respelled
    start: int                       # source range, code points
    end: int
    row: int                         # 0-based row of the start
    seconds: float                   # estimated at rate 1.0
    joins: bool = False              # continues the previous utterance's paragraph (spoken as one when the voice is the same)


@dataclass
class ReadPlan:
    mode: str                        # script | story | research | note
    utterances: list[Utterance] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(len(u.say.split()) for u in self.utterances)

    def seconds(self, rate: float = 1.0) -> float:
        return sum(u.seconds for u in self.utterances) / max(rate, 0.1)

    def voices(self) -> dict[str, int]:
        """The voices used and how many utterances each has, in order of first appearance."""
        out: dict[str, int] = {}
        for u in self.utterances:
            out[u.voice] = out.get(u.voice, 0) + 1
        return out


def estimate_seconds(kind: str, say: str) -> float:
    return round(len(say.split()) * 60 / WORDS_PER_MINUTE + PAUSE.get(kind, 0.4), 2)


# -- pronunciations ------------------------------------------------------------------------------------------


def pronunciations(entities: list[ent.Entity]) -> dict[str, str]:
    """{name or alias: how to say it} from the ``say:`` key of notes that have one."""
    out: dict[str, str] = {}
    for e in entities:
        say = e.extra.get("say") if isinstance(e.extra, dict) else None
        if isinstance(say, str) and say.strip():
            for name in e.names:
                out[name] = say.strip()
    return out


def _respell(text: str, pron: dict[str, str]) -> str:
    if not pron:
        return text
    names = sorted(pron, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)")
    return pattern.sub(lambda m: pron[m.group(1)], text)


# -- speakable text --------------------------------------------------------------------------------------------

_EXPAND_RE = re.compile(r"\{\{expand:.*?\}\}", re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_FOOTNOTE_RE = re.compile(r"\^\[[^\]]*\]")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_PLACEMENT_RE = re.compile(r"^\s*!\[\[(fig|tbl|eq):[^\]]*\]\]\s*$")
_REF_WORD = {"fig": "the figure", "tbl": "the table", "eq": "the equation"}


def _blank(text: str, pattern: re.Pattern) -> str:
    """*text* with every match replaced by spaces (newlines kept): same length, so offsets survive."""
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def prepare(text: str) -> str:
    """*text* as the reader scans it: details block, pending AI drafts, comments and expand markers blanked."""
    return _blank(_blank(scenemeta.blank(drafts.blank_pending(text)), _COMMENT_RE), _EXPAND_RE)


def _speakable(src: str, mode: str, opts: ReadOptions) -> str:
    """One paragraph of Markdown as it should be spoken."""
    from .export.manuscript import parse_inline
    s = src
    if mode == "research":
        s = _blank_to_words(s, mode, opts)
        s = re.sub(r"\s+([)\].,;:!?])", r"\1", s)        # the words put in leave no space before punctuation
        s = re.sub(r"([(\[])\s+", r"\1", s)
    s = links.WIKILINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), s)
    s = _IMAGE_RE.sub(lambda m: m.group(1), s)
    s = _LINK_RE.sub(lambda m: m.group(1), s)
    s = _FOOTNOTE_RE.sub("", s)
    s = "".join(r.text for r in parse_inline(s))
    s = re.sub(r"^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)", "", s)
    return " ".join(s.split())


def _blank_to_words(s: str, mode: str, opts: ReadOptions) -> str:
    """Research: citations dropped (or "citation"), figure / table / equation references and math as words."""
    edits: list[tuple[int, int, str]] = []
    for c in links.find_citations(s):
        edits.append((c.start, c.end, " citation " if opts.citations else " "))
    for r in objects.find_refs(s):
        edits.append((r.start, r.end, " " + _REF_WORD.get(r.kind, "the figure") + " "))
    # math: strip_math blanks each span to spaces, so a whitespace run of the copy that holds changed characters
    # is one equation (two spans with only whitespace between them are spoken once)
    stripped = objects.strip_math(s, mode=mode)
    i = 0
    while i < len(s):
        if stripped[i] != s[i]:
            j, last = i, i
            while j < len(s) and stripped[j].isspace():
                if stripped[j] != s[j]:
                    last = j
                j += 1
            edits.append((i, last + 1, " equation "))
            i = j
        else:
            i += 1
    edits.sort(key=lambda e: e[0])
    out, pos = [], 0
    for a, b, word in edits:
        if a < pos:
            continue                     # overlapping edit (a reference inside math): the first wins
        out += [s[pos:a], word]
        pos = b
    out.append(s[pos:])
    return "".join(out)


# -- adapters ---------------------------------------------------------------------------------------------------


def _row_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset)


# An all-capitals word with no vowel (SSDD, TV, HQ) cannot be said as a word: spell it out. Words with a vowel
# (NASA, MILO) are left to the speech engine.
_LETTERS_RE = re.compile(r"(?<![\w'])[B-DF-HJ-NP-TV-Z]{2,6}(?![\w'])")


def _spell_out(say: str) -> str:
    return _LETTERS_RE.sub(lambda m: " ".join(m.group(0)), say)


def _make(text: str, kind: str, voice: str, shown: str, say: str, start: int, end: int,
          pron: dict[str, str], joins: bool = False) -> Utterance | None:
    say = _spell_out(_respell(" ".join(say.split()), pron))
    if not say or not any(c.isalnum() for c in say):
        return None
    return Utterance(kind, voice, " ".join(shown.split()), say, start, end, _row_of(text, start),
                     estimate_seconds(kind, say), joins)


_SCENE_PREFIXES = ((re.compile(r"^(INT\./EXT|INT/EXT|I/E)\.?\s+", re.I), "Interior and exterior, "),
                   (re.compile(r"^INT\.?\s+", re.I), "Interior, "),
                   (re.compile(r"^EXT\.?\s+", re.I), "Exterior, "),
                   (re.compile(r"^EST\.?\s+", re.I), "Establishing, "))


def spoken_heading(heading: str) -> str:
    """"INT. KITCHEN - DAY #3#" -> "Interior, Kitchen, Day"."""
    s = heading.strip()
    if s.startswith(".") and len(s) > 1 and s[1].isalnum():
        s = s[1:]
    s = re.sub(r"\s*#[A-Za-z0-9.\-]+#\s*$", "", s)
    for pattern, word in _SCENE_PREFIXES:
        if pattern.match(s):
            s = word + pattern.sub("", s, count=1)
            break
    s = re.sub(r"\s+[-–—]+\s+", ", ", s)
    return " ".join(w if w.islower() or not w.isupper() else w.capitalize() for w in s.split())


def _script(text: str, entities: list[ent.Entity], opts: ReadOptions, pron: dict[str, str]) -> list[Utterance]:
    out: list[Utterance] = []
    action: list[fountain.Line] = []
    speech: list[fountain.Line] = []
    speaker = ""

    def emit(kind: str, voice: str, lines: list[fountain.Line], shown: list[str]) -> None:
        first, last = lines[0], lines[-1]
        start = first.start + (len(first.text) - len(first.text.lstrip()))
        end = last.start + len(last.text.rstrip())
        u = _make(text, kind, voice, " ".join(shown), " ".join(shown), start, end, pron)
        if u is not None:
            out.append(u)

    def plain(ln: fountain.Line) -> str:
        return fountain.plain(ln.clean.strip())

    def flush_action() -> None:
        if action:
            emit("narration", NARRATOR, action, [plain(a).lstrip("!") for a in action])
            action.clear()

    def flush_speech() -> None:
        if speech:
            emit("dialogue", speaker or NARRATOR, speech, [plain(s) for s in speech if s.clean.strip()])
            speech.clear()

    for ln in fountain.parse_scene(text):
        k = ln.kind
        if k == fountain.ACTION:
            flush_speech()
            action.append(ln)
            continue
        if k in (fountain.NOTE, fountain.BONEYARD):
            continue
        flush_action()
        if k == fountain.DIALOGUE:
            speech.append(ln)
            continue
        flush_speech()
        if k == fountain.CHARACTER:
            speaker = dialogue.speaker_key(fountain.cue_name(ln.clean), entities)
            continue
        if k == fountain.PARENTHETICAL:
            if opts.directions:
                emit("direction", NARRATOR, [ln], [plain(ln).strip("() ")])
            continue                     # the speech goes on after it: the speaker stays
        speaker = ""
        if k == fountain.TITLE and opts.titles:
            emit("title", NARRATOR, [ln], [ln.clean.strip()[2:]])
        elif k == fountain.SCENE_HEADING and opts.headings:
            emit("scene-heading", NARRATOR, [ln], [spoken_heading(ln.clean)])
        elif k == fountain.TRANSITION and opts.transitions:
            raw = ln.clean.strip().lstrip(">").strip().rstrip(":").strip()
            emit("transition", NARRATOR, [ln], [raw.capitalize()])
        elif k == fountain.CENTERED:
            emit("narration", NARRATOR, [ln], [ln.clean.strip().strip("<>").strip()])
        elif k == fountain.LYRICS:
            emit("narration", NARRATOR, [ln], [plain(ln).lstrip("~").strip()])
    flush_action()
    flush_speech()
    return out


_OPEN_CLOSE = {"“": "”"}


def _quote_segments(raw: str) -> list[tuple[bool, int, int]]:
    """(is_quote, start, end) of a paragraph's narration and quoted speech, inside quote marks; offsets into
    *raw*. An unbalanced straight quote means no splitting: the paragraph is narration."""
    spans: list[tuple[int, int]] = []
    i = 0
    if raw.count('"') % 2:
        straight_ok = False
    else:
        straight_ok = True
    while i < len(raw):
        c = raw[i]
        close = '"' if (c == '"' and straight_ok) else _OPEN_CLOSE.get(c)
        if close:
            j = raw.find(close, i + 1)
            if j != -1:
                spans.append((i + 1, j))
                i = j + 1
                continue
        i += 1
    out: list[tuple[bool, int, int]] = []
    pos = 0
    for a, b in spans:
        if raw[pos:a - 1].strip():
            out.append((False, pos, a - 1))
        out.append((True, a, b))
        pos = b + 1
    if raw[pos:].strip():
        out.append((False, pos, len(raw)))
    return out


def _markdown(text: str, mode: str, opts: ReadOptions, pron: dict[str, str]) -> list[Utterance]:
    """Story, research and any other note: headings and paragraphs; quotes split from narration (story / note)."""
    out: list[Utterance] = []
    lines = text.split("\n")
    pos = 0
    para: list[tuple[int, int]] = []     # (start, end) of the lines of the open paragraph
    in_code = False
    seen_title = False

    def flush() -> None:
        if not para:
            return
        a, b = para[0][0], para[-1][1]
        raw = text[a:b].replace("\n", " ").replace("\r", " ")
        lead = len(raw) - len(raw.lstrip())
        if mode == "research":
            segments = [(False, 0, len(raw))]
        else:
            segments = _quote_segments(raw)
        first = True
        for is_quote, s, e in segments:
            chunk = raw[s:e]
            seg_start = a + max(s, lead)                                  # not the paragraph's indent
            seg_end = a + (len(raw.rstrip()) if e == len(raw) else e)     # nor its trailing space
            u = _make(text, QUOTE if is_quote else "narration", QUOTE if is_quote else NARRATOR,
                      chunk, _speakable(chunk, mode, opts), seg_start, seg_end, pron, joins=not first)
            if u is not None:
                out.append(u)
                first = False
        para.clear()

    for line in lines:
        start, end = pos, pos + len(line)
        pos = end + 1
        s = line.strip()
        if _FENCE_RE.match(line):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        if not s:
            flush()
            continue
        if s.startswith("#"):
            flush()
            level_text = re.sub(r"^#+\s*", "", s)
            first = not seen_title
            seen_title = True
            if first and line.startswith("# ") and not opts.titles:
                continue
            if not first and not opts.headings:
                continue
            u = _make(text, "title" if first and line.startswith("# ") else "heading", NARRATOR, level_text,
                      _speakable(level_text, mode, opts), start + (len(line) - len(line.lstrip())), start + len(line.rstrip()), pron)
            if u is not None:
                out.append(u)
            continue
        if s.startswith("|") or re.fullmatch(r"[-*_]{3,}", s) or _PLACEMENT_RE.match(line):
            flush()                       # table rows, rules and figure placements are not read
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            flush()                       # a list item is its own utterance
        seen_title = True
        para.append((start, end))
    flush()
    return out


# -- entry point ------------------------------------------------------------------------------------------------


def plan(text: str, mode: str = "story", entities: list[ent.Entity] | None = None,
         options: ReadOptions | None = None) -> ReadPlan:
    """The utterances of *text*. *mode*: ``script`` (Fountain), ``story``, ``research`` or ``note`` (any other
    document). Entities supply character names for script cues and the ``say:`` pronunciations."""
    if mode not in ("script", "story", "research", "note"):
        raise ValueError(f"unknown reading mode: {mode}")
    entities = list(entities or [])
    opts = options or ReadOptions()
    pron = pronunciations(entities)
    prepared = prepare(text)
    if mode == "script":
        items = _script(prepared, entities, opts, pron)
    else:
        items = _markdown(prepared, mode, opts, pron)
    return ReadPlan(mode, items)
