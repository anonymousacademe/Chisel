# AGENTS.md — guide for AI assistants working on Chisel

Naming: the app, the package `chisel` (PyPI distribution `chisel-writer`), the commands `chisel` / `chisel-gui`,
the state folders, the `CHISEL_*` variables and the repo (`anonymousacademe/Chisel`) are all called Chisel. The
old LoreWriter names (`lorewrite`, `LOREWRITE_*`, `.lorewrite/`) must appear only in
`src/chisel/core/migrate.py` / `envvars.py`, their tests, and the rename notes. The packaging files are
`packaging/chisel.spec` / `chisel.iss`; the desktop executable is `Chisel`, the terminal one `chisel-tui`
(`chisel.exe` and `Chisel.exe` would be one file on Windows and macOS).

Read this before changing anything. [SPEC.md](SPEC.md) is the source of truth
for design; this file is the operational guide.

## Project in one paragraph

Chisel is a fiction-writing app with a terminal front end (Python 3.11+,
Textual) and a desktop front end (pywebview + React) over the same core. Scenes
are plain Markdown files; characters/places are Markdown notes with small YAML
frontmatter; `[[wiki-links]]` connect them; a SQLite index (a rebuildable
cache, never the truth) powers backlinks; AI features go through OpenRouter
and are **suggest-and-confirm only — AI never edits prose unprompted**.

## Repo layout

