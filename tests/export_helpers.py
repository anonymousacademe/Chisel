"""A structured project for the export tests: front matter, two parts, an
unplaced scene, a trashed scene, pending AI drafts with sidecar originals,
expand markers, [[links]], scene details, italics and scene breaks."""

from pathlib import Path

from lorewrite.core import drafts
from lorewrite.core.project import Project

from tests.gui_helpers import make_project

RAIN = """\
---
pov: Mara Vale
status: draft
---
# Rain on the Spur

Mara stepped off the tram. [[Elias Vale|Elias]] waited under the *clock*,
and the rain, **heavy** and copper-smelling, had not stopped.

She said nothing. {{expand: describe the platform}}

* * *

The second half began with a `code` word and an escaped \\*star\\*.
"""

CAPSULE = """\
# Capsule 7-19

<!--ai id="abc123"-->A grand rewritten sentence.<!--/ai--> The capsule hummed.
Then <!--ai-->an invented line<!--/ai-->silence.

---

[[Lower Meridian]] slept.
"""

SIGNAL = """\
# Signal

The signal came in at dawn.
"""


def make_structured(root: Path) -> Project:
    project = make_project(root)
    ms = root / "manuscript"
    for f in ms.glob("0*.md"):
        f.unlink()

    def write(rel: str, text: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    write("manuscript/00-front-matter/01-dedication.md", "# Dedication\n\nFor the ones who remember.\n")
    write("manuscript/00-front-matter/_part.md", "# Front Matter\n")
    write("manuscript/01-the-recall/_part.md", "# The Recall\n\nnotes for me\n")
    write("manuscript/01-the-recall/01-rain-on-the-spur.md", RAIN)
    capsule = write("manuscript/01-the-recall/02-capsule-7-19.md", CAPSULE)
    drafts.save_originals(root, capsule, {"abc123": "Original sentence."})
    write("manuscript/02-ghost-frequency/01-signal.md", SIGNAL)
    write("manuscript/_unplaced/01-cut-scene.md", "# Cut Scene\n\nNever in the book.\n")
    trashed = write("manuscript/02-ghost-frequency/02-doomed.md", "# Doomed\n\nGoing to the trash.\n")
    project = Project.open(root)
    project.delete_scene(trashed)
    # research notes must never appear
    (root / "notebook").mkdir(exist_ok=True)
    (root / "notebook" / "tides.md").write_text("# Tides\n\nResearch only.\n", encoding="utf-8")
    return Project.open(root)
