from pathlib import Path

from chisel.core import entities as ent


def test_slugify():
    assert ent.slugify("Elara Vance") == "elara-vance"
    assert ent.slugify("  The  Old  Mill! ") == "the-old-mill"
    assert ent.slugify("Café de Flore") == "cafe-de-flore"


def test_roundtrip(tmp_path: Path):
    e = ent.Entity(name="Borin", type="character",
                   aliases=["the old smith", "Borin Stonehand"],
                   body="Gruff. Owes [[Elara Vance]] money.\n")
    path = tmp_path / "borin.md"
    ent.save_entity(e, path)
    loaded = ent.load_entity(path)
    assert loaded.name == "Borin"
    assert loaded.type == "character"
    assert loaded.aliases == ["the old smith", "Borin Stonehand"]
    assert "Gruff" in loaded.body


def test_from_markdown_tolerates_missing_frontmatter():
    e = ent.Entity.from_markdown("Just some notes.\n", path=Path("thornwick.md"))
    assert e.name == "thornwick"
    assert e.type == "character"
    assert e.body == "Just some notes.\n"


def test_resolve_by_alias_case_insensitive():
    entities = [
        ent.Entity(name="Elara Vance", aliases=["the captain"]),
        ent.Entity(name="Thornwick", type="place"),
    ]
    assert ent.resolve("elara vance", entities).name == "Elara Vance"
    assert ent.resolve("The Captain", entities).name == "Elara Vance"
    assert ent.resolve("thornwick", entities).type == "place"
    assert ent.resolve("Nobody", entities) is None


def test_new_entity_note_parses_back():
    note = ent.new_entity_note("Thornwick", "place")
    e = ent.Entity.from_markdown(note)
    assert e.name == "Thornwick"
    assert e.type == "place"
    assert e.aliases == []