```
SPEC.md                 # master design doc — update it when design changes
README.md               # user-facing intro
src/chisel/
  core/                 # pure Python, no Textual — fully unit-testable
    links.py            # [[link]] parsing, plain-name mentions, offset<->rowcol
    entities.py         # entity notes: frontmatter, aliases, resolve, add_alias
    project.py          # project layout, entities, settings (Project mixes in Structure)
    structure.py        # parts (folders), unplaced scenes, trash, scene moves/renumbering
    snapshots.py        # .snapshots/: create/list/restore/delete, daily auto, word diff
    sync.py             # optional git: status (read-only), commit, push, init — explicit only
    scenemeta.py        # scene details = YAML frontmatter: find/strip/blank/set_details
    timeline.py         # optional story time: StoryTime, scene_times, mode, scenes_up_to, age_at, fact tags
    continuity.py       # continuity flags/waivers shared by both front ends
    spans.py            # UTF-16 <-> code point offsets for the GUI bridge
    index.py            # SQLite backlink index; no-ops after close()
    recents.py          # recent projects; state dir = platformdirs (Linux ~/.local/state/chisel); CHISEL_STATE_DIR env override (via envvars.get_env)
    soundpacks.py       # typing-sound packs + ambience loops in the user DATA dir (CHISEL_DATA_DIR in tests); zip import/export validation
    atmosphere.py       # sound prefs + radio stations in user settings (http(s) only)
    desktop.py          # open_path: os.startfile / open / xdg-open (only on a click)
    migrate.py          # one-time migration from the old lorewrite names (state/data dirs, keyring, .lorewrite/ -> .chisel/); envvars.py: get_env with the deprecated LOREWRITE_* aliases
    fsutil.py           # replace/rename with a short retry (Windows PermissionError); use instead of Path.replace
    settings.py         # user settings (tour_seen, ...)
    style.py            # style.md (project root): load/save/backup, manuscript sampling
    drafts.py           # pending AI text markers (<!--ai-->), expand markers
    spelling.py         # spell check: check/suggestions, accepted terms, dictionary files
    collections.py      # collections: definitions in project.toml, membership in scene frontmatter
    comments.py         # comments: .comments/<scene>.json, anchored by quote + context
    research.py         # Notebook notes (notebook/; research/ migrated on open): list/new/templates/from-url/delete/clippings, keyword search, assistant-notes
    chats.py            # saved assistant chats: .assistant/chats/<id>.json
    attach.py           # chat attachments (scene/note/research(=notebook)/comments), capped and reported
    stats.py            # writing stats/streak/sprints: Tracker, state dir stats/<project-id>.json
    inspiration.py      # inspiration/ pictures + .md sidecars: save/list/update/pin, `for:` link (any item), sniff_ext, remap_links / remap_paths
    rename.py           # rename an entity everywhere: plan (read-only) / apply (snapshots first) / undo
    export/             # M7: manuscript.py (assemble -> Book), layouts/ (PDF: book, manuscript, plain),
                        #   pdfkit.py (fonts), markdown.py, pandoc.py, __init__.py (run_export, options)
  ai/
    client.py           # OpenRouter via openai SDK; keyring/env key resolution
    links.py            # alias finder (ctrl+l): prompt, schema, validate (never edits text)
    continuity.py       # continuity check + canon (story-bible) proposals: plan_check / plan_canon
    stream.py           # streaming text calls, CancelToken, Cancelled
    usage.py            # AI spend ledger (usage.cost) -> status bar
    style.py            # learn a style guide from sampled prose
    writing.py          # draft / expand / rewrite: context builder + plain-text generate
    images.py           # inspiration pictures: generate (OpenRouter image output), suggest_prompt
    budget.py           # context budget: estimate_tokens, Section/Item, fit(), SentReport, window_for, BudgetError
    relevance.py        # which entities a scene is about (named / POV+place / rest), for continuity, canon, aliases
  gui/                  # desktop GUI backend (pywebview); no Textual
    api.py              # Api: JSON bridge (every method -> {ok,...}); facade() = js_api
    workspace.py        # Project -> Workspace JSON for the React UI
    devserver.py        # headless: built UI (gui/web/, see webroot.py) + POST /api/<method> (+ --mock-ai)
    aijobs.py           # AI jobs for ai_start / ai_poll / ai_cancel (Stop)
    mockai.py           # canned AI for screenshots/demos (never the real app)
    inspiration.py      # bridge helpers for the pictures (rows, data URLs, save batch, upload: save_upload; byte sniffing is core/inspiration.sniff_ext)
    app.py              # chisel-gui: pywebview window
    webroot.py          # finds the built UI: package web/ first, then repo gui/dist
    exports.py          # export worker-thread jobs (export_start / export_status)
  tui/                  # everything Textual
    app.py              # ChiselApp: layout, save, status, actions, AI wiring
    editor.py           # LinkedTextArea — see "fragile spots" below
    sidebar.py panels.py launch.py commands.py linkreview.py (alias review)
    structurescreens.py (part picker, Trash, scene details form)
    inspirationmixin.py inspirationscreens.py (inspiration images: ChiselApp mixin + modals)
    spellscreen.py (f6 fix window)
    stylereview.py promptscreen.py tour.py theme.py
    exportscreen.py (Export manuscript form)
gui/                    # React/TS front end (see gui/README.md); src-tauri/ is unused
  src/components/SentReport.tsx   # the "What was sent" disclosure (data/sent.ts)
  src/data/subject.ts             # the "About:" chip: subjectOf + the subject_id payload
  src/data/storyTime.ts           # story-time display helpers (parsing stays in Python)
packaging/              # PyInstaller spec, build.py, Inno Setup script (see docs/dev/packaging.md); chisel.spec /
                        #   chisel.iss (renamed from lorewriter.*), their output is Chisel-*
CHANGELOG.md            # user-facing changes; add a line under Unreleased with every user-visible change
.github/workflows/      # ci.yml (tests), release.yml (installers, draft release on a v* tag)
tests/                  # pytest; asyncio_mode=auto; Pilot for TUI tests
docs/dev/               # internal design history: plan-*.md (one per feature wave, historical: written when
                        # the app was called LoreWriter), specification-guide.md, ux-review-glm.md; README.md
                        # explains this. packaging.md is current.
docs/user-guide/        # sources + build scripts of the User's Guide (the PDF is a Release asset)
docs/screenshots/       # README images
docs/brand/             # the Chisel logo: icon (rounded square) and mark (no background), SVG + 1024 px PNG; README.md there
requirements*.txt       # run / dev dependencies for a source checkout (pyproject mirrors them)
```

