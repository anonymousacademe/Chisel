"""Entity notes: characters, places, and other story-bible entries.

An entity note is a Markdown file with a small YAML frontmatter block
(name, type, aliases) followed by free text. See SPEC.md §4.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import fsutil

VALID_TYPES = ("character", "place", "object", "faction")

ENTITY_TEMPLATE = """\
---
name: {name}
type: {type}
aliases: []
---

"""


MAX_SLUG = 60  # keeps file and folder names far below Windows' 255/260 limits

_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
             *(f"lpt{i}" for i in range(1, 10))}
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def fold(text: str) -> str:
    """Comparison form of a name: NFC, curly quotes made straight."""
    return unicodedata.normalize("NFC", text.translate(_QUOTES))


def slugify(name: str) -> str:
    """'Elara Vance' -> 'elara-vance' (filesystem-safe note filename).

    Unicode letters are kept (Latin accents are folded away), everything else
    that is not a letter, digit, space or hyphen is dropped; capped at
    MAX_SLUG characters; Windows device names get a suffix."""
    decomposed = unicodedata.normalize("NFKD", name)
    # strip Latin combining accents only (other scripts need their marks)
    decomposed = "".join(c for c in decomposed if not "̀" <= c <= "ͯ")
    text = unicodedata.normalize("NFC", decomposed)
    text = "".join(c for c in text
                   if c.isalnum() or c in "-_" or c.isspace()
                   or unicodedata.category(c).startswith("M"))
    slug = re.sub(r"[\s_]+", "-", text.strip().lower())
    slug = slug[:MAX_SLUG].strip("-.")
    if slug in _RESERVED:
        slug += "-note"
    return slug or "untitled"


@dataclass
class Entity:
    name: str
    type: str = "character"
    aliases: list[str] = field(default_factory=list)
    body: str = ""
    path: Path | None = None

    @property
    def names(self) -> list[str]:
        """The canonical name plus all aliases."""
        return [self.name, *self.aliases]

    def matches(self, term: str) -> bool:
        """Case-insensitive match against name or any alias."""
        term = fold(term).casefold()
        return any(term == fold(n).casefold() for n in self.names)

    def to_markdown(self) -> str:
        frontmatter = {
            "name": self.name,
            "type": self.type,
            "aliases": self.aliases,
        }
        return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)}---\n\n{self.body}"

    @classmethod
    def from_markdown(cls, text: str, path: Path | None = None) -> Entity:
        """Parse a note file. Tolerates missing/malformed frontmatter."""
        meta: dict = {}
        body = text
        m = re.match(r"\A---\n(.*?)\n---\n?", text, re.DOTALL)
        if m:
            try:
                meta = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                meta = {}
            body = text[m.end():].lstrip("\n")
        name = str(meta.get("name") or (path.stem if path else "Untitled"))
        etype = str(meta.get("type") or "character")
        if etype not in VALID_TYPES:
            etype = "character"
        aliases = meta.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        return cls(name=name, type=etype, aliases=[str(a) for a in aliases],
                   body=body, path=path)


def load_entity(path: Path) -> Entity:
    return Entity.from_markdown(fsutil.read_text_lenient(path), path=path)


def save_entity(entity: Entity, path: Path) -> None:
    """Write a note atomically (temp file + rename)."""
    fsutil.ensure_utf8(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(entity.to_markdown(), encoding="utf-8", newline="\n")
    fsutil.replace(tmp, path)


def new_entity_note(name: str, etype: str = "character") -> str:
    if etype not in VALID_TYPES:
        etype = "character"
    return ENTITY_TEMPLATE.format(name=name, type=etype)


def resolve(term: str, entities: list[Entity]) -> Entity | None:
    """Resolve a link target to an entity by name or alias (case-insensitive)."""
    for entity in entities:
        if entity.matches(term):
            return entity
    return None


def alias_owner(alias: str, entity: Entity, entities: list[Entity]) -> Entity | None:
    """Another note (not *entity*) whose name or alias is *alias*, if any."""
    for other in entities:
        if other is entity or (other.path is not None and other.path == entity.path):
            continue
        if other.matches(alias):
            return other
    return None


def add_alias(entity: Entity, alias: str, entities: list[Entity] | None = None) -> Entity:
    """Add an alias to an entity note (deduped) and save it to disk.

    With *entities* (the project's notes), an alias already used as another
    note's name or alias is refused with ValueError."""
    alias = alias.strip()
    if not alias:
        return entity
    if entities is not None and alias_owner(alias, entity, entities) is not None:
        raise ValueError(f"{alias!r} is already a name or alias of another note")
    already = [entity.name, *entity.aliases]
    if all(fold(alias).casefold() != fold(n).casefold() for n in already):
        entity.aliases.append(alias)
        if entity.path is not None:
            save_entity(entity, entity.path)
    return entity
