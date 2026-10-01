# Brief: User's Guide, Fourth Edition (manuscript structure, history, notes, writing aids)

Update the guide in `docs/user-guide/` to document Lorewrite as it is now on
**`main`** in `~/lorewrite`. The Third Edition (73725ab) documents main at
5aa99e0; since then four waves of features landed. Same house style and rules
as `BRIEF.md`, `BRIEF-M4.md` and `BRIEF-v3.md` (read them); the code is the
source of truth. Read `docs/plan-workspace.md` (the plan), the "As built" /
storage sections of `SPEC.md`, `README.md`, `AGENTS.md`, and `git log
5aa99e0..main`.

## What to document (both the terminal and the desktop application, side by side)

- **Wave 1 — manuscript structure:** parts (folders, `_part.md`, front matter
  part), the scene/chapter label setting, Unplaced Scenes, the Trash (move,
  restore, delete forever, empty), scene details (POV, place, purpose,
  status, target — frontmatter, the GUI inspector and details dialog, the TUI
  form), corkboard/outline drag-to-reorder with confirm and Undo.
- **Wave 2 — history:** snapshots (manual, automatic daily and before
  restore/accept-all/reject-all, the History dialog, compare, restore,
  delete; TUI palette), the Draft N counter and Start new draft, git sync
  (status meanings; Commit, Push, Initialize — explicit only; what Push needs).
- **Wave 3 — notes around the manuscript:** collections, comments (anchoring,
  detached comments), research notes and the Research question mode,
  assistant conversation history, attach, Save to notes.
- **Wave 4 — writing aids:** session stats page, streak and daily target,
  focus sprints, Brainstorm; research notes now go to the Trash.
- Remove "Parts Not Built Yet" items that are now real; keep an honest short
  list of anything still a placeholder (check the code).
- Appendix A: every new file and folder (`manuscript/NN-part/`, `_part.md`,
  `_unplaced/`, `.trash/`, scene frontmatter keys, `.snapshots/`,
  `[manuscript] draft` and `unit`, `[collections]`, `.comments/`,
  `research/`, `.assistant/chats/`, stats in the state folder) with examples.
  A one-page "What is in my project folder" map would help readers.
- Messages / Problem Solving, key reference, Settings reference, Glossary,
  Index, Tutorial (add a short section using parts, a snapshot and a sprint on
  the Residual copy).
- Edition: **Fourth Edition (October 2026)**, `LW00-0001-3`, Summary of Changes.
  Chapter structure is your call — likely new chapters "Organizing the
  Manuscript", "History and Versions", "Notes, Comments and Research", and
  "Writing Aids", renumbering the rest consistently.

## Figures

Re-capture TUI and GUI figures from `main` as before (`build_guide.py
--capture`; GUI via the headless devserver + Chromium scripts you already have
in `build/`). Build a richer copy of `examples/residual` for the new figures
in a temp dir: two parts plus front matter, one unplaced scene, scene details
on two scenes, a couple of snapshots, a collection, two comments (one
detached), two research notes, a saved chat, some stats history. Always a temp
copy and a temp `LOREWRITE_STATE_DIR`; mock AI only; no network; never a
desktop window; stop what you start by PID; delete temp browser profiles.

## Rules

Write only inside `~/lorewrite/docs/user-guide/`. Do not commit. Render and
look at every page; `qpdf --check`. Run the Jev review on your script changes
(`build_guide.py` is too large for Jev — note it). Report to
`/tmp/guide-v4-report.md` (page count, what changed, anything uncertain) and
reply with the path.
