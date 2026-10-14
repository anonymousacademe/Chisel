# Plan: Research mode (Zotero sources, figures, equations, Word and LaTeX output)

Status: draft for review. Nothing here is built. Items marked **VERIFY** rest on recollection of
Zotero / Better BibTeX / pandoc behaviour and must be checked against current documentation or the
author's actual library before they are relied on.

## 1. Goal

Make Chisel usable for research writing (papers, proposals, theses) without giving up its principles:
a project is a folder of plain Markdown, AI only suggests, nothing leaves the machine unless the author
triggers it. Research mode adds:

1. A connection to the author's Zotero library, so sources are articles the author actually has.
2. Source notes (the research analogue of a character card) holding Zotero notes, highlights and the
   author's own notes.
3. Figures, tables and equations with captions and cross-references.
4. Two outputs: a Word document that follows a required format, and a LaTeX PDF.

Non-goals for the first version: writing back to Zotero, live Word fields, exact page counts,
reading full text from PDFs, replacing Zotero's own reference management.

## 2. Principles kept (from SPEC section 2 / AGENTS.md)

- Plain text always. Sources, figures, tables and equations are files in the project.
- The index is a rebuildable cache. Source notes are the offline cache of the Zotero library; the SQLite
  index only speeds up backlinks.
- AI suggests, never edits. Anything AI-made (a LaTeX equation, a suggested source) is a pending
  proposal. An AI-suggested citation is never inserted unless it matches a source already in the project.
- Nothing from Zotero reaches an AI unless the author attaches it, and the "What was sent" line shows it.
- Network is explicit. Sync runs only on a click; nothing contacts Zotero in the background.

## 3. Project mode

`project.toml` gains a mode:

```toml
[project]
mode = "research"        # "fiction" (default) or "research"

[research]
citation_style = "apa"           # a CSL style name or a path to a .csl file
word_template = "templates/nsf.docx"
section_template = "imrad"       # imrad | proposal | review | blank
```

The mode changes labels, sidebar groups, inspector fields and which checks and exports appear. It does not
change the file format, so a project can switch back. Fiction-only features (POV, story time, character
relationships) are hidden in research mode, not deleted; their data stays in the files.

### Sidebar (binder) in research mode

| Fiction | Research |
|---|---|
| Manuscript (parts, scenes) | Sections (parts, sections) |
| Characters | Sources |
| Places | Concepts / Methods / Datasets (entity types) |
| (none) | Claims (optional) |
| (none) | Figures, Tables, Equations |
| Notebook | Notebook (unchanged) |
| Parked scenes | Parked paragraphs |
| Trash | Trash (unchanged) |

The scene inspector's POV, place and story time are replaced by: status (outline, draft, revising,
final), word limit for the section, and target (for example "Specific Aims").

## 4. Zotero connection

### 4.1 Backends and fallback order

A single `ZoteroSource` interface, three implementations, tried in this order:

1. **Web API** (`api.zotero.org`, user library). Needs the user ID and an API key with read access.
   The key is stored in the system keyring, never in a project file or `project.toml`.
