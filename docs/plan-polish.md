# Plan: polish pass after Waves 1-4 (branch `polish`)

Small fixes found while writing the User's Guide, Fourth Edition. Same rules
as `docs/plan-workspace.md` ("Rules for every wave"). One commit per item,
each with a regression test. Keep both front ends consistent.

1. **Trash restore toast (GUI):** the toast says the scene's part is gone for
   *every* restore into Unplaced. Say "its part is gone, so it went to
   Unplaced Scenes" only when the original part folder no longer exists;
   otherwise name where it went ("Restored to Part II", "Restored to
   Unplaced Scenes" when it came from there).
2. **TUI snapshot Compare title** shows the snapshot's file id; show the
   label (if any) and the human time, like the list does.
3. **Word-delta formatting:** use one form everywhere (`±0`, `+12`, `−5`
   with a real minus) in both UIs (snapshot lists, stats, sprint end notice).
4. **TUI part commands** act on the open scene's part, so deleting an empty
   part needs a non-part file open. Make Rename part / Move part up/down /
   Delete empty part ask which part (a small picker, defaulting to the open
   scene's part).
5. **Palette label "Toggle chapter/chapter labels"** (and any similar
   doubled wording): the label should name the switch it performs, e.g.
   "Call them scenes" / "Call them chapters" depending on the current unit.
6. **TUI assistant `ctrl+h`** (saved conversations) arrives as Backspace in
   many terminals. Pick a key that reaches the app in a Pilot test and is not
   a terminal control code (check AGENTS.md "Terminal key limits"); update
   the window's hint line, HELP_TEXT, README.
7. **README accuracy:** it says unplaced scenes are "not in continuity"; the
   continuity check only looks at the open scene. Make README/SPEC say what the
   code does (unplaced scenes are not counted and not in reading order).
8. **Dead code:** `_placeholder()` in `gui/workspace.py` is unused; remove it
   (keep the dev mock working).

Done: full pytest, vitest, build, lint (no new warnings); Jev per commit
(table in the report); report to `/tmp/polish-report.md` listing every
user-visible text that changed (the guide will be corrected from it).
