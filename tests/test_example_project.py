"""The bundled example project stays loadable and keeps its demo features."""

from pathlib import Path

from chisel.core.index import Index
from chisel.core.links import find_all_links
from chisel.core.project import Project

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


def test_example_project_has_none_of_the_wave_3_data_and_reading_it_creates_none(tmp_path: Path):
    """Collections, comments, research and chats are opt-in: the example opens exactly as before."""
    import shutil

    from chisel.core import attach, chats, collections, comments, research
    from chisel.gui import workspace as ws

    copy = tmp_path / "residual"
    shutil.copytree(EXAMPLE, copy)
    before = sorted(p.relative_to(copy).as_posix() for p in copy.rglob("*"))
    proj = Project.open(copy)
    assert collections.list_collections(proj) == []
    assert research.list_notes(proj) == [] and chats.list_chats(proj) == []
    for scene in proj.list_scenes():
        assert comments.load(proj.root, scene) == []
        assert comments.place(scene.read_text("utf-8"), []) == []
    built = ws.build_workspace(proj, proj.load_entities(), baseline_words=0, session_minutes=0, ai_cost=0)
    assert built["collections"] == [] and built["research"] == []
    assert [n["id"] for n in built["binder"] if n["kind"] == "research"] == ["group:research"]
    assert attach.build(proj, []) == ("", [])
    assert sorted(p.relative_to(copy).as_posix() for p in copy.rglob("*")) == before    # nothing was created
