# Plan: Research mode (Zotero sources, figures, equations, Word and LaTeX output)

Status: draft 3, revised after two independent reviews against the code (see "Review changes" at the end).
Nothing here is built. The implementation split across agents is in
[plan-research-mode-work-packages.md](plan-research-mode-work-packages.md); the interface contracts that
let those packages run in parallel are in [research-mode-contracts.md](research-mode-contracts.md).

Items marked **VERIFY** are not yet confirmed against current documentation or the author's library.
Items marked **Verified** were checked on 2026-10-14 (Zotero schema and docs, pandoc 3.9.0.2 and MiKTeX on
the author's machine).

## 1. Goal

Make Chisel usable for research writing (papers, proposals, theses) without giving up its principles:
a project is a folder of plain Markdown, AI only suggests, nothing leaves the machine unless the author
triggers it. Research mode adds:

1. A connection to the author's Zotero library, so sources are articles the author actually has.
2. Source notes (the research analogue of a character card) holding Zotero notes, highlights and the
   author's own notes.
3. Figures, tables and equations with captions and cross-references, **shown as they will look (WYSIWYG)
   in the desktop editor**.
4. Two outputs: a Word document that follows a required format, and a LaTeX PDF.

Non-goals for the first version: writing back to Zotero, live Word fields, exact page counts, reading full
text from PDFs, replacing Zotero's own reference management, SVG/PDF figure files, Claims, section templates
beyond a starter IMRaD.

## 2. Principles kept (SPEC section 2 / AGENTS.md)

- Plain text always. Sources, figures, tables and equations are files in the project.
- The index is a rebuildable cache. Source notes are the offline cache of the Zotero library.
- AI suggests, never edits. An AI-made equation is a pending proposal. The first version has **no**
  AI-suggested citations (cut: it had no defined feature).
- **Nothing from Zotero reaches an AI unless the author attaches it** (see 5.3: this needs code, because
  today every entity is sent as canon), and the "What was sent" line shows it.
- Network is explicit. Sync runs only on a click; nothing contacts Zotero in the background.

## 3. Project mode

`project.toml`:

```toml
[project]
mode = "research"        # "fiction" (default) or "research"

[research]
citation_style = "apa"           # a bundled CSL name or a path to a .csl file
word_template = "templates/proposal.docx"
```

The mode is a **thin gate built first** (labels, binder groups, which checks and exports exist), polished
last, so every later step has somewhere to appear. It does not change the file format; a project can switch
back. Fiction-only features (POV, story time, relationships) are hidden in research mode, not deleted.

### Binder in research mode

| Fiction | Research |
|---|---|
| Manuscript (parts, scenes) | Sections (parts, sections) |
| Characters | Sources |
| Places | Concepts / Methods / Datasets |
| (none) | Figures, Tables, Equations |
| Notebook | Notebook (unchanged) |
| Parked scenes | Parked paragraphs |
| Trash | Trash (unchanged) |

The scene inspector's POV, place and story time give way to: status (outline, draft, revising, final), word
limit, and target. Section templates and Claims are deferred.

## 4. Zotero connection

### 4.1 Backends

One `ZoteroSource` interface, four implementations. **One order for `chain_fetch`: web, local, file,
cache** (the build order differs: the file backend is built first, but it sits third in the fall-through
chain). Fall-through never mixes version state across backends: a result carries the backend that produced
it, and sync state is kept per backend.

0. **Better BibTeX auto-export file** (CSL JSON or BibTeX that the author points Chisel at). Offline, needs
   no key and no running Zotero, and carries the author's real keys. This is the first backend built, so
   citations and export work before any network code exists.
1. **Web API** (`api.zotero.org`). Needs an API key (read access), kept in the keyring only. The user ID is
   read from `GET /keys/current`, so the author does not type it.
2. **Local API** (`http://localhost:23119/api/`, requires "Allow other applications on this computer to
   communicate with Zotero"). **Verified (Zotero docs, but stated for Zotero 10 and later, so gate on the
   running version):** read-only unless a local key is granted; object and library versions have no relation
   to the web API's; results are not paginated by default; every response carries `Zotero-Server-ID`; the
   user in the path is 0 or your numeric user ID (others give 400). **VERIFY:** annotation routes,
   `/deleted`, and `include=csljson` on the local API (not documented).
3. **Cache**: the source notes already in the project. If nothing else answers, citations and export still
   work from cached data.

Failure of one backend falls through to the next and is reported in plain words.

### 4.2 Citation keys

**Verified:** the Zotero schema has a native `citationKey` field (CSL `citation-key`); on Zotero 8 Better
BibTeX uses it, always pins keys, and keys sync. Zotero 7 is no longer supported by Better BibTeX.

- Read `data.citationKey`. Only for older libraries, fall back to `Citation Key:` in the Extra field.
- **Chisel does not generate keys by default** (a generated key will differ from the one Better BibTeX
  assigns later). An item with no key is listed as "no citation key"; the author fixes it in Zotero.
  Generating a key is an explicit opt-in per item, marked `key_source: generated`.
- Keys are **case-sensitive** and may contain characters unsafe in file names. A key, once stored, is stable:
  sync never renames it silently. A key change is shown and resolved by the author (see 6.4).

### 4.3 Sync

- Manual only: *Action: Sync sources from Zotero*, optionally limited to a collection or tag.
- Pull only. Chisel never writes to Zotero in the first version.
- Dry run first: new, changed, missing and key-mismatch rows; the author ticks what to apply (the shape
  rename and canon updates already use). Apply refuses files changed since the preview.
- Web protocol: `If-Modified-Since-Version` (304 means nothing changed), `since=`, `format=versions`, fetch by
  key at most 50 per request (`limit` at most 100), `/deleted?since=` for removals, restart if the library
  version changes mid-run. **Verified rule:** honour a `Backoff: <seconds>` header on **any** response (not
  only 429), and wait at least `Retry-After` on a 429.
- **Sync state is per backend**, in the per-user state folder, never in the project: web as `users/<id>`,
  local per `Zotero-Server-ID`. A note stores `web_version` only (meaningless for the local backend).
- Removed from Zotero does not delete the note; it is marked `zotero_status: missing` and kept.

## 5. Source notes

### 5.1 Kind, folder and name

- Sources are a new entity kind, `source`, added to `VALID_TYPES`, `project.TYPE_SUBDIRS` and the GUI type
  list, so they are read back as sources (today any unknown type becomes `character`). Concepts, Methods and
  Datasets are added the same way.
- They live in **`entities/sources/`** (the entity listing globs `entities/*/*.md`; a root `sources/` folder
  would never be listed, indexed or opened).
- File name is `slugify(key)` plus a collision suffix, **not** the display name: two different "Smith 2024"
  papers must not merge into one note, and `Smith2024` and `smith2024` are one file on Windows. The real key
  lives only in frontmatter. `name` is the key (or a disambiguated "Smith 2024a").
- `Project.entity_path` and `create_entity` today derive the file from `slugify(entity.name)` and return
  an existing note on a name match; both get a source branch that uses the key-based rule above, and the
  rename paths use it too. **"Rename everywhere" is disabled for sources**: a key changes only through 6.4.
- Aliases ("Smith and Lee") remain plain mentions; the "never cited" check counts explicit citations only.

### 5.2 Content

```markdown
---
name: smith2024
type: source
key: smith2024
key_source: zotero              # zotero | extra | file | generated
zotero_status: current          # current | missing
web_version: 4821
csl: { ...the item's full CSL JSON, verbatim... }
title: "..."                    # derived display fields
authors: ["Smith, Jane", "Lee, Wei"]
year: 2024
aliases: ["Smith et al. 2024"]
---

<!-- zotero:begin -->
## From Zotero
### Notes
...
### Highlights
- p. 4: "quoted text" (comment)
<!-- zotero:end -->

## My notes
Free text. Sync never touches anything outside the zotero markers.
```

- The **full CSL JSON is stored verbatim** under `csl:` (the entity round trip already keeps unknown keys).
  The bibliography is generated from it, because APA and similar styles need item type, volume, issue, pages,
  publisher, editors, URL, accessed date and given/family names. `title`, `authors`, `year` are derived.
- Sync regenerates only the text between the markers. Highlights keep page, comment and the Zotero
  annotation ID so a re-sync updates rather than duplicates.
- **Notes and highlights:** Zotero notes are HTML. A sanitising HTML-to-Markdown step converts them and
  **escapes `[[` and `<!-- zotero:`** so pulled text can neither create links nor break the markers.
  Annotations are child items of PDF attachments (`annotationText`, `annotationComment`,
  `annotationPageLabel`): one extra request per attachment.

### 5.3 Never sent to an AI by default

Today `self.entities` feeds the canon into every scene context (draft, expand, chat, Brainstorm), the
continuity check, canon updates, the alias finder and `relevance.rank`. Source notes would therefore be
sent on every AI call. Required change:

- Source-kind entities are excluded from `canon_map`, relevance ranking and the alias finder, unless
  attached by the author or the open "About:" subject.
- A test asserts that no source text appears in any `build_context_sections` output.

## 6. Citations in the manuscript

### 6.1 Syntax

The existing link parser reads `[[smith2024; lee2023]]` and `[[smith2024, p. 12]]` as one unknown target
(and `|` already means display text), the index would store that folded target, and key matching is
case-insensitive. So citations get their own form:

- `[[@smith2024]]`, with pandoc semantics inside: `[[see @smith2024, p. 12; @lee2023]]` and
  `[[-@smith2024]]` (suppress author).
- **Narrative citations ("Smith (2024)") use a leading `+`: `[[+@smith2024]]`.** (Decided; the earlier
  `|n` spelling collided with the existing `|display text` meaning. APA needs the narrative form.)
- Plain pandoc `[@key]` is also accepted and rendered the same.
- **The existing link parser must ignore these.** `find_links` / `find_all_links` skip any target that
  starts with `@`, `-@` or `+@`, contains ` @`, or starts with `fig:`, `tbl:` or `eq:`; `find_citations` and
  `find_refs` own them. The `!` of a placement line (`![[...]]`) is outside the link match and is handled by
  `find_placements`. Without this, citations and object references would be shown as unresolved links,
  indexed as folded targets, offered for "create note", and touched by rename and backlinks.
- A new `links.find_citations(text) -> list[Citation]` is the single parser, used by the index, the TUI
  highlighter and the Python span computation (`link_spans` / `compute_spans` also emit citation,
  reference, placement and inline-math spans). The GUI never parses citations in TypeScript. Offsets are
  code points; UTF-16 only at the bridge.
- `resolve_key` is case-sensitive and matches only source keys; it never competes with entity names (a
  Concept called "kalman2020" cannot shadow a key).
- **Index:** a separate case-sensitive `citations(source, key)` table (the existing `links` table folds
  case). The index schema has no version, so switching a project's mode must trigger a rebuild.

### 6.2 Checks (read-only report, like the continuity check)

Citation with no source note; source never cited; source marked `missing`; duplicate key; reference to a
missing figure, table or equation; object never referenced; duplicate label; missing image file.
Export is **blocked** by unresolved citations or references unless the author overrides.

### 6.3 Bibliography

Built at export time from cited sources only, in the chosen CSL style, by pandoc citeproc from CSL JSON
generated from the stored `csl:` data (so it works offline). A few `.csl` files are bundled (CC BY-SA;
add to `packaging/chisel.spec` and `selftest.py`); without one, citeproc falls back to Chicago author-date.

### 6.4 Changing a key

Rename-everywhere gains a mode that rewrites `@old` inside multi-citations (today it rewrites names and
aliases only), with the same preview, snapshot and undo rules.

## 7. Figures, tables and equations

### 7.1 Files

```
figures/fig-flow-model.md       # YAML: caption, file, width, alt; body = notes
figures/fig-flow-model.png      # PNG or JPG only in version 1; 10 MB cap; kind decided from the bytes
tables/tbl-results.md           # YAML: caption; body = a Markdown pipe table
tables/tbl-results.csv          # optional source data
equations/eq-mass-balance.md    # YAML: caption (optional); body = LaTeX
```

- **`data/`** holds CSV and other input files for generated figures and tables (7.4). It is project content:
  rename and move handling (`remap`) and the Trash cover it, and every `data:` path in frontmatter must
  stay inside the project (paths with `..` or absolute paths are refused).
- **`.py` and `.csv` files are not documents today** (`Api.resolve_document` refuses anything but `.md`, and
  saving through the scene path would run link spans, spell check, word counts and indexing on them). A new
  document kind `code` (no spans, spelling, reflow, title block or index) opens scripts in the editor; CSV
  data is edited in the table panel or the system editor (`desktop.open_path`).
- **The label is the file-name stem** (`fig-flow-model.md` is `fig:flow-model`). It is not also stored in
  YAML, so there is one source of truth; a rename is a file rename plus a reference rewrite.
- Separate from `inspiration/`, which is reference only and never exported or sent to an AI. Figures are
  manuscript content. The two folders and their rules must not be mixed.
- The app must know these: they get document kinds (they open in the GUI), are indexed for backlinks, and
  the Trash gains a fourth kind, `object`, which every Trash code path must handle.

### 7.2 Placement and references

- **Placement** is a block line alone in the text: `![[fig:flow-model]]`, `![[tbl:results]]`,
  `![[eq:mass-balance]]`. This is what puts the object in the document; a reference alone does not.
- **Reference** in prose: `[[fig:flow-model]]`, `[[tbl:results]]`, `[[eq:mass-balance]]`.
- A project-wide **numbering service** (Python, called through the bridge) assigns numbers in reading order
  and recomputes when sections are reordered. Numbers are never stored in files.
- Numbering schemes: plain (1, 2, 3), per-section (2.1) for theses, and supplementary (S1) for papers. A
  number is therefore a display string (`Num(seq, display)`), not an integer.
- References render as "Figure 2", "Table 1", "Eq. (3)"; captions render with the number.
- Inline math `$...$` in prose works in the editor and in export (see 8). Spell check, word counts and
  mention scans must skip math (a `strip_math` helper, used like `scenemeta.strip`, wired into `spelling`,
  `drafts.count_words` and `find_mentions`).
- **Math handling is research-mode only** and follows pandoc's `tex_math_dollars` rule (no space after the
  opening `$`, none before the closing `$`, no digit directly after it), so "$5 and $10" in a fiction
  project, or in research prose, is not math. A test asserts fiction spans, counts and spelling are unchanged.

