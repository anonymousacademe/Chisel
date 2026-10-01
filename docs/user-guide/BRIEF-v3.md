# Brief: User's Guide, Third Edition (desktop GUI + spelling + style card)

Update the guide in `docs/user-guide/` (`build_guide.py`, `build/guidelib.py`,
`build/capture.py` → `lorewrite-users-guide.pdf`) to document Lorewrite as it is
now on **`main`** in `~/lorewrite`, which has gained the desktop GUI. Same
house style as the First and Second Editions (classic computer-manual look,
chapter-page numbers, Note/Attention callouts, railroad syntax diagrams,
figures of real screens, glossary, index with verified page references). Read
`docs/user-guide/BRIEF.md` and `BRIEF-M4.md` for the style rules; they still
apply. The code is the source of truth over the docs.

## What changed since the Second Edition (read `git log`, SPEC.md, README.md,
`docs/plan-gui.md`, `docs/plan-spelling.md`)

- **The desktop GUI** (`lorewrite-gui`, pywebview + React): launch screen
  (title-first New project → `~/novels/<title>`, `--new TITLE`), the window
  (title bar, activity rail, binder, editor with CodeMirror live preview —
  hidden brackets and AI markers, mention colours, hover cards, ctrl+click —
  Manuscript / Corkboard / Outline, inspector, status bar), the Assistant
  (quick actions, continuity cards, chat with Insert as draft, Context and
  Notes tabs, the **Your style** card with Learn / Relearn my style), pending
  drafts with inline Accept / Reject, Settings dialog, quick switcher
  (`ctrl+k`), conflict banner, window placement on Omarchy/Hyprland.
  Placeholders ("Not in LoreWriter yet") exist; document them briefly as
  planned, without listing every one.
- **Spell check** in both front ends: underlines, the TUI `f6` window, the GUI
  popover, project `dictionary.txt` and the personal dictionary, phrases,
  ignore, what is never flagged.
- **Voice samples**: `ctrl+g` now sends ~2,000 words of the author's own prose
  as examples (explain plainly, with the cost note).
- **Style guide provenance** line in `style.md` and "out of date" logic.
- The continuity pre-screen fix (the check now really runs when Jev is
  installed) and the 180 s AI request timeout — reflect in AI chapters and
  Problem Solving where relevant.
- Commands: both `lorewrite` and `lorewrite-gui` are on the PATH (from
  `~/.local/bin`); the Omarchy app-menu entry and top-bar button open the GUI
  (check what was actually installed — ask the managing session's notes in
  `~/lorewrite-progress.md` if unsure).

## Structure

Add a new chapter **"The Desktop Application"** (after "Installing and
Starting" or as Part II — your call, keep cross-references and numbering
consistent) that walks through the GUI with figures, and weave the GUI into
the existing feature chapters (each feature: TUI keys and GUI controls side by
side, e.g. a two-column table). Add a **Spelling** chapter or section. Update
the key reference (TUI table + GUI table), Settings reference (GUI dialog),
File Formats (`dictionary.txt`, personal dictionary location, provenance line),
Messages, Tutorial (add a GUI path through the Residual example), Glossary,
Index. Edition: **Third Edition (October 2026)**, document number
`LW00-0001-2`, Summary of Changes.

## Figures from the GUI

Capture the GUI headlessly: `PYTHONPATH=src ~/lorewrite/.venv-gui/bin/python
-m lorewrite.gui.devserver --project <COPY of examples/residual> --mock-ai`
(prints a localhost URL; isolated `LOREWRITE_STATE_DIR`; set
`OPENROUTER_API_KEY=sk-mock` so AI controls are enabled with mocked answers)
and headless Chromium (`chromium --headless=new --window-size=1600,1000
--screenshot=…`, or CDP for interactions such as opening the popover or a
dialog). Convert to grayscale like the other figures. Stop every server you
start by its PID. Never open a real GUI window on the desktop. Never make real
AI calls.

## Rules

Write only inside `~/lorewrite/docs/user-guide/`. Do not commit. Render every
page and look at it; `qpdf --check`. Report to `/tmp/guide-v3-report.md`
(page count, what changed, anything uncertain) and reply with the path.
