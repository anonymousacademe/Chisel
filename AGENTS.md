# AGENTS.md — guide for AI assistants working on lorewrite

Read this before changing anything. [SPEC.md](SPEC.md) is the source of truth
for design; this file is the operational guide.

## Project in one paragraph

lorewrite is a terminal fiction-writing app (Python 3.11+, Textual). Scenes
are plain Markdown files; characters/places are Markdown notes with small YAML
frontmatter; `[[wiki-links]]` connect them; a SQLite index (a rebuildable
cache, never the truth) powers backlinks; AI features go through OpenRouter
and are **suggest-and-confirm only — AI never edits prose unprompted**.

## Repo layout

```
SPEC.md                 # master design doc — update it when design changes
README.md               # user-facing intro
src/lorewrite/
  core/                 # pure Python, no Textual — fully unit-testable
    links.py            # [[link]] parsing, plain-name mentions, offset<->rowcol
    entities.py         # entity notes: frontmatter, aliases, resolve, add_alias
    project.py          # project layout, entities, settings (Project mixes in Structure)
    structure.py        # parts (folders), unplaced scenes, trash, scene moves/renumbering
    snapshots.py        # .snapshots/: create/list/restore/delete, daily auto, word diff
    sync.py             # optional git: status (read-only), commit, push, init — explicit only
    scenemeta.py        # scene details = YAML frontmatter: find/strip/blank/set_details
    index.py            # SQLite backlink index; no-ops after close()
    recents.py          # recent projects; LOREWRITE_STATE_DIR env override
    settings.py         # user settings (tour_seen, ...)
    style.py            # style.md (project root): load/save/backup, manuscript sampling
    drafts.py           # pending AI text markers (<!--ai-->), expand markers
    spelling.py         # spell check: check/suggestions, accepted terms, dictionary files
    collections.py      # collections: definitions in project.toml, membership in scene frontmatter
  ai/
    client.py           # OpenRouter via openai SDK; keyring/env key resolution
    links.py            # alias finder (ctrl+l): prompt, schema, validate (never edits text)
    usage.py            # AI spend ledger (usage.cost) -> status bar
    style.py            # learn a style guide from sampled prose
    writing.py          # draft / expand / rewrite: context builder + plain-text generate
  gui/                  # desktop GUI backend (pywebview); no Textual
    api.py              # Api: JSON bridge (every method -> {ok,...}); facade() = js_api
    workspace.py        # Project -> Workspace JSON for the React UI
    devserver.py        # headless: gui/dist + POST /api/<method> (+ --mock-ai)
    mockai.py           # canned AI for screenshots/demos (never the real app)
    app.py              # lorewrite-gui: pywebview window
  tui/                  # everything Textual
    app.py              # LorewriteApp: layout, save, status, actions, AI wiring
    editor.py           # LinkedTextArea — see "fragile spots" below
    sidebar.py panels.py launch.py commands.py linkreview.py (alias review)
    structurescreens.py (part picker, Trash, scene details form)
    spellscreen.py (f6 fix window)
    stylereview.py promptscreen.py tour.py theme.py
gui/                    # React/TS front end (see gui/README.md); src-tauri/ is unused
tests/                  # pytest; asyncio_mode=auto; Pilot for TUI tests
docs/ux-review-glm.md   # independent UX review (source of the M1.5 polish)
docs/plan-workspace.md  # the four-wave feature plan (Wave 1 = parts/trash/details/reorder)
docs/specification-guide.md  # M3–M8 implementation guide for parallel agent
                             # execution (contracts, workstreams, ownership)
```

## Commands

```bash
.venv/bin/pip install -e ".[dev]"   # after pulling
.venv/bin/python -m pytest          # full suite (must stay green)
.venv/bin/lorewrite                 # run the app
```

GUI (branch `gui`; plan: docs/plan-gui.md, spec: SPEC "Desktop GUI"):

```bash
python3 -m venv --system-site-packages .venv-gui && .venv-gui/bin/pip install -e ".[dev,gui]"
(cd gui && npm install && npm run build && npm run lint && npm test)
.venv-gui/bin/lorewrite-gui [--project PATH]
PYTHONPATH=src .venv-gui/bin/python -m lorewrite.gui.devserver --project COPY --mock-ai   # headless
```

## Non-negotiable principles (from SPEC §2)

