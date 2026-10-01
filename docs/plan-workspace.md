# Plan: the workspace features (everything except M7 export)

Status: approved by the author 2026-10-01 ("implement everything except M7";
"build those too" for the GUI placeholders). Built in four waves on branch
`features` (worktree `~/lorewrite-features`, from `main`), each wave by a
fresh agent, reviewed and merged to `main` by the managing session.

## Rules for every wave

- Read `AGENTS.md`, `SPEC.md`, `docs/plan-gui.md` ("As built"), and this file.
- Plain text first (SPEC §2): every new piece of author data is a readable
  file in the project folder, never only in `.lorewrite/` (that folder is a
  disposable cache: index, waivers). Name new author-data files/folders as
  given below; none of them may be git-ignored by the project `.gitignore`.
- **No visible markup in prose** (the author dislikes it): comments, tags and
  metadata never go inline in scene text except the scene's own YAML
  frontmatter block (hidden/collapsed in both editors, see Wave 1).
- AI suggests, never edits unprompted; AI output is chat text, a list to
  accept from, or a pending `<!--ai-->` draft. Never call real AI in tests;
  mock at the function boundary. No network in tests.
- One logic implementation in `core/` / `ai/`; the TUI and the GUI both call
  it. Both front ends get every feature unless marked GUI-only.
- Keep `pytest`, `vitest`, `npm run build`, `npm run lint` (no new warnings)
  green after every commit-sized step; commit per numbered item on
  `features`; never commit to `main`, never push.
- Verify visually: headless devserver + chromium screenshots on a *copy* of
  `examples/residual`; look at them. Never open GUI windows on the desktop.
  Stop servers you start by PID (not `pkill -f`, which can match your shell).
- Migration: existing projects (flat `manuscript/*.md`, no frontmatter) must
  open and behave exactly as before. Add a test that opens
  `examples/residual` unchanged.
- Docs per wave: SPEC.md (mark items implemented, record storage formats),
  README, AGENTS.md (layout, fragile spots), HELP_TEXT / tour where keys
  change. Not the PDF guide.
- Final report per wave to `/tmp/wave<N>-report.md` (built, storage formats,
  keys, deviations, limitations, Jev table per chunk) and reply with the path.

---

## Wave 1 — manuscript structure

### 1.0 First: the intermittent test
One full-suite run in four on `main` (c196348) had a single failure that was
not captured. Run the suite repeatedly (e.g. 6 times with `-rf`) to find it;
fix the cause (usually a timing assumption in a Pilot/devserver test), commit
separately.

### 1.1 Parts (the design's "Part I — The Recall")
- A **part is a folder** under `manuscript/`: `manuscript/02-ghost-frequency/`
  holding scene files `01-…md`. Part title: the first `# heading` of an
  optional `manuscript/<part>/_part.md` (may also hold the author's notes on
  the part), else the folder name de-slugged. Scenes may still sit directly in
  `manuscript/` (unparted; listed before parts) — existing projects need no
  change.
- Order: part folders by numeric prefix, scenes by prefix within a part.
  `Project.list_scenes()` returns all scenes in reading order (recursive);
  add `Project.list_parts()` and `Project.part_of(path)`. Audit every caller
  of `list_scenes`/`manuscript_dir` (index, style sampling, voice samples,
  TUI sidebar/commands/app, GUI workspace/api) — none may assume a flat dir.
- Ops (core, then both UIs): new part, rename part, move part up/down, delete
  empty part, move scene to part (end of part), reorder scene within part.
  Renames keep numeric prefixes contiguous like `move_scene` does today.
- **Sidecars must be keyed by project-relative path, not filename**: today
  `.drafts/<scene-filename>.json` would collide between parts. Migrate:
  `.drafts/<rel-path-with-slashes-as-__>.json` (or mirror the folder tree
  under `.drafts/`) — pick one, migrate existing sidecars on open, test.
- Display unit: `project.toml` `[manuscript] unit = "scene" | "chapter"`
  (default "scene") — only changes labels ("Scene 03" vs "Chapter 03"),
  kicker text, palette wording. Numbering is global across parts.
- GUI: binder shows real parts (expand/collapse), Front Matter = a part named
  `00-front-matter` (excluded from manuscript word counts, styled muted as in
  Figma); Parts placeholders removed.
- TUI: sidebar groups scenes under part headers; palette actions for the ops.

### 1.2 Unplaced scenes and Trash
- **Unplaced Scenes** = `manuscript/_unplaced/` (written, not in the book):
  not counted in manuscript words, not in continuity's reading order, still
  indexed for backlinks. Move a scene in/out.
