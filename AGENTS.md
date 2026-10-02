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
    recents.py          # recent projects; state dir = platformdirs (Linux ~/.local/state/lorewrite); LOREWRITE_STATE_DIR env override
    soundpacks.py       # typing-sound packs + ambience loops in the user DATA dir (LOREWRITE_DATA_DIR in tests); zip import/export validation
    atmosphere.py       # sound prefs + radio stations in user settings (http(s) only)
    desktop.py          # open_path: os.startfile / open / xdg-open (only on a click)
    fsutil.py           # replace/rename with a short retry (Windows PermissionError); use instead of Path.replace
    settings.py         # user settings (tour_seen, ...)
    style.py            # style.md (project root): load/save/backup, manuscript sampling
    drafts.py           # pending AI text markers (<!--ai-->), expand markers
    spelling.py         # spell check: check/suggestions, accepted terms, dictionary files
    collections.py      # collections: definitions in project.toml, membership in scene frontmatter
    comments.py         # comments: .comments/<scene>.json, anchored by quote + context
    research.py         # research/ notes: list/new/from-url/delete, keyword search, assistant-notes
    chats.py            # saved assistant chats: .assistant/chats/<id>.json
    attach.py           # chat attachments (scene/note/research/comments), capped and reported
    stats.py            # writing stats/streak/sprints: Tracker, state dir stats/<project-id>.json
    inspiration.py      # inspiration/ pictures + .md sidecars: save/list/update/pin, scene-link remap
    rename.py           # rename an entity everywhere: plan (read-only) / apply (snapshots first) / undo
    export/             # M7: manuscript.py (assemble -> Book), layouts/ (PDF: book, manuscript, plain),
                        #   pdfkit.py (fonts), markdown.py, pandoc.py, __init__.py (run_export, options)
  ai/
    client.py           # OpenRouter via openai SDK; keyring/env key resolution
    links.py            # alias finder (ctrl+l): prompt, schema, validate (never edits text)
    usage.py            # AI spend ledger (usage.cost) -> status bar
    style.py            # learn a style guide from sampled prose
    writing.py          # draft / expand / rewrite: context builder + plain-text generate
    images.py           # inspiration pictures: generate (OpenRouter image output), suggest_prompt
  gui/                  # desktop GUI backend (pywebview); no Textual
    api.py              # Api: JSON bridge (every method -> {ok,...}); facade() = js_api
    workspace.py        # Project -> Workspace JSON for the React UI
    devserver.py        # headless: built UI (gui/web/, see webroot.py) + POST /api/<method> (+ --mock-ai)
    mockai.py           # canned AI for screenshots/demos (never the real app)
    inspiration.py      # bridge helpers for the inspiration images (rows, data URLs, save batch)
    app.py              # lorewrite-gui: pywebview window
    webroot.py          # finds the built UI: package web/ first, then repo gui/dist
    exports.py          # export worker-thread jobs (export_start / export_status)
  tui/                  # everything Textual
    app.py              # LorewriteApp: layout, save, status, actions, AI wiring
    editor.py           # LinkedTextArea — see "fragile spots" below
    sidebar.py panels.py launch.py commands.py linkreview.py (alias review)
    structurescreens.py (part picker, Trash, scene details form)
    inspirationmixin.py inspirationscreens.py (inspiration images: LorewriteApp mixin + modals)
    spellscreen.py (f6 fix window)
    stylereview.py promptscreen.py tour.py theme.py
    exportscreen.py (Export manuscript form)
gui/                    # React/TS front end (see gui/README.md); src-tauri/ is unused
packaging/              # PyInstaller spec, build.py, Inno Setup script (see docs/dev/packaging.md)
.github/workflows/      # ci.yml (tests), release.yml (installers, draft release on a v* tag)
tests/                  # pytest; asyncio_mode=auto; Pilot for TUI tests
docs/dev/               # internal design history: plan-*.md (one per feature wave),
                        # specification-guide.md, ux-review-glm.md (source of the M1.5 polish)