## Commands

```bash
.venv/bin/pip install -e ".[dev]"   # after pulling
.venv/bin/python -m pytest          # full suite (must stay green)
.venv/bin/chisel                 # run the app
```

Desktop GUI (plan: docs/dev/plan-gui.md, spec: SPEC "Desktop GUI"):

```bash
python3 -m venv --system-site-packages .venv-gui && .venv-gui/bin/pip install -e ".[dev,gui]"
(cd gui && npm install && npm run build && npm run lint && npm test)
.venv-gui/bin/chisel-gui [--project PATH]
PYTHONPATH=src .venv-gui/bin/python -m chisel.gui.devserver --project COPY --mock-ai   # headless
```

CI (`.github/workflows/ci.yml`): pytest on ubuntu / windows / macos x Python 3.11 and 3.13, plus a Node job
(`npm ci`, lint, test, build). Keep tests platform-safe: use `os.devnull`, project-relative ids with `/`
(`as_posix()`), no symlinks without a Windows skip, and set both `HOME` and `USERPROFILE` when faking the home.

## Non-negotiable principles (from SPEC §2)

1. Plain text, always — a project is a folder of Markdown; no database blobs.
2. The index is a rebuildable cache (`f9`); files are the truth.
3. AI suggests, never edits — every AI feature ends in an accept/reject UI.
4. Entity notes = free text + minimal YAML frontmatter (name, type, aliases, plus any other keys kept verbatim).

## Fragile spots — read before touching

- **`tui/editor.py` uses private Textual APIs** (`_render_line`, `_line_cache`,
  `wrapped_document._offset_to_line_info`) to highlight `[[links]]`. Every use
  is wrapped in try/except with a plain-TextArea fallback.
  `tests/test_tui.py::test_link_highlighting_styles` locks the behavior — if it
  fails after a Textual upgrade, the internals moved.
- **Migration from the LoreWriter names is non-destructive** (`core/migrate.py`): the old `lorewrite`
  state/data folders are *copied* once (never moved or deleted, never over an existing `chisel` folder, skipped
  when an env override is set), the keyring key is read from the old service and copied, and a project's
  `.lorewrite/` is renamed to `.chisel/` in `Project.open`, falling back to a fresh `.chisel/` if the rename
  fails. Every step is wrapped so it cannot block start-up. Tests use the `fake_keyring` fixture from
  `tests/conftest.py`; never touch the real keyring or the real user folders from a test.
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
- **Manuscript structure** (`core/structure.py`; SPEC "Manuscript structure"). The GUI calls the Unplaced
  folder **Parked scenes** (binder group, menus, kicker `PARKED`); the group is not in the binder while it is
  empty, and internal names (`manuscript/_unplaced/`, `group:unplaced`, `unplaced` fields) did not change:
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
- **Notebook notes go to the Trash** (`Project.trash_research`, `research.delete_note`): `.trash/` holds
  scenes (`manuscript__…`), notebook notes (`notebook__…`; old `research__…` items still list and restore into notebook/) and inspiration pictures (`inspiration__…`) told
  apart by `TrashItem.kind`; code that lists, restores or empties the Trash must handle all three
  (`restore_scene` returns the restored path of any).
- **Notebook notes** (`core/research.py`; the UI says Notebook, the code keeps `research` for the module, bridge methods, `kind`, rename scope and the binder group id `group:research`) live in `notebook/`. `Project.open` runs `research.migrate_folder` (move, never overwrite; a leftover `research/` is still read by `list_notes`/`is_research_path`, so use those, never a hard-coded folder). Note ids come from `Note.id`. Chat sources/attachments saved as `research/...` are mapped by `attach.modern_id`. They are documents of kind `research` in the GUI bridge
  (`Api._doc_kind`) but are **never indexed** (`_index_file`, TUI `_write_to_disk` skip them), never
  spell-checked, and not scenes (`is_scene_path` is false). The Ask-my-notebook question is
  `ai.writing.research_context` + `research_answer` (shared by `gui/api.py` and `tui/app.py`; mock it
  in `gui/mockai.py` and `chisel.tui.app.research_answer`). It must refuse with no AI call when
  there are no notes. The palette has a `Notebook ·` category (like `Scene ·`).
