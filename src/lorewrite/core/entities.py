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

VALID_TYPES = ("character", "place", "object", "faction")

ENTITY_TEMPLATE = """\
---
name: {name}
type: {type}
aliases: []
---

"""


def slugify(name: str) -> str:
    """'Elara Vance' -> 'elara-vance' (filesystem-safe note filename)."""
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^\w\s-]", "", slug).strip().lower()
    return re.sub(r"[\s_]+", "-", slug) or "untitled"


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
        term = term.casefold()
        return any(term == n.casefold() for n in self.names)

    def to_markdown(self) -> str:
        frontmatter = {
            "name": self.name,
            "type": self.type,
            "aliases": self.aliases,
        }
        return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n\n{self.body}"

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
    return Entity.from_markdown(path.read_text(encoding="utf-8"), path=path)


def save_entity(entity: Entity, path: Path) -> None:
    """Write a note atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(entity.to_markdown(), encoding="utf-8")
    tmp.replace(path)


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


def add_alias(entity: Entity, alias: str) -> Entity:
    """Add an alias to an entity note (deduped) and save it to disk."""
    alias = alias.strip()
    if not alias:
        return entity
    already = [entity.name, *entity.aliases]
    if all(alias.casefold() != n.casefold() for n in already):
        entity.aliases.append(alias)
        if entity.path is not None:
            save_entity(entity, entity.path)
    return entity
