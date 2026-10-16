# Research mode: work packages for agentic coders

Companion to [plan-research-mode.md](plan-research-mode.md). Splits the implementation so agents can work in
parallel with few merge conflicts and controlled token use. Model tiers are recommendations: Opus for
decisions and risky integration, Sonnet for standard implementation, Haiku for mechanical work.

## Packages

| # | Package | Owns | Depends on | Interface it must expose | Tests | Model | Cost |
|---|---|---|---|---|---|---|---|
| P0 | Contracts, stubs, mode gate | `docs/dev/research-mode-contracts.md` (the frozen contract), SPEC research section, `core/paper/types.py`, one-line registrations in shared files (mixin stub, `TYPE_SUBDIRS`/`VALID_TYPES`, Trash kind `object`, `_doc_kind` incl. new `code` kind, `types.ts` placeholders, mocked-name tuples), `project.toml` mode accessor | none | All types and signatures in the contracts file (`Citation`, `CiteRef`, `Placement`, `ObjectRef`, `Num`/`Numbering`, `RefObject`, `ZItem`, `Flag`, parser, entity, Zotero, sources, objects, export, checks, AI and bridge signatures) | import and smoke; registrations do not change fiction behaviour | Opus | M |
| P1 | Kinds and citations core | `core/entities.py` (types), `core/project.py` TYPE_SUBDIRS, `core/links.py` `find_citations`, `core/index.py`, AI exclusion in `core/continuity.canon_map` and `ai/relevance.py` | P0 | `find_citations(text)`, `resolve_key(key, entities)` (case-sensitive), `Entity.is_source`, `index.citers(key)` | parser edge cases (`;`, `,`, `\|`, `-@`, unicode), type round trip, **no source text in any context builder** | Sonnet; Opus reviews the AI-exclusion diff | M |
| P2 | Zotero client and file backend | new `core/zotero/` (web, local, file, html2md) | P0 | `ZoteroSource` protocol: `probe()`, `fetch(scope, since)` returning items, deleted keys, library version, server id; `open_sources(settings)`; `chain_fetch(...)` returning result and a plain-words report | fake HTTP server with scrubbed recorded JSON; 304, 429/Backoff, pagination, deleted, Extra fallback, sanitiser | Sonnet | M |
| P3 | Source notes and sync | new `core/sources.py`, sync state in the user state dir | P1, P2 | `item_to_note`, `replace_block`, `plan_sync` (rows: new, changed, missing, key-mismatch), `apply_sync(plan, ticked)` | marker preservation byte for byte, extra round trip, no overwrite of author text, refuse if changed since plan | Sonnet; Opus reviews apply | L |
| P4 | Objects core, tables and numbering | new `core/objects.py`, `core/tables.py` (`parse_pipe`/`to_pipe`, canonical form), `strip_math`, Trash kind `object` in `core/structure.py`, `data/` folder handling (remap, Trash, path containment), `code` document kind, `_figure_file` door | P0 | `list_objects`, `create_figure`, `numbering(project)` (reading order, `Num` display strings, schemes), `find_placements`, `find_refs`, `strip_math`, `parse_pipe`, `to_pipe` | numbering across parts and reorders, all schemes, duplicate labels, Trash restore, image sniff and size cap, canonical table byte-exact round trip, `data:` paths outside the project refused, `strip_math` follows the dollar rule and is a no-op in fiction, `resolve_document` refuses `.py` unless kind `code` | Sonnet | M |
| P4b | Generated figures and tables | new `core/figscripts.py` (trust, staleness, provenance, job), `core/chisel_runner.py` (the Chisel-owned script that runs the author's code), `core/tablefmt.py` (CSV plus format spec to Markdown, grid and LaTeX forms), starter script template, figure style file | P4 | `trust_state`, `trust_figure(project, id, sha)` (the only writer of the per-user trust record), `run_figure(project, id)` (refuses unless trusted), `figure_status`, `build_table`; execution contract in plan 7.4 | runner on a temp project with a trivial script (no matplotlib needed); hash change asks again; a trust record placed in the project is ignored; interpreter inside the project folder is refused; planted `figures/json.py` is not imported (`-I`); timeout kills a child process tree; output and stderr capped; env scrub; failed run leaves the old PNG byte-identical; stale detection on script and data; formatting spec cases; fiction projects unaffected | Sonnet; Opus reviews the trust and execution path | M |
| P4c | AI proposals for LaTeX and plot code | `ai/` functions `suggest_latex`, `suggest_plot_code`, `gui/mockai.py` entries, mocked-name tuples, signature test, budget `Section` and `SentReport` | P0 | `suggest_latex(description, ...)`, `suggest_plot_code(description, columns, ...)`; pending proposals only, never run | mocked at the function boundary (no network); `columns` sent only when ticked and shown in "What was sent"; stopped call inserts nothing | Sonnet | S |
| P5 | Research export | new `core/export/research.py`, `csljson.py`, research branch in `pandoc.py`, model additions in `manuscript.py`, bundled `export/csl/` | P1, P4 contracts | `assemble_research(project, opts)` returning a Book with Heading, Math, Citation, Figure, Table, Equation; `convert_research(book, fmt, out, csl, reference_doc, resource_path)` | golden docx XML (oMath, bookmarks, citeproc text), strict escaping for author text, **fiction exports byte-identical**, PDF test skipped without TeX | **Opus** | L |
| P6 | Research checks | new `core/researchchecks.py` | P1, P3, P4 | `run_checks(project)` returning flags; `blocking(flags)` gating export | one test per check | Haiku | S |
| P7 | GUI bridge | new `gui/research_api.py` (mixin), `gui/workspace.py` additions, span emission in `gui/api.py` / `core/spans.py` (citation, reference, placement, inline-math spans; research mode only) | P3 to P6, P4b, P4c | The bridge table in the contracts file: `zotero_status`, `zotero_sync_plan`, `zotero_sync_apply`, `list_sources`, `list_objects`, `object_numbers`, `object_render(ids)`, `object_image(label)`, `read_table`, `save_table`, `insert_figure`, `trust_figure`, `figure_run_start/status/cancel`, `build_table`, `suggest_latex`, `suggest_plot_code`, `research_checks`, `export_research_start` (gated by `blocking(run_checks(...))`); all `@bridge`, network and script runs outside `self._lock` | `tests/test_gui_research.py`, signature and mock-name tests, fiction `link_spans` output byte-identical | Sonnet | M |
| P8a | GUI: sources and sync review | `gui/src/components/research/` Sources and SyncReview | P7 JSON shapes | uses only P7 | vitest | Sonnet | L |
| P8b | GUI: WYSIWYG objects | CodeMirror widgets in `editor/cm.ts` (`objectsField`, `setObjects`) for figure, table (modal grid editor calling `read_table`/`save_table`), equation (KaTeX, hardened options), reference previews, script confirmation dialog | P7 | uses only P7 JSON; widget `eq()` on (label, content hash); sized placeholders; block placements atomic with Move/Remove; `softBreaks` treats `![[...]]` as a hard break | vitest incl. widget `eq`, KaTeX rejection of untrusted input; **acceptance:** typing in a scene with 5 figures does not re-create image DOM (measured) | Sonnet; Opus reviews the StateField changes | L |
| P9 | Terminal app minimum | `tui/researchmixin.py`, export screen options | P3 to P6 | palette `Action` entries, citation highlighting, placeholders | Pilot tests | Sonnet | M |
| P10 | Docs, packaging, fixtures | CHANGELOG, `packaging/chisel.spec`, `selftest.py`, workspace fixture regeneration | all | none | packaging and selftest tests | Haiku | S |

## Waves and merge order

- Wave 0: P0 (writes and freezes the contracts file). Wave 1 in parallel: P1, P2, P4, P4c. Wave 2 in
  parallel: P3 (after P1, P2), P4b (after P4), P5 (can start on the P0 contracts with stubbed numbering),
  P6 (after P3). Wave 3: P7. Wave 4 in parallel: P8a, P8b, P9. Wave 5: P10.
- Merge order: P0, P1, P4, P4c, P4b, P2, P3, P6, P5, P7, P8a, P8b, P9, P10. One git worktree per package;
  the full suite runs at each merge.
- **Gate:** P4b, P7 and P8b do not start until the plan's section 7.4 trust and execution rules and the
  table ownership rules are in the contract (they are, as of draft 3).

## Acceptance criteria (beyond each package's tests)

- P1: a Concept note named like a key cannot shadow it; `[[smith2024]]` (no `@`) still resolves as an
  ordinary link; citations never appear as unresolved links or in "create note" offers.
- P3: a re-sync never changes text outside the zotero markers (byte comparison); a sync interrupted halfway
  leaves every note valid.
- P4b: a cloned project with an edited script prompts again; a cloned project containing a trust record or
  its own interpreter does not run; a failed run leaves the old PNG byte-identical.
- P5: fiction exports are byte-identical before and after; a research export with a citation, a figure, a
  table and an equation opens in Word with a native equation and a bibliography.
- P7: no bridge method holds `self._lock` across a network call or a script run.
- P8b: widget DOM is not re-created while typing in a scene with five figures (measured).

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
