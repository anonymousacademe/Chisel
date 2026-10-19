# Plan: research mode usability, slice 2 (from the author's first trial, 2026-10-19)

Source: the author's notes after trying slice 1 (Zotero settings, sync, citations, source card). Ten requests, grouped
into six work packages. Nothing here is built yet. Companion docs: plan-research-mode.md (design),
research-mode-status.md (what exists).

## The ten requests

| # | Request | Where it lives today |
|---|---|---|
| 1 | Sync: tick several sources (or collections) to sync | `SyncReviewDialog.tsx` picks ONE collection (radio); `Scope` is one collection or one tag; the preview already has a per-paper tick list |
| 2 | A spinner / "working" message while previewing (and applying) | none: the dialog just waits |
| 3 | A citation in the text turns into a normal-looking citation: (Name et al., year) | `[[@key]]` shows as raw text with a dotted underline (slice 1) |
| 4 | Source notes formatted for reading: abstract, notes, metadata in separate readable sections | `core/sources.py` writes a CSL dump in frontmatter plus a "From Zotero" block; the GUI shows it raw |
| 5 | Delete a section, the rest renumber | `core/structure.py` renumbers only the destination "to keep file names stable"; gaps remain |
| 6 | Research mode says "sections", not "scenes" | the `unit` setting (scene or chapter) exists but only 13 places use it; about 20 GUI strings hard-code "scene" |
| 7 | An outline mode with an assistant that helps build or revise an outline | the Outline view lists sections; no assistant |
| 8 | Choose what kind of research product: manuscript, proposal or pre-proposal | not modelled |
| 9 | Upload guideline documents (author instructions, RFP) and have the assistant know them | not modelled |
| 10 | Once data arrives, the assistant checks whether Results and Discussion fit what the figures and tables show; Chisel must understand what those figures and tables mean | figures and tables exist as objects (captions, CSV, scripts) but no AI reads them and no screen inserts them yet |

Parked for later (the author's own suggestion): a summary tool for a source (an AI summary of its abstract, notes and
highlights, suggest-only; maybe better done on the Zotero side).

## Work packages

### W1 Sync dialog (requests 1, 2): small
- Collection picker becomes checkboxes with the existing filter box, plus "include subcollections" (default on) and
  "select all shown". Backend: `Scope` gains `collections: tuple[str, ...]`; `chain_fetch` fetches each and merges
  by item key (an item in two collections appears once); a plan records the scope.
- Per-paper list in the preview: select all / none, a search box, a count ("7 of 12 selected"). Unticked papers are
  never written (already true).
- Progress: a spinner and a plain sentence ("Reading Zotero... first read can take a minute") while previewing and
  while applying, a disabled button during the call, an elapsed-seconds counter after 5 s, and a Cancel for the
  preview (abandon the request; nothing was written yet).
- Files: `core/zotero/base.py` (Scope), `__init__.py` (chain_fetch), `gui/research_sources_api.py` (scope arg),
  `SyncReviewDialog.tsx`, tests. No schema change in saved notes.

### W2 Reading experience (requests 3, 4): medium
- **Inline citation display (3).** Python formats the text, TypeScript only shows it (GUI rule): each citation span
  gets a `display` string: parenthetical "(Daneshgar et al., 2024)", narrative "Daneshgar et al. (2024)", locator
  "(Daneshgar et al., 2024, p. 3)", several "(Wang et al., 2026; Zhang and Valeo, 2026a)", with a/b/c suffixes when
  two sources share author and year (the 'Agentic SWMM' case), and the key for an unresolved citation in the orange
  style. The editor replaces the raw `[[@key]]` with that text as a widget when the cursor is not inside it, and
  shows the raw text (editable) when the cursor enters it, like live-preview editors. The export still uses the
  CSL style; the on-screen form is an approximation of APA and says so in a tooltip. Files: `core/spans.py`
  (formatter, new `core/paper/citefmt.py`), `gui/src/editor/cm.ts` (replace decoration in the single StateField;
  widget `eq()` on the display string so typing does not rebuild it), tests incl. the spans-offset rule (UTF-16).