### 7.3 WYSIWYG in the desktop editor

Decision (wave F fix round): a block placement is NOT atomic. The cursor touching the line reveals the raw line with the rendered block above it, and Backspace edits the text like any line (no confirm). Images load lazily (object_render with images=false, then object_image per placed figure, cached by key and mtime).

Figures, tables and equations are shown as they will look, not as source text. This follows the editor's
existing approach (one CodeMirror `StateField` holds block widgets; Python computes spans, TypeScript only
draws).

- **Figure:** a placement line renders as the image at its set width, with the numbered caption beneath
  ("Figure 2. ..."). The image comes through `object_image(label)`, which serves only
  `figures/<stem>.{png,jpg}` resolved through one `_figure_file` door (plain stem, no symlinks, inside
  `figures/`), cached client-side by mtime. (A downscaled preview needs an image library the app does not
  have, so version 1 serves the file as is, within the 10 MB cap; a thumbnail is a later optimisation.)
  Click opens the figure panel (replace image, edit caption, width, alt text, notes). A missing image shows
  a clear placeholder.
- **Table:** a placement line renders as a real table with the numbered caption above it. A **panel or
  modal grid editor** (not live inputs inside the widget: writing back rebuilds the widget and would lose
  focus) lets the author type in cells, add and remove rows and columns, paste a spreadsheet selection
  (TSV, parsed client-side) and import CSV. **All parsing and serialising is in Python** (`core/tables.py`:
  `parse_pipe(text) -> Table(cells, align)`, `to_pipe(table)` in a canonical form: escaped `\|`, no newlines
  in cells, deterministic dash counts, because pandoc derives column widths from them once a line exceeds
  `--columns`). The bridge is `read_table(id)` and `save_table(id, cells, align, base_mtime)`. Byte-exact
  round trip is guaranteed for canonical tables; a hand-written table is normalised on its first grid save,
  after a one-line notice.
