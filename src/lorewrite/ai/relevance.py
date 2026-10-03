"""Which entities matter to one scene (SPEC "Context budget and the sent report").

AI features that carry the story bible send the notes of the entities a scene is
about, best first: tier 0 = named in the prose, tier 1 = the scene's POV or place
(from its details block), tier 2 = everyone else. Pure Python, no network.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import scenemeta
from ..core.entities import Entity, resolve
from ..core.links import find_all_links

# Authors with fewer entities than this send every entity (tier 2 included, budget
# permitting); with more, only tiers 0 and 1 - a long book's whole bible is not sent
# for one scene.
ALL_MAX = 40
TIER_MENTIONED, TIER_DETAILS, TIER_REST = 0, 1, 2
_TIER = 1_000_000   # priority = tier * _TIER + position, so tiers never interleave


@dataclass(frozen=True)
class Ranked:
    entity: Entity
    tier: int
    order: int        # position in the scene for tiers 0/1; position in the project for tier 2

    @property
    def priority(self) -> int:
        return self.tier * _TIER + self.order


def _found(text: str, names: list[str], entities: list[Entity]) -> list[Entity]:
    out: list[Entity] = []
    for link in find_all_links(text, names):
        entity = resolve(link.target, entities)
        if entity is not None and entity not in out:
            out.append(entity)
    return out


def rank(scene_text: str, entities: list[Entity]) -> list[Ranked]:
    """Every entity once, in the project's order, with its tier. *scene_text* may carry its
    details block (its POV / place count as tier 1) and must not carry pending AI drafts."""
    names = [n for e in entities for n in e.names]
    prose = _found(scenemeta.blank(scene_text), names, entities)
    overall = _found(scenemeta.blank(scene_text, keep=scenemeta.MENTION_FIELDS), names, entities)
    tier0 = {id(e) for e in prose}
    where = {id(e): i for i, e in enumerate(overall)}
    ranked = []
    for i, e in enumerate(entities):
        if id(e) in where:
            ranked.append(Ranked(e, TIER_MENTIONED if id(e) in tier0 else TIER_DETAILS, where[id(e)]))
        else:
            ranked.append(Ranked(e, TIER_REST, i))
    return ranked


def in_scene(ranked: list[Ranked]) -> list[Ranked]:
    """The tier 0 and 1 entities in the order they appear in the scene (details first)."""
    return sorted((r for r in ranked if r.tier < TIER_REST), key=lambda r: r.order)


def priority_limit(entities: list[Entity]) -> int:
    """The largest ``Ranked.priority`` that is sent for a project of this size (a
    ``Section.max_priority``): everyone for a small project, tiers 0 and 1 for a big one."""
    tier = TIER_REST if len(entities) < ALL_MAX else TIER_DETAILS
    return (tier + 1) * _TIER - 1