docs/user-guide/        # sources + build scripts of the User's Guide (the PDF is a Release asset)
docs/screenshots/       # README images
requirements*.txt       # run / dev dependencies for a source checkout (pyproject mirrors them)
```

## Commands

```bash
.venv/bin/pip install -e ".[dev]"   # after pulling
.venv/bin/python -m pytest          # full suite (must stay green)
.venv/bin/lorewrite                 # run the app
```

Desktop GUI (plan: docs/dev/plan-gui.md, spec: SPEC "Desktop GUI"):

```bash
python3 -m venv --system-site-packages .venv-gui && .venv-gui/bin/pip install -e ".[dev,gui]"
(cd gui && npm install && npm run build && npm run lint && npm test)
.venv-gui/bin/lorewrite-gui [--project PATH]
PYTHONPATH=src .venv-gui/bin/python -m lorewrite.gui.devserver --project COPY --mock-ai   # headless
```

CI (`.github/workflows/ci.yml`): pytest on ubuntu / windows / macos x Python 3.11 and 3.13, plus a Node job
(`npm ci`, lint, test, build). Keep tests platform-safe: use `os.devnull`, project-relative ids with `/`
(`as_posix()`), no symlinks without a Windows skip, and set both `HOME` and `USERPROFILE` when faking the home.

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
- **Comments** (`core/comments.py`) are a sidecar keyed like `.drafts/` and must travel with the
  scene: any new code that renames, moves or trashes a scene goes through
  `Structure._apply_renames` (it stages the comments file too). Never put comment text in the
  scene, never feed it to an AI unless the author attached it, and never drop a comment that
  fails to anchor (it is detached). In the GUI the first line of a *hard-wrapped paragraph* is
  one DOM line for several doc lines, so the margin marker's line decoration goes on the first of
  them (`softBreakSet` in `editor/cm.ts`); the marker is outside the editor's box, so its click is
  caught on `.lw-editor__scroll` (`marginClick`), not in CodeMirror.
- **Research notes go to the Trash** (`Project.trash_research`, `research.delete_note`): `.trash/` holds
  scenes (`manuscript__…`), research notes (`research__…`) and inspiration pictures (`inspiration__…`) told
  apart by `TrashItem.kind`; code that lists, restores or empties the Trash must handle all three
  (`restore_scene` returns the restored path of any).
- **Research notes** (`core/research.py`) are documents of kind `research` in the GUI bridge
  (`Api._doc_kind`) but are **never indexed** (`_index_file`, TUI `_write_to_disk` skip them), never
  spell-checked, and not scenes (`is_scene_path` is false). The Research question is
  `ai.writing.research_context` + `research_answer` (shared by `gui/api.py` and `tui/app.py`; mock it
  in `gui/mockai.py` and `lorewrite.tui.app.research_answer`). It must refuse with no AI call when
  there are no notes. The palette has a `Research ·` category (like `Scene ·`).
- **Inspiration images** (`core/inspiration.py`, `ai/images.py`; SPEC "Inspiration images") are
  reference only: never in the prose, never indexed, counted, spell-checked or sent to an AI. They
  cost money (~$0.03), so generation is only ever started by a click / palette pick, never
  automatically (Describe this scene fills a box; Generate is a second click). Files are
  `inspiration/<stem>.<jpg|png|webp>` + `<stem>.md` (YAML: prompt, model, scene, created, cost,
  pinned, title; body = notes); ids cross the bridge, so go through `inspiration._sidecar` /
  `_picture` / `read_file` (they refuse non-plain ids and symlinks out of the folder) and serve
  pictures only via `inspiration_image`. `scene:` is a project-relative path: anything that renames
  or moves scenes goes through `Structure._apply_renames` / `move_part`, which call
  `inspiration.remap_paths` (do not add another rename path). Deleting goes to the Trash
  (`Project.trash_inspiration`; `TrashItem.kind == "inspiration"`, the picture rides beside the
  sidecar as `<item>.<ext>`) - code that lists, restores or empties the Trash handles three kinds
  now. `image` is a fourth model role (`resolve_model("image")`); the picker lists only
  `output_modalities` containing `image`. Never send `provider.require_parameters` or a JSON schema
  to an image model. The TUI app calls `lorewrite.tui.app.generate_image` /
  `suggest_image_prompt` and the GUI `lorewrite.gui.api.generate_images` / `suggest_image_prompt`
  (mock those names; `gui/mockai.py` returns a generated PNG, and the signature test lists them).
  the desktop opener (`core/desktop.open_path`: startfile / open / xdg-open) runs only when the author chooses (`inspiration.open_path`; tests stub
  `LorewriteApp.open_external`). Method names on `InspirationMixin` must not collide with
  `LorewriteApp`'s (`_generate_worker` already exists - the mixin's are `_inspiration_*`).
- **Chats and attachments** (`core/chats.py`, `core/attach.py`). The GUI saves the whole conversation
  after each answer (`persistChat` ref + effect in `App.tsx`); keep it client-driven so regenerate /
  delete / load stay consistent, and never store `error` messages. Chat ids and attachment ids
  cross the bridge: `chats._path` and `attach._path` are the only doors, keep them. Comments reach
  an AI **only** through an explicit attachment. Attachments are capped and every trim/skip is in
  the `attached` report the UI shows - do not add a silent cap. The terminal chat window
  (`tui/assistantscreen.py`) has no attach in v1; its AI calls are `lorewrite.tui.app.ask_writer` /
  `research_answer` (mock those names). Brainstorm is `lorewrite.tui.app.brainstorm_ideas` (terminal) and
  `lorewrite.gui.api.brainstorm_writer` (GUI; `gui/mockai.py` fakes it, and the signature test in
  `tests/test_gui_shell.py` lists it); a brainstorm reply is a chat message carrying `ideas`.
- **AI jobs and Stop** (`ai/stream.py`, `gui/aijobs.py`, `tui/aimixin.py`). Streaming text calls take
  `on_delta=` / `cancel=` (a `CancelToken`) and raise `Cancelled` when stopped; a stopped call must never
  insert, save or register anything - in the GUI the sync bridge methods run unchanged inside a job
  (`Api._stream` routes deltas; `aijobs.checkpoint()` before any write that follows a slow call), in the TUI
  every AI call goes through `LorewriteApp._ai_call` and the worker catches `Cancelled` and returns.
  A stopped non-streaming request is only abandoned: it may still finish server-side and its cost is still
  recorded (the connection is not closed). New AI function in `ai/`: add the kwargs (or `call_ai` filters them), mock it with them in `gui/mockai.py`.
  `ctrl+x` is a priority App binding gated by `check_action` (it is cut when no job runs).
- **Writing stats** (`core/stats.py`) are personal: `<state dir>/stats/<project-id>.json`, never in the
  project folder, and they MUST honour `LOREWRITE_STATE_DIR` (tests/screenshots point it at a temp dir).
  Both front ends call `Tracker.seen(key, words)` when a scene is opened or replaced wholesale (snapshot
  restore!) and `record(key, words)` on save; anything that rewrites a scene's prose behind the editor's
  back must `seen` it or the difference is counted as writing. Accepting an AI draft calls `accepted`
  (AI words; the baseline moves) *before* the text changes. The GUI Api holds one Tracker per open
  project (`Api.stats`); a Tracker writes only its own deltas merged into the file (`_unsaved`), because the TUI
  and GUI may both be open on one project; typing pings arrive through `stats_touch` (throttled client-side).
  A focus sprint lives in the Tracker (`start_sprint` / `finish_sprint`); the GUI ends it from a client
  timer (`App.tsx`, hooks above the early returns) and the TUI from a 1 s `set_interval`; both save
  first so the last words count. Tests fake time through `Tracker(clock=...)`.
- **Export** (`core/export/`; SPEC "Export"). Everything goes through `manuscript.assemble` (one model for
  every writer): never re-read scenes in a writer. It is read-only, skips `_unplaced/`, the Trash,
  research and scene frontmatter, uses `drafts.reject_all` with the sidecar originals unless
  `include_drafts`, and reports expand markers. New file formats/layouts: a module in `layouts/`
  exposing `LAYOUT` and listed in `_REGISTRY`. ReportLab is optional (the `export` extra): import
  `pdfkit` / layouts only through `layouts` after `reportlab_available()`. Details that bit: set
  `initialFontName` on the doc and a TOC `tableStyle` font or every PDF references an unembedded
  Helvetica; the TOC needs `multiBuild`, with bookmark keys reset in `handle_documentBegin`; running
  heads and page numbers are drawn in `onPageEnd` (page flags are only known after the flowables).
  The manuscript layout's line numbers assume the 24 pt grid (no paragraph spacing). pandoc input is
  escaped (`markdown.py`) and read with raw HTML/TeX off. Output names come from `run_export` and are
  never overwritten; the UI opens files only through `resolve_export` + `open_in_desktop` and only
  on a click. Tests mock `lorewrite.core.export.open_in_desktop`.
- **Rename everywhere** (`core/rename.py`; SPEC "Rename a character everywhere"). `plan_rename` never writes;
  `apply_rename` takes only the ticked ids, refuses files changed since the preview, snapshots each scene
  (`before-rename`) before any write and keeps an undo journal in `.lorewrite/rename-undo/`. Pending AI draft
  bodies are `in_draft` and unticked by default; never rewrite markers or sidecars. Anything new that
  renames or moves notes/scenes must keep going through `Structure._apply_renames`; this module only
  rewrites text and the note's own file. GUI/TUI callers flush the open buffer first and reopen it after
  (detach `current_path` / the save controller; the note's file name changes).
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
- **Portability (Windows/macOS/Linux)**. Write text with `write_text(..., newline="\n")` (a test
  enforces it); rename/replace through `core/fsutil` (retries a locked file); open files through
  `core/desktop.open_path`; state lives under `recents.default_state_dir()`. Export fonts (Noto
  Serif, Liberation Mono) are bundled in `core/export/fonts/` with their OFL licences; other fonts
  are found on the system if present. Omarchy theming is Linux-only and optional.
- **Terminal key limits**: `ctrl+[` IS Escape; `ctrl+enter` doesn't reach most
  terminals; `ctrl+h` arrives as Backspace (the assistant's saved conversations are `ctrl+t`).
  Scene nav is `alt+←/→`, writer mode is `f11`.
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
- **Atmosphere audio** (`gui/src/audio/`, `core/soundpacks.py`, `core/atmosphere.py`). Typing sounds are hooked
  in `editor/cm.ts` at `Prec.highest` (Enter/Backspace are handled by the keymaps, which would end the handler
  chain); the hook returns false and swallows every error. Audio starts only from a gesture and the app starts
  silent: never autoplay, never contact a station before the author picks it. Pack/loop names cross the
  bridge: go through `soundpacks._plain` / `_inside`; zip import is all-or-nothing. Tests set
  `LOREWRITE_DATA_DIR` (conftest does).
- **Placeholders** use `components/placeholder.ts` only. Do not invent a second
  treatment, and do not show fake data in them.
- **Dev-only fakes**: `mockai.py` and `backend/mock.ts` must never be reachable in
  the real app; tests booby-trap `make_client`. Screenshots/interaction tests run
  headless Chromium against `devserver` on a *copy* of `examples/residual` with
  `LOREWRITE_STATE_DIR` pointed at a temp dir and the keyring backend nulled.
- Key map differences from the TUI: `ctrl+j` in the GUI editor opens/makes a note
  (elsewhere it focuses the composer, as designed); `ctrl+k` quick switcher; `f11`
  focus mode.

- **Packaging** (`packaging/`, docs/dev/packaging.md). The bundles are built by PyInstaller; anything that
  loads a data file by path or a module by name (export layouts, fonts, dictionaries, UI) must keep working
  frozen: put new data in `lorewrite/` package folders, add it to `packaging/lorewriter.spec` and, if it
  can break silently, to `src/lorewrite/selftest.py` (no window, no network). Do not add imports of
  `webview` / Textual at module level of `selftest.py`.

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
- **Optional: Jev review.** If you have the Jev CLI (`~/.config/jev/jev.py`), diff only
  the files you changed into `jev.py review --task "..." --files ...` before reporting a
  code task done. HOLDs on `network` (the OpenRouter client) and `out_of_scope` (state
  files outside the repo) are expected for this project: report the scores, don't reword
  to dodge. Nothing in the app requires Jev.
- No emojis in the UI or docs unless the user asks. Category prefixes use
  `Scene · / Entity · / Research · / Link · / Action ·` text.
- Commits only when the user asks. Match existing style; minimal diffs.

## Current state

Everything below is on `main`: M1 (editor + links), M1.5 (UX polish), M2 (alias finder),
M3 (continuity + Contextual Tracker), settings, bracket-free implicit mentions (SPEC §5),
AI spend tracking, **M4** (style guide, `ctrl+g` draft/expand/rewrite, pending AI drafts;
docs/dev/plan-m4-ai-writing.md), the **desktop GUI** (pywebview + React over the same core;
docs/dev/plan-gui.md), spell check (both front ends), the **workspace waves** (parts, Unplaced
Scenes, Trash, scene details, snapshots, drafts, git sync, collections, comments, research
notes, assistant chats, session stats and focus sprints, Brainstorm; docs/dev/plan-workspace.md),
**inspiration images** (docs/dev/plan-inspiration.md) and **M7 export** (PDF / DOCX / EPUB /
LaTeX / Markdown; docs/dev/plan-export.md). The public release work is in
docs/dev/plan-release.md (Phase A: licence, packaging, portability, docs, CI).
Known concern: the author is unconvinced by the command palette as the primary UI
(SPEC §11b) — the desktop GUI is the answer being tried.
