# Plan: M7 — export the manuscript (branch `export`)

Status: approved by the author 2026-10-01 ("let's do the M7 export"). Same rules
as `docs/plan-workspace.md` ("Rules for every wave") — read them. Another agent
is building AI inspiration images in parallel on branch `inspiration`; keep your
edits to shared files (`gui/src/App.tsx`, `gui/api.py`, `tui/app.py`,
`tui/commands.py`, settings screens) small and self-contained so the two merge
cleanly. Put new code in new files.

## Tooling (verified on this machine)

No LaTeX, no typst, no weasyprint. Available: **ReportLab 5.0.1** (system
`python3` and pip-installable into the venvs — add `reportlab>=4` to a new
optional dependency group `export` in `pyproject.toml` and install it in
`.venv` and `.venv-gui`), **pandoc** (`/usr/bin/pandoc`), fonts
**Liberation Serif/Sans/Mono** and **Noto Serif** (TTF, `fc-list`). SPEC §7 M7
said LaTeX; record in SPEC that export uses ReportLab (PDF) and pandoc
(DOCX/EPUB) because no TeX is installed, and that a LaTeX source can still be
produced via pandoc (`.tex`) for authors who have TeX elsewhere.

## What gets exported (`core/export/manuscript.py`, pure)

`assemble(project, options) -> Book` — the manuscript in reading order:
title, author (`project.toml`), front matter part (if `include_front_matter`),
then parts (part titles as part pages) and their scenes. Excluded: Unplaced
Scenes, Trash, research, comments, notes. Per scene:
- frontmatter removed; the `# heading` is the scene/chapter title (the
  `[manuscript] unit` decides the word: "Chapter 3" vs "Scene 3", or titles
  only — option `numbering: "words" | "numbers" | "titles-only"`);
- `[[Name]]` / `[[Name|text]]` → their display text; plain mentions are
  just text already;
- **pending AI drafts:** default **exclude** (use the original text from the
  `.drafts` sidecar, like `strip_pending`); option to include them; the export
  dialog warns "3 scenes have unaccepted AI drafts" either way;
- `{{expand: …}}` markers: removed with a warning listing where they were;
- Markdown inline formatting (`*italic*`, `**bold**`, `` `code` `` → plain)
  and paragraphs/blank lines/scene-break lines (`***`, `---`, `* * *` inside a
  scene → a centred scene-break ornament) carried into a small intermediate
  model (paragraph runs with italic/bold), shared by all writers.
- Word count of the result is reported.

## Formats and layouts (`core/export/`)

1. **PDF — Book** (`pdf_book.py`, ReportLab platypus): title page, optional
   copyright/edition line, optional table of contents, part title pages,
   each scene (or chapter) starting on a new page (option: continuous with a
   scene-break ornament when unit = scene), drop-cap-free classic look:
   first paragraph of a chapter not indented, the rest indented, justified,
   running heads (book title / chapter title), page numbers, mirrored
   margins. Page sizes: Trade 6×9 in (default), A5, US Letter. Fonts: Noto
   Serif or Liberation Serif (embedded TTF; check italics/bold exist),
   11 pt / 14 pt leading by default.
2. **PDF — Manuscript review** (`pdf_manuscript.py`): standard manuscript
   format — US Letter, 1-inch margins, 12 pt Liberation Mono or Serif,
   **double-spaced**, **line numbers** in the left margin (per page),
   header "Author / TITLE / page", chapter starts a third down the page,
   `#` scene breaks, word count on the title page ("about 82,000 words").
3. **DOCX** and **EPUB** (`pandoc.py`): write the intermediate model to
   Markdown (with a YAML metadata block: title, author) and call pandoc
   (`subprocess`, timeout, no network); EPUB gets chapter splits per scene /
   part and the title page. If pandoc is missing, those formats are greyed
   out with "install pandoc".
4. **Markdown** (single combined `.md`) and **LaTeX source** (`.tex` via
   pandoc) as plain extras.

Template system: a layout is a small Python module or TOML under
`core/export/layouts/` exposing `name`, `description`, and a render
function; Book and Manuscript are the first two. A third simple layout
(**"Plain proof"**, A4, sans, 1.5 spacing) proves the mechanism.

Output: `<project>/exports/<slug>-<layout>-<YYYYMMDD-HHMM>.<ext>` (author's
folder, not git-ignored — mention in docs that it can be added to
`.gitignore`); never overwrite (suffix `-2`). Return path, pages (PDF), words,
warnings.

## UI

- GUI: **Export…** in the project menu and the binder "…" menu → a dialog in
  the design's style: format (PDF book / PDF manuscript / DOCX / EPUB /
  Markdown / LaTeX), layout options (page size, font, numbering, TOC,
  include front matter, include pending drafts), a live summary ("4 scenes,
  1,502 words, 2 parts; 1 scene has unaccepted AI drafts"), **Export**,
  progress, then "Saved to exports/…" with **Open file** / **Show folder**
  (via `xdg-open`, only on click). Export runs in a worker thread.
- TUI: palette `Action · Export manuscript` → small form (format, layout,
  page size, include drafts) → notify with the path; `Action · Open exports
  folder`.
- Settings: remember the last export options per project in `project.toml`
  `[export]`.

## Tests and verification

- Unit: assemble on `examples/residual` (copy) and on a structured temp
  project (parts, front matter, unplaced, trash, pending drafts with
  sidecar originals, expand markers, `[[links]]`, frontmatter, italics,
  scene breaks) — correct order, exclusions, warnings, text.
- Each writer produces a valid file: PDFs open and have the expected page
  count range and text (extract with `pdftotext`), DOCX/EPUB via pandoc
  produce non-empty files (skip with a clear reason if pandoc absent),
  `qpdf --check` clean.
- **Look at the output**: render a few pages of each PDF layout with
  `pdftoppm` and view them; fix typography issues (widows/orphans of
  headings, running heads, line numbers alignment, double spacing).
- GUI: headless screenshots of the dialog; API tests; TUI Pilot test of the
  palette form.
- Docs: SPEC M7 (implemented; formats; tooling decision), README, AGENTS.md.

Report to `/tmp/export-report.md` with Jev per commit.
