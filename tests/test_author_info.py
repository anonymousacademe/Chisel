"""Project and author details: reading and writing to project.toml."""

from pathlib import Path
from chisel.core.project import Project


def test_author_info_read_defaults_when_not_set(tmp_path: Path):
    """Reading author info when not set returns empty strings and default language."""
    proj = Project.create(tmp_path, "Test Project")
    info = proj.author_info()
    assert info["author"] == ""
    assert info["pen_name"] == ""
    assert info["subtitle"] == ""
    assert info["copyright"] == ""
    assert info["contact"] == ""
    assert info["language"] == "en"


def test_author_info_write_and_read(tmp_path: Path):
    """Writing and reading author info persists values to project.toml."""
    proj = Project.create(tmp_path, "Test Project")
    proj.update_author_info(
        author="Jane Writer",
        pen_name="J. Stone",
        subtitle="A Novel of Tomorrow",
        copyright_="© 2026 Jane Writer",
        contact="jane@example.com",
        language="fr"
    )
    proj = Project.open(tmp_path)
    info = proj.author_info()
    assert info["author"] == "Jane Writer"
    assert info["pen_name"] == "J. Stone"
    assert info["subtitle"] == "A Novel of Tomorrow"
    assert info["copyright"] == "© 2026 Jane Writer"
    assert info["contact"] == "jane@example.com"
    assert info["language"] == "fr"


def test_author_info_write_partial_update(tmp_path: Path):
    """Updating only some fields preserves others."""
    proj = Project.create(tmp_path, "Test Project")
    proj.update_author_info(
        author="Jane Writer",
        pen_name="J. Stone",
        language="de"
    )
    proj = Project.open(tmp_path)
    info = proj.author_info()
    assert info["author"] == "Jane Writer"
    assert info["pen_name"] == "J. Stone"
    assert info["language"] == "de"
    assert info["subtitle"] == ""
    assert info["copyright"] == ""
    assert info["contact"] == ""

    # Now update only subtitle and copyright
    proj.update_author_info(
        subtitle="New Subtitle",
        copyright_="© 2027"
    )
    proj = Project.open(tmp_path)
    info = proj.author_info()
    assert info["author"] == "Jane Writer"  # preserved
    assert info["pen_name"] == "J. Stone"   # preserved
    assert info["subtitle"] == "New Subtitle"
    assert info["copyright"] == "© 2027"
    assert info["language"] == "de"  # preserved


def test_author_info_strips_whitespace(tmp_path: Path):
    """Whitespace is stripped from saved values."""
    proj = Project.create(tmp_path, "Test Project")
    proj.update_author_info(
        author="  Jane Writer  ",
        pen_name="\tJ. Stone\n",
        subtitle="  A Novel  ",
        language="  en  "
    )
    proj = Project.open(tmp_path)
    info = proj.author_info()
    assert info["author"] == "Jane Writer"
    assert info["pen_name"] == "J. Stone"
    assert info["subtitle"] == "A Novel"
    assert info["language"] == "en"


def test_author_info_language_defaults_to_en(tmp_path: Path):
    """Language defaults to 'en' when set to empty string."""
    proj = Project.create(tmp_path, "Test Project")
    proj.update_author_info(language="")
    proj = Project.open(tmp_path)
    info = proj.author_info()
    assert info["language"] == "en"


def test_export_uses_pen_name_when_set(tmp_path: Path):
    """Export uses pen_name if set, otherwise author."""
    from chisel.core.export.manuscript import assemble

    proj = Project.create(tmp_path, "Test Project")
    (proj.manuscript_dir / "01-opening.md").write_text(
        "# Scene One\n\nSome prose.", encoding="utf-8", newline="\n")

    proj.update_author_info(
        author="Real Name",
        pen_name="Pen Name"
    )
    proj = Project.open(tmp_path)
    book = assemble(proj)
    assert book.author == "Pen Name"

    # Test without pen name
    proj.update_author_info(author="Jane Writer", pen_name="")
    proj = Project.open(tmp_path)
    book = assemble(proj)
    assert book.author == "Jane Writer"

    # Test with only pen name
    proj.update_author_info(author="", pen_name="Anonymous")
    proj = Project.open(tmp_path)
    book = assemble(proj)
    assert book.author == "Anonymous"


def test_author_info_round_trips_quotes_backslashes_and_newlines(tmp_path: Path):
    proj = Project.create(tmp_path, "Test Project")
    nasty = {"author": 'Jane "JW" O\'Hara', "contact": "a@b.c\nhttps://x.y", "copyright_": "\\ © 2026"}
    proj.update_author_info(**nasty)
    info = Project.open(tmp_path).author_info()
    assert (info["author"], info["contact"], info["copyright"]) == (
        nasty["author"], nasty["contact"], nasty["copyright_"])
