"""ai/relevance.py: which entities a scene is about (named, POV / place, everyone else)."""

from lorewrite.ai import relevance
from lorewrite.core import scenemeta
from lorewrite.core.entities import Entity

MARA = Entity(name="Mara Vale", aliases=["Mara"], body="a")
ELIAS = Entity(name="Elias Vale", aliases=["Elias"], body="b")
CITY = Entity(name="Lower Meridian", type="place", body="c")
OTHER = Entity(name="Orin Pell", body="d")
ENTITIES = [OTHER, CITY, ELIAS, MARA]


def scene() -> str:
    text = "# Arrival\n\nMara stepped off the tram.\n"
    return scenemeta.set_details(text, pov="Elias", place="Lower Meridian")


def test_rank_orders_by_tier_and_keeps_every_entity_once():
    ranked = relevance.rank(scene(), ENTITIES)
    assert [r.entity.name for r in ranked] == [e.name for e in ENTITIES]    # the project's order
    tiers = {r.entity.name: r.tier for r in ranked}
    assert tiers == {"Mara Vale": 0, "Elias Vale": 1, "Lower Meridian": 1, "Orin Pell": 2}
    in_scene = relevance.in_scene(ranked)
    assert [r.entity.name for r in in_scene] == ["Elias Vale", "Lower Meridian", "Mara Vale"]  # as they appear: details first
    assert min(r.priority for r in ranked if r.tier == 2) > max(r.priority for r in ranked if r.tier < 2)


def test_a_name_in_the_details_and_the_prose_counts_as_named():
    text = scenemeta.set_details("# T\n\nElias waited.\n", pov="Elias")
    assert {r.entity.name: r.tier for r in relevance.rank(text, ENTITIES)}["Elias Vale"] == 0


def test_everyone_is_sent_below_the_threshold_and_only_the_scenes_entities_above_it():
    few = [Entity(name=f"E{i}") for i in range(relevance.ALL_MAX - 1)]
    many = few + [Entity(name="Extra")]
    assert relevance.priority_limit(few) >= relevance.rank("x", few)[0].priority          # tier 2 is sent
    assert relevance.priority_limit(many) < relevance.rank("x", many)[0].priority         # tier 2 is not
    named = Entity(name="Named")
    big = many + [named]
    ranked = relevance.rank("Named walked in.", big)
    assert [r.priority <= relevance.priority_limit(big) for r in ranked if r.entity is named] == [True]