- **Equation:** a placement line renders as typeset math (KaTeX) with its number at the right. Click opens a
  LaTeX box with live preview, a symbol and template palette, and the optional AI "describe it, get LaTeX"
  step, shown as a pending proposal and listed in "What was sent". Inline `$...$` renders as typeset math in
  place and shows its source when the cursor enters it. KaTeX is **typeset closely to the export, not
  identical** (`siunitx`, `\newcommand` across equations and some environments differ from LaTeX and Word),
  so a check flags "macro unsupported in preview". KaTeX is a new npm dependency with its fonts bundled
  locally (no CDN); it runs with `trust: false`, `maxExpand` about 1000, a `maxSize`, and
  `throwOnError: false`, because pasted or AI-proposed LaTeX is untrusted. Check the build size.

**Widget engineering rules (CodeMirror).** These follow the editor's one-`StateField` design and its
rebuild-on-every-change behaviour:

- Image, KaTeX and table widgets implement `eq()` on (label, content hash) so they do not rebuild their DOM
  on every keystroke or cursor move. A scene with five figures must not re-create image DOM while typing
  (measured, an acceptance test).
- Object data arrives asynchronously: an `objectsField` plus a `setObjects` effect (like `setSpans`), part of
  the rebuild trigger, with a sized placeholder (set `estimatedHeight`) until it arrives, so the scroll does
  not jump.