- **Trash** = `<project>/.trash/<timestamp>-<rel-path-flattened>.md` (plus its
  `.drafts` sidecar). Deleting a scene moves it to Trash (no more permanent
  delete from the UI). Trash view (GUI binder item, TUI palette): restore
  (to its original part, or Unplaced if gone), delete forever (confirm), empty
  Trash (confirm). Keep the existing "detach current_path before opening the
  next scene" rule (AGENTS.md fragile spot).

### 1.3 Scene details (POV, place, purpose, status, target)
- Stored as the scene's own **YAML frontmatter** (Obsidian-compatible):
  ```
  ---
  pov: Mara Vale
  place: Lower Meridian
  purpose: First contact with Elias's signal
  status: revising        # free text; suggested: idea | draft | revising | done
  target: 2400            # words
  collections: [Needs continuity pass]   # Wave 3
  ---
  # A City That Remembers
  ```
  Only written when the author sets a field; absent = no frontmatter (existing
  scenes untouched). The `# heading` stays the title.
- Frontmatter is excluded from: word counts, spelling, mention scanning
  (except that `pov`/`place` values that resolve to entities count as
  mentions for backlinks), continuity evidence, style sampling.
- Editors: GUI — the frontmatter block is collapsed/hidden in CodeMirror and
  edited through the inspector (Status, POV / Place, Scene purpose) and the
  context bar (status tag, `words / target`); POV and place pick from
  entities (characters / places) with free text allowed. TUI — collapse is not
  possible; show it faded (bracket style) and add a palette action
  `Scene · Edit details` (small form modal).
- AI: `build_context` and the continuity prompt include the scene details
  (POV + place + purpose) as a short header — e.g. continuity can flag a POV
  character knowing something they shouldn't.
- Corkboard cards and Outline rows show status, POV and word/target.

### 1.4 Corkboard drag-to-reorder
- GUI: drag a card to reorder within a part or onto another part; confirm
  dialog ("Move 'Capsule 7-19' to Part II, position 3?"); performs the core
  move ops; undo = move back (offer in the toast). Outline view: same with
  drag handles. TUI keeps palette move up/down.

---

## Wave 2 — history and drafts

### 2.1 Snapshots
- Storage: `<project>/.snapshots/<rel-path-flattened>/<YYYYMMDD-HHMMSS>[--label].md`
  — a verbatim copy of the scene file (frontmatter included); its `.drafts`
  originals copied alongside as `…json` if present.
- Create: manual ("Snapshot scene" with optional label), and automatic before
  any whole-scene destructive operation: restore, accept-all/reject-all
  drafts, applying alias/canon changes is not scene-destructive (skip),
  moving to Trash (the trash copy suffices — skip). Optional auto snapshot
  when a scene is first edited each day (setting, default on) — the
  low-cost safety net.
- Browse (GUI: the rail **History** button opens a Snapshots panel for the
  open scene; TUI: palette `Scene · Snapshots`): list with time, label, word
  count and ± words vs now; **Compare** (word-level diff of snapshot vs
  current, rendered side by side in GUI / unified in TUI; use `difflib`);
  **Restore** (takes a snapshot of the current text first, then restores);
  delete a snapshot (confirm).
- Project-wide: "Snapshot all scenes" (one label for all).
- Status bar "Snapshot 12 min ago" becomes real (latest snapshot of the open
  scene).

### 2.2 Drafts (the "Draft 2" badge)
- `project.toml` `[manuscript] draft = 1` (default 1 when absent).
- "Start new draft" (GUI title-bar badge menu, TUI palette): confirm, take a
  project-wide snapshot labelled `end-of-draft-<N>`, increment `draft`.
- Badge shows "Draft N" (real), status bar "Draft N".

### 2.3 Sync (the "Project synced" indicator) — git, explicit only
- If the project folder is (inside) a git repository: status bar shows
  `Synced` (clean and not ahead), `N changes` (uncommitted), or `Ahead N`
  (committed, not pushed); refresh on save, cheap (`git status
  --porcelain=v2 --branch`, subprocess with timeout; no git = hidden).
- Actions (GUI status-bar menu, TUI palette), **only on explicit click**:
  "Commit changes" (message prefilled `lorewrite: <date> — <N> scenes
  changed`, editable; commits the project folder only), "Push" (only shown if
  a remote is configured; confirm dialog naming the remote; never force).
  "Initialize git for this project" if none (creates repo + `.gitignore` with
  `.lorewrite/`). Never push automatically. Tests use a temp repo and a
  local bare remote — no network.

