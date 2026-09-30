# Plan: desktop GUI (pywebview + the Figma React UI)

Status: approved 2026-09-30. Implementer: one agent, branch `gui` in worktree
`~/lorewrite-gui` (based on `m4-ai-writing`). Read `AGENTS.md`, `SPEC.md`
("Future direction — Obsidian-like GUI"), `gui/README.md` (the Figma
handoff), and look at `gui/design/figma-reference.png` before starting.

## Decisions already made by the author

1. **Shell: pywebview**, not Tauri. Python opens a native WebKitGTK window
   showing the React UI; the UI calls the Python core in-process through
   pywebview's `js_api`. Keep `gui/src-tauri/` in the tree untouched and
   unused (a possible later packaging path); do not build or delete it.
2. **Scope: the full design, with placeholders.** Every panel, control and
   view in the Figma design appears. Anything Lorewrite really does is wired to
   the real core. Anything it doesn't do yet is a visible **placeholder**:
   rendered as designed but disabled, with a tooltip "Not in LoreWriter yet"
   (one shared `Placeholder`/`disabled` treatment — never fake data that looks
   real, never a control that silently does nothing).
3. **Base: `m4-ai-writing`**, so the GUI has drafts, style guide, alias
   finder, cost tracking from day one.

## Non-negotiables

- `core/` and `ai/` stay the single source of truth; the GUI never
  re-implements project logic in TypeScript (matching, parsing, file writes).
  If the GUI needs something new, add it to `core/`/`ai/` with tests, usable by
  the TUI too. The TUI keeps working unchanged (full pytest suite green).
- SPEC §2 principles hold: plain Markdown files; AI suggests, never edits
  unprompted (every AI output is either chat text or a pending draft in the
  existing `<!--ai-->` format with accept/reject); index is a cache.
- Never hit the network in tests; mock AI at the function boundary.
- No emojis. Product name in the GUI chrome is "LoreWriter" (as designed);
  fix the design's stray "Muse can be wrong…" to "LoreWriter can be wrong.
  Review changes before applying."

## Environment

- A dedicated venv that can see the system's PyGObject/WebKit2 4.1 bindings
  (system Python 3.14.7 has `gi` + `WebKit2 4.1`; building PyGObject from
  source is not possible here — no gobject-introspection dev package):
  `python3 -m venv --system-site-packages ~/lorewrite-gui/.venv-gui`
  then `~/lorewrite-gui/.venv-gui/bin/pip install -e "~/lorewrite-gui[dev,gui]"`.
  Add `.venv-gui/` to the repo `.gitignore`.
- `pyproject.toml`: optional dependency group `gui = ["pywebview>=6"]`;
  console script `lorewrite-gui = "lorewrite.gui.app:main"`.
- Frontend: Node 26 / npm 11 are installed. `cd gui && npm install`,
  `npm run build` (must pass `tsc -b`), `npm run lint` (oxlint).
  `gui/dist/` stays git-ignored; `lorewrite-gui` exits with a clear message if
  `gui/dist/index.html` is missing ("run `npm run build` in gui/").
- Rust is NOT installed and must not be installed.

## Architecture

```
src/lorewrite/gui/
  __init__.py
  app.py        main(): argparse (--project PATH, --dev URL), create the
                pywebview window (frameless, 1600x1000, min 1280x760, bg
                #121318, drag region), serve gui/dist, expose Api
  api.py        class Api — every method JSON-in/JSON-out, thread-safe
                (pywebview calls js_api methods on worker threads: guard
                project writes with one RLock). No pywebview import here, so
                it is unit-testable with plain pytest.
  workspace.py  pure builders: Project -> Workspace JSON (binder, documents,
                status) matching gui/src/data/types.ts (extend the types as
                needed; keep TS and Python shapes in sync, with one JSON
                fixture test on each side)
  devserver.py  `python -m lorewrite.gui.devserver --project P`: serves
                gui/dist + a POST /api/<method> JSON bridge onto the same Api,
                for headless-browser screenshots and debugging (localhost
                only, random free port printed on stdout)
gui/src/backend/index.ts
                add a pywebview backend (window.pywebview.api.*, wait for the
                `pywebviewready` event) and an HTTP backend for devserver;
                keep the mock backend for `npm run dev`
```