- Placements are block `Decoration.replace({widget, block: true})` over the whole line and are atomic.
  "Cursor entering shows the source" does **not** apply to block placements. Deletion and moves: Backspace
  from the next line removes the placement after a confirm, and the widget menu offers Move and Remove.
- `softBreaks` treats a `![[...]]` line as a hard break; otherwise its newline gets a space replace that
  overlaps the block replace.
- **Cross-references** show as the resolved text ("Figure 2"); the cursor entering one shows `[[fig:...]]`.
  A reference that resolves to nothing is drawn with the same warning style as unresolved links.
- Hovering a figure, table or equation reference shows a small preview.
- **Terminal app:** cannot draw images. It shows a one-line placeholder with the number and caption,
  supports citation highlighting, the checks and the export options, and opens the object's file for editing.
  (Decision needed: whether table and equation text editing is in scope for the TUI in version 1.)

### 7.4 Generated figures and tables

A figure can be **made from Python code** (a graph) and a table can be **built from data with a formatting
spec** (a well-formatted table), instead of being a pasted image or hand-typed Markdown. The code and data
stay in the project as plain files, so the result is reproducible and re-runnable.

**Generated figure**

```
figures/fig-flow-model.md       # YAML adds: source: script, script: fig-flow-model.py, data: [data/flow.csv],
                                #   run: { python, packages, script_sha, data_sha, at, status }  (provenance only;
                                #   it is NOT a trust record, see "Trust")
figures/fig-flow-model.py       # the author's plotting code (matplotlib in version 1)
figures/fig-flow-model.png      # the output; the same file the rest of this plan already shows and exports
```

