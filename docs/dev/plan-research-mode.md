# Plan: Research mode (Zotero sources, figures, equations, Word and LaTeX output)

Status: draft 2, revised after an independent review against the code (see "Review changes" at the end).
Nothing here is built. The implementation split across agents is in
[plan-research-mode-work-packages.md](plan-research-mode-work-packages.md).

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

One `ZoteroSource` interface, four implementations. Default order: web, local, file, cache.

0. **Better BibTeX auto-export file** (CSL JSON or BibTeX that the author points Chisel at). Offline, needs
   no key and no running Zotero, and carries the author's real keys. This is the first backend built, so
   citations and export work before any network code exists.
1. **Web API** (`api.zotero.org`). Needs an API key (read access), kept in the keyring only. The user ID is
   read from `GET /keys/current`, so the author does not type it.
2. **Local API** (`http://localhost:23119/api/`, requires "Allow other applications on this computer to
   communicate with Zotero"). Read-only unless a local key is granted. **Verified:** object and library
   versions have no relation to the web API's; results are not paginated by default; only user 0 is
   available; every response carries `Zotero-Server-ID`. **VERIFY:** annotation routes, `/deleted`, and
   `include=csljson` on the local API.
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
  key at most 50 per request, `/deleted?since=` for removals, restart if the library version changes mid-run.
  **VERIFY** the 429 / `Backoff` / `Retry-After` behaviour and honour it.
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

- `[[@smith2024]]`, with pandoc semantics inside: `[[see @smith2024, p. 12; @lee2023]]`,
  `[[-@smith2024]]` (suppress author), and narrative "Smith (2024)" as `[[@smith2024|n]]`
  (**decision needed:** exact narrative spelling; APA needs the narrative form).
- Plain pandoc `[@key]` is also accepted and rendered the same.
- A new `links.find_citations(text) -> list[Citation]` is the single parser, used by the index, the TUI
  highlighter and the Python span computation. The GUI never parses citations in TypeScript.
- `resolve_key` is case-sensitive and matches only source keys; it never competes with entity names (a
  Concept called "kalman2020" cannot shadow a key).

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
- Numbering schemes: plain (1, 2, 3), per-section (2.1) for theses, and supplementary (S1) for papers.
- References render as "Figure 2", "Table 1", "Eq. (3)"; captions render with the number.
- Inline math `$...$` in prose works in the editor and in export (see 8). Spell check, word counts and
  mention scans must skip math (a `strip_math` helper, used like `scenemeta.strip`).

### 7.3 WYSIWYG in the desktop editor

Figures, tables and equations are shown as they will look, not as source text. This follows the editor's
existing approach (one CodeMirror `StateField` holds block widgets; Python computes spans, TypeScript only
draws).

- **Figure:** a placement line renders as the image at its set width, with the numbered caption beneath
  ("Figure 2. ..."). The image comes through a bridge method that serves only project figure files (like
  `inspiration_image`), as a downscaled preview for large files, never a raw path. Click opens the figure
  panel (replace image, edit caption, width, alt text, notes). A missing image shows a clear placeholder.
- **Table:** a placement line renders as a real table with the numbered caption above it. Click turns it into
  a **grid editor** (type in cells, add and remove rows and columns, paste from a spreadsheet, import CSV).
  Edits are written back as the Markdown pipe table; the file stays plain text.
- **Equation:** a placement line renders as typeset math (KaTeX) with its number at the right. Click opens a
  LaTeX box with live preview, a symbol and template palette, and the optional AI "describe it, get LaTeX"
  step, shown as a pending proposal and listed in "What was sent". Inline `$...$` renders as typeset math in
  place and shows its source when the cursor enters it.
- **Cross-references** show as the resolved text ("Figure 2"); the cursor entering one shows `[[fig:...]]`.
  A reference that resolves to nothing is drawn with the same warning style as unresolved links.
- Hovering a figure, table or equation reference shows a small preview.
- **Terminal app:** cannot draw images. It shows a one-line placeholder with the number and caption,
  supports citation highlighting, the checks and the export options, and opens the object's file for editing.
  (Decision needed: whether table and equation text editing is in scope for the TUI in version 1.)

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
2. Exact narrative-citation spelling, and whether plain `[@key]` is accepted everywhere.
3. Which funder or proposal formats come first; sample Word templates or format specs.
4. Terminal app scope for table and equation editing in version 1.
5. Multi-panel figures: one image per figure in version 1?
6. Is write-back to Zotero wanted later?
7. Where per-funder Word templates live: per project or a shared folder.

## 14. Risks

- The export pipeline change (section 8) is the largest blast radius; the fiction-export byte-identical test
  is the guard.
- WYSIWYG widgets add CodeMirror complexity (block widgets and line-spanning replaces must live in the one
  `StateField`); table grid editing must round-trip Markdown exactly.
- Word cross-references are text, not fields.
- Local and web Zotero APIs differ in detail (annotations, deleted items, versions, rate limits).
- MiKTeX package prompts can hang LaTeX export.
- Scope touches entities, links, the index, the editor, export, Trash and the GUI; the build order keeps each
  slice testable and reversible.

## 15. Review changes (draft 1 to draft 2)

Applied from the independent review: new entity kind and `entities/sources/` folder (5.1); sources excluded
from AI context (5.3); citation syntax and parser (6.1); key-based file naming and key-change flow (5.1,
6.4); export model additions and escaping rule (8); objects visible to the app, new Trash kind, placement
syntax, label from file stem (7.1, 7.2); native `citationKey` and no default key generation (4.2); per-backend
sync state and sync protocol (4.3); verbatim CSL JSON and bundled styles (5.2, 6.3); HTML note sanitising
(5.2); template caveat and starter (8.1); MiKTeX behaviour and PNG/JPG-only images (8.2); Better BibTeX
auto-export as the first backend and re-ordered build (4.1, 11); mode gate first (3, 11); numbering schemes
and strip-math (7.2); terminal app scope (7.3); AI-suggested citation cut (2). Added by request: WYSIWYG
figures, tables and equations (7.3).
