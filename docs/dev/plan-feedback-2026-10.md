# Plan: author feedback, October 2026 (after first real use)

Status: drafted 2026-10-01 from the author's first real use of the desktop app.
All batches approved 2026-10-01; the author's decisions are recorded under
DECIDED. Same rules as `docs/dev/plan-workspace.md` ("Rules for every
wave"), and the anonymity rule in `docs/dev/plan-release.md` (public repo,
pseudonym Mishkin: never add a real name, institution, home path or personal
email).

The feedback, in the author's words (condensed):
1. Make it more apparent when the AI is working, especially long tasks like drafting.
2. Settings for the author's name and other details that show up in exports.
3. A way to stop the AI.
4. Chat should stream, and its Markdown should be formatted.
5. The style guide should show formatted Markdown.
6. What is the "LW" logo at the bottom? Make it look cooler.
7. No intuitive way to add research notes; unclear what they are for.
8. Rename a character and update the name and aliases across the whole text, on request.
9. Bold/italics in the manuscript should display as bold/italics, not symbols.
10. Optional typewriter / mechanical-keyboard typing sounds, easy to customise.
11. A little "radio": relaxing, nature, café, meditative sounds, lo-fi.

---

## Batch 1 — polish the daily experience

### 1.1 Formatted Markdown in the manuscript editor (feedback 9) — GUI
- CodeMirror live preview for inline formatting, using the same mechanism that
  already hides `[[brackets]]` and `<!--ai-->` markers (`gui/src/editor/cm.ts`,
  one `StateField`): `**bold**` / `__bold__` → bold, `*italic*` / `_italic_` →
  italic, `***both***`, `` `code` `` → monospace; the markers are hidden except
  when the cursor is inside or touching the span (Obsidian-style). `# `–`###`
  headings inside a scene render as headings (the scene's own first heading
  keeps its title block). Escaped `\*` stays literal.
- Use the Lezer Markdown syntax tree from `@codemirror/lang-markdown` (already a
  dependency) to find spans — do not regex Markdown.
- No file changes: display only. Spell check, mention spans and comments keep
  working with hidden markers (offsets are unchanged; add tests).
- TUI: already syntax-highlights Markdown; make sure bold/italic spans use
  bold/italic styles if Textual's theme does not (small, optional).