- The script follows a small contract: it receives the project's data folder, the figure style and the output
  path, and writes one PNG. A starter template is provided (read CSV, plot, save). No other output is used.
- **Project figure style:** one shared style (fonts, sizes, line widths, colour-blind-safe palette, figure
  width matched to the Word template's column or the LaTeX text width, 300 dpi) so every figure matches and
  fits the page. Set once, applied to every script.
- **Run on click only.** *Run script* regenerates the PNG; nothing runs on open, on save or in the
  background. The figure panel shows the status: current, **stale** (script or data changed since the last
  run, detected by hash) or failed (with the error text).
- **Trust:** running code is as risky as opening a notebook, and a project can be shared or cloned. A script
  is never run until the author confirms, and the confirmation is tied to the script's hash: any change asks
  again. The dialog shows the file and where it will run. **Confirmed hashes are stored only in the
  per-user state folder, keyed by project id, figure path and SHA-256; nothing in the project can mark a
  script as trusted** (a cloned project must never arrive pre-confirmed). `run_figure(project, id)` checks
  that record; `trust_figure(project, id, sha)`, called only from the confirmation dialog, is the only way
  to write it.
- **Interpreter:** a per-user setting only. Chisel never runs an interpreter found inside the project folder
  (a cloned project could ship its own `python.exe`). The installed desktop app has no Python of its own, so
  with no interpreter set, Run says so and names the setting.
- **Execution contract (Windows-safe):**
  - Copy the hashed bytes to a temp file and run that copy, so there is no gap between hashing and running.
  - Run `<python> -I -X utf8 <chisel_runner.py> --script <copy> --out <tmp.png> --data <dir> --style <mplstyle>`.
    `-I` keeps a planted `figures/numpy.py` or `matplotlib.py` from shadowing imports; `-X utf8` is needed
    because `-I` ignores `PYTHONIOENCODING`.
  - Working directory is a temp dir, not the project (otherwise matplotlib reads a project `matplotlibrc`).
  - Scrubbed environment: drop `OPENROUTER_API_KEY`, `CHISEL_*` and `PYTHON*`; set `MPLBACKEND=Agg`.
  - `**desktop.NO_CONSOLE`; a timeout that kills the **whole process tree** (a Job Object with
    KILL_ON_JOB_CLOSE, or `taskkill /T /F`), because `subprocess.run(timeout=)` kills only the direct child;
    captured stdout and stderr are capped.
  - The output is checked by bytes (`sniff_ext`, the 10 MB cap) before an atomic `fsutil` replace.
  - It runs as a job (`figure_run_start` / `figure_run_status` / cancel, like `gui/exports.py`), never
    holding `self._lock`.
  - `chisel_runner.py` is Chisel's own code; it also records the Python and package versions
    (`importlib.metadata`) to a JSON file, which is where "Provenance" gets its data.
- **Matplotlib** must be installed in the **chosen interpreter**, not in Chisel's environment (it is not an
  extra of Chisel). Run checks for it through the runner and names `<python> -m pip install matplotlib`.
  Chisel cannot sandbox network or file access from a script, and says so.