- **Inspiration images** (`core/inspiration.py`, `ai/images.py`; SPEC "Inspiration images") are
  reference only: never in the prose, never indexed, counted, spell-checked or sent to an AI. They
  cost money (~$0.03), so generation is only ever started by a click / palette pick, never
  automatically (Describe this scene fills a box; Generate is a second click). Files are
  `inspiration/<stem>.<jpg|png|webp>` + `<stem>.md` (YAML: prompt, model, for, created, cost,
  pinned, title, source; body = notes); ids cross the bridge, so go through `inspiration._sidecar` /
  `_picture` / `read_file` (they refuse non-plain ids and symlinks out of the folder) and serve
  pictures only via `inspiration_image`. `for:` is the project-relative path (= GUI document id) of
  **any** item - scene, entity note or notebook note; always WRITE `for:`, keep READING the legacy
  `scene:` (`Image.link`, with `Image.scene` as a compatibility property; the files stay in
  `inspiration/`, never beside the note). `pinned` means "show with that item" for every kind. Anything
  that renames or moves a scene goes through `Structure._apply_renames` / `move_part`, and an entity
  note rename (and its undo) goes through `rename.apply_rename` / `undo_rename`; both call
  `inspiration.remap_paths` (do not add another rename path; notebook notes have stable ids). A link
  that no longer resolves is kept (Trash, deleted): the listing marks it `unlinked` and a restore
  reconnects it. **Uploads** (`Api.upload_inspiration` -> `gui/inspiration.save_upload`): data URL, 10 MB,
  JPG / PNG / WebP decided from the BYTES (`sniff_ext`; a lying mime type, GIF and SVG are refused), the
  user's file name is only the display title (the file name is stamp + `_slug`), `source: upload`,
  `model: upload`, no cost; `regenerate_inspiration` refuses them. Uploaded or generated, a picture is
  never sent to an AI. Deleting goes to the Trash
  (`Project.trash_inspiration`; `TrashItem.kind == "inspiration"`, the picture rides beside the
  sidecar as `<item>.<ext>`) - code that lists, restores or empties the Trash handles three kinds
  now. `image` is a fourth model role (`resolve_model("image")`); the picker lists only
  `output_modalities` containing `image`. Never send `provider.require_parameters` or a JSON schema
  to an image model. The TUI app calls `chisel.tui.app.generate_image` /
  `suggest_image_prompt` and the GUI `chisel.gui.api.generate_images` / `suggest_image_prompt`
  (mock those names; `gui/mockai.py` returns a generated PNG, and the signature test lists them).
  the desktop opener (`core/desktop.open_path`: startfile / open / xdg-open) runs only when the author chooses (`inspiration.open_path`; tests stub
  `ChiselApp.open_external`). Method names on `InspirationMixin` must not collide with
  `ChiselApp`'s (`_generate_worker` already exists - the mixin's are `_inspiration_*`).
