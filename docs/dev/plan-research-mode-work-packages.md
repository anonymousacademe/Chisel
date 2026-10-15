# Research mode: work packages for agentic coders

Companion to [plan-research-mode.md](plan-research-mode.md). Splits the implementation so agents can work in
parallel with few merge conflicts and controlled token use. Model tiers are recommendations: Opus for
decisions and risky integration, Sonnet for standard implementation, Haiku for mechanical work.

## Packages

| # | Package | Owns | Depends on | Interface it must expose | Tests | Model | Cost |
|---|---|---|---|---|---|---|---|
| P0 | Contracts, stubs, mode gate | SPEC research section, `core/research/__init__.py`, one-line registrations in shared files, `project.toml` mode accessor | none | Dataclasses `Citation(keys, start, end, raw)`, `CiteRef(key, prefix, locator, suffix, suppress_author, narrative)`, `ZItem(key, version, csl, citation_key, notes, annotations, deleted)`, `RefObject(kind, label, path, caption, file)`, `Numbering = dict[str, int]` | import and smoke | Opus | M |
| P1 | Kinds and citations core | `core/entities.py` (types), `core/project.py` TYPE_SUBDIRS, `core/links.py` `find_citations`, `core/index.py`, AI exclusion in `core/continuity.canon_map` and `ai/relevance.py` | P0 | `find_citations(text)`, `resolve_key(key, entities)` (case-sensitive), `Entity.is_source`, `index.citers(key)` | parser edge cases (`;`, `,`, `\|`, `-@`, unicode), type round trip, **no source text in any context builder** | Sonnet; Opus reviews the AI-exclusion diff | M |
| P2 | Zotero client and file backend | new `core/zotero/` (web, local, file, html2md) | P0 | `ZoteroSource` protocol: `probe()`, `fetch(scope, since)` returning items, deleted keys, library version, server id; `open_sources(settings)`; `chain_fetch(...)` returning result and a plain-words report | fake HTTP server with scrubbed recorded JSON; 304, 429/Backoff, pagination, deleted, Extra fallback, sanitiser | Sonnet | M |
| P3 | Source notes and sync | new `core/sources.py`, sync state in the user state dir | P1, P2 | `item_to_note`, `replace_block`, `plan_sync` (rows: new, changed, missing, key-mismatch), `apply_sync(plan, ticked)` | marker preservation byte for byte, extra round trip, no overwrite of author text, refuse if changed since plan | Sonnet; Opus reviews apply | L |
| P4 | Objects core and numbering | new `core/objects.py`, Trash kind `object` in `core/structure.py`, document-kind entries | P0 | `list_objects`, `create_figure`, `numbering(project)` (reading order), `find_placements`, `find_refs`, `strip_math` | numbering across parts and reorders, schemes (plain, per-section, supplementary), duplicate labels, Trash restore, image sniff and size cap | Sonnet | M |
| P4b | Generated figures and tables | new `core/figscripts.py` (runner, trust, staleness, provenance), `core/tablefmt.py` (CSV plus format spec to Markdown, grid and LaTeX forms), starter script template, figure style file | P4 | `run_figure(project, id, confirmed_sha)` returning status and error text (never runs when the confirmation does not match the script hash); `figure_status(project, id)` (current, stale, failed); `build_table(project, id)` returning Markdown and the export form; `trust_state(project, id)` | runner uses a temp project and a trivial script (no matplotlib needed in tests); hash-mismatch refuses to run; timeout; failed run keeps the old image; stale detection on script and data; formatting spec cases (decimals, significant figures, alignment, footnotes); fiction projects unaffected | Sonnet; Opus reviews the trust and execution path | M |
| P5 | Research export | new `core/export/research.py`, `csljson.py`, research branch in `pandoc.py`, model additions in `manuscript.py`, bundled `export/csl/` | P1, P4 contracts | `assemble_research(project, opts)` returning a Book with Heading, Math, Citation, Figure, Table, Equation; `convert_research(book, fmt, out, csl, reference_doc, resource_path)` | golden docx XML (oMath, bookmarks, citeproc text), strict escaping for author text, **fiction exports byte-identical**, PDF test skipped without TeX | **Opus** | L |
| P6 | Research checks | new `core/researchchecks.py` | P1, P3, P4 | `run_checks(project)` returning flags; `blocking(flags)` gating export | one test per check | Haiku | S |
| P7 | GUI bridge | new `gui/research_api.py` (mixin), `gui/workspace.py` additions | P3 to P6 | `zotero_status`, `zotero_sync_plan`, `zotero_sync_apply`, `list_sources`, `list_objects`, `object_numbers`, `object_preview` (downscaled, project figures only), `save_table`, `research_checks`, `insert_figure`, `export_research_start`; all `@bridge`, network outside `self._lock` | `tests/test_gui_research.py`, signature and mock-name tests | Sonnet | M |
| P8a | GUI: sources and sync review | `gui/src/components/research/` Sources and SyncReview | P7 JSON shapes | uses only P7 | vitest | Sonnet | L |
| P8b | GUI: WYSIWYG objects | CodeMirror widgets in `editor/cm.ts` for figure, table (grid editor), equation (KaTeX), reference previews | P7 | uses only P7 | vitest; round-trip tests for table Markdown | Sonnet; Opus reviews the StateField changes | L |
| P9 | Terminal app minimum | `tui/researchmixin.py`, export screen options | P3 to P6 | palette `Action` entries, citation highlighting, placeholders | Pilot tests | Sonnet | M |
| P10 | Docs, packaging, fixtures | CHANGELOG, `packaging/chisel.spec`, `selftest.py`, workspace fixture regeneration | all | none | packaging and selftest tests | Haiku | S |