- **Figure width:** a project setting in inches in version 1 (reading the Word template's page setup is
  deferred; it would make P4b depend on P5).
- **Provenance:** the sidecar records the script and data hashes, the Python and package versions and the
  time, so a result can be traced and a stale one detected.
- **AI help (optional):** "describe the plot, get code" is a *pending proposal* shown in the panel and
  listed in "What was sent" (the description, and the data column names only if the author ticks them). It
  is never run automatically; accepting it only saves the script, and running is the separate trusted step.
- **WYSIWYG:** the figure shows like any other (7.3); the panel adds *Edit script* (opens the `.py` in the
  editor) and *Run*. A run that fails keeps the previous image.

**Generated table**

```
tables/tbl-results.md           # YAML adds: source: data, data: data/results.csv, format: { ... }
tables/tbl-results.csv          # or any CSV in data/
```

- The table is built from a **CSV** (an Excel sheet saved as CSV works; reading `.xlsx` directly would need
  another dependency and is deferred) plus a **formatting spec** in YAML: column
  headers and units, number format per column (decimals or significant figures, thousands separators),
  alignment (decimal-aligned numbers), bold or marked best values, row and column order, footnotes, and
  caption. Re-build when the data changes; a changed CSV marks the table stale, like a figure.
- **Output forms:** a Markdown pipe table for the file and the editor view, and the richer form on export.
  Plain pipe tables cannot do merged cells, multi-row headers or decimal alignment, so the export path uses
  pandoc's grid or simple table forms, or generated LaTeX (booktabs) for the PDF. **VERIFY** how far Word
  output follows this (merged header cells, decimal alignment) with the author's real template; where a
  feature cannot survive into Word it is dropped with a visible warning, never silently.
- **No code is needed for tables** in version 1: the spec is data, not a script. A "table from a Python
  script" is deferred, because a script can only be trusted case by case.
- WYSIWYG: the table renders formatted as it will export (7.3). **A `source: data` table's body is
  generated and read-only (marked by a comment line); edits go to the spec only.** Hand-typed tables are
  the 7.1 kind, and only they have cells the grid editor writes.

## 8. Export

All export goes through `core/export/manuscript.assemble`, but the current pipeline **strips what research
needs**, so this is the largest and riskiest piece, not a one-line addition:

- The `Book` model is only Paragraph (bold and italic runs) and Break. Sub-headings become bold
  paragraphs, quotes and comments are dropped, and `$ @ | [ ]` are escaped. The pandoc reader disables
  citations, math, pipe tables, implicit figures and footnotes, and `[[...]]` links are flattened to text
  before parsing.
- Research export needs new block and run types (Heading with level, Math, Citation, Figure, Table,
  Equation, Footnote) and a second reader string. **Generated constructs bypass escaping while author text
  keeps the strict escaping**; fiction exports must stay byte-identical (a test).
- Scenes export as chapters ("Chapter N"); research needs section numbering instead.
- pandoc currently runs with `cwd=exports/`, so image paths fail ("Could not fetch resource", observed):
  pass `--resource-path=<project root>` or absolute paths.