### Api surface (grow as needed; every call returns `{ok, ...}` or
`{ok: false, error}` — never raise across the bridge)

- Project: `open_project(path)`, `recent_projects()`, `new_project(title,
  path)`, `get_workspace()`.
- Scenes: `read_document(id)` → text + mtime; `save_document(id, text,
  base_mtime)` → atomic write via core, re-index; returns `conflict` if the
  file changed on disk since `base_mtime` (the TUI may be open on the same
  project) instead of overwriting; `new_scene(title)`, `rename_scene`,
  `move_scene(delta)`, `delete_scene` (sidecar-aware, see `.drafts/`).
- Mentions: `link_spans(id, text)` → spans for plain mentions, explicit links
  (with the bracket sub-ranges), unresolved links, `{{expand:}}` markers and
  pending drafts — computed by `core.links` / `core.drafts`, so matching is
  never duplicated in TS. The editor calls it debounced (~150 ms).
- Entities: `list_entities()`, `get_entity(name)` (note body + canon +
  backlinks), `create_entity(name, type)`, `add_alias`.
- AI: `find_aliases(id)`, `check_continuity(id)`, `waive(key)`,
  `restore_waivers(id)`, `propose_canon(id)`, `apply_canon(facts)`,
  `learn_style()`, `save_style(text)`, `generate(mode, instruction, id,
  cursor, selection)` → inserts nothing itself; returns the wrapped draft text
  + range for the editor to insert (reuse `ai/writing.py` and the `.drafts/`
  sidecar exactly as the TUI does — factor shared helpers out of
  `tui/app.py` into `core/`/`ai/` rather than copying them), `accept_draft`,
  `reject_draft`, `ask(prompt, scope, id)` (see Assistant below),
  `usage()` (session cost).
- Settings: `get_settings()`, `set_settings(...)` (fast / strong / writing
  model, editor prefs), `set_api_key(key)`, `clear_api_key()`,
  `list_models(structured_only)`.
- Window: `minimize()`, `toggle_maximize()`, `close()` (flush saves first).

## Editor

Replace the design's paragraph-array editor with **CodeMirror 6**
(`@codemirror/view`, `state`, `lang-markdown`, `commands`, `history`),
styled to match the design exactly (Source Serif 4 prose, measure, chapter
kicker + title + meta line + violet rule, paragraph spacing, revised-passage
left rule style for pending drafts).
- The file is plain Markdown; the first `# heading` is the scene title and is
  rendered as the design's big title block (kicker "SCENE 02" from the
  filename prefix; meta line from placeholders unless real).
- Decorations from `link_spans`:
  - plain mentions: link color, no underline; hover shows a small note card;
    `ctrl+click` opens the entity in the Notes tab.
  - explicit `[[links]]`: **hide the brackets** (and `Name|`) with replace
    decorations except when the cursor is inside the link (Obsidian live
    preview) — the author dislikes seeing brackets. Unresolved links in the
    unresolved color.
  - pending AI drafts: **hide the `<!--ai…-->` markers entirely**; body in
    the draft style (the TUI's teal italic + tint, adapted to the design's
    tokens) with an inline Accept / Reject widget; `f7` / `f8` still work.
  - `{{expand: …}}` markers styled as a chip.
- Autosave debounced 1.5 s + on blur/close; `ctrl+s` saves now; the title bar
  "Saved" indicator reflects real state; a conflict shows a banner (reload /
  keep mine).