1. Plain text, always — a project is a folder of Markdown; no database blobs.
2. The index is a rebuildable cache (`f9`); files are the truth.
3. AI suggests, never edits — every AI feature ends in an accept/reject UI.
4. Entity notes = free text + minimal YAML frontmatter (name, type, aliases).

## Fragile spots — read before touching

- **`tui/editor.py` uses private Textual APIs** (`_render_line`, `_line_cache`,
  `wrapped_document._offset_to_line_info`) to highlight `[[links]]`. Every use
  is wrapped in try/except with a plain-TextArea fallback.
  `tests/test_tui.py::test_link_highlighting_styles` locks the behavior — if it
  fails after a Textual upgrade, the internals moved.
- **Never name a method `_render` on a Widget** — it shadows Textual's
  internal `Widget._render()` and crashes rendering (bit us in the sidebar;
  the filter helper is `_render_lists`).
- **Widget IDs must be unique app-wide** — two `id="empty-hint"` items broke
  the DOM; use CSS classes for repeated things.
- **Rich markup eats brackets**: any dynamic label containing user text
  (`[character]`, `[[link]]`) must be wrapped in `rich.text.Text(...)`, never
  passed as a plain string to `Label(...)`.
- **Teardown races**: autosave timers can fire during shutdown. Widgets are
  held as direct refs (no `query_one` in save paths), timers are stopped in
  `on_unmount`, the final save skips UI updates, and `Index` no-ops after
  `close()`. Regression: `test_teardown_with_pending_autosave_does_not_crash`.
- **Deleting the open scene**: detach `current_path` BEFORE calling
  `open_file`, or autosave resurrects the deleted file (regression-tested).
- **ListView swallows Enter** — modal screens with a ListView must handle
  `on_list_view_selected` if Enter should confirm (see AliasReviewScreen).
- **Manuscript structure** (`core/structure.py`; SPEC "Manuscript structure"):
  - Never assume a flat `manuscript/`. `Project.list_scenes()` is the book in reading order
    (recursive, **excludes** `_unplaced/`); `all_scene_files()` adds Unplaced (the index covers
    it); `counted_scenes()` also drops front matter (use it for word totals and style
    sampling); `is_scene_path()` is the test for "is this a scene" (not `path.parent ==
    manuscript_dir`). `_part.md` and dot/underscore names are never scenes.
  - **Draft sidecars are keyed by project-relative path** (`manuscript__02-x__01-a.md.json`);
    never build `.drafts/<name>.json` by hand — `drafts.sidecar_path`. Every move, rename and
    trash must carry the sidecar: use `Structure._apply_renames` (two-phase, so swaps and
    cycles do not collide) and read `Project.last_renames` to follow files in a UI.
  - Deleting a scene is `Project.delete_scene` = **move to `.trash/`** (restore with
    `restore_scene`); there is no permanent delete except `delete_forever` / `empty_trash`,
    which UIs must confirm. Keep detaching `current_path` before opening the next scene.
  - `place_scene(path, part, index)` renumbers only the destination; ids of other scenes in it
    change, so the GUI's `place_scene` / `move_scene` / `move_part` return a `remap`
    ({old id: new id}) and the client reopens the open document through it.
- **Snapshots are author data** (`.snapshots/<sidecar key>/<stamp>[--label].md` + optional
  `.json` of draft originals; `core/snapshots.py`). Everything that moves or trashes a scene must
  carry the folder (`snapshots.stage/unstage/archive/unarchive`, already wired into
  `Structure._apply_renames`, `move_part`, `delete_scene`, `restore_scene`). Never build the path
  by hand (`snapshots.scene_dir`); snapshot ids come over the GUI bridge, so go through
  `snapshots._file` (it refuses anything that is not a plain id). Whole-scene destructive ops
  (restore, accept/reject-all) call `snapshots.create` with the editor buffer first; the daily
  auto snapshot (`ensure_daily`, setting `auto_snapshot`) runs in both save paths *before* the
  write and must never block a save. `snapshots._daily_done` is a per-process cache — tests clear it.
- **Collections** (`core/collections.py`). Membership is scene frontmatter, so a rename or delete
  rewrites many files: the GUI flushes the open scene first and reopens it when its id is in the
  bridge's `changed`; the TUI re-reads its buffer (`_collection_op`; never `open_file`, which
  saves the stale buffer over the rewritten file). `Collection.declared` false = used by scenes
  but not in `project.toml`; never hide those. Collection names in TOML keys are written with
  `json.dumps` (valid TOML basic strings).
