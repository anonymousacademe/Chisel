# Lorewrite — Design Spec

**Status:** Draft v1 — pending approval before implementation
**Date:** 2026-09-27

## 1. Vision

A terminal-native fiction-writing app. The core loop: write scenes in a clean Markdown editor, mark characters and places with `[[wiki-links]]`, and let an AI assistant keep the link graph and the story's internal consistency up to date — without ever touching your prose uninvited.

The niche is open: no existing TUI fiction app has wikilinks, and no wikilink tool has continuity checking.

## 2. Core principles

1. **Plain text, always.** A project is a folder of UTF-8 Markdown files. Greppable, git-diffable, opens in Obsidian. No database blobs (the #1 praised trait of novelWriter; the #1 complaint about bibisco/Scrivener).
2. **The index is a cache, never the truth.** All metadata is derivable from the files. The index can be rebuilt from scratch (like novelWriter's F9) and must tolerate external edits (watch files; rebuild on demand).
3. **AI suggests, never edits.** Links are proposed for accept/reject; lore checks produce a report; expansion only fires where the author placed an explicit marker. (Avoids the main Sudowrite criticism.)
4. **Minimal machine-readability.** Entity notes are free text plus a small frontmatter block. No forms, no rigid sheets (avoids bibisco/Manuskript form fatigue).

## 3. Non-goals (v1)

- No publishing pipeline (no store uploads, no ISBN/metadata services). Exporting the manuscript to
  PDF / DOCX / EPUB / Markdown / LaTeX source is built (M7, see *Export*).
- No collaboration or automatic sync (plain files + user's own git/Syncthing). Optional, explicit
  git commit / push from the app exists (see *History and drafts*); nothing is ever sent on its own.
- No block references, embeds, or `[[Note#Section]]` links (consider later).
- No auto-applied AI edits of any kind.

## 4. On-disk project layout

```
my-novel/
├── project.toml              # title, author, settings
├── dictionary.txt            # optional: words/phrases spell check never flags
├── manuscript/
│   ├── 01-arrival.md         # scenes; leading number = order (unparted scenes read first)
│   ├── 02-the-tavern.md
│   ├── 00-front-matter/      # optional parts (folders): see "Manuscript structure"
│   ├── 01-the-recall/        #   _part.md = title + notes; scenes 01-…md inside
│   └── _unplaced/            # written, but not in the book
├── .trash/                   # deleted scenes, research notes, pictures (restorable); .drafts/ = AI draft originals
├── .snapshots/               # verbatim copies of scenes, one folder per scene (History)
├── .comments/                # author notes anchored to passages, one JSON file per scene
├── research/                 # plain Markdown research notes (any subfolders; not entities)
├── inspiration/              # AI pictures of settings + a .md sidecar each (prompt, scene, notes)
├── exports/                  # files written by Export (author's folder; add to .gitignore if unwanted)
├── .assistant/chats/         # saved assistant conversations, one JSON file per chat
└── entities/
    ├── characters/
    │   ├── elara-vance.md
    │   └── borin.md
    └── places/
        └── thornwick.md
```

Cache (gitignored, rebuildable): `.lorewrite/index.sqlite`

**Scene file** — plain Markdown, first `#` heading is the scene title:

```markdown
# The Tavern

[[Elara Vance]] pushed through the door of [[Thornwick]]'s only inn.
The old smith, [[Borin]], was already drunk.
```

**Entity note** — YAML frontmatter (machine-readable) + free text (author's bible):

```markdown
---
name: Elara Vance
type: character        # character | place | object | faction
aliases: [Elara, the captain, Captain Vance]
---

Former navy captain. Green eyes, scar on left cheek. Hates [[Borin]].
First appears: manuscript/01-arrival.md
```

Aliases in frontmatter drive both auto-linking and lore retrieval.

## 5. Link syntax (minimal Obsidian subset)

| Syntax | Meaning |
|---|---|
| `[[Name]]` | Link to entity note (resolved case-insensitively, by name or alias) |
| `[[Name\|display text]]` | Link with display alias |
| Unresolved link | Shown as "new"; jump-to offers **Create note** (Obsidian create-on-click) |
| Plain name (no brackets) | **Implicit mention** — see below |

**Brackets are optional (2026-09, author request: brackets distract from the
prose).** Once an entity note exists, every plain-text occurrence of its name
or an alias in a scene is an implicit mention: colored quietly in the editor
(no bold/underline), jumpable with `ctrl+j`, shown in the entity panel, and
counted in backlinks. Files are never rewritten to add brackets. The first
time, the author selects the name and presses `ctrl+j` to create the note.

- Matching (`core.links.find_mentions`): whole words, longest name first,
  case-sensitive as written in the note (so a character named "Will" doesn't
  match "will") except that a leading capital is allowed for sentence starts;
  names/aliases under 2 characters are ignored; spans inside `[[...]]` skipped.
- Scope: scenes only. Entity notes count explicit links only (their own
  frontmatter/body would otherwise self-match).
- Existing `[[links]]` still work; their brackets (and the `Name|` part of
  `[[Name|display]]`) are faded so only the shown text stands out.
- Creating an entity or changing aliases rebuilds the index so earlier scenes
  pick up the new name immediately.
- Trade-off: plain mentions are not links for Obsidian or other tools.
- Link colors come from the Omarchy theme; if its cyan equals the foreground
  (e.g. matte-black), the next distinct hue is used so mentions stay visible.

Explicitly deferred: `[[Note#Section]]`, `![[embeds]]`, block refs.

Rename handling: renaming an entity updates its note file; link rewrite across the manuscript is an explicit, previewable command (M2).

## 6. App architecture

```
lorewrite/
├── pyproject.toml
├── src/lorewrite/
│   ├── core/               # pure Python, no Textual — unit-testable
│   │   ├── project.py      # project discovery, create, open
│   │   ├── links.py        # [[...]] parsing, span detection, cursor-in-link
│   │   ├── entities.py     # entity model, note read/write, alias resolution
│   │   └── index.py        # SQLite cache: links, backlinks, mentions; rebuild()
│   ├── ai/
│   │   ├── client.py       # OpenRouter via openai SDK (stub in M1)
│   │   └── prompts.py
│   └── tui/
│       ├── app.py          # LorewriteApp
│       ├── editor.py       # LinkedTextArea(TextArea) — link highlighting
│       ├── sidebar.py      # scene list + entity list
│       ├── panels.py       # entity preview + backlinks panel
│       └── commands.py     # command palette providers
└── tests/
```

**Key Textual decisions (from research):**

- **Editor:** `TextArea` (soft_wrap on, line numbers on). `[[link]]` highlighting by subclassing and post-processing styled lines — *uses a private rendering hook; isolated in one file (`editor.py`) with a graceful-degradation fallback to plain TextArea so a Textual update can't break the app.* A read-only Markdown preview pane (where links are styled and clickable) is included regardless.
- **Quick-switcher:** built-in Command Palette (`ctrl+p`) with custom `Provider`s — "Open scene", "Open entity", "Insert link to entity". Zero dependencies, exactly the Obsidian pattern.
- **Async:** all indexing and AI calls in `@work(exclusive=True)` workers; `TextArea.Changed` handlers debounced (never regex-scan per keystroke).
- **Ghost text:** `TextArea.suggestion` / `update_suggestion()` gives Copilot-style inline preview for AI expansion later (M4).
- **Keybindings:** TextArea consumes most keys; use `ctrl+` chords for app actions, check focused-widget bindings win over app bindings.

## 7. Milestones

### M1 — Editor + wiki-links (the approved MVP)

- **Launch screen** (added in polish): recent projects (stored in `<state dir>/recent.json` — `platformdirs.user_state_dir("lorewrite")`, i.e. `~/.local/state/lorewrite` on Linux — `LOREWRITE_STATE_DIR` override), open folder, new project (title + location, slug-prefilled). `lorewrite` bare → launch screen; `--project PATH` opens directly; `--new TITLE` creates.
- Create/open project; three-pane layout: scene list | editor | entity panel
- Markdown `TextArea` with **tree-sitter Markdown highlighting**, soft wrap, autosave (atomic temp-file-rename writes) + explicit `ctrl+s`, saved/modified **status bar** (file, words, cursor, link hint)
- `[[...]]` parsing; links highlighted in editor (theme-aware colors); unresolved links styled distinctly
- `ctrl+j` with cursor inside a link → open entity note (creating it from template if unresolved)
- Entity panel: shows note of link under cursor + **backlinks** (every scene mentioning it, with line context)
- Command palette opens as a menu (`discover()` populated; empty query matches all): open scene/entity, insert link, **scene organization** (new / rename / move up / move down / delete-with-confirm), new entity, rebuild index
- Scene files renamed by numeric prefix swap on move; delete detaches the buffer before opening the next scene (avoids autosave resurrecting the deleted file)
- Index in SQLite, updated on save, full rebuild command (`f9`)
- `f1` help screen (`?` too when not typing in the editor), `ctrl+b` sidebar toggle
- Headless smoke tests with Textual `Pilot`

### M2 — AI auto-linking ✅ (implemented)

- OpenRouter client (`openai` SDK, key via `keyring` with `OPENROUTER_API_KEY` env override; "Set OpenRouter API key" palette action stores in keyring)
- **Find aliases in this scene** (`ctrl+l` / palette; was "Link mentions" until 2026-09 — the author dislikes `[[brackets]]`, and plain names/aliases are recognized without AI, §5): fast model (default `google/gemini-2.5-flash`, override per-project via `[ai] fast_model` in project.toml), JSON-schema structured output with `provider.require_parameters`. The AI finds only *other* ways the prose refers to known entities ("the old smith" → Borin). **Offsets validated app-side** (`text[start:end]` must match surface exactly; drift dropped, never guessed) and suggestions are dropped when they are pronouns, < 2 or > 40 chars, already a name/alias, inside an existing link/mention, or duplicates
- Review modal: each row `"the old smith" → Borin (line 12: …context…)`, all pre-checked, `space` toggle, `a` all, `enter` apply, `esc` cancel; **nothing applied without enter**. Accepting only **adds aliases** to entity notes (a leading capitalized article is stored lowercase) and rebuilds the index so every scene picks them up; scene text is never modified
- Deferred: previewable entity-rename link rewrite

### M3 — Lore/continuity checking + the Contextual Tracker ✅ (implemented)

*Expanded from vault notes ("The AI Integration.md"): the Contextual Tracker is
the distinguishing mechanic — entity notes become a living story bible.
Implemented via parallel agents per docs/specification-guide.md.*

- "Check scene for continuity issues" (palette): strong model (default `anthropic/claude-sonnet-4.5`, override `[ai] strong_model`), **Jev pre-screen gate** (`core/jev_interface.py`, fail-open) so only canon-bearing entities flagged as plausible get the expensive call
- Structured report (type/severity/entity/evidence/fix) validated app-side; evidence located to a line; **ContinuityScreen**: `space` waives (persisted in `.lorewrite/waivers.json` by stable content key, with the scene it was waived in; never re-reported unless restored via the palette action "Restore waived continuity issues (this scene)"), `enter` jumps to the offending line and closes the report
- **Note accumulation (additions only)**: "Update story bible from scene" (palette) → the AI is sent each entity's existing canon (capped 1500 chars) and proposes only NEW facts (`{entity, new_facts[], evidence}`); unknown entities, empty facts and facts already in the canon (case-insensitive) are dropped app-side → review modal shows every fact in full, grouped by entity with existing canon dimmed, each fact toggleable with `space` → accepted facts are appended as `- fact` bullets to the managed `## Canon (auto)` section (created if missing). Existing lines are never removed or rewritten; author text outside the section is never touched
- Error classes: physical attributes, timeline, character knowledge, object custody, present/absent, spelling drift
- Deferred: whole-manuscript check, cross-scene retrieval layer

### M4 — Placeholder expansion + the Style Tracker ✅ (implemented)

*Expanded from vault notes: AI-written text is always visually marked and
review-gated.*

- **Style guide** ✅: `<project>/style.md` — plain Markdown at the project root (**not** `.lorewrite/`: it is author content, hand-editable, and the cache is disposable). Sections: Voice, Rhythm & syntax, Diction, Dialogue, Avoid, Exemplars (2–3 paragraphs quoted verbatim, each with its source scene filename). "AI: learn style guide from manuscript" (palette) samples ~6000 words spread across all scenes (`core/style.py`), the **writing** model describes the author's habits and picks exemplar paragraphs (indexes validated app-side; the app quotes them, the model never writes them), and a read-only review modal shows the proposed file (`enter` save — an existing guide is kept as `style.md.bak` — / `esc` discard). "Open style guide" edits it in the editor (stub template if missing). Used as context for all generative features.
- **Generate (`ctrl+g`, one key, three modes)** ✅ — uses the **writing** model (plain-text output, no JSON schema) with context from `ai/writing.py::build_context`: the full style guide (which carries the exemplar paragraphs), ±500 words around the cursor (cut at word boundaries, `<<CURSOR>>` marks the spot), and the notes/canon of entities the scene mentions (1200 chars each, 6000 total); pending AI text is stripped from the context. Post-processing removes code fences, leading labels and wrapping quotes; empty replies are errors.
  - **Selection present → Rewrite**: prompt window prefilled "Rewrite this in my style." (editable); the result replaces the selection as an `<!--ai id=…-->` draft (reject restores it byte-for-byte).
  - **Cursor on `{{expand: instruction}}` → Expand**: no modal; the marker's instruction is the prompt; the result replaces the marker (reject restores the marker). Markers are faded in the editor.
  - **Otherwise → Draft**: hotkey prompt window ("Give me one paragraph describing the busy street… stressed mood"), a small multi-line box submitted with `ctrl+g` (enter inserts a newline; `ctrl+enter` never reaches terminals), `esc` cancels. The result is inserted at the cursor as `<!--ai-->…<!--/ai-->` (a leading space goes *inside* the draft when the cursor follows a word, so reject leaves the text exactly as it was).
  - Runs in a worker ("Drafting… (model)"); failures notify without touching the scene; if the author flips scenes or the marked text changed meanwhile, the draft is discarded rather than misplaced. A missing style guide still works, with a one-time "learn a style guide first" tip. Cost is recorded (§8).
- **Pending AI text** ✅ (the marking mechanism for every generated span): stored *in the scene file* so it survives saves, reopening and external editors (Obsidian hides HTML comments): `<!--ai-->text<!--/ai-->` for pure insertions, or `<!--ai id="k3f9q2"-->text<!--/ai-->` for a draft that replaced something (id = 6 lowercase base36 chars, unique in the project). The replaced original lives in the sidecar `<project>/.drafts/<project-relative-path-with-/-as-__>.json` (e.g. `manuscript__02-ghost__01-a.md.json`; pre-parts sidecars named by filename alone are renamed when a project is opened) (`{"k3f9q2": "original text"}`, written atomically) — author data, not cache: never under `.lorewrite/`, never git-ignored. Entries are deleted on accept/reject, the file when empty, and the sidecar is renamed/moved/trashed together with its scene (`core/structure.py`). **If an id's original is missing, reject refuses** with a notice and changes nothing (prose is never deleted on a failed lookup); accept still works. No encoded blobs appear in the prose. The editor shows the body in italics on a subtle background tint (theme `selection`) with a hue chosen by `theme.distinct_color` — the candidate farthest in RGB from the foreground, link and unresolved-link colors, with built-in fallback hues when the theme has nothing distinct (matte-black is all reds and ambers) — and the marker comments faded. `f7` accepts the draft under the cursor (markers removed, body is normal text), `f8` rejects it (original restored exactly from the sidecar, or the insertion removed); palette: accept/reject all in the scene. The status bar hints `AI draft — f7 accept · f8 reject` while the cursor is inside one. Word counts, backlinks/index, continuity checks, story-bible updates, the alias finder and style sampling all ignore pending bodies (index and alias finder blank the draft to same-length whitespace, so line numbers stay true) — unaccepted AI text is not canon. `f7` is TextArea's select-all; select-all moves to `f5`. Nested/malformed markers are treated as plain text. Core: `core/drafts.py`.
- **Style rewrite** ✅ (vault): author selects a section that "feels off" and presses `ctrl+g`; the rewrite appears in place as a pending draft (the original rides along in the marker) — `f7` approves, `f8` rolls back to the original. (No side-by-side diff view; the original is restored on reject.)
- Optional inline completion via `TextArea.suggestion` ghost text, off by default

### M6 — Writing aids

*From vault "Additional Items.md". Session stats reverse the M1.5 dashboard
rejection — the author explicitly wants a lightweight version.*

- **Spell check** ✅ (implemented; **spelling only — the author decided against grammar checking**). Offline, no AI: `pyspellchecker` (bundled English dictionary) behind `core/spelling.py`, so the engine can be swapped (e.g. Hunspell). Scenes only (entity notes and `style.md` are not checked).
  - *What is never flagged* (`accepted_terms`): entity names and aliases (each word and the whole name), the project dictionary `<project>/dictionary.txt`, the personal dictionary `<state dir>/dictionary.txt` (all projects; honours `LOREWRITE_STATE_DIR`), and words ignored this session (memory only). Dictionary files are plain UTF-8, one word or phrase per line, `#` comments allowed; they are author data (not in `.lorewrite/`, not a scene, not an entity, not indexed). An entry with a space is a *phrase*: the words inside every occurrence of it (any case/whitespace) are accepted even if a word alone would be flagged. A lowercase entry matches any capitalisation; a capitalised one (`Kessler`) only capitalised forms.
  - *Tokenizing*: possessives (`Rook's`, `Rook’s`, `dogs'`) and contractions are handled (never `str.strip("'s")`), hyphenated words are checked part by part, and these are skipped: frontmatter, fenced and inline code, URLs and e-mail addresses, tokens with digits, single letters, short ALL-CAPS tokens (`NYPD`, `K-V`), `<!--…-->` comments, `{{expand: …}}` markers, `[[Name]]` link targets (but not the display text of `[[Name|text]]`) and non-Latin scripts. Pending AI drafts are checked (the author reviews that text); only their marker comments are skipped.
  - *Terminal app*: red underline (lowest-priority span in `LinkedTextArea`, computed in a worker thread on a 0.6 s debounce; stale underlines are dropped as you type); `f6` jumps to the next misspelling after the cursor (wrapping) and opens a small window: `1`–`5`/`enter` replace, `a` add to the project dictionary, `p` add to the personal dictionary, `i` ignore this session, `esc` cancel. `f6` was TextArea's select-line, which the editor now overrides (like `f7`). Setting `spellcheck` (default on; Settings checkbox "Underline misspellings", palette *Action · Toggle spell check*); palette *Add selection to dictionary* (word or phrase, project) and *Open project dictionary*.
  - *Desktop GUI*: wavy red underline; click a misspelled word, right-click it, or press `ctrl+.` for a popover (suggestions replace as a normal undoable edit, **Add to dictionary**, **Add to my dictionary (all projects)**, **Ignore**); with a multi-word selection the popover (or the toolbar button) offers **Add phrase to dictionary**. Same `spellcheck` setting (Settings dialog); status bar `N spelling` jumps to the next one; the binder lists `Dictionary` next to the Style Guide so `dictionary.txt` can be edited by hand.
- **Focus timer** ✅ (Wave 4.2, sprint state in `core/stats.Tracker`). A sprint is 15 / 25 / 45 / custom (1-240) minutes. The countdown is in the status bar (`SPRINT 24:05 (+120)` in the terminal, a timer button in the desktop app); starting can switch writer mode / focus mode on (and the end switches it off again only if the sprint turned it on). When time is up there is a quiet notice (no sound) with the sprint's words, the last words are saved first, and the sprint is **recorded in the day's stats** (`sprints: [{at, minutes, elapsed, words, completed}]`, shown under the Session stats page). *Stop* ends it early (`completed: false`, words so far kept); quitting with a sprint running records it as stopped unless under a minute with no words. Sprint words = the author's net words saved since it began (accepted AI drafts excluded). One sprint at a time; the desktop countdown runs in the page from the server's end time, so a reload resumes it. Desktop: status-bar timer button (dialog: length chips, custom field, "hide everything but the page" checkbox, remembered in the browser). Terminal: palette *Action · Focus sprint*.
- **Session stats page** ✅ (Wave 4.1, `core/stats.py`). Read-only summary, not a dashboard. Personal data, so it lives in the user state dir, **not** the project: `<state>/stats/<project-id>.json` (project id = first 16 hex characters of the SHA-1 of the resolved project path; `LOREWRITE_STATE_DIR` honoured), `{version: 1, project, days: {"YYYY-MM-DD": {words, ai_words, seconds, sessions, sprints: [...]}}}`.
  - *Words* = net change of the author's own prose per scene, counted when a scene is **saved** (baseline taken when it is opened or replaced from disk, so opening, snapshot restore and reload count nothing; the first save of a scene never seen counts nothing). It can be negative on a day of cutting. Pending `<!--ai-->` drafts are not prose (`drafts.count_words`). **Accepted AI drafts** are counted as `ai_words` instead and the baseline moves with them, so they are never also the author's. Scene details frontmatter is not counted.
  - *Active minutes*: each typing ping adds the gap since the previous one if it is at most 2 minutes. A *session* starts at the first activity after 30 idle minutes (or in a new process); sessions are counted on the day they start. Per-day totals and "this session" (since the tracker started or the last 30 idle minutes) are both shown.
  - *Two apps on one project*: each process remembers what it added since its last write and merges that into the file on disk when it writes, so the terminal and desktop apps do not overwrite each other's numbers.
  - *Daily target* (user setting `daily_target`, default 500, 0 = off; Settings in both front ends). *Streak* = consecutive days with words >= target (>= 1 when off), counted back from today; today only breaks it once the day is over.
  - *Status bar* (both): `Streak N` and `+N / target words today` (today's words across sessions, not the net change since opening; with the target off, `+N words today`). Desktop: click either for the **Session stats** dialog (today, this session, streak, best day, average per session, project words, 30-day bar chart with days that met the target highlighted). Terminal: palette *Action · Session stats* (text plus a 30-day sparkline).
- **Idea generator (Brainstorm)** ✅ (Wave 4.3, `ai.writing.brainstorm`). The *writing* model gets the scene around the cursor (`build_context`: pending AI drafts excluded, `<<CURSOR>>` marked), the canon of the characters and places it mentions and the style guide - or, with no scene open, the project context (titles + canon) - and returns 3-5 ideas from different angles (what-if questions, complications, sensory angles, character pressure points, unused canon), each one or two sentences. `parse_ideas` reads the numbered list (at most five; `<!--` stripped). Ideas are suggestions in a list, never prose in the scene. Each has **Draft from this** (opens the `ctrl+g` prompt prefilled with the idea, at the cursor; the result is the usual pending draft) and **Save to notes** (appends it under `## date - Brainstorm idea - <scene>` to `research/assistant-notes.md`). Desktop: the Brainstorm quick action posts a chat turn whose reply is the idea list (per-idea buttons; *Regenerate* asks again; the reply is saved with the conversation, `ideas` in `.assistant/chats/<id>.json`; attachments are honoured). Terminal: palette *Action · Brainstorm* opens a list (`enter`/`d` draft from this, `s` save to notes, `esc`). No attach in the terminal; the usual cost note shows.

### M7 — Manuscript organization + export

*From vault "The Manuscript Organizer and Printer.md".*

- **Manuscript ordering in the main screen**: promote drag-reorder of the scene list (with confirm) from deferred. ✅ in the desktop GUI (corkboard cards and outline rows; see *Manuscript structure*); the terminal keeps *Move up / down*.
- **Export** ✅ (implemented on branch `export`, 2026-10-01; plan: docs/plan-export.md; see *Export* below).
  The original wording said LaTeX. **Decision:** no TeX is installed on the author's machine, so PDF
  is typeset with ReportLab and DOCX / EPUB go through pandoc; a LaTeX *source* file is still
  available (pandoc `.tex`) for authors who have TeX elsewhere. The template system is a package of
  small layout modules (`core/export/layouts/`), so more layouts can be added.

### M8 — Beyond novels (exploratory)

*From vault "Additional Items.md". Deliberately not core-roadmap; revisit once
fiction workflow is solid.*

- **Technical documents/textbooks**: figures, tables, captions, and LaTeX equations become the "entities" (first-class linkable, checked for consistency); AI format-consistency checking; figure generation from a figure/table design guide
- **Screenplay mode**: screenplay formatting rules in the editor, same AI toolset, LaTeX screenplay export

### Inspiration images ✅ (implemented 2026-10-01; plan: docs/plan-inspiration.md)

*Requested by the author 2026-10-01.* Describe a setting while writing ("a dark subway platform,
flickering lights") and get a picture to keep on screen as visual inspiration. **Reference only -
never inserted into the prose, counted, indexed, spell-checked or sent to an AI** (SPEC §2: AI
suggests, never edits). An image costs real money (about $0.03), so nothing is automatic: two
explicit clicks - *Describe this scene*, then *Generate*.

- **The call** (`ai/images.py`). An OpenRouter chat completion with
  `extra_body={"modalities": ["image", "text"], "usage": {"include": True}}` on the image model
  (default `google/gemini-3.1-flash-lite-image`, the cheapest; measured 3.8 s, one 1408x768 JPEG,
  `usage.cost` $0.034). The reply's `message.images` holds `data:image/...;base64` URLs: all are
  kept, JPEG / PNG / WebP are told apart by their bytes (the mime type can lie), remote URLs are never
  fetched, junk parts are skipped. No picture in the reply raises `ImageError` carrying what the model
  said (text or refusal). No JSON schema and no `provider.require_parameters`. The call is recorded in
  the spend ledger as feature `image` (the status-bar total). A **style suffix** (Settings; default
  "cinematic, atmospheric, no text, no watermark", empty = off) is appended when sending; the saved
  prompt is the author's own text, so a changed suffix applies to *Regenerate* too.
- **Describe this scene** (`ai.images.suggest_prompt`). The **fast** model turns the passage around
  the cursor (`writing.build_context` with no style guide: +-500 words, pending AI drafts stripped,
  the notes of the places and characters it mentions, the scene's POV / place) into one paragraph:
  setting, light, mood, era; no text in the image; no named real people. Fast, not writing, because it
  is a short mechanical summary where prose skill buys nothing, it is cheaper, and the click should
  come back quickly. The author edits the description before generating; describing saves nothing.
- **Model role.** A fourth model, `image` (`image_model` user setting, `project.toml [ai] image_model`
  overrides, like the others). The picker lists only models whose
  `architecture.output_modalities` contains `"image"` (`parse_models(..., output_modality="image")`,
  not limited to structured-output models) with the catalog's per-image price when it has one; the
  settings say "about $0.03 per image". `image_style` is a user setting.
- **Storage** (`core/inspiration.py`). `<project>/inspiration/<YYYYMMDD-HHMMSS>-<slug>.<jpg|png|webp>`
  plus a sidecar `<same stem>.md`: YAML frontmatter `prompt`, `model`, `scene` (project-relative scene
  path, optional), `created` (ISO local), `cost` (USD, split between the pictures of one call),
  `pinned` (true = shown with that scene; needs a `scene`), `title` (optional name); the body is the
  author's notes. Plain author data in the project folder, not git-ignored, never in `.lorewrite/`. An
  image's id is its file stem; ids cross the bridge, so `_sidecar` / `_picture` refuse anything that
  is not a plain id and `read_file` refuses a symlink pointing out of the folder. Operations: `save`,
  `save_batch`, `get`, `list_images(scene=None)`, `pinned_for`, `update` (pin / unpin, scene, title,
  notes), `read_file`, `remap_scenes`. Several pictures can be pinned to one scene; pinning from another
  scene moves the link.
- **Scene moves keep the link.** `Structure._apply_renames` and `move_part` call
  `inspiration.remap_paths` with `last_renames` once all moves are known (so swaps do not collide).
  Deleting a scene leaves its pictures where they are (listed under *All*); a restored scene may get a
  new number, in which case pin the picture again.
- **Trash.** Deleting a picture moves the sidecar to `.trash/<stamp>-inspiration__<stem>.md` and the
  picture beside it as `<that name>.<ext>`; `TrashItem.kind == "inspiration"`. Restore puts both back
  (a free name if one was taken since); delete forever and empty remove both.
- **Desktop GUI.** An **Inspiration** tab in the assistant panel (kept mounted, so a half-written
  description survives switching tabs): prompt box, *Describe this scene*, *Generate* with "about
  $0.03 per image", "Pin to this scene" (default on); the open scene's pinned pictures large at the top
  (they follow the open scene), a grid of this scene's other pictures with a *This scene / All* toggle;
  per picture a menu and a large view (lightbox): open large, pin / unpin, regenerate (a new picture
  from the same prompt; the old one stays), rename / notes, copy prompt, reveal file (opens the folder
  in the real window only), move to Trash (confirmed). Pictures reach the page as data URLs from
  `inspiration_image` (only files inside `inspiration/`). Bridge: `list_inspiration`,
  `inspiration_image`, `describe_scene`, `generate_inspiration`, `regenerate_inspiration`,
  `update_inspiration`, `delete_inspiration`, `reveal_inspiration`. The focus-mode corner picture
  from the plan was not built.
- **Terminal.** Terminals cannot show images well, so: palette *Action · Inspiration image…* (a prompt
  form: `ctrl+d` describe this scene, `ctrl+g` generate, a pin checkbox) saves the picture and says its
  path; *Action · Inspiration images* lists the open scene's pictures (prompt, date, pinned; `enter`/`o`
  open, `p` pin, `t` Trash, `a` all); *Open last inspiration image* and *Open inspiration folder* use
  the desktop opener (`core/desktop.py`) **only when chosen**. Settings has an *Image model* row (picker limited to image models)
  and an *Image style* field.

### Manuscript structure ✅ (Wave 1, implemented 2026-10-01; plan: docs/plan-workspace.md)

*Parts, unplaced scenes, trash, scene details and drag-to-reorder. All plain files
(§2); the index and `.lorewrite/` stay a rebuildable cache. Existing flat projects
open and behave exactly as before.*

- **Parts.** A part is a folder under `manuscript/` (`02-ghost-frequency/`) holding
  numbered scenes. Its title is the first `# heading` of an optional `_part.md`
  (which may also hold the author's notes on the part), else the folder name
  de-slugged. Scenes may still sit directly in `manuscript/`; they read first.
  Order: part folders by numeric prefix (numeric, so `2-` precedes `10-`), scenes by
  prefix within a part. `Project.list_scenes()` is the whole book in reading order
  (recursive); `list_parts()`, `part_of()`, `part_title()`, `counted_scenes()`,
  `scene_number()` are in `core/structure.py` (mixed into `Project`). A part named
  `00-front-matter` is **front matter**: listed first and muted, not counted in the
  manuscript word total or style sampling (the continuity check looks only at the open scene, whichever it is). Numbering shown to the author
  ("Scene 07") is global across parts (front matter and unplaced scenes have none);
  projects without parts keep showing the filename prefix.
  Operations (core, both UIs): new part, rename part (retitles `_part.md`; the folder
  keeps its name so no scene path changes), move part up/down (swaps numeric
  prefixes), delete empty part, move scene to a part (end), place a scene at an index
  (renumbers the destination contiguously; the folder it left keeps a gap, as after a
  delete), swap with a neighbour inside the part. `Project.last_renames` lists every
  path the last operation changed so a UI can follow the file it has open.
- **Draft sidecars are keyed by path.** `.drafts/<project-relative path, "/" as "__">.json`
  (a filename alone collides between parts). Old filename-keyed sidecars are migrated when a
  project is opened (`drafts.migrate_sidecars`); sidecars travel with every move, rename and
  trash.
- **Display unit.** `project.toml` `[manuscript] unit = "scene" | "chapter"` (default
  `scene`) changes only labels: the kicker ("Chapter 03"), the sidebar heading, palette
  wording and GUI menus. Terminal: *Call them chapters* / *Call them scenes* (names the switch it performs); GUI: project menu.
- **Unplaced Scenes** = `manuscript/_unplaced/`: not counted in the manuscript words, not in
  the reading order (`list_scenes()`), still indexed (backlinks) and openable. The continuity check
  looks only at the open scene, so being unplaced neither includes nor excludes a scene from it. *Move scene to
  Unplaced* / *Place scene in the book*.
- **Trash** = `<project>/.trash/<YYYYMMDD-HHMMSS>[-n]-<project-relative path, "/" as "__">.md`
  plus `….md.drafts.json` for the draft originals. Deleting a scene moves it there (no
  permanent delete from either UI); the Trash view (GUI binder row, terminal *Open Trash*)
  restores it to the end of its original part (Unplaced if the part is gone), deletes one
  forever, or empties the Trash, each after a confirmation. The "detach the open scene before
  opening the next" rule still applies. **Research notes go to the same Trash** (Wave 4.4): a
  deleted note becomes `.trash/<stamp>[-n]-research__<path inside research/, "/" as "__">.md` (no
  sidecars), is listed with the kind "research note", and *Restore* puts it back at its original
  path - a free name (`-2`) if one was made since, `research/` itself if its folder is gone.
  Delete forever and Empty Trash treat scenes and research notes alike.
- **Scene details** are the scene's own YAML frontmatter (Obsidian-compatible), written only
  when the author sets a field (no field, no block; unknown keys such as `tags:` survive):
  `pov`, `place`, `purpose`, `status` (free text; suggested idea / draft / revising / done),
  `target` (words), and `collections` (Wave 3.1, below). The `# heading` stays the title.
  `core/scenemeta.py` parses, edits and blanks the block. It is **not prose**: excluded from
  word counts, spelling, mention scanning, continuity evidence and style sampling — except that
  a `pov` / `place` value naming an entity counts as a mention (backlinks, retrieved context).
  A leading `---` rule that is not a YAML mapping is not frontmatter. AI: `build_context` and
  the continuity / story-bible prompts get a short `SCENE DETAILS` header (POV, place,
  purpose, status) in place of the raw block, so continuity can flag a POV character knowing
  something they could not.
  Terminal: the block is shown faded and *Scene · Edit details* (palette) opens a small form.
  GUI: the block is hidden in the editor and edited in a dialog opened from the status tag,
  the word-target chip or the inspector (POV / place pick from characters / places, free text
  allowed); the edit is computed by Python (`set_scene_details`) and applied as an ordinary
  undoable editor change, which autosave writes. Corkboard cards and Outline rows show status,
  POV and words / target.
- **Drag-to-reorder (GUI).** Corkboard cards and Outline rows (drag handle) are grouped by part
  (front matter muted, Unplaced last); dropping before a card, or in a group's end strip, asks
  "Move 'Capsule 7-19' to Part II, position 3?"; confirming performs the core move
  (`place_scene`), and the toast offers **Undo** (moves it back to where it was).
- **Not done / limits.** (Collections, comments and Research arrived in Wave 3, below.) (still
  placeholders). The terminal has no drag. Part folders are not renamed with their title.

### History and drafts ✅ (Wave 2, implemented 2026-10-01; plan: docs/plan-workspace.md)

*Snapshots, the draft counter and git sync. Plain files again; `.lorewrite/` stays a cache.*

- **Snapshots** (2.1, `core/snapshots.py`). `<project>/.snapshots/<scene's project-relative path,
  "/" as "__">/<YYYYMMDD-HHMMSS>[-n][--label].md` is a verbatim copy of the scene file
  (frontmatter included); if the scene had pending-draft originals they sit beside it as
  `<same stem>.json`. Author data like `.drafts/`: committed with the project, never under
  `.lorewrite/`. Labels are made file-safe (no `/ \ : * ? " < > |`, 60 characters); `-n`
  disambiguates snapshots taken in the same second; nothing is ever overwritten. The folder
  travels with its scene on every rename / move / part swap (`Structure._apply_renames`,
  `move_part`) and into the Trash (`.trash/<name>.md.snapshots/`, restored with the scene,
  removed by *delete forever* / *empty Trash*).
  - *Created* by hand (**Snapshot scene**, optional label; **Snapshot all scenes**, one label for
    book and Unplaced), and automatically (labels `auto`, `before-restore`, `before-accept-all`,
    `before-reject-all`, `end-of-draft-N`): before a restore, before *Accept all* / *Reject all*
    drafts (not for a single draft), when a new draft starts (2.2), and — setting `auto_snapshot`,
    default **on**, user settings (Settings dialog in both front ends) — before the first save that
    changes a scene on a given day (the file as it was; skipped when a snapshot from today exists or
    the latest snapshot already holds exactly that text). Deleting to the Trash and alias/canon
    changes take none (the trash copy suffices / they are not scene text). Snapshots take the
    editor's buffer when given, so unsaved words are kept.
  - *Browse*: GUI — the rail **History** button, the status-bar item "Snapshot 12 min ago", or the
    scene menu open the **History** dialog (list: label, time, words, ± words against the current
    text; **Compare**: side by side, snapshot with removed words struck through on the left, the
    current text with added words highlighted on the right, opening at the first change;
    **Restore**; **Delete**, each destructive step confirmed). Terminal — palette
    *Scene · Snapshots* (enter compares, `r` restores, `d` deletes, `n` new, `a` all scenes),
    *Scene · Snapshot scene*, *Action · Snapshot all scenes*; compare is one unified word-level
    stream (removed red + struck, added green + underlined), and the status bar says
    `Snapshot 12 min ago`.
  - *Compare* is `difflib` on lines, then on words inside changed lines
    (`snapshots.diff_words`; whitespace travels with its word so each side re-concatenates to the
    original; a hunk over 40M token pairs degrades to one replace).
  - *Restore* snapshots the current text first (`before-restore`), writes the snapshot atomically and
    puts its draft originals back as the scene's `.drafts` sidecar (replacing it; the
    pre-restore snapshot keeps the old originals). The GUI flushes the editor, calls
    `restore_snapshot`, detaches the save controller and reopens the scene.

- **Drafts** (2.2). `project.toml` `[manuscript] draft = N` (default 1 when absent or invalid;
  `Project.draft`). *Start new draft* (GUI: the title-bar "Draft N" badge or the status-bar item
  opens a menu, then a confirmation; terminal: palette *Action · Start new draft*, confirmed)
  snapshots every scene (book and Unplaced) as `end-of-draft-N`, then writes `draft = N + 1`
  (`Project.start_new_draft`; if a snapshot fails the counter is not advanced). Scene text is not
  changed. The badge and the status bar say "Draft N" (the terminal puts it in its status line).
  The `end-of-draft-N` snapshots appear in History as "End of draft N".

- **Sync** (2.3, `core/sync.py`; git, explicit only). If the project folder is (inside) a git
  repository — `git` itself is optional — the status bar shows `Synced` (clean and not ahead),
  `N changes` (uncommitted: modified, staged or untracked files inside the project; changes win over
  ahead) or `Ahead N` (committed, not pushed; for a branch that was never pushed, commits not on any
  remote). One read-only `git status --porcelain=v2 --branch -z --untracked-files=all -- .` (5 s
  timeout, `GIT_OPTIONAL_LOCKS=0`, so it never blocks or alters the repo) runs when the project
  opens and 2.5 s after a save (trailing throttle; the workspace refresh does not run git). A hung or
  failing git hides the item rather than freezing the app. No git installed: the item is hidden. No
  repository: the GUI shows a muted `Sync` whose menu offers only *Initialize git*; the terminal
  offers the palette action.
  - Actions, **only on an explicit click / palette pick** (GUI: status-bar menu; terminal: palette
    *Commit changes*, *Push* — listed only when a remote is configured — and *Initialize git for this
    project*): **Commit changes** — message prefilled `lorewrite: 2026-10-01 — 3 scenes changed`
    (files when no scene changed), editable, multi-line allowed; stages and commits the project folder
    only (`git add -A -- .` then `git commit -- .`, so a project inside a bigger repository never
    commits anything outside itself and files staged elsewhere stay staged; the dialog names the
    repository); the editor is flushed first. **Push** — a confirmation naming the branch, the remote
    and its URL; plain `git push` (or `-u <remote> <branch>` the first time); never `--force`, never
    automatic, `GIT_TERMINAL_PROMPT=0` and `ssh -o BatchMode=yes` so it fails instead of waiting for a
    password. A diverged remote is refused with git's message. **Initialize git** — `git init` plus a
    `.gitignore` containing `.lorewrite/` (appended if missing, never duplicated); refuses inside an
    existing repository; commits nothing. Everything under `.snapshots/`, `.drafts/`, `.trash/` and
    `style.md` is committed (none is ignored). Errors are git's own words, shown as a notice.
  - Not done: pull / fetch / merge (the status shows `behind` internally but nothing acts on it),
    branches, credentials management, a commit history view.

### Notes around the manuscript ✅ (Wave 3, implemented 2026-10-01; plan: docs/plan-workspace.md)

*Collections, comments, research and the assistant's conversation history. All plain files
(§2); nothing here lives only in `.lorewrite/`, and none of it is git-ignored.*

- **Collections** (3.1, `core/collections.py`). Named groups of scenes ("Needs continuity pass",
  "Mara's arc"). *Definitions* are a `[collections]` table in `project.toml`, name → colour, one of
  the design's swatch tokens `violet | amber | green | red | gray`
  (`"Needs continuity pass" = "amber"`). *Membership* is each scene's own frontmatter,
  `collections: [Needs continuity pass]` (the Wave 1 format), so it travels with the scene and
  needs no index. A name that scenes use but `project.toml` does not define is still listed (grey,
  "not defined"; recolouring it defines it): membership is never hidden. Names are matched
  case-insensitively and stored as defined; at most 60 characters.
  Operations: create, recolour, rename (rewrites the definition and every member scene's
  frontmatter), delete (takes the name off every scene after a confirmation; no scene is
  deleted), tick a scene in or out (`toggle`). The open scene's membership is edited through its
  editor buffer like the other details (GUI `set_scene_details`, terminal the same
  `scenemeta.set_details` on the buffer); rename and delete rewrite *other* files, so the GUI
  flushes the open scene first and reopens it if it changed (`changed` ids from the bridge), and
  the terminal re-reads its buffer. Unplaced scenes keep their membership; trashed ones are not
  counted.
  GUI: the binder's Collections section is real (swatch, name, count); a click filters the
  binder and the corkboard / outline to the members ("Only “X” · 3 — Show all"; drag-to-reorder
  still plans against the whole book), **Edit** opens the manager (add with a swatch, click a
  name to rename, swatches to recolour, trash to delete), and the inspector's **Collections**
  entry or the scene menu opens a checkbox list for the open scene. Terminal: palette
  *Scene · Collections* (`space`/`enter` tick, `n` new, `r` rename, `c` next colour, `d` delete) and the
  sidebar filter accepts `#collection-name` (a part of the name is enough; scenes only).

- **Comments** (3.2, `core/comments.py`). Author notes anchored to a passage, **never inline**:
  `<project>/.comments/<scene's project-relative path, "/" as "__">.json` is a JSON list of
  `{id, quote, prefix, suffix, body, created, resolved}` (id = 8 hex characters; created =
  local ISO time; body ≤ 5000 characters, quote ≤ 2000). Author data like `.drafts/`: committed,
  never under `.lorewrite/`, and carried with its scene on every rename / move / part swap and into
  the Trash (`.trash/<name>.md.comments.json`, restored with the scene, removed by *delete forever*).
  - *Anchoring.* The quote plus up to 40 characters of context each side. `locate` finds the
    passage again in this order: the quote itself (several matches: the one whose context matches
    best; whitespace runs match any whitespace run, so re-wrapped lines still match); the quote's two
    ends (24 characters each) when its middle was edited; the text between the stored prefix and
    suffix when it was rewritten. Otherwise the comment is **detached**: it stays in the file and
    in the list (listed first, "Detached"), and re-attaches if the text returns (undo). `reanchor`
    runs on save (both front ends) and when the GUI lists comments: a comment found by the fuzzy
    rules gets its stored quote and context refreshed so the next find is exact; a detached one is
    never rewritten. Comments cannot be placed on the scene-details frontmatter.
  - *Not scene text.* Not spell-checked, not counted, not sent to the AI; only the author attaches
    them to a chat (3.4).
  - GUI: the toolbar comment button (enabled with a selection) opens an Add dialog; the passage gets a
    quiet amber highlight and a marker in the page margin of its first line; clicking the marker opens
    the popover (edit the text, Resolve / Reopen, Delete after a confirmation); the Notes tab lists
    comments (open ones top to bottom, detached first, resolved ones folded under "Show resolved") and a
    click selects the passage and opens its popover. Positions are computed by Python against the
    editor's text (UTF-16 offsets) and refetched 0.5 s after edits; between refetches the highlights
    follow the text through CodeMirror's change mapping. Terminal: palette *Scene · Add comment on
    selection* (a one-line prompt) and *Scene · Comments* (`enter` jump to and select the passage, `r`
    resolve / reopen, `e` edit, `d` delete); commented text is underlined faintly (open comments only).

- **Research** (3.3, `core/research.py`). `<project>/research/` holds plain Markdown notes, any
  subfolders (dot-files ignored). They are not scenes (not in the book, not counted, not read by
  continuity) and not entities (no frontmatter; **not in the link index**, so `[[links]]` inside
  them are highlighted but add no backlinks). A note's title is its first `# heading`, else the
  file name de-slugged. Creating: *New research note* (`research/<slug>.md`, `-2` for a clash) and
  *from a link* - a note holding the URL and a title made from it (`host - last path segment`);
  **nothing is fetched**. A link pasted outside a text field, or dropped on the binder, offers to
  save itself this way (GUI). *Delete research note* asks first ("Move to Trash") and moves the
  note to the project Trash (4.4), from where it can be restored.
  - *The Research question* (assistant quick action in the GUI, where it turns Research mode on for
    the next questions; `ctrl+r` inside the terminal's assistant window; palette *Action · Research
    question*). `research.search` scores notes by keyword (query terms of 3+ letters minus stop words,
    crudely stemmed; per-term count damped and weighted by rarity across notes, extra for a title
    hit; zero-score notes are not returned) and returns the best paragraph of each of the top 5.
    `ai.writing.research_context` numbers them `[1]…` with the project canon (characters and
    places, capped) and `research_answer` asks the *writing* model to answer **only** from them,
    citing `[n]`, saying so when the notes do not cover it, and never citing the canon. With no
    research notes at all it refuses without an AI call. The reply is chat text with its `sources`
    (id, title, in citation order): GUI chips open the note, terminal `ctrl+o`. No web access.
  - GUI: the binder's Research group is real (count; subfolders as folders; notes open in the
    editor as `RESEARCH`, no spelling, mentions or index); the quick switcher lists them. Terminal:
    palette *Research · <title>* opens one; *New research note*, *New research note from a link*,
    *Delete research note*.

- **Assistant conversations, attach and Save to notes** (3.4, `core/chats.py`, `core/attach.py`).
  - *History.* Chats persist per project as `<project>/.assistant/chats/<id>.json` (id = `c` + 10 hex
    characters): `{id, title, created, updated, scope, attachments, messages[{id, role, text,
    error?, sources?}]}`. Title = the first prompt (60 characters), kept unless renamed. The client
    sends its whole conversation after every answer (`save_chat`), so a regenerated answer simply
    replaces the old one; failed answers (`error`) are not stored; at most 400 messages, 20,000
    characters each. Chat ids come over the bridge, so every lookup refuses anything that is not a
    plain id. GUI: the Assistant header's **History** button lists chats (newest activity first; open,
    rename, delete after a confirmation, **New chat**), the AI menu has *New chat* and *Conversation
    history…*; opening a chat restores its messages, scope and attachments. Terminal: palette *Action ·
    Ask the assistant* opens the chat window (`ctrl+r` research mode, `ctrl+t` saved conversations,
    `ctrl+n` new chat, `ctrl+s` save the last answer to notes, `ctrl+o` open a cited note); *Action ·
    Saved conversations* goes straight to the list. The terminal chat has **no attach** in v1. A chat
    about the open scene reads it (`build_context`); with no scene open, the project (titles + canon).
  - *Attach* (GUI paperclip). Pick scenes, entity notes, research notes, or a scene's open
    **comments** (the only way a comment reaches the AI). Chips above the composer, removable; a
    change to a saved chat's attachments is saved. `core.attach.build` resolves them at send time:
    each item at most 8,000 characters, all together at most 24,000, at most 12 items, below 200
    characters of room an item is skipped; scene text loses its details block and pending AI drafts;
    comment text loses `<!--`. The reply carries an `attached` report (truncated / skipped with the
    reason) and the GUI says so in a notice: nothing is trimmed or dropped silently. The picker shows
    approximate words against the cap (about 4,000 words). Both *Ask* and *Research* take attachments
    as `ATTACHED …` sections after the normal context.
  - *Save to notes.* The reply's bookmark button (was the placeholder thumb) appends the reply, under
    `## <date> - <prompt>` with a `**Prompt:**` line, to `research/assistant-notes.md` (created with
    `# Assistant notes`). It is an ordinary research note afterwards, so the Research action can
    find it again. Nothing is sent anywhere.

### Export ✅ (M7, implemented 2026-10-01; plan: docs/plan-export.md)

*The manuscript as a file to print, send or read elsewhere. Read-only: export never changes a scene.*

- **What is in the book** (`core/export/manuscript.py`, `assemble`): the title and author
  (`project.toml`), the Front Matter part (option, default on), then the unparted scenes and the
  parts in reading order with their part titles. **Left out:** Unplaced Scenes, the Trash,
  research, comments, notes, entities, scene details (frontmatter). Per scene: the `# heading` is
  the title; `[[Name]]` / `[[Name|text]]` become their display text; Markdown `*italic*`,
  `**bold**`, `***both***` are kept as runs, backticks drop away; a `***` / `---` / `* * *` line is a
  scene break (drawn as an ornament); `{{expand: ...}}` markers are removed and reported (scene and
  instruction). **Pending AI drafts** are rejected by default (the original text from the `.drafts`
  sidecar, like `strip_pending`; a draft whose original is missing is dropped and reported), or
  accepted as written with *Include pending AI drafts*; either way the dialog says how many scenes
  have unaccepted drafts. The word count of the result is reported.
- **Headings:** the `[manuscript] unit` gives "Scene 3" / "Chapter 3"; option `numbering`:
  `words` ("Scene 3"), `numbers` ("3") or `titles-only`. Numbers run through the book, front matter
  excluded; parts are "Part I", "Part II" (roman). Option `continuous` runs a part's scenes together
  with the break ornament and no scene headings or pages.
- **Formats:** *PDF* with three layouts, *DOCX*, *EPUB* (one file per scene, per part when there
  are parts, with a title page), *Markdown* (one combined `.md`), *LaTeX source* (pandoc `.tex`).
  DOCX / EPUB / LaTeX need `pandoc`; without it they are greyed out with "install pandoc". PDF needs
  ReportLab (`pip install 'lorewrite[export]'`, which also brings `pyphen` for hyphenation).
  The Markdown given to pandoc is escaped and read with raw HTML / TeX off, so nothing in a scene
  becomes markup and pandoc has nothing to fetch (pandoc's `--sandbox` stops this pandoc from
  finding its own templates, so it is not used).
- **PDF layouts** (`core/export/layouts/`, registry in `layouts/__init__.py`; embedded TrueType
  fonts: Noto Serif, Liberation Serif / Sans / Mono):
  - *Book* (default): title page (+ optional copyright / edition line), optional contents with page
    numbers, part title pages, every scene or chapter on a new page, justified text with
    hyphenation, first paragraph unindented, running heads (book title on left pages, chapter title
    on right pages; none on opening pages), page numbers, mirrored margins, bookmarks. Trade 6 x 9 in
    (default), A5 or US Letter; Noto Serif or Liberation Serif at 11 / 14 pt; curly quotes.
  - *Manuscript review*: US Letter, 1 inch margins, 12 pt Liberation Serif or Mono, double spaced
    on a 24 pt grid (27 lines per page), **line numbers** in the left margin restarting on every
    page, header "Surname / TITLE / page", each chapter a third of the way down its page, `#` for
    scene breaks, "about 82,000 words" on the title page.
  - *Plain proof*: A4 (or Letter), Liberation Sans 10.5 pt, 1.5 spacing, left aligned, a page per
    chapter, title and page number in the foot.
- **Output:** `<project>/exports/<slug>-<layout or format>-<YYYYMMDD-HHMM>.<ext>`; never overwrites
  (`-2`, `-3`); written to a temporary `.part` file and renamed, so a failed export leaves
  nothing. The folder is the author's, not git-ignored. The result reports path, pages (PDF),
  words, scenes and warnings. If the chosen font is not installed another font of the layout is used
  and the result says so.
- **Remembered options** per project in `project.toml` `[export]` (format, layout, page_size, font,
  numbering, toc, include_front_matter, include_drafts, continuous, copyright).
- **Desktop:** *Export...* in the project menu (title bar "..."), and in the binder "..." menu: a
  dialog with format, layout, page size, font, headings, switches and a live summary ("4 scenes,
  1,502 words, 2 parts; 1 scene has unaccepted AI drafts"). The open scene is saved first; the
  export runs in a worker thread (`gui/exports.py`: `export_start` / `export_status` polling);
  then "Saved to exports/..." with **Open file** and **Show folder** (`core/desktop.open_path`, only on a click,
  only for files inside `exports/`).
- **Terminal:** palette *Action · Export manuscript* (a form: format, layout, page size, headings,
  switches, copyright line; ctrl+s exports in a worker and the path is shown in a notification) and
  *Action · Open exports folder*.
- No AI is involved anywhere in export.

### Desktop GUI (pywebview + the React design) ✅ (implemented; merged to main 2026-10-01)

An Obsidian-style desktop front end over the same `core/` and `ai/`: a native
window (pywebview, WebKitGTK) showing a React/TypeScript UI built from the
"LoreWriter" Figma design (`gui/`). The TUI stays fully supported and unchanged;
both edit the same plain-Markdown projects.

- **Shell.** `lorewrite-gui` (`src/lorewrite/gui/app.py`) opens a frameless
  1600×1000 window on the built UI (`src/lorewrite/gui/web/`, found by `gui/webroot.py`; falls back to `gui/dist`) and hands it a bridge object. The UI calls the
  Python core **in-process** through pywebview's `js_api`; there is no server in
  the real app. Tauri is not used (`gui/src-tauri/` is kept untouched for a
  possible later packaging path).
- **Bridge.** `gui/api.py::Api` — every public method takes JSON and returns
  `{ok: true, …}` or `{ok: false, error}`; it never raises across the bridge.
  One `RLock` guards project writes and is **not** held during AI network calls
  (saves stay responsive). `workspace.py` builds the binder/status JSON the UI
  renders (`gui/src/data/types.ts` mirrors it; one JSON fixture is checked by
  pytest and vitest). `devserver.py` serves the built UI plus `POST /api/<method>`
  on localhost for headless-browser screenshots; `--mock-ai` answers AI calls
  with canned results (no network).
- **Nothing is re-implemented in TypeScript.** Matching of names, `[[links]]`,
  pending drafts and `{{expand:}}` markers is computed by `core/spans.py` (offsets
  converted to UTF-16 for the editor); saving, index updates, drafts, canon,
  waivers, models and cost all call the existing `core/`/`ai/` modules. Logic the
  TUI and GUI share was factored out of `tui/app.py` (`write_atomic`,
  `count_words`, `canon_map`, `resolve_model`, `prepare_draft`, `fresh_id`,
  `locate_evidence`, `ai.writing.ask`).
- **Editor.** CodeMirror 6 on the plain Markdown file. The first `# heading` is
  the scene title (kicker "SCENE NN" from the filename prefix); mentions are
  coloured, `[[` `]]` and `Name|` are hidden unless the cursor is inside the link,
  pending AI drafts hide their `<!--ai-->` markers and show inline Accept/Reject
  (`f7`/`f8`), hard-wrapped source lines are shown as flowing paragraphs (display
  only, a setting). Autosave after 1.5 s of idle, on blur and on `ctrl+s`; if the
  file changed on disk since it was opened (the TUI may be running) nothing is
  overwritten and a banner offers *Reload from disk* / *Keep my version*.
- **AI stays suggest-and-confirm.** Continuity issues are cards (Review passage /
  Dismiss = waive); alias finder and story-bible updates are review dialogs with
  opt-in rows; the style guide is an editable proposal saved only on confirm;
  draft/expand/rewrite text only ever arrives as a pending `<!--ai-->` draft
  whose replaced original is stored in `.drafts/` **before** the marker is written;
  chat (`ask`) answers in the panel only, with *Insert as draft*.
- **Placeholders.** Parts of the design that LoreWriter does not do yet are drawn
  as designed but dimmed, non-interactive, tooltip "Not in LoreWriter yet"
  (`gui/src/components/placeholder.ts`): nothing is left as a placeholder since Wave 4 (the Draft
  badge and status item, Snapshots, Sync and the History button became real in Wave 2; the Research
  row, Collections, the comment button, the Research quick action, conversation history, attach-context
  and the reply's Save to notes in Wave 3; the status-bar Streak and `session words / target`, the focus
  timer and the Brainstorm quick action in Wave 4). The helper stays for future design elements.
  No fake data is ever shown in one.
- **Keys.** `ctrl+k` quick switcher, `ctrl+s` save, `ctrl+n` new scene, `f11`
  focus mode, `ctrl+j` in the editor: open the note under the cursor / make a note
  for the selected name (elsewhere it focuses the assistant composer, as in the
  design), `ctrl+g` draft / expand / rewrite, `f7`/`f8` accept/reject the draft
  under the cursor, ctrl-click a name to open its note in the Notes tab, `ctrl+.`
  on a misspelled word (or click / right-click it) for the spelling popover (M6).
- **Known limits.** Closing the window from the window manager (not the in-app
  button) relies on the 1.5 s autosave and the blur/pagehide flush rather than a
  synchronous final save. Window resizing on a frameless GTK window depends on the
  compositor. Tauri packaging is untested.

## 8. Cost & key management

- BYOK via OpenRouter; `keyring` storage (Secret Service on Linux), config-file fallback `chmod 600`, env var for dev
- Estimated hobbyist cost at 2–5k words/day with all AI features: **~$1.50–3.00/month** mid-tier, <$10–15 on premium models
- Model slugs resolved from `/api/v1/models` at runtime, never hardcoded (catalog churns). Settings has a **Choose…** picker per model field: filterable list of the live catalog (name, id, $/M in/out, context), limited to models with `structured_outputs` for the fast/strong fields (their calls require a strict JSON schema), the whole catalog for the writing field (drafting is plain text); fetched once per session, free-text slug entry still works offline
- **Three model roles**: `fast` (alias finding), `strong` (continuity, story bible), `writing` (drafting, rewrites, style guide). Precedence per role: `project.toml [ai] <role>_model` > user setting `<role>_model` > built-in default. The writing model is a user choice, not hardcoded.
- Per-call cost tracked from `usage.cost` (requests send `usage: {include: true}`) in a session ledger (`ai/usage.py`) and shown in the status bar (`AI $0.0123`) and in each AI call's notification — AI spend is always visible

## 9. Testing strategy

- `core/` is pure Python: full unit tests, no TUI needed (parsing, index, backlinks, entity resolution)
- TUI: `pytest` + `pytest-asyncio` + Textual `Pilot` headless tests (open project, type a link, jump, create note, backlinks update)
- GUI: the `Api`/`workspace`/`spans` layers are plain pytest (temp projects, AI mocked at `lorewrite.gui.api.<fn>`, `make_client` booby-trapped); the React side uses `vitest` for pure logic (decoration mapping, save state machine, transports, draft anchoring) and headless Chromium against `devserver --mock-ai` for screenshots and interaction checks
- AI: responses mocked at the `openai` client boundary; golden-file tests for prompt assembly and offset validation

## 10. Risks

| Risk | Mitigation |
|---|---|
| Link highlighting uses a private TextArea hook | Isolated subclass + plain fallback; pin Textual version |
| Structured-output compliance varies per OpenRouter endpoint | `provider.require_parameters: true`; app-side offset validation; retry path |
| Large-scene editor performance (tree-sitter reparse) | Debounced handlers; benchmark at 50k-word scenes in M1 |
| Index staleness after external edits | Index is rebuildable (`f9`); mtime check on project open |
| pywebview/WebKitGTK quirks (frameless window, key events, tooltips) | Everything user-visible is also exercised in headless Chromium against the same bridge; one manual smoke launch per release; `src-tauri/` kept as a fallback shell |
| AI scope creep into prose | Hard rule: no AI feature mutates text without explicit per-instance author confirmation |

## 11. Decisions (resolved)

1. Keybindings: `ctrl+j` jump, `ctrl+p` palette, `f9` rebuild, `ctrl+s` explicit save, `ctrl+b` sidebar toggle, `?` help screen.
2. Scene ordering by filename prefix (`01-`, `02-`); parts are folders ordered the same way; drag-reorder in the GUI (Wave 1).
3. One project per app instance; `--project` flag to open.
4. Platform target: Omarchy (Arch/Hyprland) — follow the system theme, launchable from the top bar (see M5).

### M1.5 — UX polish (from independent GLM review, docs/ux-review-glm.md)

- **First-run tour**: 4-page modal (project layout, writing, links, finding things), shown once; `tour_seen` in `~/.local/state/lorewrite/settings.json`
- **Palette categorization**: every hit prefixed `Scene · / Entity · / Link · / Action ·`
- **Writer mode** (`f11`): hides sidebar/panel/header/footer, pads editor; status bar stays
- **Scene navigation**: `alt+left/right` prev/next scene (`ctrl+[` is Escape in terminals; `ctrl+enter` unreachable)
- **Sidebar filter**: type-to-filter input above the lists; teaching placeholders when empty
- **Status bar**: dirty dot, `saved HH:MM`, scene + project word counts
- **Editor prefs in project.toml** `[editor]`: `padding` (0–8), `line_numbers`
- Palette providers are error-isolated; version shown in header and launch screen
- Deferred P2: mouse menus, outline viz, hover cards (session stats moved to M6 per author request)

## 11b. Known concerns

- **Command palette UX** (user, 2026-09): still not convinced the palette is the
  right primary interface even after categorization. Options to revisit: a plain
  drop-down command menu modal, a menu bar, or more direct keybindings moving
  actions out of the palette. Not blocking; revisit after M2.

## 12. M5 — Omarchy integration

**Theme following (implemented ahead of schedule):** `tui/theme.py` reads the
current theme slug from `~/.local/state/omarchy/current/theme.name`, loads its
`colors.toml` (user overlay `~/.config/omarchy/themes/<slug>/` wins over stock
`/usr/share/omarchy/themes/<slug>/`, same precedence as Omarchy), and maps it
to a Textual `Theme` (accent→primary, cyan→resolved links, orange→unresolved
links, etc.). Off-Omarchy it returns None and the built-in Textual theme is
used. Live theme-switching while running: deferred (relaunch picks up changes;
could later use a `theme-set` hook or file watch).

**Launcher:** `omarchy tui install "Lorewrite" "lorewrite --project <path>" <window-style> <icon>`
creates a desktop launcher; `omarchy launch or focus tui --app-id=lorewrite ...`
gives launch-or-focus behavior.

**Top bar ✅ (2026-09):** user shell plugin `~/.config/omarchy/plugins/<user>.lorewrite/`
(manifest + Panel.qml — a `BarWidget` with one pencil button) registered in the
right section of `~/.config/omarchy/shell.json`. Click runs
`omarchy launch or focus tui --app-id=lorewrite <repo>/.venv/bin/lorewrite` —
launch-or-focus, so a running window gets focused instead of duplicated.