- **Chats and attachments** (`core/chats.py`, `core/attach.py`). The open item is the chat's
  **subject**: `ask`, `brainstorm` and `describe_scene` take an optional `subject_id` (any document id) and
  `Api._subject_context` / `_chat_context` append `SUBJECT (character|place|object|notebook note): name` + the
  note body (frontmatter stripped, capped by `attach.subject` at `ITEM_CHARS`) to the project/scene context;
  an unknown id is a clean error before any AI call. The GUI shows it as the "About: ..." chip in the
  Assistant header (`data/subject.ts`; removing it omits `subject_id` for that chat): the chip must be visible
  whenever the text is sent, so keep `subjectOf` and the payload in step. The `ask_writer` /
  `brainstorm_writer` signatures did not change (the subject rides in the context string). The GUI saves the whole conversation
  after each answer (`persistChat` ref + effect in `App.tsx`); keep it client-driven so regenerate /
  delete / load stay consistent, and never store `error` messages. Chat ids and attachment ids
  cross the bridge: `chats._path` and `attach._path` are the only doors, keep them. Comments reach
  an AI **only** through an explicit attachment. Attachments are capped and every trim/skip is in
  the `attached` report the UI shows - do not add a silent cap. The terminal chat window
  (`tui/assistantscreen.py`) has no attach in v1; its AI calls are `chisel.tui.app.ask_writer` /
  `research_answer` (mock those names). Brainstorm is `chisel.tui.app.brainstorm_ideas` (terminal) and
  `chisel.gui.api.brainstorm_writer` (GUI; `gui/mockai.py` fakes it, and the signature test in
  `tests/test_gui_shell.py` lists it); a brainstorm reply is a chat message carrying `ideas`.
- **Context budget** (`ai/budget.py`, `ai/relevance.py`; SPEC "Context budget and the sent report"). Every
  AI context is a list of `budget.Section`s run through `fit()` (or `writing.fit_context`, which also
  preflights and renders): continuity (`continuity.plan_check`), canon proposals (`plan_canon`), the alias
  finder (`links.plan_aliases`), draft / expand / rewrite, chat, Brainstorm, project scope and Ask-my-notebook
  (`writing.build_context_sections`, `build_project_context_sections`, `research_sections`). **Never add a
  silent `continue`, `break` or `[:N]` to a context builder**: a fixed cap is an `Item.cap` / `Section.group_cap`
  and the budget, not the builder, drops things, so every cap, drop and trim lands in the `SentReport`
  (names, not counts). The `plan_*` functions run before any network call, raise `BudgetError` (a
  `ValueError`, listed in `USER_ERRORS`: the message is shown as is) when even the parts that cannot be dropped
  exceed the window, and pass the fitted entities / canon through the existing parameters of the mocked
  functions (`check_scene`, `propose_canon_updates`, `suggest_links`, `generate_text`, `ask_writer`...), whose
  signatures did not change. Each bridge method returns the report as `sent` beside its other fields;
  attachments are merged in (`merge_attached`), not listed twice. The window is `window_for(model)`: the
  `context_window` setting, else the model's `context_length` from the catalogue the picker already fetched
  (`client.cached_context_length`, never a new request), else 32k. Token counts are estimates (chars / 4).
  Continuity, canon and alias requests send only the entities the scene is about (`relevance.rank`) once the
  project has `relevance.ALL_MAX` (40) entities; below that, everything, exactly as before. The terminal app
  appends `SentReport.summary()` to each AI notification (`ChiselApp._cost_note(calls, sent)`). The fixed
  caps of `describe_scene` (small, no budget) and the chat history (last 6 turns, 1500 characters each) are not
  in the report yet.
- **AI jobs and Stop** (`ai/stream.py`, `gui/aijobs.py`, `tui/aimixin.py`). Streaming text calls take
  `on_delta=` / `cancel=` (a `CancelToken`) and raise `Cancelled` when stopped; a stopped call must never
  insert, save or register anything - in the GUI the sync bridge methods run unchanged inside a job
  (`Api._stream` routes deltas; `aijobs.checkpoint()` before any write that follows a slow call), in the TUI
  every AI call goes through `ChiselApp._ai_call` and the worker catches `Cancelled` and returns.
  A stopped non-streaming request is only abandoned: it may still finish server-side and its cost is still
  recorded (the connection is not closed). New AI function in `ai/`: add the kwargs (or `call_ai` filters them), mock it with them in `gui/mockai.py`.
  `ctrl+x` is a priority App binding gated by `check_action` (it is cut when no job runs).
- **Writing stats** (`core/stats.py`) are personal: `<state dir>/stats/<project-id>.json`, never in the
  project folder, and they MUST honour `CHISEL_STATE_DIR` (tests/screenshots point it at a temp dir).
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
  on a click. Tests mock `chisel.core.export.open_in_desktop`.
