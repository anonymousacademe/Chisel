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