### 1.2 Formatted style guide (feedback 5) — GUI
- `style.md` (document kind `style`) opens with the same live preview as 1.1
  plus block-level rendering (headings, bullet lists, blockquotes for the
  exemplars). Editing stays possible (it is the author's file).

### 1.3 Formatted chat (feedback 4, part) — GUI + TUI
- GUI: render assistant replies (and Brainstorm / Research answers) as
  Markdown — headings, bold, italics, lists, blockquotes, code, links (links
  open in the system browser only on click). Use a small, maintained renderer
  (`marked` or `markdown-it`) **with HTML disabled** and the output
  sanitised (`DOMPurify`) — replies are untrusted model output. Copy keeps the
  raw Markdown.
- TUI: the chat window renders replies with Textual's `Markdown` widget.

### 1.4 Project & author details (feedback 2, 6) — core + both UIs
- `project.toml [project]`: `author` (exists), `pen_name` (optional; used
  instead of author when set), `title` (exists), `subtitle`, `copyright`
  (e.g. "© 2026 Jane Writer"), `contact` (email/website), `language` (for
  EPUB metadata and hyphenation, default `en`). One core module
  (`core/project.py` or `core/projectinfo.py`) reads/writes them; never edit TOML
  in TS.
- GUI: Settings → **Project & author** section; TUI: Settings screen rows.
- Export uses them: title page (title, subtitle, author/pen name), copyright
  line (replaces the export dialog's separate copyright field — keep the field
  as an override), PDF metadata (Title/Author), EPUB/DOCX metadata, running
  heads, manuscript header surname.
- **The "LW" mark (feedback 6):** it is the avatar, showing the author's
  initials ("LW" is the fallback when no author is set). Show the pen name's /
  author's initials; with no author, show the LoreWriter logo instead of "LW";
  clicking it opens Project & author. Design a proper app logo (SVG, an inkwell
  /quill or open-book mark in the design's violet), used for the rail mark,
  launch screen, window icon and packaging icons (regenerate
  `gui/src-tauri/icons/*` and the Windows/macOS/Linux icons from the SVG).

### 1.5 Streaming, a visible working state, and Stop (feedback 1, 3, 4) — core + both UIs
- **AI layer** (`ai/`): streaming variants of the text calls — chat (`ask`),
  Research, Brainstorm, `generate` (draft / expand / rewrite) — using
  `stream=True`. Yield text deltas; collect the final usage/cost (OpenRouter
  sends usage in the last chunk when `usage.include` is set) into the ledger.
  A **cancel token** (threading.Event) checked between chunks; cancelling closes
  the HTTP stream (`response.close()`), records the cost of what was generated if
  reported, and raises a `Cancelled`. Non-streaming JSON calls (continuity,
  story bible, aliases, style learning, image generation) cannot stream usefully:
  they get Stop too — the request is abandoned (connection closed / result
  ignored) and nothing is applied.
- **Never insert a partial result.** A stopped draft inserts nothing; a stopped
  chat reply is shown as "(stopped)" and not saved as an answer.
- **GUI bridge:** the existing pattern for long jobs (`gui/exports.py`: start /
  status / cancel) generalised into one AI-jobs helper: `ai_start(kind, args) →
  job id`, `ai_poll(job_id, since)` → new text + state, `ai_cancel(job_id)`. The
  client polls ~10×/s while a job runs (or uses pywebview's `evaluate_js` push if
  simpler and robust — pick one, justify, keep the devserver working).
- **GUI working state:** a clear, consistent indicator for every AI action: in
  the place the result will appear (chat bubble typing in live; a drafting
  panel under the cursor showing the text as it is written, the elapsed time and
  "Stop"; a progress strip for non-streaming actions with elapsed seconds and
  Stop), plus a status-bar item "AI: drafting… 12 s · Stop". Esc stops the
  active job when its panel has focus.
- **TUI:** streaming in the chat window and a live preview in the draft prompt
  area; a "Stop" key (`ctrl+x` or `escape` while a job runs — check it reaches
  the app) and a status-bar line "AI: drafting… 12 s (ctrl+x to stop)".
- `gui/mockai.py` gets streaming fakes (yield words with small delays) so the
  devserver shows the live states; tests use fake streams and assert cancel
  closes the stream and inserts nothing.
- One real streaming call in review by the managing session (cents).

## Batch 2 — rename a character everywhere (feedback 8) — core + both UIs
- `core/rename.py`: `plan_rename(project, entity, new_name, *, keep_old_as_alias,
  rename_aliases: {old: new}, scope)` → a preview: every occurrence per scene (and
  optionally entity notes, research/notebook notes, comments) with line, context
  and a stable id; covers plain mentions (`core.links.find_mentions` rules:
  whole words, case rules, longest match, possessives), explicit `[[links]]`
  (target and `|display`), and frontmatter `pov`/`place`. Skips pending AI
  draft bodies (or flags them) and quoted text the author excludes.
- `apply_rename(plan, accepted_ids)`: **snapshot every affected scene first**
  (`snapshots.create`, label `before-rename`), then rewrite with the existing
  atomic writers and `Structure` helpers, update the entity note (`name`, aliases,
  file name via the existing rename path so `.drafts`/comments/inspiration links
  follow), rebuild the index, and return a summary. Capitalisation follows the
  original occurrence (sentence-start capital kept).
- UI: entity note → **Rename…** → new name, "keep old name as an alias"
  (default on), per-alias renames, then a **preview** grouped by scene with
  checkboxes (all on), counts, and Apply; nothing changes before Apply; afterwards
  "Undo" restores the snapshots. TUI: palette `Entity · Rename everywhere…` with a
  list-based preview (space toggles).
- This is deterministic code (no AI). Tests: possessives, case, overlapping
  names ("Elara" vs "Elara Vance"), links with display text, frontmatter, a name
  that is also an ordinary word with unticked occurrences, undo.

## Batch 3 — research notes → Notebook (feedback 7) — DECIDED: Notebook — DONE (branch feedback-4; internals keep the name "research")
The author chose the Notebook:
rename **Research** to **Notebook** — notes about anything that is not the
manuscript (ideas, world-building, outlines, research, links). Make it obvious:
a **+ New note** button on the binder group and in the Notebook view, "Send
selection to notebook" in the editor's context menu, paste a link → offer a note,
templates (blank / idea / location / timeline), and rename the Research question
to **Ask my notebook** with a one-line explanation. Storage stays `research/`
→ **migrate to `notebook/`** on project open (move files, keep reading `research/` if present, update Trash kinds and the index skip rules), so the folder name matches the UI.

## Batch 4 — atmosphere (feedback 10, 11) — GUI only
### 4.1 Typing sounds — DECIDED: synthesised now; the author will record packs and share them
- **Synthesised in the browser** (Web Audio: filtered noise
  bursts + short resonant clicks per key class: letter, space, return, backspace;
  ±random pitch/level so it never loops audibly), three built-in packs
  ("Typewriter", "Mechanical — clicky", "Mechanical — thocky"), a volume slider,
  off by default, toggle in the status bar and Settings. No licensing, no files.
- **Custom packs:** a folder in the user's data dir
  (`platformdirs.user_data_dir("lorewrite")/sounds/<pack>/`) with
  `key-*.wav|ogg`, `space.*`, `return.*`, `backspace.*` (any subset; missing
  classes fall back to `key`), plus an optional `pack.toml` (name, volume). Listed
  automatically; "Open sounds folder" button. Served to the webview through a
  bridge method that only reads that folder (no path traversal).
- **Sharing packs:** "Import sound pack…" takes a `.zip` (validate: audio files
  only — wav/ogg/mp3/flac by magic bytes, ≤ 20 MB total, ≤ 200 files, no paths
  outside the pack, no executables), "Export pack…" zips a pack. Document the
  pack format in `docs/sound-packs.md` so others can make and upload them (e.g.
  as GitHub Release assets or a `sound-packs` discussion); no in-app download
  store in this batch.
- Latency matters: preload buffers, play on `keydown` in the editor only (not in
  dialogs), never block typing.

### 4.2 Ambience "radio" — DECIDED: built-in generated layers + free internet streams for music
- **Built-in, offline, generated** layers (Web Audio): rain, ocean, wind,
  forest (birds = sparse chirp synthesis), fireplace crackle, café murmur
  (filtered babble approximation — label honestly), brown / pink / white noise,
  a soft meditative drone. Each layer has a volume; save mixes as presets
  ("Rainy café"). Optional user files: a `user_data_dir/ambience/` folder of
  loops, listed alongside.
- **Internet stations** for music (lo-fi etc.): a small editable list (name +
  stream URL), defaulting to a few free, permission-friendly streams (verify each
  station's terms before listing; SomaFM-style ambient channels); clearly
  marked as using the internet; nothing plays until the author picks a station;
  stream URLs are http(s) only; no account, no tracking.
- A compact player in the status bar (play/pause, current layer/station,
  volume) and a small panel to mix; fades in/out; pauses during focus-sprint
  end notice; remembers the last mix.

---

## How the agents are set up (and kept cheap)

**Model choice per task.**
| Work | Model | Why |
|---|---|---|
| Planning, reviewing diffs, merging, final checks | Opus (managing session) | judgment; touches little code |
| Feature implementation with design decisions (1.1, 1.5, Batch 2, 4.x) | **Sonnet 5.5** | good code, much cheaper than Opus |
| Mechanical work: 1.2 on top of 1.1, 1.4 settings fields + export wiring, docs/README updates, CI-fix loops, fixture regeneration, icon regeneration | **Haiku 4.5** (`--model claude-haiku-4-5-20251001`) | cheapest; fine for well-specified edits |
| User-guide updates | Sonnet 5.5, **no sub-agents** | prose quality; the last guide run spawned 8 sub-agents — forbid that |

**Prompt hygiene (biggest savings).**
- Each brief names the exact files to read (e.g. "read `gui/src/editor/cm.ts`,
  `gui/src/editor/spans.ts`, AGENTS.md §GUI fragile spots") instead of "read
  SPEC.md and AGENTS.md" in full; SPEC sections by heading only.
- **No sub-agents** (`Agent`/`Task` tools) unless the brief allows it.
- Tests: run the **targeted** test files while working; the **full suite once**
  at the end of a batch (it takes ~5 min and its output is large).
- Screenshots only for the views the batch changed (2–4 per batch), not a full
  re-capture.
- Reports: ≤ 60 lines — what changed, deviations, limits, Jev table.
- Fresh agent per batch (small context) but **reuse** the worktree environment
  (`.venv-gui`, `node_modules`) between batches of the same branch.

**Parallelism (only where files don't collide).**
- Run **1.1+1.2 (editor/rendering, front end)** and **1.4 (project info,
  backend + settings)** in parallel; 1.3 and 1.5 after them (both touch the
  Assistant and the bridge).
- **Batch 4** (new components, a new status-bar item) can run in parallel with
  **Batch 2** (core + entity UI).
- The packaging agent (Phase B, branch `packaging`) keeps running; feedback
  batches use separate branches (`feedback-1`, `feedback-2`, …) and are merged in
  order by the managing session.

**Review gates (managing session, per batch).** Re-run the full suite and the
UI build once; read the diff of risky parts (anything that writes author files:
rename, settings, streaming insert paths); 2–4 screenshots; for 1.5 one real
streaming chat + one real streaming draft with a Stop (cents); Jev per chunk;
anonymity grep; then merge to `main` and push (CI on three systems).

**Rough cost shape.** Batch 1 ≈ two Sonnet runs + one Haiku run; Batch 2 ≈ one
Sonnet run; Batch 4 ≈ one Sonnet run; real-AI checks < $0.10 total.

---

## Appendix — the AI job contract for 1.5 (written by the managing session 2026-10-02)

Two agents build 1.5 in parallel against this contract: **A (backend)** owns
`ai/`, `gui/api.py` job methods, `gui/aijobs.py`, `gui/mockai.py`, the TUI;
**B (desktop UI)** owns `gui/src/**` (1.3 Markdown rendering, the working
states, Stop, the drafting panel). Neither edits the other's files; the
managing session merges and wires them together.

**Bridge (Python, `gui/api.py`, all `@bridge`, never raise):**
- `ai_start(kind: str, args: dict) -> {"job": "<id>"}` — kinds:
  `ask`, `research`, `brainstorm`, `generate` (streaming) and `continuity`,
  `canon`, `aliases`, `style`, `image`, `describe_scene` (non-streaming).
  `args` are exactly the keyword arguments of the existing synchronous bridge
  method for that kind (`ask(prompt, scope, doc_id, text, cursor, history,
  attachments)`, `generate(mode, instruction, doc_id, text, start, end)`, …);
  the existing synchronous methods stay (tests and TUI use them).
- `ai_poll(job: str, since: int = 0) -> {"state": "running"|"done"|"cancelled"|"error",
  "text": <new streamed text from character offset `since`>, "length": <total
  streamed chars>, "elapsed": <seconds>, "result": <the exact dict the
  synchronous method returns, only when done>, "error": <message, only when
  error>, "cost": <float|null>}`. Non-streaming kinds return `text: ""`.
- `ai_cancel(job: str) -> {"state": "cancelled"}` — idempotent; closes the HTTP
  stream / abandons the request; the job's result is discarded (nothing is
  saved, inserted or registered — for `generate` no draft sidecar entry).
- Jobs run on worker threads, the project lock is NOT held during the network
  call (existing rule); finished jobs are kept 5 minutes for a late poll.

**Client (`gui/src`):** one `runAiJob(kind, args, {onText, label})` helper
replacing the body of `aiCall`: start, poll every 100 ms, call `onText` with
deltas, resolve with `result`, reject on error, `cancel()` returns a promise.
The mock backend (`gui/src/backend/mock.ts`) implements the three methods with
a fake word-by-word stream so the UI works in `npm run dev` before A lands.