### 8.1 Word (.docx)

- pandoc with `--reference-doc`. **A funder's own .docx or .dotx will not map onto pandoc's style names**
  (`Heading 1`, `Image Caption`, `Table Caption`, ...). Chisel ships a starter reference document made from
  pandoc's own default, plus a **"Check template"** step that lists missing styles. One template per
  funder, stored in the project (`templates/`) or the user data folder.
- **Verified (pandoc 3.9.0.2):** TeX display math becomes native Word equations (`m:oMath`); `--citeproc`
  works; `{#fig:x}` becomes a Word bookmark.
- **Equation numbers: VERIFY, probably not buildable as first written.** Plain pandoc does not accept
  attributes on display math (`$$..$$ {#eq:x}` is pandoc-crossref syntax) and raw TeX is off in the reader.
  Plan: Word gets the equation plus a right-aligned "(n)" via a two-column borderless table or a tab stop;
  LaTeX gets a raw `equation` environment with `\label` emitted by the writer (a generated construct, not
  author text).
- Cross-references and numbers are typed text, not Word fields; they will not renumber if the document is
  edited in Word. The export dialog says so.
- Page limits: a word-count estimate against section limits. No Word page count is claimed. (A LibreOffice
  page count is deferred.)

### 8.2 LaTeX and PDF

- pandoc writes `.tex` (and the bibliography); a TeX engine builds the PDF with `--pdf-engine=xelatex`.
  **Verified:** MiKTeX with xelatex, lualatex and pdflatex is installed on the author's machine; Tectonic
  is not.
- MiKTeX can install missing packages on the fly, which can open a dialog or reach the network. That breaks
  "network is explicit" and can hang the subprocess (120 s today). So: a pre-flight list of needed packages,
  a longer timeout, `NO_CONSOLE`, and a clear message if a package is missing.
- Image formats: PNG and JPG work everywhere. PDF images fail in Word; SVG in LaTeX needs Inkscape. Version
  1 accepts PNG and JPG only.
- Outputs go to `exports/` and are never overwritten. The existing ReportLab PDF stays for fiction.

## 9. Settings

User (per machine): API key (keyring, using the service-name and `fake_keyring` test pattern in `migrate.py`),
preferred backend order, auto-export file path, default CSL style, template folder.

Project (`project.toml`): `mode`, the `[research]` keys, numbering scheme, per-section word limits (section
frontmatter), the Zotero collection to sync.

AI: existing roles and models; no new role in version 1.

## 10. Privacy and safety

- The API key lives in the keyring only and is never logged.
- Zotero data comes over HTTPS (web) or loopback (local). No telemetry.
- Attachment of a source to an AI goes through the capped `attach` path and the "What was sent" report; no
  silent caps. Sources are otherwise excluded from every AI context (5.3).
- Syncing never deletes author text; replacement is limited to the marked Zotero block.
- Pulled HTML is sanitised and escaped (5.2).
- **Scripts never run on their own** (7.4): only on a click, only after a confirmation tied to the script's
  hash, with a timeout. Chisel does not sandbox them and states that. Data and code are never sent to an AI
  except what the author ticks in a "describe the plot" request, shown in "What was sent".
- Export refuses unresolved citations and references unless the author overrides.

## 11. Build order

0. **Contracts and the mode gate:** dataclasses and stub registrations in every shared file, `mode`, binder
   groups and labels.
1. **Kinds, citation syntax and the AI-exclusion rule** (sections 5.1, 5.3, 6.1).
2. **Sources from the Better BibTeX auto-export file, and research export (Word, then PDF).** Offline and
   usable immediately with the author's real keys.
3. **Zotero web and local sync, notes and highlights.**
4. **Figures, tables and equations, with the WYSIWYG editor widgets (7.3) and cross-references.** Export of
   objects lands here at the latest.
4b. **Generated figures and tables (7.4):** script runner with trust and staleness, figure style, table
   formatting spec. Built after step 4, because it only writes the same PNG and Markdown files step 4
   already displays and exports.
5. **GUI and TUI polish.**

Docs, `CHANGELOG.md`, `SPEC.md` and packaging data files are updated at merge time by one integrator.

## 12. Cheap checks before the expensive work