- **Rename everywhere** (`core/rename.py`; SPEC "Rename a character everywhere"). `plan_rename` never writes;
  `apply_rename` takes only the ticked ids, refuses files changed since the preview, snapshots each scene
  (`before-rename`) before any write and keeps an undo journal in `.chisel/rename-undo/`. Pending AI draft
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
- **Entity frontmatter round trip** (`core/entities.py`). `Entity.extra` holds every key other than
  name/type/aliases (any YAML type, file order) and `to_markdown` writes it back after them; a note with
  only managed keys serialises byte-identically. Every path that rebuilds an Entity from a note must go
  through `from_markdown` (or keep `extra`): `save_entity`, `add_alias`, `apply_canon_update`, rename's note
  rewrite, `set_entity_born`. Never construct `Entity(name=..., aliases=...)` to overwrite an existing note.
  YAML comments inside the block are not preserved (documented, accepted). Malformed frontmatter reads as
  empty, as before.
- **Story time is optional** (`core/timeline.py`; SPEC "Story time"). `when:` (scene frontmatter) and `born:`
  (entity frontmatter) are a year, optional month and day, as `StoryTime(year, month|None, day|None)`: never a
  `datetime` (years past 9999 and negative ones must work; missing month/day sorts first). A scene without
  `when:` inherits the previous scene's in READING ORDER (`list_scenes`, no Parked scenes); before the first
  explicit one it has none. With no story times anywhere every feature falls back to reading order **and says
  so** (`timeline.mode(...).sentence`); never sort or reorder the book by story time and never guess silently
  (invalid values are kept as text and flagged). `timeline.scenes_up_to` is the single door for "as of"
  filtering (a later "talk as a character" feature must use it and show the mode it returns). `when` is
  stripped/blanked like the other scene details and is not in `MENTION_FIELDS`; do not add it to the AI
  `scenemeta.header` without a decision. The GUI only displays what Python resolves (`when` on scene
  summaries, `timeline` on the workspace, `ageNow`); parsing stays in Python (`check_story_time`).
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
  `CHISEL_DATA_DIR` (conftest does).
- **Placeholders** use `components/placeholder.ts` only. Do not invent a second
  treatment, and do not show fake data in them.
- **Dev-only fakes**: `mockai.py` and `backend/mock.ts` must never be reachable in
  the real app; tests booby-trap `make_client`. Screenshots/interaction tests run
  headless Chromium against `devserver` on a *copy* of `examples/residual` with
  `CHISEL_STATE_DIR` pointed at a temp dir and the keyring backend nulled.
- Key map differences from the TUI: `ctrl+j` in the GUI editor opens/makes a note
  (elsewhere it focuses the composer, as designed); `ctrl+k` quick switcher; `f11`
  focus mode.

- **Packaging** (`packaging/`, docs/dev/packaging.md). The bundles are built by PyInstaller; anything that
  loads a data file by path or a module by name (export layouts, fonts, dictionaries, UI) must keep working
  frozen: put new data in `chisel/` package folders, add it to `packaging/chisel.spec` and, if it
  can break silently, to `src/chisel/selftest.py` (no window, no network). Do not add imports of
  `webview` / Textual at module level of `selftest.py`.

## Testing conventions

- `tests/conftest.py` isolates app state per test via `CHISEL_STATE_DIR`
  and pre-marks the tour as seen. New user-state features must honor the env
  override.
- TUI tests use `app.run_test(size=(120, 40))` + `pilot`; call
  `await pilot.pause()` after actions before asserting.
- Context-size tests (`tests/test_budget*.py`) build a 400-entity / 200-scene project in `tmp_path`; small-project
  equivalence tests keep a copy of the pre-budget builders as the reference - if one fails, the text a short
  project sends changed.
- Mock AI at the function boundary: monkeypatch `chisel.tui.app.<ai_fn>`
  (see `tests/test_ai_links.py`) or, for the GUI, `chisel.gui.api.<fn>`
  (see `tests/test_gui_ai.py`). Never hit the network in tests.
