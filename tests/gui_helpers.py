"""Shared builders for the GUI tests: a small deterministic project."""

from pathlib import Path

from lorewrite.core import entities as ent
from lorewrite.core.project import Project

SCENE_1 = """\
# Arrival

Mara stepped off the tram into Lower Meridian. The rain had not stopped for
three days and the city smelled of copper. Elias was waiting under the clock.
"""

SCENE_2 = """\
# The Archive

## Night shift

Mara read the files until dawn. <!--ai-->This sentence is an unaccepted AI draft.<!--/ai-->
"""


def make_project(root: Path) -> Project:
    project = Project.create(root, "Test Novel")
    (root / "manuscript" / "01-opening.md").unlink()
    (root / "manuscript" / "01-arrival.md").write_text(SCENE_1, encoding="utf-8")
    (root / "manuscript" / "02-the-archive.md").write_text(SCENE_2, encoding="utf-8")
    mara, _ = project.create_entity("Mara Vale", "character")
    elias, _ = project.create_entity("Elias Vale", "character")
    ent.add_alias(mara, "Mara")
    ent.add_alias(elias, "Elias")
    project.create_entity("Lower Meridian", "place")
    (root / "project.toml").write_text(
        'title = "Test Novel"\nauthor = "Jane Writer"\n', encoding="utf-8")
    return Project.open(root)


def make_book(root: Path) -> Project:
    """make_project's cast, but the manuscript is a book: front matter and two
    parts (folders) instead of flat scenes."""
    project = make_project(root)
    for f in (root / "manuscript").glob("0*.md"):
        f.unlink()

    def scene(rel: str, title: str, body: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")

    scene("manuscript/00-front-matter/01-title.md", "Title Page", "front " * 4)
    scene("manuscript/01-the-recall/01-rain.md", "Rain", "rain " * 10)
    scene("manuscript/01-the-recall/02-capsule.md", "Capsule", "capsule " * 10)
    scene("manuscript/02-ghost/01-signal.md", "Signal", "signal " * 10)
    return Project.open(root)