---

## Wave 3 — notes around the manuscript

### 3.1 Collections (the design's "Needs continuity pass", "Mara's arc")
- Definitions in `project.toml` `[collections]` table: name → color (one of
  the design's swatch tokens). Membership in each scene's frontmatter
  `collections: [...]` (Wave 1 format).
- GUI: Collections section real — counts, click to filter the binder (and
  corkboard), "Edit" opens a small manager (add / rename / recolor / delete —
  delete removes membership from scenes after confirm); inspector or scene
  menu toggles membership. TUI: palette `Scene · Collections`, and the
  sidebar filter accepts `#collection-name`.

### 3.2 Comments (author notes anchored to text, never inline)
- Sidecar `<project>/.comments/<rel-path-flattened>.json`: list of `{id,
  quote, prefix, suffix, body, created, resolved}` — anchored by quoted text
  plus a little context so it survives edits (re-anchor by fuzzy find; if
  lost, show as "detached" at the top of the list, never silently drop).
- GUI: the toolbar comment button and the editor gutter comment marker
  (design) become real: select text → add comment; highlighted span
  (subtle), gutter marker, popover thread (edit / resolve / delete); comments
  panel in the Notes tab. TUI: palette `Scene · Add comment on selection`,
  `Scene · Comments` (list, jump, resolve); commented text underlined faintly.
- Comments are author notes: not spell-checked, not sent to AI unless the
  author attaches them (3.4).

### 3.3 Research
- Folder `<project>/research/` of plain Markdown notes (not entities, not
  scenes; any subfolders). Binder "Research" lists them (count real), opens
  them in the editor; "New research note"; drag/paste a URL creates a note
  with the link and a title (no fetching).
- Assistant quick action **Research** (real): ask a question answered from
  the research notes + project canon with the writing model; keyword
  retrieval over notes (simple scoring, no embeddings), cite the notes used
  (clickable). No web access.

### 3.4 Assistant conversation history, attach, save
- Chats persist per project in `<project>/.assistant/chats/<id>.json`
  (title = first prompt, created, messages, scope). The History button in the
  Assistant header lists past chats (open, rename, delete); "New chat".
- Paperclip **attach**: pick scenes / notes / research notes / comments to add
  to this chat's context (shown as chips, capped total size, removable).
- Reply "like" (thumb) becomes **Save to notes**: appends the reply, with date
  and the prompt, to `research/assistant-notes.md`.
- TUI: palette `Action · Ask the assistant` opens a simple chat modal using
  the same `ai.writing.ask` + history store (no attach in TUI v1).

---

## Wave 4 — writing aids (M6)

### 4.1 Session stats, streak, targets
- Stats are personal, not book content: store them in the state dir
  `<state>/stats/<project-id>.json` (project id = hash of the resolved root
  path), honouring `LOREWRITE_STATE_DIR`. Per day: words added (net of the
  author's prose — pending AI drafts excluded; accepted drafts count as AI
  words separately), minutes active (editor focused and typing within the
  last 2 minutes), sessions.
- Settings: daily word target (default 500; 0 = off).
- Streak = consecutive days meeting the target (or ≥ 1 word if target off).
- Status bar: streak and `session words / target` become real (both UIs).
- **Session stats page** (GUI: from the status bar / rail; TUI: palette):
  today, this session, last 30 days bar chart (GUI; TUI a sparkline), average
  per session, best day, streak, project total — read-only, not a dashboard.

### 4.2 Focus timer
- Start a sprint (15 / 25 / 45 / custom minutes): status bar countdown,
  optional writer/focus mode on start, gentle end notice (no sound), sprint
  word count shown at the end and recorded in stats. GUI: status bar control;
  TUI: palette `Action · Focus sprint` + status bar.

### 4.3 Brainstorm (idea generator)
- Assistant quick action **Brainstorm** (real): writing model, current scene
  + canon + style guide context; returns 3–5 "unstuck" prompts (what-if
  questions, complications, sensory angles, character pressure points) as a
  chat reply; each idea has "Draft from this" (opens the ctrl+g prompt
  prefilled) and "Save to notes". TUI: palette `Action · Brainstorm` showing
  the list in a modal with the same two actions.

---

## Future (do not build): AI inspiration images
Generate an image of a described setting ("a dark subway platform") to keep
on screen while writing; reference only, never inserted into prose; likely an
OpenRouter image model with the same key; stored in `<project>/inspiration/`.
Record in SPEC.md's roadmap only.