- GUI: `tests/test_gui_*.py` + `tests/test_spans.py` (plain pytest, temp projects via
  `tests/gui_helpers.py`); `gui/src/**/*.test.ts` (vitest). The workspace JSON
  fixture `gui/src/data/fixtures/workspace.json` is regenerated with
  `CHISEL_REGEN_FIXTURE=1 pytest tests/test_gui_workspace.py`.

## Workflow requirements

- **Keep SPEC.md current** when design/scope/decisions change (it's the master
  document; README mirrors it for users).
- **Optional: Jev review.** If you have the Jev CLI (`~/.config/jev/jev.py`), diff only
  the files you changed into `jev.py review --task "..." --files ...` before reporting a
  code task done. HOLDs on `network` (the OpenRouter client) and `out_of_scope` (state
  files outside the repo) are expected for this project: report the scores, don't reword
  to dodge. Nothing in the app requires Jev.
- No emojis in the UI or docs unless the user asks. Category prefixes use
  `Scene · / Entity · / Notebook · / Link · / Action ·` text.
- Commits only when the user asks. Match existing style; minimal diffs.

## Current state

Released: 0.4.0 (2026-10-03; CHANGELOG.md has the user-facing list): hardening of file handling and names,
the rename of the app to Chisel in user-facing text, menu-aware AI (the "About:" chip), pictures linked to any
item and picture upload, *Parked scenes* (desktop name of the Unplaced folder), the context budget with the
"What was sent" report, entity frontmatter round trip, optional story time, the Chisel logo and icons, and the
Windows window-icon fix. The previous release was 0.3.1.

**Icons and the logo** (artwork supplied by the project author; vector and PNG sources in `docs/brand/`, see
its README). The rule: the desktop window icon is `src/chisel/gui/icon.ico` on Windows (pywebview's WinForms
backend only accepts an `.ico`) and `src/chisel/gui/icon.png` everywhere else (`gui/app.py` picks by
`sys.platform`; both are package data in `pyproject.toml`; `tests/test_packaging_files.py` checks it). The
installers and bundles use `gui/src-tauri/icons/icon.ico` (Windows), `icon.icns` (macOS) and `icon.png`
(Linux) plus the sized PNGs beside them. The in-app logo (rail, launch screen) is `gui/src/assets/logo.svg`
(the `Logo` component; `gui/public/logo.svg` and `favicon.png` are copies). `gui/scripts/make-icons.sh`
regenerates the PNGs, `.ico` and `.icns` from `gui/src/assets/logo.svg`; it does not write
`src/chisel/gui/icon.ico`, so copy `gui/src-tauri/icons/icon.ico` over it after running it.

Done before that: M1 (editor + links), M1.5 (UX polish), M2 (alias finder), M3 (continuity + Contextual
Tracker), settings, bracket-free implicit mentions (SPEC §5), AI spend tracking, **M4** (style guide,
`ctrl+g` draft/expand/rewrite, pending AI drafts; docs/dev/plan-m4-ai-writing.md), the **desktop GUI**
(pywebview + React over the same core; docs/dev/plan-gui.md), spell check, the **workspace waves** (parts,
Parked/Unplaced scenes, Trash, scene details, snapshots, drafts, git sync, collections, comments, notebook
notes, assistant chats, session stats and focus sprints, Brainstorm; docs/dev/plan-workspace.md),
**inspiration images** (docs/dev/plan-inspiration.md), **M7 export** (docs/dev/plan-export.md) and the public
release work (docs/dev/plan-release.md; installers, CI).

Planned next, in this order (SPEC §14 has the one-line descriptions): character relationships, "talk as a
character" with an as-of point (use `timeline.scenes_up_to`), local models (Ollama / OpenAI-compatible),
per-scene summaries and a rolling story-so-far, a timeline view. Until local models land, AI is OpenRouter-only.

Known concern: the author is unconvinced by the command palette as the primary UI (SPEC §11b) — the desktop
GUI is the answer being tried.
