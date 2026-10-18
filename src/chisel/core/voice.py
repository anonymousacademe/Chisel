"""Dialogue by speaker (script mode): who says what in a scene, and what the same speaker says elsewhere.

Pure Python, no AI. A script marks every speaker (the character cue), so this is exact: ``speeches`` groups
each cue with its spoken lines, ``by_speaker`` files them under the character, and ``gather_references``
collects the same speaker's lines from the other scenes for ``ai.voice`` to compare against.

A cue is filed under the character note's name when it resolves to one (aliases, any case), else under the
cue as written ("WAITER" -> "Waiter"), so a recurring character with no note is still followed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import drafts, fountain, fsutil, scenemeta
from . import entities as ent

MIN_REFERENCE_LINES = 5     # fewer lines elsewhere and a character has no voice to compare against


@dataclass(frozen=True)
class Speech:
    """One speech: a cue and the lines spoken under it."""
    speaker: str                 # the key it is filed under (note name, else the cue as written)
    cue: str                     # the cue without extension or marks ("KEITH")
    lines: tuple[str, ...]       # what is spoken (parentheticals, notes and blank lines left out)
    row: int                     # 0-based row of the cue
    rows: tuple[int, ...] = ()   # 0-based row of each spoken line

    @property
    def text(self) -> str:
        return " ".join(self.lines)

    @property
    def words(self) -> int:
        return len(self.text.split())


def speaker_key(cue: str, entities: list[ent.Entity] | tuple = ()) -> str:
    """The name a cue is filed under: the character note's name when the cue is a name or alias of one."""
    entity = ent.resolve(cue, list(entities)) if entities else None
    return entity.name if entity is not None else cue.strip().title()


def speeches(text: str, entities: list[ent.Entity] | tuple = ()) -> list[Speech]:
    """Every speech of the scene *text* in order. A speech is a cue and the dialogue lines that follow it; it
    ends at a blank line or any other element (a note between lines does not end it)."""
    out: list[Speech] = []
    cue = ""
    start = -1
    lines: list[str] = []
    rows: list[int] = []

    def close() -> None:
        nonlocal cue, start, lines, rows
        if cue and lines:
            out.append(Speech(speaker_key(cue, entities), cue, tuple(lines), start, tuple(rows)))
        cue, start, lines, rows = "", -1, [], []

    for row, ln in enumerate(fountain.parse_scene(text)):
        if ln.kind in (fountain.NOTE, fountain.BONEYARD):
            continue
        if ln.kind == fountain.CHARACTER:
            close()
            cue, start = fountain.cue_name(ln.clean), row
        elif ln.kind == fountain.DIALOGUE and cue:
            spoken = ln.clean.strip()
            if spoken:
                lines.append(spoken)
                rows.append(row)
        elif ln.kind == fountain.PARENTHETICAL and cue:
            continue
        else:
            close()
    close()
    return out


def by_speaker(text: str, entities: list[ent.Entity] | tuple = ()) -> dict[str, list[Speech]]:
    """The speeches of *text* filed by speaker, in order of first appearance."""
    out: dict[str, list[Speech]] = {}
    for s in speeches(text, entities):
        out.setdefault(s.speaker, []).append(s)
    return out


def line_count(speeches_: list[Speech]) -> int:
    return sum(len(s.lines) for s in speeches_)


@dataclass(frozen=True)
class Excerpt:
    """What one speaker says in one other scene."""
    scene: str                   # the scene's title
    path: str                    # project-relative path
    distance: int                # scenes between it and the one being checked
    lines: tuple[str, ...] = field(default_factory=tuple)


def gather_references(project, entities: list[ent.Entity], scene: Path,
                      speakers: set[str] | None = None) -> dict[str, list[Excerpt]]:
    """For each speaker (limited to *speakers* when given), their lines in every OTHER scene of the book, the
    scenes nearest *scene* first (a voice drifts, so the closest scenes say most), ties earlier first. Pending
    AI drafts are not canon and are left out. Scenes that cannot be read are skipped."""
    paths = project.list_scenes()
    try:
        here = paths.index(scene)
    except ValueError:
        here = len(paths)       # a Parked scene or one outside the reading order: every scene is "before" it
    found: dict[str, list[Excerpt]] = {}
    tokens = None            # a scene that never mentions a requested speaker (or an alias) is not parsed
    if speakers is not None:
        tokens = {name.casefold() for name in speakers}
        tokens |= {a.casefold() for e in entities if e.name in speakers for a in e.aliases}
    for i, path in enumerate(paths):
        if path == scene:
            continue
        try:
            text = fsutil.read_text_lenient(path)
            if tokens is not None:
                folded = text.casefold()
                if not any(t in folded for t in tokens):
                    continue
            text = drafts.strip_pending(text, drafts.load_originals(project.root, path))
        except OSError:
            continue
        mine = by_speaker(text, entities)
        if not mine:
            continue
        title = _title(text) or path.stem
        rel = path.relative_to(project.root).as_posix()
        for name, group in mine.items():
            if speakers is not None and name not in speakers:
                continue
            lines = tuple(line for s in group for line in s.lines)
            found.setdefault(name, []).append(Excerpt(title, rel, abs(i - here), lines))
    for excerpts in found.values():
        excerpts.sort(key=lambda e: (e.distance, e.path))
    return found


def _title(text: str) -> str:
    for line in scenemeta.strip(text).splitlines():
        if line.strip():
            return line[2:].strip() if line.startswith("# ") else ""
    return ""


def reference_lines(excerpts: list[Excerpt]) -> int:
    return sum(len(e.lines) for e in excerpts)


def format_reference(excerpts: list[Excerpt]) -> str:
    """The reference lines as the prompt shows them: a scene title, then the lines, nearest scene first."""
    blocks = []
    for e in excerpts:
        blocks.append(f"[{e.scene}]\n" + "\n".join(f"- {line}" for line in e.lines))
    return "\n\n".join(blocks)
