# Brief: Lorewrite User's Guide (PDF, classic IBM-manual style)

Produce `docs/user-guide/lorewrite-users-guide.pdf` from a reproducible build
script `docs/user-guide/build_guide.py`. Use the system `python3` (ReportLab
5.0.1 is installed there; the project venv does not have it). pandoc,
rsvg-convert, pdftoppm and qpdf are available; there is no LaTeX.

## Scope and accuracy

- Document Lorewrite **as it exists on `main` in `~/lorewrite`** (HEAD
  366a825, version 0.2.0). Sources of truth: the code first
  (`src/lorewrite/tui/app.py` BINDINGS + HELP_TEXT, `tour.py`, `commands.py`,
  `settingscreen.py`, `launch.py`, `core/*.py`, `ai/*.py`), then `README.md`
  and `SPEC.md`. Every key binding, palette label, file name and message you
  print must match the code exactly. When the docs and the code disagree, the
  code wins.
- Do NOT document features that are only planned (`docs/plan-m4-ai-writing.md`
  is in progress on another branch). Note in particular: on `main`, `ctrl+l`
  "Link mentions" still inserts `[[brackets]]` when suggestions are accepted —
  describe it as it behaves today.
- Audience: fiction writers, not programmers. Explain concepts plainly;
  keep installation/developer detail in its own chapter/appendix.

## Look and feel: a 1970s–80s IBM user manual (homage, not imitation)

- US Letter, generous margins, single column body in a serif (Times-Roman) or
  Helvetica; headings in Helvetica-Bold; thin horizontal rules under chapter
  titles; running header (book title on one side, chapter title on the other)
  and footer page numbers in **chapter-page** form (`3-4`), with front matter
  in roman numerals.
- Front matter: cover ("Lorewrite / User's Guide and Reference / Version 0.2"),
  a fictional document number (e.g. `LW00-0001-0`), edition notice
  ("First Edition (September 2026) — This edition applies to Version 0.2.0 of
  Lorewrite…"), Contents, "About This Book" (who should read it, how it is
  organized, typographic conventions), "Summary of Changes".
- Conventions typical of the genre: **Note:** / **Attention:** callouts,
  numbered procedure steps, figures captioned `Figure 3-1. The main window`,
  tables captioned `Table 7-1. Editor keys`, at least one **syntax
  (railroad) diagram** for the command line
  (`lorewrite [--project PATH | --new TITLE]` — check the real argparse in
  `app.py::main`), a Glossary, and a back-of-book **Index** with page
  references (two-pass build is fine).
- Figures: real screens of the app. Capture them headlessly with Textual Pilot
  (`app.run_test(size=(100, 32))`, `app.save_screenshot(...)` → SVG →
  `rsvg-convert` PNG → convert to grayscale for the period look) and embed
  them in ruled boxes. Use a *copy* of the demo project
  (`cp -r ~/lorewrite-demo "$TMP"/demo`) and a temp
  `LOREWRITE_STATE_DIR` with `{"tour_seen": true}` so you never modify the
  demo or the user's real settings. Never make real AI/network calls; for AI
  screens, monkeypatch the AI functions (see `tests/test_ai_links.py`,
  `tests/test_continuity_ui.py`) with plausible canned results based on the
  demo story (e.g. the planted contradictions: Sallow's eyes grey vs green in
  scene 2; Kuroda's chrome arm left vs right in scene 3).
- **Do not use the IBM name, logo, trademarks, or real IBM form numbers.** No
  emojis. Style only.

## Suggested contents

1. Introducing Lorewrite — projects, scenes, entities (characters, places,
   objects, factions), plain-name mentions and aliases, `[[links]]`,
   backlinks, the index as a rebuildable cache, "AI suggests, never edits".
2. Installing and Starting — install, launch screen, recent projects,
   `--project` / `--new`, first-run tour, Omarchy theme + top-bar launcher.
3. Writing Scenes — editor, autosave/`ctrl+s`, status bar fields, writer mode,
   scene navigation, new/rename/reorder/delete scenes, sidebar filter.
4. Characters, Places and Mentions — making a note (select a name + `ctrl+j`),
   aliases, how matching works (whole words, case rules, longest match),
   faded brackets, orange = no note, entity panel, backlinks, `f9` rebuild.
5. AI Assistance — API key (paste with `ctrl+v`), models and the Choose…
   picker, Link mentions (`ctrl+l`) and alias learning, continuity check
   (report, waive with `space`, jump with `enter`), Update story bible and the
   `## Canon (auto)` section; costs/privacy notes.
6. Settings Reference.
7. Command and Key Reference — every binding and palette action, in tables.
- Appendix A: File Formats (project layout, `project.toml` keys incl. `[ai]`
  and `[editor]`, scene files, entity notes + frontmatter, Canon section,
  `.lorewrite/` cache and `waivers.json`).
- Appendix B: Messages and Problem Solving (the real notify texts from the
  code, e.g. keyring unavailable, model list failed to load, no API key).
- Appendix C: Tutorial — walk through the "Residual" demo project.
- Glossary; Index.

## Process and constraints

- Write only inside `docs/user-guide/` (build script, intermediate assets
  under `docs/user-guide/build/`, final PDF). Touch nothing else in the repo;
  do not touch `~/lorewrite-m4` (another agent works there). Do not commit.
- Verify visually: render pages with `pdftoppm -r 50 -png` and look at every
  page image; fix overflow, orphaned headings, broken tables, bad figure
  scaling, wrong page references. Check the PDF opens with `qpdf --check`.
- Finish with a short report: output path, page count, chapter list, any
  place where you were unsure how the app behaves.
