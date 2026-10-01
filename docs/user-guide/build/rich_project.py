"""Build a richer copy of examples/residual for the Fourth Edition's figures.

    PYTHONPATH=src python docs/user-guide/build/rich_project.py DEST STATE_DIR [--git]

DEST must not exist; STATE_DIR is a temporary LOREWRITE_STATE_DIR. The copy has
front matter and two parts, one unplaced scene, scene details on two scenes,
snapshots (including the end-of-draft ones of "Start new draft"), a collection,
two comments (one of them detached), two research notes, a saved chat and 35
days of stats. With --git the folder is also a git repository with one commit
and one uncommitted change. Only core calls; nothing touches the network.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
dest, state = Path(sys.argv[1]), Path(sys.argv[2])
os.environ["LOREWRITE_STATE_DIR"] = str(state)
state.mkdir(parents=True, exist_ok=True)

import lorewrite  # noqa: E402

assert Path(lorewrite.__file__).resolve().is_relative_to(REPO), lorewrite.__file__

from lorewrite.core import (  # noqa: E402
    chats, collections, comments, research, scenemeta, snapshots, stats, sync,
)
from lorewrite.core.project import Project  # noqa: E402

shutil.copytree(REPO / "examples" / "residual", dest)
p = Project.open(dest)
ms = p.manuscript_dir
s1, s2, s3, s4 = p.list_scenes()

# ---- parts: front matter, "The Recall" (scenes 1-2), "Ghost Frequency" (3-4)
front = ms / "00-front-matter"
front.mkdir()
(front / "_part.md").write_text("# Front Matter\n", encoding="utf-8")
(front / "01-title-page.md").write_text(
    "# Title Page\n\nResidual\n\nA novella in four scenes.\n", encoding="utf-8")
recall = p.new_part("The Recall")
ghost = p.new_part("Ghost Frequency")
s1 = p.place_scene(s1, recall)
s2 = p.place_scene(s2, recall)
s3 = p.place_scene(s3, ghost)
s4 = p.place_scene(s4, ghost)

# ---- an unplaced scene: written, not in the book
unplaced = p.unplaced_dir
unplaced.mkdir(exist_ok=True)
(unplaced / "01-the-night-market.md").write_text(
    "# The Night Market\n\nRook walked the Hollow Market after the lights went "
    "down. Nobody sold anything he wanted to buy.\n", encoding="utf-8")

# ---- scene details on two scenes
s2.write_text(scenemeta.set_details(
    s2.read_text(encoding="utf-8"), pov="Rook Tanaka", place="The Meridian",
    purpose="Rook finds the body and the shard", status="revising", target=600),
    encoding="utf-8")
s4.write_text(scenemeta.set_details(
    s4.read_text(encoding="utf-8"), pov="Rook Tanaka", place="Hollow Market",
    purpose="Wren confesses what she is", status="draft", target=450),
    encoding="utf-8")

# ---- a collection
collections.create(p, "Needs continuity pass", "amber")
collections.create(p, "Rook's arc", "violet")
collections.toggle(p, s2, "Needs continuity pass", True)
collections.toggle(p, s3, "Needs continuity pass", True)
for s in (s1, s3, s4):
    collections.toggle(p, s, "Rook's arc", True)

# ---- snapshots (backdated), then "Start new draft" -> Draft 2
when = datetime.now()
t2 = s2.read_text(encoding="utf-8")
snapshots.create(p, s2, "before the rewrite", text=t2.replace(
    "Her green eyes were open", "Her grey eyes were open"),
    when=when - timedelta(days=2, hours=3))
snapshots.create(p, s2, "", text=t2 + "\nAn extra line that was later cut.\n",
                 when=when - timedelta(days=1, hours=1))
snapshots.create(p, s3, "first pass", when=when - timedelta(hours=5))
p.start_new_draft()
p = Project.open(dest)

# ---- comments: one anchored, one detached
t3 = s3.read_text(encoding="utf-8")
quote = "The shard sat in Rook's pocket like a coin from another country."
i = t3.index(quote)
comments.add(dest, s3, t3, i, i + len(quote), "Better than the rewrite? Compare with the AI version.")
t2 = s2.read_text(encoding="utf-8")
j = t2.index("Rook climbed the ladder and looked in.")
comments.add(dest, s2, t2, j, j + len("Rook climbed the ladder and looked in."),
             "Check how many tiers up this is.")
t2b = t2.replace("Rook climbed the ladder and looked in.\n\n", "")
s2.write_text(t2b, encoding="utf-8")   # the commented words are gone: detached

# ---- research notes
research.new_note(p, "Capsule hotels", "Real capsule hotels stack units two high "
                  "and share a washroom.\n\nA night costs about the price of a "
                  "meal. Guests leave shoes in lockers at the door.\n")
research.new_note(p, "Data forensics", "Recovering deleted data from a neural "
                  "implant: the residue of a write persists in the buffer for "
                  "days.\n\nA forensic freelancer is paid by the extraction.\n")

# ---- a saved chat
chats.save(p, None, [
    {"id": "m1", "role": "user", "text": "How can I make the stairwell scene more tense?"},
    {"id": "m2", "role": "assistant", "text": "Three options:\n1. Let a floor "
     "above go silent.\n2. Have Wren stop answering.\n3. Cut the lights on the "
     "landing."},
], scope="scene")

# ---- stats: 35 days (a streak of the last 6, a gap before)
days = {}
today = date.today()
pattern = [620, 540, 710, 505, 880, 560, 0, 310, 450, 900, 620, 0, 0, 480, 520,
           300, 750, 660, 410, 380, 520, 800, 0, 560, 640, 350, 530, 610, 500,
           690, 720, 880, 640, 1010, 560]
for n, words in enumerate(reversed(pattern)):
    day = today - timedelta(days=n)
    if words == 0:
        continue
    days[day.isoformat()] = {"words": words, "ai_words": 40 if n % 4 == 0 else 0,
                             "seconds": words * 7, "sessions": 1 + n % 2, "sprints": []}
days[today.isoformat()] = {"words": 240, "ai_words": 0, "seconds": 1500, "sessions": 1,
                           "sprints": [{"at": datetime.now().isoformat(timespec="seconds"),
                                        "minutes": 25, "words": 190, "completed": True}]}
sp = stats.stats_path(dest, state)
sp.parent.mkdir(parents=True, exist_ok=True)
sp.write_text(json.dumps({"version": 1, "project": str(dest.resolve()), "days": days}, indent=1))

# ---- the Trash: a cut scene and a research note
cut = ghost / "03-a-scene-i-cut.md"
cut.write_text("# A Scene I Cut\n\nRook waited. Nothing happened.\n", encoding="utf-8")
p.delete_scene(cut)
old_note = research.new_note(p, "Old tide tables", "Notes I no longer need.\n")
p.trash_research(old_note)

if "--git" in sys.argv:
    os.environ.update(GIT_AUTHOR_NAME="Residual Author", GIT_AUTHOR_EMAIL="author@example.com",
                      GIT_COMMITTER_NAME="Residual Author", GIT_COMMITTER_EMAIL="author@example.com",
                      GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    sync.init(dest)
    st = sync.status(dest)
    sync.commit(dest, sync.default_message(st))
    if "--remote" in sys.argv:        # a local bare repository: nothing leaves this computer
        bare = dest.parent / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        subprocess.run(["git", "-C", str(dest), "remote", "add", "origin", str(bare)], check=True)
        subprocess.run(["git", "-C", str(dest), "push", "-q", "-u", "origin", "HEAD"], check=True)
    s3.write_text(s3.read_text(encoding="utf-8") + "\nOne more line after the commit.\n",
                  encoding="utf-8")
print("built", dest)