## Waves and merge order

- Wave 0: P0. Wave 1 in parallel: P1, P2, P4. Wave 2 in parallel: P3, P4b (after P4), P5 (can start on P0
  contracts with stubbed numbering), P6 (after P3). Wave 3: P7 (gains `run_figure`, `figure_status`,
  `build_table` bridge methods and a confirmation dialog in P8b). Wave 4 in parallel: P8a, P8b, P9. Wave 5: P10.
- Merge order: P0, P1, P4, P4b, P2, P3, P6, P5, P7, P8a, P8b, P9, P10. One git worktree per package; the full suite
  runs at each merge.

## Avoiding merge conflicts

Shared files: `gui/api.py` (mixin list, facade, mocked-name tuples), `core/project.py`, `core/entities.py`,
`core/structure.py`, `core/export/manuscript.py`, `core/export/pandoc.py`, `gui/workspace.py`,
`gui/src/data/types.ts`, `App.tsx`, the Sidebar, SPEC.md, CHANGELOG.md, `packaging/chisel.spec`,
`tests/test_gui_shell.py`, the workspace fixture JSON.

- P0 makes every one-line registration up front (mixin stub, TYPE_SUBDIRS entries, Trash kind constant,
  document-kind branches, types.ts placeholders), so later packages touch only their own new modules.
- One owner per file: `manuscript.py` and `pandoc.py` belong to P5; `structure.py` to P4; `entities.py`,
  `links.py` and `index.py` to P1.
- SPEC, CHANGELOG and fixture regeneration are touched only by the integrator at merge time. Packages put
  their SPEC notes in their final report.

## Usage management

- **Hand each agent:** the P0 contract, its package row, its owned-file list, and only the `AGENTS.md`
  paragraphs that apply (P1: entity round trip, context budget; P4: Trash, structure, inspiration uploads;
  P5: export, portability; P7: GUI fragile spots, AI jobs; P8b: GUI fragile spots, CodeMirror decorations).
  Withhold the whole SPEC, other plan sections, GUI code from core agents, and core internals from React
  agents (they get the P7 JSON shapes and `gui/README.md`). `AGENTS.md` is about 12k tokens.
- **Lookups:** Grep or a Haiku Explore agent rather than reading whole files (`gui/api.py` is over 1,100
  lines).
- **Fresh vs continued:** a fresh agent per package; continue the same agent through its own fix rounds;
  never carry an agent into the next package. Reviews use a fresh Opus agent given only the diff and the
  contract.
- **Cheap checks first:** the four checks in plan section 12, run before any Zotero or export spend.
- **Test gates:** each agent runs only its own tests plus the linter (GUI: `npm run lint` and vitest on its
  files); the full suite runs once per merge. A package is done only when its tests pass, fiction tests and
  exports are unchanged, and no test touches the network or the real keyring.
- **Opus spend** concentrates on P0, P5, P8b's StateField changes and three short reviews (P1 AI-exclusion,
  P3 apply, P4b trust and execution path).
- **Stop conditions** (report back instead of looping): the same test fails after 3 fix attempts; the work
  needs a file outside the package or a change to a P0 contract; a VERIFY assumption proves false; a test
  seems to need the network or real keyring; the full suite already fails before any change; about 40 tool
  calls or 60% of context without green tests. The report states what was tried, the last 30 lines of the
  failure, and a one-paragraph proposal. No speculative refactors.