- **Readable source notes (4).** `core/sources.py` writes the Zotero block as proper Markdown: title, authors,
  venue/year/DOI/URL line with links, an "Abstract" section (cleaned text), "Notes" and "Highlights" sections
  (highlight quotes with page), then the author's "My notes". The CSL dump stays in frontmatter (it is the data the
  export reads) and the GUI hides entity frontmatter for source notes the way it already hides scene details
  (extend `frontmatterRange` use; a note's editable part is below it). A sync regenerates only the Zotero block
  (the byte-preservation rule is unchanged); existing source notes upgrade on the next sync, with the preview
  showing the "changed" rows.
- Also from the trial notes: rank first-author matches above co-author matches in `search_sources`.

### W3 Section wording and numbering (requests 5, 6): medium, one decision
- **Wording (6).** Research projects get `[manuscript] unit = "section"` at creation (the unit setting gains
  "section"); every hard-coded "scene" string in the GUI and the TUI is audited and routed through the existing
  `unit` (about 20 strings: menus, dialogs, kickers, toasts, empty states), plus the Python-side labels
  (`workspace.LABELS`, error messages that say scene). Story and script keep "scene". "Parked paragraphs" becomes
  "Parked sections". Tests lock story/script wording byte for byte.
- **Renumber on delete (5).** After a delete (and on restore) the remaining siblings are renumbered
  contiguously through the existing `Structure._apply_renames` (two-phase, carries drafts, comments and snapshots),
  and the bridge returns a `remap` so an open document follows, as `place_scene` already does. DECISION D1: all
  modes or research only (see below).

### W4 Research product type and guidelines (requests 8, 9): large
- **Type (8).** `[research] kind = "manuscript" | "proposal"`, chosen in the new-project
  dialog when mode is Research and changeable in a project settings dialog (the kind is a label that steers
  templates, checks and the assistant, so it can change, unlike the mode). The "Start here" note and a starter
  outline follow the kind (manuscript: Title/Abstract/Introduction/Methods/Results/Discussion/Conclusions/
  References; proposal: summary, background, objectives, approach, timeline, budget justification, broader
  impacts; pre-proposal: a short form of that), as editable starting sections, never forced.
- **Guidelines (9).** A "Guidelines" group in the binder (research projects). Add a document by file picker or
  drag-drop (.pdf, .docx, .md, .txt) or by pasting text or a URL as a note. Files are copied into
  `guidelines/` (plain files, the author's data); extracted text is a rebuildable cache in `.chisel/guidelines/`.
  Extraction: .md/.txt as is; .docx with the standard library (a zip of XML); .pdf with `pypdf` as an OPTIONAL
  dependency (`research` extra, pure Python), with a plain-words fallback ("paste the text instead") when it is
  absent or the PDF is scanned. DECISION D3 on the dependency.
- **Requirements checklist.** One AI call ("Read these guidelines and propose the requirements") returns a short
  structured list the author edits and confirms: page or word limits (whole and per section), required sections
  and their order, formatting (font, spacing, margins, citation style), submission items, deadlines. Saved in
  `project.toml` `[research.requirements]` and shown in a "Requirements" panel. Suggest-and-confirm like the alias
  finder: plan (budget) then call then per-row review then apply. The confirmed list feeds per-section word-limit
  tracking (the details dialog already has a word target), the research checks (a new warning kind, "section over
  its limit", "required section missing") and the assistant.
- **What the assistant sees.** Guidelines reach an AI only through the requirements call and the outline
  assistant (and an explicit attach in chat), as budget `Section`s with caps; every trim or skip lands in the
  "What was sent" report by name. Never sent automatically, never in a source note.

### W5 Outline assistant (request 7): medium, after W4
- An "Assist" button in the Outline view (research projects). The author states what they want ("build an outline",
  "tighten this outline", "check it against the requirements"); the call sends: product kind, the confirmed
  requirements, the guideline text (capped), the current outline (section titles, one-line purposes, word counts,
  status), and optionally the titles (never the text) of cited sources. Result: a proposed outline as a list of
  items, each one of: keep, add (title, purpose, suggested position, why), rename, move, merge or drop (advice
  only; nothing is deleted).
- Review dialog as everywhere else: per-item ticks, a before/after outline preview, "Apply N changes". Apply
  creates new sections (new files), renames and moves through the existing structure functions after a snapshot of
  the affected sections; drop/merge stay advice. Stop button and the AI job mechanism as for other AI calls
  (`ai_start`), mockable (`ai/outline.py` `suggest_outline`, `gui/mockai.py`, signature test).
- Starter-outline templates by kind (W4) are the offline fallback when no AI is configured.

### W6 Data-aware review of Results and Discussion (request 10): large, after W4 and the figure/table screens
Prerequisite the author may not have noticed: the screens to insert and edit figures and tables (P8b in the original
plan) are not built, so today a paper cannot get data into the editor. They come first (W0 below).
- **What a figure or table means (the reading).** Every figure and table gets a "Reading": a short plain-language
  statement of what it shows (variables, units, the comparison, the headline result), stored in the object's own
  note body under a "Reading" heading, never in the prose. Chisel proposes it; the author edits and confirms
  (suggest-and-confirm, same shape as the alias finder). Inputs to the proposal, built locally in Python wherever
  possible so little is sent: the caption; the author's notes on the object; for a table, its cells (capped, with
  column names and units); for a generated figure, its provenance (script name, data files) plus a local
  data summary (columns, ranges, counts, simple statistics, computed by Chisel and not by AI); for a static
  image, a vision-capable model only if the author ticks "let the model look at the picture" (DECISION D6; images
  are otherwise never sent, as for inspiration pictures).
- **The consistency check.** "Check Results and Discussion against the data": the model gets the Results and
  Discussion text (accepted text only, pending AI drafts stripped as always), every confirmed Reading with its
  number (Figure 2, Table 1), the guideline requirements if any, and returns flags, each with a quote and its
  position: a claim the data do not support or only partly support; a number in the text that differs from the
  table; a trend described the wrong way round; a figure or table never discussed; a conclusion in the Discussion
  with no result behind it; a result never interpreted. Read-only report like the continuity check: dismiss or
  waive each flag, never an automatic edit.
- **Awareness elsewhere.** The same Readings feed the outline assistant (W5: "your Results has two tables but the
  outline discusses one"), the research checks (an object without a Reading is a warning), and an optional
  "About:" attach in chat so the author can ask "does Figure 2 support what I say in 4.3?".
- **Privacy and cost.** Data reaches an AI only in these explicit calls, capped, listed by name in "What was
  sent" (columns, row counts, trimmed rows); large CSVs are summarised locally first; a table can be marked
  "do not send" for unpublished or sensitive data (DECISION D7 on whether that is the default for tables built
  from CSV).
- Files (indicative): `core/paper/reading.py` (local data summaries, Reading storage), `ai/data_review.py`
  (`suggest_reading`, `check_results`), a bridge mixin, a review dialog; mocked at the function boundary.

### W0 Figure and table screens (prerequisite for W6)
The original P8b: insert a figure (file picker or drag-drop) or table (grid editor) or equation, see them in the
editor, numbered and cross-referenced. This is the largest remaining UI item and the riskiest CodeMirror work in
the plan; it has its own sub-plan in plan-research-mode.md section 7.3.

## Order and sizing

| Wave | Packages | Size (relative to the last two waves, about 260k to 450k tokens each) | Notes |
|---|---|---|---|
| A | W1, W3 wording, W2 formatter | one wave | independent files; W3 touches many GUI strings, so run it alone on the GUI files or last |
| B | W2 widget and source-note format, W3 renumber | one wave | W2 widget is the risky CodeMirror change (Opus review of the StateField edit, as the plan says) |
| C | W4 | one to two waves | model + files + extraction + requirements call + panel |
| D | W5 | one wave | needs W4 |
| E | W0 | one to two waves | the figure/table/equation editor screens; Opus review of the editor change |
| F | W6 | one to two waves | needs W0 and W4; data-aware review of Results and Discussion |

Each wave: small Sonnet agents in worktrees started from the pushed commit (with the explicit fast-forward step),
one full-suite run on a clean checkout, then push. I stop after each wave for the author's trial.

## Decisions taken (author, 2026-10-19)

- **Renumber on delete: all modes.**
- **Sync:** a tick list of COLLECTIONS (no new per-paper features beyond the existing preview ticks). The ticked
  collections are remembered per project (`[research] zotero_collections` in `project.toml`, key names only), so
  reopening the dialog preselects them and a "Sync again" preview picks up papers added to those collections since:
  they appear as "new" rows. A paper that left a collection is never marked missing or removed.
- **Product kinds: manuscript and proposal only** (no pre-proposal, no "other", for now).
- **Outline assistant input:** a paragraph the author writes describing the scope of the paper or proposal (kept in
  the project as the "Scope" statement, editable), plus the guideline documents if any. With no guidelines it uses
  a standard structure for the kind (manuscript: IMRaD-style; proposal: the usual funder sections). Output is a
  proposed outline the author reviews and applies per item.
- **Pictures and data to AI:** excluded by default; the author ticks a figure or table ("let the assistant use
  this") and only then does a model see it (a picture through a vision-capable model). A visible badge shows which
  objects are shared. Tables built from the author's own CSV follow the same rule.
- **Guideline PDFs:** optional `pypdf` extra with a plain-words fallback, as recommended (wave C).

## Original questions (answered above)

- **D1 Renumber on delete:** all modes (my recommendation: a gap serves nobody, and the machinery already carries
  drafts, comments and snapshots), or research projects only (leaves fiction projects exactly as they are).
- **D2 Sync "multiple sources":** I read it as multiple collections plus a tick list of papers (W1 does both). Say
  if you meant something else, such as pasting a list of keys or DOIs.
- **D3 PDF guidelines:** add `pypdf` as an optional dependency (works for text PDFs, not scans), or accept only
  Word, Markdown, text and pasted text at first.
- **D4 Product kinds:** manuscript, proposal, pre-proposal, other: is that the right list, or also thesis,
  report, conference paper?
- **D5 Outline apply:** may the assistant's accepted items rename and move existing sections (with a snapshot
  first), or only add new sections and leave reordering to you?

- **D6 Pictures to AI:** may the assistant ever look at a static figure image (a vision model, only when you tick it
  for that figure), or should it read only captions, your notes, tables and data summaries?
- **D7 Data privacy default:** should tables and data built from your own CSV be excluded from AI unless you tick
  them (my recommendation, since unpublished results are the most sensitive thing in the project), or included
  once you start a data-aware check?

## Risks

- Inline citation widgets are the most fragile part of the editor so far (CodeMirror decorations, hard-wrapped
  lines, cursor behaviour): measure that typing in a long section does not rebuild widget DOM, and keep the raw
  text one keystroke away.
- Guideline text can be long and PDFs messy: caps, a visible "what was read" preview, and the plain-words
  fallback keep it honest.
- The AI proposes requirements from prose: it can be wrong, so nothing is enforced until the author confirms the
  list, and checks say "from your confirmed requirements".
- Telling the model what the data mean is only as good as the Reading the author confirms; the check reports
  against the confirmed Readings and says so, and never claims a result is "right", only "consistent or not with
  what you described".
- Token use: five waves at the previous size would be a lot. Waves A and B are the visible-polish ones; C and D
  can wait for your go.