About ten minutes, before Zotero sync work starts, against the author's real library (responses scrubbed of
personal data and saved as test fixtures):

1. `GET /users/<id>/items/top?limit=5` with the key: is `data.citationKey` filled in? Which Zotero version?
2. One PDF attachment's `/children`: do annotations come back?
3. The same two against `localhost:23119/api/users/0/...`.
4. A pandoc run with the author's real Word template and one CSL file, and `--pdf-engine=xelatex`, to see
   whether MiKTeX prompts for packages.

## 13. Open questions

1. Zotero version and whether keys are populated in the web API (check 1 above).
2. ~~Narrative-citation spelling~~ decided: `[[+@key]]` (6.1). Still open: whether plain `[@key]` is
   accepted everywhere or only on export.
3. Which funder or proposal formats come first; sample Word templates or format specs.
4. Terminal app scope for table and equation editing in version 1.
5. Multi-panel figures: one image per figure in version 1?
6. Is write-back to Zotero wanted later?
7. Where per-funder Word templates live: per project or a shared folder.
8. Which Python the figure scripts use (an existing environment of yours, or one Chisel creates), and which
   plotting library besides matplotlib, if any.
9. Which table features matter most for your proposals: merged headers, decimal alignment, footnotes,
   significance marks.

## 14. Risks

- The export pipeline change (section 8) is the largest blast radius; the fiction-export byte-identical test
  is the guard.
- WYSIWYG widgets add CodeMirror complexity (block widgets and line-spanning replaces must live in the one
  `StateField`); table grid editing must round-trip Markdown exactly.
- Word cross-references are text, not fields.
- Running author-supplied Python is the one place Chisel executes arbitrary code. The hash-bound trust step
  is the guard; a cloned project must never run code without that prompt.
- Rich table features (merged cells, decimal alignment) may not survive into Word, so the formatted table
  and the exported one can differ; the warning in 7.4 is the mitigation.
- Local and web Zotero APIs differ in detail (annotations, deleted items, versions, rate limits).
- MiKTeX package prompts can hang LaTeX export.
- Scope touches entities, links, the index, the editor, export, Trash and the GUI; the build order keeps each
  slice testable and reversible.

## 15. Review changes

### Draft 2 to draft 3 (second review, 2026-10-15)

Applied: script trust record and interpreter live in the per-user state folder, never the project (7.4);
Windows-safe execution contract with runner, temp copy, isolated Python, scrubbed environment, process-tree
kill, job (7.4); matplotlib belongs to the chosen interpreter, not a Chisel extra (7.4); new `code` document
kind and a `data/` folder (7.1); table parse and serialise in Python with a canonical form (7.3); generated
table bodies are read-only (7.4); the link parser ignores citation and object targets and narrative
citations use `[[+@key]]`, with a separate case-sensitive index table and rebuild on mode change (6.1);
`Num` display strings for numbering (7.2); widget engineering rules for the StateField, KaTeX hardening and
image serving through one door (7.3); Word equation numbers marked VERIFY (8.1); math handling restricted to
research mode with pandoc's dollar rule (7.2); source file naming and rename rules (5.1); one fall-through
order (4.1); Zotero local-API claims gated on version and the Backoff rule (4.1, 4.3). Contracts are now in
[research-mode-contracts.md](research-mode-contracts.md).

### Draft 1 to draft 2

Applied from the independent review: new entity kind and `entities/sources/` folder (5.1); sources excluded
from AI context (5.3); citation syntax and parser (6.1); key-based file naming and key-change flow (5.1,
6.4); export model additions and escaping rule (8); objects visible to the app, new Trash kind, placement
syntax, label from file stem (7.1, 7.2); native `citationKey` and no default key generation (4.2); per-backend
sync state and sync protocol (4.3); verbatim CSL JSON and bundled styles (5.2, 6.3); HTML note sanitising
(5.2); template caveat and starter (8.1); MiKTeX behaviour and PNG/JPG-only images (8.2); Better BibTeX
auto-export as the first backend and re-ordered build (4.1, 11); mode gate first (3, 11); numbering schemes
and strip-math (7.2); terminal app scope (7.3); AI-suggested citation cut (2). Added by request: WYSIWYG
figures, tables and equations (7.3); figures generated from Python code and tables built from data with a
formatting spec (7.4).