- **Git sync is explicit** (`core/sync.py`). `status()` is the only call that may run by itself
  (read-only, 5 s timeout, never on the UI thread: TUI worker, GUI debounced bridge call outside
  `self._lock`; `get_workspace` must not call it). `commit` / `push` / `init` run only from a
  click or palette pick; push never forces and the UI confirms it, naming the remote. Always
  run git with `cwd=project root` and pathspec `.`. Tests must use a temp repo + local bare
  remote and the `isolated_git` fixture (`GIT_CONFIG_GLOBAL/SYSTEM=/dev/null`, identity from
  env) — never the real repository the tests run in.
- **Scene details are frontmatter, not prose.** Anything that counts words, scans names,
  spell-checks, samples style or sends scene text to an AI must skip the block:
  `scenemeta.strip` (drop), `scenemeta.blank` (same-length whitespace so offsets and rows
  survive; `keep=("pov","place")` leaves those values visible so they count as mentions),
  `drafts.count_words` already strips it. In the GUI the editor hides it (`sceneFrontmatter`
  in `editor/spans.ts` mirrors `scenemeta.find`; keep them in step) and Python returns the
  edit for it (`set_scene_details`), never TypeScript.
- **Pending AI drafts live in the scene file** as `<!--ai-->…<!--/ai-->`
  comments (`core/drafts.py`); text a draft replaced is in the sidecar
  `.drafts/<scene>.json` (author data, moved/deleted with the scene; reject
  refuses if the original is missing). Anything that sends scene text to an AI or
  counts words must go through `drafts.strip_pending` (unaccepted AI text is
  not canon). Generated text is only ever inserted wrapped, never bare.
- **`f7` is TextArea's select-all**: `LinkedTextArea.BINDINGS` overrides it
  (f7/f8 accept/reject a draft, `f5` select-all). Focused-widget bindings beat
  App bindings, so a new App key that collides with a TextArea binding must be
  re-bound on the editor too. `ctrl+g` (generate) is free in TextArea and is
  also the submit key of `PromptScreen`.
- The writing model may lack structured outputs: `ai/writing.py` and
  `ai/style.py` never send `provider.require_parameters`.
- **Spell check** (`core/spelling.py`, spelling only — never grammar). The engine
  (`pyspellchecker`) stays behind `_Engine`. `check` returns code-point offsets; the
  GUI converts with `core.spans.to_utf16`. Never spell-check on the UI thread for a
  whole scene: the TUI uses a worker + 0.6 s debounce, the GUI a debounced bridge
  call (`Api.spelling`, computed outside `self._lock`). `dictionary.txt` (project
  root) is author data: not a scene/entity, never indexed — `tui/app.py` skips it
  like `style.md`, `Api._doc_kind` gives it kind `dictionary` (GUI renders it as
  plain text: no Markdown, title block or reflow). `f6` is TextArea's select-line;
  `LinkedTextArea.BINDINGS` overrides it. The GUI editor turns the browser's native
  `spellcheck` off (ours is the only one).
- **Terminal key limits**: `ctrl+[` IS Escape; `ctrl+enter` doesn't reach most
  terminals. Scene nav is `alt+←/→`, writer mode is `f11`.
- **Command palette**: providers must implement `discover()` (else the palette
  opens empty) and treat empty queries as match-all (`Matcher.match("")`
  raises). Wrap entry generation in try/except so one bad provider can't blank
  the palette (`_Provider._safe_entries`).

## GUI fragile spots — read before touching

- **The GUI never re-implements project logic in TypeScript.** Matching, parsing,
  drafts, canon, waivers, models, cost: add it to `core/`/`ai/` (with tests, usable
  by the TUI) and expose it through `gui/api.py`. `tui/app.py` and `gui/api.py`
  share helpers — change both callers when you change one.
- **pywebview recurses into every public attribute of `js_api`.** Hand it
  `Api.facade()` (bridge methods only), never the `Api` (it holds `project`/`index`).
  Every bridge method must be `@bridge` (returns `{ok,...}`, never raises) and every
  method that touches the project takes `self._lock` — but **release it before any
  AI network call** (a held lock freezes saves).
