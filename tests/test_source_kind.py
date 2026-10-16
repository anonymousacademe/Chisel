"""Source / concept / method / dataset kinds, their folders and the AI exclusion (research mode, P1)."""

from chisel.ai import relevance
from chisel.ai.links import build_prompt
from chisel.ai.writing import build_context_sections
from chisel.core import entities as ent
from chisel.core.continuity import canon_map
from chisel.core.project import Project


def test_types_round_trip():
    for kind in ("source", "concept", "method", "dataset"):
        e = ent.Entity.from_markdown(ent.new_entity_note("x", kind))
        assert e.type == kind
    assert ent.Entity.from_markdown(ent.new_entity_note("x", "source")).is_source
    assert not ent.Entity(name="a").is_source


def test_story_project_gains_no_research_folders(tmp_path):
    p = Project.create(tmp_path / "book", "B")
    assert sorted(d.name for d in p.entities_dir.iterdir()) == ["characters", "factions", "objects", "places"]
    r = Project.create(tmp_path / "paper", "P", mode="research")
    names = {d.name for d in r.entities_dir.iterdir()}
    assert {"sources", "concepts", "methods", "datasets"} <= names


def test_source_file_name_is_key_with_collision_suffix(tmp_path):
    p = Project.create(tmp_path / "paper", "P", mode="research")
    a, pa = p.create_entity("Smith2024", "source")
    b, pb = p.create_entity("smith2024", "source")   # different key, same file name on Windows
    again, pc = p.create_entity("Smith2024", "source")
    assert pa.parent.name == "sources" and pa.name == "smith2024.md"
    assert pb != pa and pc == pa
    assert pb.name == "smith2024-2.md"
    assert ent.resolve_key("smith2024", p.load_entities()).path == pb
    assert ent.resolve_key("Smith2024", p.load_entities()).path == pa


def test_source_creation_ignores_alias_of_other_note(tmp_path):
    p = Project.create(tmp_path / "paper", "P", mode="research")
    c, _ = p.create_entity("Kalman filter", "concept")
    c.aliases.append("kalman2020")
    ent.save_entity(c, c.path)
    s, _ = p.create_entity("kalman2020", "source")
    assert s.is_source


def _mixed():
    char = ent.Entity(name="Elara", type="character", body="Elara is a pilot.")
    src = ent.Entity(name="smith2024", type="source", aliases=["Smith and Lee"],
                     body="SECRETSOURCETEXT highlights", extra={"title": "T"})
    return char, src


def test_no_source_text_in_any_context_builder():
    char, src = _mixed()
    ents = [char, src]
    scene = "Elara read Smith and Lee and smith2024 and [[smith2024]]."
    assert "SECRETSOURCETEXT" not in "".join(canon_map(ents).values())
    assert "smith2024" not in canon_map(ents)
    ranked = relevance.rank(scene, ents)
    assert [r.entity.name for r in ranked] == ["Elara"]
    secs = build_context_sections(scene, 0, ents, canon_map(ents), None)
    assert "SECRETSOURCETEXT" not in repr(secs)
    assert not any("smith2024" in repr(s.items) for s in secs if s.items)
    # even a caller-built canon map cannot leak it: the entity is never ranked
    leaky = build_context_sections(scene, 0, ents, {"smith2024": "SECRETSOURCETEXT"}, None)
    assert "SECRETSOURCETEXT" not in repr(leaky)
    assert "smith2024" not in build_prompt(scene, ents).split("SCENE:")[0]
    assert relevance.priority_limit([char] + [src] * 100) == relevance.priority_limit([char])
