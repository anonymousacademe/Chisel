# Research mode: status (2026-10-18, end of the overnight run)

Supersedes the build-state tables in research-mode-handoff.md (which is from 2026-10-15). The plan, contracts and work
packages are unchanged except where noted below.

## Built, merged and pushed (`main`)
- Project mode chosen when a project is created (Story, Research, and Script from the other session); no later switch.
  Research projects relabel the binder (Sections, Sources, Concepts and methods, Parked paragraphs) and hide POV, place,
  story time and relationships. Pickers: desktop launch screen and the terminal new-project prompt.
- P1 citations (`core/links.py` find_citations), source note kinds, case-sensitive citations index, AI exclusion of sources.
- P2 Zotero client (`core/zotero/`): web, local, Better BibTeX file, cache; note-HTML sanitiser. Read-only.
- P3 source notes and review-then-apply sync (`core/sources.py`), hardened after review (CRLF and BOM notes, per-row failures,
  duplicate keys, digest re-check before write).
- P4 objects, pipe tables, numbering, Trash kind `object`; P4b figure scripts (hash-bound trust in the per-user state folder,
  isolated run) and tables from CSV; hardened after review (no symlink temp writes, absolute interpreter, bounded reads).
- P4c AI proposals for LaTeX and plot code; P5 export to docx/tex/pdf via pandoc with CSL; P6 research checks.
- P7 bridge: 28 methods (`gui/research_sources_api.py`, `gui/research_objects_api.py`, wired in `gui/research_api.py`).
- Packaging entries and a selftest check for the research data files; `.gitattributes`.
- Full suite on a clean checkout: 1502 passed, 26 skipped.

## Not built
- Screens: P8a (Sources panel, sync review, Zotero settings) and P8b (figures, tables, equations in the editor), P9 terminal
  minimum, P10 docs and the CHANGELOG/SPEC entries. Nothing research-specific is visible in the app beyond the picker, labels
  and hidden fields.
- P7 follow-ups that touch files the Script-mode session was editing: span emission (citation, reference, placement, inline
  math) in `core/spans.py`/`gui/api.py`; TypeScript wrappers for the 28 methods in `gui/src/backend/api.ts`; `import
  suggest_latex, suggest_plot_code` in `gui/api.py` plus their entries in `gui/mockai.py` and the mocked-name tuples in
  `tests/test_gui_shell.py`; `AI_JOBS` entries so the two AI methods run as stoppable jobs; `_doc_kind` / `resolve_document`
  refusing `.py` unless kind `code`; `strip_math` callers in spell check, word count and mention scanning.

## Not verified (needs real tools or the author)
- PDF export never produced; Word export tested with pandoc 2.12 only. pandoc 3.9 and MiKTeX are not on this machine.
- Zotero never contacted: needs the author's Zotero version, API key (kept in the keyring, never in settings) and library.
- Figure scripts: one real matplotlib run succeeded (starter template, valid PNG). Symlink refusal tests skip on this Windows
  box (cannot create symlinks); run them on Linux/macOS CI.
- The mode picker and labels have not been tried by the author in the running app (build with `npm run build` in `gui/`).

## Decisions the author still owes
Zotero version and API key; a funder Word template or format spec; which Python runs figure scripts; whether attached or
"About:" source notes reach AI in version 1 (today they do when attached, as the plan allows); whether to cut figure scripts
and the table editor from the first release (the Product seat's recommendation).

## Process notes
- Another session (Script mode) edits the same working tree. Commit specific files, never `git add -A`.
- Worktree agents start from the last pushed commit: push first, and tell each agent to `git merge --ff-only <commit>`.
- Leftover worktrees under `.claude/worktrees/` (all merged) can be removed with `git worktree remove`.
- The leadership-meeting memos are in the Windows temp folder `chisel-meeting\reports\` (not in the repo).

## Update 2026-10-19 (usability slice 2, waves A and B)

Built, reviewed by Opus (every branch) and merged; 1815 Python tests and 269 front-end tests pass on a clean checkout.
Plan: docs/dev/plan-research-usability-2.md (with the author's decisions).
- Sync: tick several collections (remembered in project.toml [research] zotero_collections; sync again picks up new
  papers), spinner/elapsed/Cancel, select all/none and search over papers; a stale preview cannot be applied.
- Citations: Python formats "(Name et al., year)" (core/paper/citefmt.py, APA-like, a/b letters when needed);
  the editor shows that text in place of [[@key]] and reveals the raw text when the cursor touches it.
- Source notes: readable block (title, authors, venue/year/DOI, Abstract, Notes, Highlights); the editor hides the
  frontmatter and the begin marker (protected from edits) and shows the other sync markers dimmed. Existing notes
  upgrade on the next sync ("reformatted" rows).
- Research projects say "sections" (unit setting by mode); renumbering after a delete in ALL modes (parts keep front
  matter first).

Known open items (none block use):
- Terminal app: footer shortcut labels ("New/Prev/Next scene") and the AI status-bar label still say scene in research
  projects; several newly routed terminal strings lack real-path tests.
- html_to_markdown still drops characters inside text it treats as HTML (e.g. "<p>if a<b and c>d</p>").
- Sync dialog: the remembered selection is saved from the preview-time ticks; if the ticks change between Preview and
  Apply the saved selection can differ from what the dialog shows until reopened. An inline comment on the
  zotero_collections line is dropped when it is rewritten.
- Citation widget and source-note hiding have not been seen in a running window (CSS look, dark mode contrast of the
  dimmed markers, cursor feel around the top of a source note).
- Flaky under load: tests/test_sync_tui.py (passes alone).
- Leftover worktrees under .claude/worktrees (merged) and %TEMP%\chisel-clean5 can be deleted.

Not started (waiting on the author): wave C (research kind manuscript/proposal, guideline documents and the confirmed
requirements checklist, optional pypdf extra), wave D (outline assistant from a scope paragraph), wave E (figure and
table screens, P8b), wave F (data-aware review of Results and Discussion; pictures and data excluded from AI unless
the author ticks them).

## Update 2026-10-19 (wave C: paper kind, journal profiles, guidelines)

Merged and pushed (full suite 1881 passed before the last two test-only edits; 285 front-end tests):
- Project kind (manuscript or proposal) and target journal, chosen when a research project is created and editable in
  Project settings. Profiles are data in src/chisel/core/paper/journals/*.toml (ems.toml, manuscript.toml,
  proposal.toml), restated in our own words from the journal's Guide for Authors (read 2026-10-19); the guide's text is
  not in the repository.
- Starting from a profile creates its starter outline (front matter part + article sections + declarations) as editable
  sections; the "Start here" note is parked.
- Journal requirements: Python evaluates the profile's checks (abstract length, keyword and highlight counts and
  lengths, required sections present and non-empty, figure and table captions and citations, citations resolve, DOIs,
  AI-use declaration when AI words were accepted); advice items are reminders. Empty sections never read as ok.
  Nothing here blocks export.
- Guidelines: guidelines/ folder (plain files), text from md/txt/docx (stdlib) and PDF (optional pypdf >= 6), cached
  under .chisel/guidelines; never sent to an AI by any current feature (tested).
- Citation style option: "harvard" writes "and" (EMS), "apa" writes "&".
- Dialogs: new-project kind/journal, Project settings, Journal requirements, Guidelines (project menu, research only).

Open items: the requirements checks do not yet read numbering schemes or equation numbering; "graphical abstract" and
file-format rules are reminders only; the outline assistant (wave D), the guideline-aware requirements extraction by AI
and the figure/table screens (wave E) are not built.