- Toolbar: undo/redo real; bold/italic insert `**`/`*` Markdown; link button =
  "make a note from selection" (the TUI's select + `ctrl+j`); comment button =
  placeholder; focus mode real.

## Mapping the design to real features

| Design element | GUI v1 |
|---|---|
| Title bar: project / scene breadcrumb, Saved, search, panel toggles, window controls | Real (search = quick switcher over scenes + entities, `ctrl+k`) |
| Title bar "Draft 2" badge | Placeholder |
| Activity rail: Binder, Search, Assistant, Library | Real (Library = entity browser) ; the two empty slots stay empty as in Figma |
| Rail: history (snapshots) | Placeholder |
| Rail: settings | Real — Settings modal: API key (paste works), fast / strong / writing model with a searchable model list (structured-only for fast/strong, full catalog for writing), editor prefs |
| Rail: avatar | Real initials from `project.toml` author (fallback "LW") |
| Binder: project root, word counts | Real |
| Binder: Parts (Part I/II/III) and Front Matter | Placeholder rows (disabled) — scenes are flat in Lorewrite; show real scenes under a "Manuscript" node in order |
| Binder: Characters, World Bible (places, objects, factions) | Real, from entity notes; clicking opens the note |
| Binder: Style Guide | Real (`style.md`), add as an item |
| Binder: Research, Unplaced Scenes, Trash | Placeholders |
| Binder: new document button | Real = new scene; "…" menu: rename / move up / move down / delete (confirm) |
| Collections (Needs continuity pass, …) | Placeholder |
| Editor tabs: Manuscript | Real |
| Corkboard | Real, read-only: one card per scene (title, first lines, word count); click opens. Drag-reorder = placeholder |
| Outline | Real, read-only: scenes with headings and word counts |
| Context bar: breadcrumb, words / target, "Revising" status | Words real; target and status placeholders |
| Inspector: Status, POV / Place, Scene purpose | Placeholders |
| Inspector: Session | Real: words written this session, minutes open |
| Assistant: Quick actions Rewrite, Continuity | Real (rewrite selection → pending draft; continuity check) |
| Quick actions Brainstorm, Research | Placeholders |
| Continuity insight card: Review passage / Dismiss | Real (jump to evidence line / waive) — one card per reported issue, conflicts count real |
| Assistant composer + chat | Real, see below |
| Retrieved context list | Real: entities mentioned in the scene + their backlinks |
| Tabs Context / Notes | Real: Context = retrieved context; Notes = the entity note under the cursor or picked in the binder (read, and edit in the editor) |
| Also real, not in the design: Find aliases, Update story bible (per-fact review), Learn style guide, Accept/Reject all drafts | Add as Assistant quick actions / a "More" menu in the Assistant header, styled like the design |
| Status bar: Ln/Col, zoom, project words, session words (target placeholder) | Real |
| Status bar: "Draft 2", snapshot, "Project synced", streak | Placeholders |
| Status bar: AI cost | Real, add (`AI $0.0123`) |

### Assistant chat (`ask`)

The composer is the centre of the design, so it is wired, conservatively:
`ai/writing.py::ask(prompt, scope, context, model)` (new, writing model)
answers **in the chat only**, using the existing context builder (style guide,
scene around the cursor, canon of mentioned entities; `scope` = "Current
scene" chip, or "Project" = all scene titles + entity canon, capped). Replies
never touch the manuscript. Each reply offers "Insert as draft" (inserts it at
the cursor as a pending `<!--ai-->` draft) plus the design's copy /
regenerate / like (like = placeholder). Chat history is per session, in
memory only.

## Phases (commit each on `gui`; suite green after each)

0. **Shell up.** venv, pyproject extras + script, `gui/app.py` opens the
   built UI with mock data inside pywebview; devserver; `npm run build` and
   `lint` pass. Delete nothing from the handoff except replacing what is
   superseded.
1. **Api + workspace + real binder/documents** (read-only), backend
   adapters in TS. Placeholder primitive and treatment everywhere.
2. **Editor** (CodeMirror 6, decorations via `link_spans`, autosave,
   conflict handling, toolbar), scene management.
3. **Entities & notes** (Notes/Context tabs, hover cards, make-note, library).
4. **AI features** (continuity cards, alias finder, story bible, style guide,
   generate + inline accept/reject, ask/chat, cost in status bar).
5. **Settings modal, window controls, corkboard/outline, status bar, polish**
   against the Figma screenshot.
6. **Docs:** SPEC (GUI section replacing "Future direction"), README (install
   + run `lorewrite-gui`), AGENTS.md (layout, commands, GUI fragile spots),
   `gui/README.md` rewritten for pywebview. Optional: Omarchy launcher line.

## Verification

- Python: pytest for `api.py`/`workspace.py`/new core helpers (temp projects,
  AI mocked, conflict detection, thread-safety smoke with concurrent saves).
  Full suite: `PYTHONPATH=src ~/lorewrite-gui/.venv-gui/bin/python -m pytest -q`.
- Frontend: add `vitest` for pure TS units (span → decoration mapping,
  backend adapters with fake bridges); `npm run build`, `npm run lint`.
- **Visual:** run `devserver` on a *copy* of `examples/residual` with AI
  mocked (an env flag in devserver that patches the AI functions with canned
  results is fine — never real calls), capture with headless Chromium
  (`chromium --headless --screenshot=… --window-size=1600,1000 URL`), and
  compare side by side with `gui/design/figma-reference.png` after each of
  phases 2, 4 and 5. Look at every screenshot; fix visible divergences.
  Do **not** open pywebview windows on the author's desktop except one final
  smoke launch at the end (close it yourself).
- Jev review per chunk at the end (diff vs `m4-ai-writing`); report verdicts.

## Rules

Work only in `~/lorewrite-gui`. Never modify `~/lorewrite`, `~/lorewrite-m4`,
`~/lorewrite-demo`. Commit per phase on `gui` only; never commit to `main` or
`m4-ai-writing`; never push. Write the final report (per-phase summary, how to
run, placeholder inventory, deviations, Jev results, known limitations) to
`/tmp/gui-report.md` and reply with the path.

## As built — deviations from this plan

Kept here so the next agent knows where the code differs from the text above.

- **Commits.** Phases 1-3 share one commit (developed together); the Phase 6 docs commit
  precedes the Phase 5 code commit. Content per phase is as described below.
- **Drafts API.** `generate` returns the wrapped draft and the range it replaces (as planned) but
  the replaced original is stored by a separate `register_draft` call the editor makes *before*
  it writes the marker, so a discarded draft leaves no sidecar entry. `accept_draft`/`reject_draft`
  became one `resolve_drafts(doc, text, accept, index|None)` (one draft or all; returns editor
  edits, skips a reject whose original is missing). Added `draft_from_reply` (chat "Insert as
  draft"), `apply_aliases`, `apply_canon`, `ensure_style`, `scene_context`, `ai_status`.
- **Title block.** The `# heading` line is drawn *as* the big title inside CodeMirror (editable in
  place, its `# ` hidden); the kicker is React above it and the mentions line + violet rule is a
  block widget under it. Entity notes and files without a heading get a React title instead.
- **Design annotations removed.** The comment/sparkle markers in the page gutter were mock
  annotations at fixed positions; drawing them would be fake data. Comments remain a placeholder
  toolbar button.
- **Binder.** Parts are three generic placeholder rows "Part I/II/III" (the design's titles are
  sample content). The Style Guide item is always listed; opening it before `style.md` exists
  creates the stub, as the TUI does.
- **Ctrl+J.** The design shows "Ctrl J" focusing the composer; the TUI uses it to open/make a
  note. In the editor it opens/makes a note when a name is selected or under the cursor, and
  otherwise falls through to focus the composer.
- **Make note** does not navigate away: the new note appears in the Notes tab (the TUI opened it
  in the editor). "New note" from the Library view does open it.
- **Hard-wrapped Markdown** (the terminal app's files, the example project) is displayed reflowed
  (newline drawn as a space, display only) with a Settings toggle. Not in the plan; needed for real
  projects.
- **Editor prefs** in Settings are GUI-specific (text size, reflow) rather than the TUI's padding
  and line numbers.
- **Core changes beyond factoring.** `find_mentions` overlap resolution and `Index.update_file` row
  lookup were quadratic (a dense 42k-word scene took ~4 s per call); both are fixed and covered by a
  property test against the old algorithm. `locate_evidence` now finds quotes that span hard-wrapped
  lines. `Index(check_same_thread=False)` for the GUI's worker threads.
- **Bridge.** pywebview gets `Api.facade()` (bridge methods only). Deliberate errors (`ValueError`,
  `FileNotFoundError`, ...) reach the UI as plain messages; other exceptions keep their class name.
  The devserver accepts only `application/json` POSTs.
- **Session words** are the net change since the project was opened (may be negative); minutes are
  time since it was opened.
- **Tauri.** The `@tauri-apps/api` npm dependency (only the deleted Tauri adapter used it) was
  removed; `@tauri-apps/cli` and `src-tauri/` are untouched.
- **Not done / limits.** No component-level React tests (vitest covers pure logic; interaction was
  checked with headless Chromium against the devserver). The window-manager close button does not
  do a synchronous final save (1.5 s autosave + blur/pagehide flush cover it). The 5 remaining
  `oxlint` warnings are React-compiler style hints, not errors.
