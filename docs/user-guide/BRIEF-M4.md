# Brief: update the User's Guide for M4 (Second Edition)

Update the guide you built (`docs/user-guide/build_guide.py` →
`docs/user-guide/lorewrite-users-guide.pdf`) to document Lorewrite as it is on
branch **`m4-ai-writing`**, checked out at **`~/lorewrite-m4`** (read-only for
you). That branch will be merged into `main` together with this guide.

- Source of truth: the code in `~/lorewrite-m4` (plus its README, SPEC.md,
  `docs/dev/plan-m4-ai-writing.md`, `docs/dev/plan-m4-fixes.md`, and `git log
  main..m4-ai-writing` in that worktree). Code wins over docs.
- Capture screens from the branch code: run your capture script with
  `PYTHONPATH=$HOME/lorewrite-m4/src ~/lorewrite/.venv/bin/python …` and
  confirm `lorewrite.__file__` points into `~/lorewrite-m4`. Same rules as
  before: copy of the demo project, temp `LOREWRITE_STATE_DIR`, AI mocked
  (monkeypatch `lorewrite.tui.app.generate`, `learn_style`, alias and canon
  functions — see `~/lorewrite-m4/tests/test_writing.py`, `test_style.py`),
  never network. Your palette CSS workaround should no longer be needed —
  check, and drop it if so.
- Keep writing only inside `~/lorewrite/docs/user-guide/`. Do not modify
  `~/lorewrite-m4`. Do not commit.

## What to change

- **Edition:** Second Edition (September 2026), applies to Version 0.2.0 on
  the M4 branch. Document number suffix `-1` (e.g. `LW00-0001-1`). Summary of
  Changes lists every change below.
- **New chapter: Writing with AI** (place it after "AI Assistance"; renumber
  following chapters and every cross-reference, figure and table number):
  the writing model and why it's a separate choice; the style guide
  (`style.md` at the project root: learn from manuscript, review, backup,
  open/edit by hand); `ctrl+g` in its three modes (draft at cursor with the
  prompt window, `{{expand: …}}` placeholders, rewrite selection); how
  pending AI text looks and where it's stored (markers in the scene file,
  originals in `.drafts/`); `f7` accept / `f8` reject / palette accept-all /
  reject-all; what happens if the original is missing; that pending text is
  excluded from word counts, continuity checks, the story bible and
  backlinks. A procedure-style walkthrough on the demo story, with figures.
- **AI Assistance chapter:** `ctrl+l` is now **Find aliases** (never edits the
  scene) — rewrite that section and its figures; story-bible update is now
  additions-only with per-fact review — replace your old Attention note;
  cost display in the status bar and notifications; continuity `enter` now
  closes the report; the new restore-waived-issues palette action.
- **Settings:** the writing-model row and its full-catalog picker; compact
  layout.
- **Keys:** `ctrl+g`, `f7`, `f8`, `f5` (select all moved from `f7`), `f1`
  (help from the editor) or whatever key the branch actually uses — check
  `BINDINGS`/HELP_TEXT. Update Chapter "Command and Key Reference" tables and
  the help-screen figure.
- **Appendix A:** `style.md`, `.drafts/<scene>.json`, the `<!--ai-->` marker
  format, `[ai] writing_model` in `project.toml`.
- **Appendix B:** every new notify/message text from the branch code.
- **Tutorial (Appendix C):** add steps for style guide + `ctrl+g` + accept/
  reject.
- Glossary and Index: new terms (pending draft, style guide, writing model,
  alias finder, expand marker, …); re-verify every page reference.
- Remove notes about problems the branch fixed (palette, `?` in editor if
  fixed, launch hint, version mismatch); keep any that still apply.

## Verify and report

Render every page and look at it, as before; `qpdf --check`. Report to
`/tmp/guide-m4-report.md` (path in your reply): page count, what changed,
anything uncertain.
