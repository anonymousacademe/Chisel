"""The bundled example project stays loadable and keeps its demo features."""

from pathlib import Path

from lorewrite.core.index import Index
from lorewrite.core.links import find_all_links
from lorewrite.core.project import Project

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "residual"


def test_example_project_opens_with_its_scenes_and_notes():
    proj = Project.open(EXAMPLE)
    assert proj.title == "Residual"
    assert [p.name for p in proj.list_scenes()] == [
        "01-rain-on-the-spur.md", "02-capsule-7-19.md",
        "03-the-stairwell.md", "04-ghost-in-the-ice.md"]
    names = {e.name for e in proj.load_entities()}
    assert {"Rook Tanaka", "Wren", "Imogen Sallow", "Dace Kuroda",
            "The Meridian", "Hollow Market", "Kessler-Voss",
            "Sallow's Shard"} <= names


def test_example_project_demo_hooks_are_intact(tmp_path: Path):
    proj = Project.open(EXAMPLE)
    names = [n for e in proj.load_entities() for n in e.names]
    scene4 = (proj.manuscript_dir / "04-ghost-in-the-ice.md").read_text("utf-8")
    links = find_all_links(scene4, names)
    assert any(l.explicit and l.target == "Tetsuo Brandt" for l in links)
    assert any(l.explicit and l.target == "Imogen Sallow" for l in links)
    # planted continuity contradictions (see examples/README.md)
    scene2 = (proj.manuscript_dir / "02-capsule-7-19.md").read_text("utf-8")
    scene3 = (proj.manuscript_dir / "03-the-stairwell.md").read_text("utf-8")
    assert "green eyes" in scene2
    assert "right hand, the chrome one" in scene3
    # indexing a copy yields plain-name backlinks (never touch the original)
    index = Index(tmp_path / "index.sqlite")
    index.rebuild(proj)
    rook = next(e for e in proj.load_entities() if e.name == "Rook Tanaka")
    assert len(index.backlinks(rook)) > 5
    index.close()