- **Offsets crossing the bridge are UTF-16** (CodeMirror); Python slices are code
  points. Use `core.spans.to_utf16/from_utf16/index_to_utf16`; astral characters
  are tested.
- **Draft markers**: `register_draft` (sidecar) must succeed **before** the editor
  writes `<!--ai id="…"-->`; reject with a missing original is skipped, never a
  delete. Saves never recreate a deleted scene (`save_document` needs the file);
  the client `detach()`es the `SaveController` before deleting.
- **Autosave vs the TUI**: saves carry the file's `mtime` (ns, as a string);
  a mismatch with different text is a conflict, never a silent overwrite.
- **CodeMirror decorations live in one `StateField`** (`editor/cm.ts`): block
  widgets and line-break-spanning replaces cannot come from a `ViewPlugin`.
  Hard-wrapped lines are joined by replacing the `\n` with a space widget (display
  only); never edit the file to "fix" wrapping.
- **Placeholders** use `components/placeholder.ts` only. Do not invent a second
  treatment, and do not show fake data in them.
- **Dev-only fakes**: `mockai.py` and `backend/mock.ts` must never be reachable in
  the real app; tests booby-trap `make_client`. Screenshots/interaction tests run
  headless Chromium against `devserver` on a *copy* of `examples/residual` with
  `LOREWRITE_STATE_DIR` pointed at a temp dir and the keyring backend nulled.
- Key map differences from the TUI: `ctrl+j` in the GUI editor opens/makes a note
  (elsewhere it focuses the composer, as designed); `ctrl+k` quick switcher; `f11`
  focus mode.

## Testing conventions

- `tests/conftest.py` isolates app state per test via `LOREWRITE_STATE_DIR`
  and pre-marks the tour as seen. New user-state features must honor the env
  override.
- TUI tests use `app.run_test(size=(120, 40))` + `pilot`; call
  `await pilot.pause()` after actions before asserting.
- Mock AI at the function boundary: monkeypatch `lorewrite.tui.app.<ai_fn>`
  (see `tests/test_ai_links.py`) or, for the GUI, `lorewrite.gui.api.<fn>`
  (see `tests/test_gui_ai.py`). Never hit the network in tests.
- GUI: `tests/test_gui_*.py` + `tests/test_spans.py` (plain pytest, temp projects via
  `tests/gui_helpers.py`); `gui/src/**/*.test.ts` (vitest). The workspace JSON
  fixture `gui/src/data/fixtures/workspace.json` is regenerated with
  `LOREWRITE_REGEN_FIXTURE=1 pytest tests/test_gui_workspace.py`.

## Workflow requirements

- **Keep SPEC.md current** when design/scope/decisions change (it's the master
  document; README mirrors it for users).
- **jev review before reporting code tasks done** (user's global instruction):
  diff only the files you changed into `~/.config/jev/jev.py review --task
  "..." --files ...`. HOLDs on `network` (OpenRouter client) and
  `out_of_scope` (state files in ~/.local/state, ~/.config/omarchy) are
  standing, expected, and acknowledged by the user — report scores, don't
  reword to dodge.
- No emojis in the UI or docs unless the user asks. Category prefixes use
  `Scene · / Entity · / Link · / Action ·` text.
- Commits only when the user asks. Match existing style; minimal diffs.

## Current state & what's next (2026-10-01)

Done: M1 (editor+links), M1.5 (UX polish from the GLM review), M2 (alias
finder), M3 (continuity + Contextual Tracker), settings screen, bracket-free
implicit mentions (SPEC §5), AI spend tracking, **M4** (style guide, `ctrl+g`
draft/expand/rewrite, pending AI drafts with `f7`/`f8`; see
docs/plan-m4-ai-writing.md). **Desktop GUI** (branch `gui`, docs/plan-gui.md):
pywebview shell, real binder/editor/notes/AI over the same core, placeholders for
the parts of the design LoreWriter does not do yet.
Spell check (offline, spelling only, personal + project dictionaries) is in both
front ends (docs/plan-spelling.md, SPEC M6).
**Wave 1 of docs/plan-workspace.md** (branch `features`): parts, Unplaced Scenes,
Trash, scene details (frontmatter), GUI drag-to-reorder. Waves 2-4 (snapshots/drafts/
sync, collections/comments/research/chat history, stats/timer/brainstorm) are not built.
Known concern: user is unconvinced by the command palette as primary UI
(SPEC §11b) — the GUI is the answer being tried.