2. **Local API** (`http://localhost:23119/api/`, Zotero 7 desktop, requires the setting "Allow other
   applications on this computer to communicate with Zotero"). No account or key. **VERIFY** current
   endpoint paths and that it mirrors the web API's item, collection, tag and annotation routes.
3. **Cache**: the source notes already in the project. If neither Zotero source is reachable, citations
   still resolve and export still works from the cached metadata.

The same reader code parses all three because the item JSON is the same shape. Failure of one backend
falls through to the next and is reported in plain words (which backend answered, which did not).

### 4.2 Citation keys

Citation keys come from Better BibTeX. **VERIFY** whether the web API exposes them. The expected case is
that Better BibTeX only writes the key into the item's "Extra" field (`Citation Key: smith2024`) when it is
configured to pin keys; otherwise keys exist only inside Zotero. Behaviour:

- If an item carries a key, use it.
- If not, generate one (`<lastname><year>`, then `a`, `b` on clash) and mark it `key_source: generated`.
- Sync reports any generated key and recommends pinning keys in Better BibTeX so Chisel and Zotero agree.
- A key, once assigned to a source note, is stable: sync never renames it silently. A mismatch with
  Zotero is shown and resolved by the author (reuses the rename-everywhere flow).

### 4.3 Sync

- Manual only: *Action: Sync sources from Zotero*, optionally limited to a collection or tag.
- Pull only. Chisel never writes to Zotero in version 1.
- Dry run first: show a list of new, changed and removed items. The author ticks what to apply
  (same review shape as rename and canon updates).
- Removed from Zotero does not delete the note; it is marked `zotero_status: missing` and kept.
- Incremental: remember the library version (`Last-Modified-Version` / `since`) per library in the
  per-user state folder, not in the project. **VERIFY** the exact mechanism.

## 5. Source notes

A source is a Markdown note in `sources/<key>.md`, free text plus YAML frontmatter, following the entity
frontmatter round-trip rule (keys Chisel does not manage are kept verbatim):

```markdown
---
name: Smith 2024
type: source
key: smith2024
key_source: zotero          # zotero | generated | manual
zotero: { library: "users/123456", item: "ABCD1234", version: 4821 }
title: "..."
authors: ["Smith, Jane", "Lee, Wei"]
year: 2024
container: "Water Research"
doi: "10.xxxx/xxxxx"
tags: [wastewater, ai]
aliases: ["Smith et al. 2024", "Smith and Lee"]
---

<!-- zotero:begin -->
## From Zotero
### Notes
...
### Highlights
- p. 4: "quoted text" (comment)
<!-- zotero:end -->

## My notes
Free text the author writes here. Sync never touches anything outside the zotero markers.
```

- Sync regenerates only the text between `zotero:begin` and `zotero:end`. Everything else is the author's.
- Highlights keep their page and comment, and their Zotero annotation ID so a re-sync updates rather than
  duplicates.
- Sources reuse the entity machinery: aliases, backlinks, mention colouring, and rename-everywhere.
  `type: source` is a new entity kind; its folder is `sources/` (a new group in the binder).
- The assistant's "About:" chip works for a source and sends its notes only when shown.

## 6. Citations in the manuscript

- Syntax: `[[smith2024]]`, the existing wiki-link form. Several sources: `[[smith2024; lee2023]]`.
  Optional locator: `[[smith2024, p. 12]]`. **Decision needed:** whether to keep `[[...]]` for citations
  or add `[@smith2024]` (pandoc native). Recommendation: author types `[[...]]`; export rewrites it.
- Resolution: a link whose target is a source key is a citation. Anything else resolves as before.
- Checks (read-only, with a report like the continuity check):
  - citation with no source note
  - source note never cited
  - source marked `zotero_status: missing`
  - two sources with the same key
- Bibliography: built at export time from the cited sources only, in the chosen CSL style, by pandoc
  citeproc from CSL JSON generated from the source notes (so it works offline).

## 7. Figures, tables and equations

### 7.1 Files

```
figures/fig-flow-model.md        # YAML: label, caption, file, width, alt; body = notes
figures/fig-flow-model.png       # the image (PNG, JPG, SVG, PDF)
tables/tbl-results.md            # YAML: label, caption; body = a Markdown pipe table
tables/tbl-results.csv           # optional source data; the .md is generated from it on import
equations/eq-mass-balance.md     # YAML: label, caption (optional); body = LaTeX
```

Separate from `inspiration/`: inspiration pictures are reference only, never exported and never sent to an
AI. Figures are manuscript content and are exported. The two folders and their rules must not be mixed.

### 7.2 Authoring

- *Insert figure*: choose a file (copied into `figures/`), enter a caption and label.
- *Insert table*: paste or import CSV, or write Markdown; caption and label.
- *Insert equation*: LaTeX editor with live preview (KaTeX in the desktop app), a symbol and template
  palette, and an optional AI step "describe it in words, get LaTeX" shown as a pending proposal the author
  accepts or rejects. The AI step sends only the author's description, and shows it in "What was sent".
- Inline math `$...$` works in prose with no object; only numbered, referenceable equations need a file.

### 7.3 Cross-references

- In prose: `[[fig:flow-model]]`, `[[tbl:results]]`, `[[eq:mass-balance]]`. The prefix distinguishes them
  from character or source links.
- Numbers are assigned in reading order across the book (Figure 1, 2, ...; Table 1, 2, ...; Eq. (1), ...).
  Never stored in files, so reordering sections renumbers everything.
- Rendered as "Figure 2", "Table 1", "Eq. (3)" in export; shown in the editor as the same text.
- Captions render with the number ("Figure 2. ...").
- Checks: reference to a missing object; object never referenced; duplicate label; a figure whose image
  file is missing.

## 8. Export

All export goes through `core/export/manuscript.assemble`, as the existing exports do (one model, no
re-reading scenes in a writer). Research mode adds an assembled form where citations, cross-references and
objects are resolved, then hands it to pandoc.

### 8.1 Word (.docx)

- pandoc with `--reference-doc=<template>.docx` supplying fonts, margins, spacing, heading and caption
  styles. One template per funder or solicitation, stored in the project (`templates/`) or the user data
  folder, picked in the export form.
- Citations through `--citeproc` with the chosen CSL style and a CSL JSON file generated from the sources.
- Equations arrive as native Word equations (pandoc converts LaTeX math). **VERIFY** on real content.
- Cross-references and numbering are inserted by Chisel as text ("Figure 2"); they are not Word fields and
  will not renumber if the document is edited in Word. State this in the export dialog.
- Page limits: Chisel shows a word-count estimate against the section limits. It does not claim a Word
  page count. Optionally, if LibreOffice is present, convert the result to PDF to report a real page count.

### 8.2 LaTeX and PDF

- pandoc writes `.tex` (and `.bib` or CSL), then a TeX engine builds the PDF (XeLaTeX or LuaLaTeX; Tectonic
  would avoid a large install). **VERIFY** which is easiest on Windows.
- Both the `.tex` and the PDF are kept in `exports/` and never overwritten, as with existing exports.
- This is separate from the current ReportLab PDF export, which stays as it is for fiction.

### 8.3 Requirements on the machine

pandoc (already optional), a TeX engine (new, optional), and for the fiction exports nothing changes.
The export form greys out any format whose tool is missing and names the install command. Whether
`pandoc-crossref` is needed depends on whether Chisel resolves references itself (this plan says it does,
so it is not required). **VERIFY** that choice against how pandoc handles captions and labels.

## 9. Settings

User settings (per machine): Zotero user ID, keyring entry for the API key, preferred backend order,
default CSL style, template folder.

Project settings (`project.toml`): `mode`, `[research]` keys above, per-section word limits (in section
frontmatter), the Zotero collection to sync from.

AI: the existing roles and models. Research mode adds no new role in version 1.

## 10. Privacy and safety

- The Zotero API key lives in the keyring only. It is never logged (`applog` already forbids keys/prose).
- Zotero data is pulled over HTTPS (web) or loopback (local). No telemetry.
- Source notes can be large (highlights). Attachment to an AI goes through the existing capped
  `attach` path and the "What was sent" report; no silent caps.
- Syncing never deletes author text. Replacing is limited to the marked Zotero block.
- A check must refuse to export if a citation is unresolved, unless the author overrides, so a proposal is
  not sent with `[[smith2024]]` showing.

## 11. Build order

1. **Sources.** `ZoteroSource` (web, local, cache), key handling, `sources/` notes with the marked Zotero
   block, dry-run sync review, citation links and the citation checks. Tests with a fake Zotero server;
   no network in tests.
2. **Figures, tables, equations.** Files, insert dialogs, live equation preview, numbering, cross-reference
   links and checks.
3. **Word export.** Assembly, citeproc, reference-doc templates, word-count limits.
4. **LaTeX and PDF export.**
5. **Research mode switch.** Sidebar groups, labels, inspector fields, section templates, hiding fiction-only
   features.

Each step ships on its own and leaves fiction projects unaffected.

## 12. Open questions

1. Does the web API expose Better BibTeX citation keys for this library, or must keys be pinned to Extra?
2. Citation syntax: keep `[[key]]` (author's preference) or also accept `[@key]`?
3. Which funder or proposal formats come first, and are there sample Word templates or format specs?
4. Which TeX engine is acceptable to install on this machine (MiKTeX, TinyTeX, Tectonic)?
5. Should figures support multi-panel layouts, or is one image per figure enough for version 1?
6. Is read-only Zotero enough, or is write-back (new notes, tags) wanted later?
7. Where do per-funder Word templates live: inside each project, or a shared folder?

## 13. Risks

- Better BibTeX key availability (see 4.2) could force generated keys and a manual reconciliation step.
- Word cross-references are text, not fields; authors who edit heavily in Word lose automatic renumbering.
- Zotero Local API and web API behaviour may differ in details (annotations, deleted items, rate limits).
- A TeX install is large and Windows-fiddly; LaTeX export may need to be optional.
- Scope: this touches entities, the index, the editor, the export package and the GUI. The build order is
  meant to keep each slice testable and reversible.
