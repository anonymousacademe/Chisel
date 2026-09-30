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

- No publishing/export pipeline (Markdown files are already exportable).
- No collaboration or sync (plain files + user's own git/Syncthing).
- No block references, embeds, or `[[Note#Section]]` links (consider later).
- No auto-applied AI edits of any kind.

## 4. On-disk project layout

```
my-novel/
├── project.toml              # title, author, settings
├── manuscript/
│   ├── 01-arrival.md         # scenes; leading number = order
│   ├── 02-the-tavern.md
│   └── ...
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

- **Launch screen** (added in polish): recent projects (stored in `~/.local/state/lorewrite/recent.json`, `LOREWRITE_STATE_DIR` override), open folder, new project (title + location, slug-prefilled). `lorewrite` bare → launch screen; `--project PATH` opens directly; `--new TITLE` creates.
- Create/open project; three-pane layout: scene list | editor | entity panel
- Markdown `TextArea` with **tree-sitter Markdown highlighting**, soft wrap, autosave (atomic temp-file-rename writes) + explicit `ctrl+s`, saved/modified **status bar** (file, words, cursor, link hint)
- `[[...]]` parsing; links highlighted in editor (theme-aware colors); unresolved links styled distinctly
- `ctrl+j` with cursor inside a link → open entity note (creating it from template if unresolved)
- Entity panel: shows note of link under cursor + **backlinks** (every scene mentioning it, with line context)
- Command palette opens as a menu (`discover()` populated; empty query matches all): open scene/entity, insert link, **scene organization** (new / rename / move up / move down / delete-with-confirm), new entity, rebuild index
- Scene files renamed by numeric prefix swap on move; delete detaches the buffer before opening the next scene (avoids autosave resurrecting the deleted file)
- Index in SQLite, updated on save, full rebuild command (`f9`)
- `?` help screen, `ctrl+b` sidebar toggle
- Headless smoke tests with Textual `Pilot`

### M2 — AI auto-linking ✅ (implemented)

- OpenRouter client (`openai` SDK, key via `keyring` with `OPENROUTER_API_KEY` env override; "Set OpenRouter API key" palette action stores in keyring)
- "Link mentions in this scene" (`ctrl+l` / palette): fast model (default `google/gemini-2.5-flash`, override per-project via `[ai] fast_model` in project.toml), JSON-schema structured output with `provider.require_parameters`, **offsets validated app-side** (`text[start:end]` must match surface exactly; drift dropped, never guessed; already-linked spans and overlaps skipped)
- Review modal: all suggestions pre-checked, `space` toggle, `a` all, `enter` apply, `esc` cancel; **nothing applied without enter**
- Alias learning: accepted surfaces that aren't known names → "add as alias?" confirm, written into the entity note
- Deferred: previewable entity-rename link rewrite

### M3 — Lore/continuity checking + the Contextual Tracker ✅ (implemented)

*Expanded from vault notes ("The AI Integration.md"): the Contextual Tracker is
the distinguishing mechanic — entity notes become a living story bible.
Implemented via parallel agents per docs/specification-guide.md.*

- "Check scene for continuity issues" (palette): strong model (default `anthropic/claude-sonnet-4.5`, override `[ai] strong_model`), **Jev pre-screen gate** (`core/jev_interface.py`, fail-open) so only canon-bearing entities flagged as plausible get the expensive call
- Structured report (type/severity/entity/evidence/fix) validated app-side; evidence located to a line; **ContinuityScreen**: `space` waives (persisted in `.lorewrite/waivers.json` by stable content key, never re-reported), `enter` jumps to the offending line
- **Note accumulation**: "Update story bible from scene" (palette) → AI proposes canon updates → review modal → accepted updates written into a managed `## Canon (auto)` section of each entity note (author text never touched)
- Error classes: physical attributes, timeline, character knowledge, object custody, present/absent, spelling drift
- Deferred: whole-manuscript check, cross-scene retrieval layer

### M4 — Placeholder expansion + the Style Tracker

*Expanded from vault notes: AI-written text is always visually marked and
review-gated.*

- **Style guide**: the app maintains a per-project style summary learned from the author's own prose (updated on demand), stored in the project (e.g. `.lorewrite/style.md`), used as context for all generative features.
- `{{expand: instruction}}` markers; mid-tier model with style guide + surrounding ±500 words + 2-3 exemplar paragraphs
- **Hotkey prompt window** (vault): "Give me one paragraph describing the busy street… stressed mood" → drafted with story + character + style context
- **AI-written text is inserted in a distinct color** flagged as AI-generated; it stays marked until the author explicitly accepts it (accept = normal text). Rollback/reject always available.
- **Style rewrite** (vault): author selects a section that "feels off"; AI proposes a rewrite in the author's style as a colored diff — approve or roll back to the original.
- Optional inline completion via `TextArea.suggestion` ghost text, off by default

### M6 — Writing aids

*From vault "Additional Items.md". Session stats reverse the M1.5 dashboard
rejection — the author explicitly wants a lightweight version.*

- **Spell/grammar check**: integrated, on/off toggle; optional live mode (misspellings underlined). aspell/hunspell for spelling (offline, free), LLM pass for grammar on demand.
- **Focus timer**: set a sprint length; countdown shown in the status bar; pairs naturally with writer mode (`f11`).
- **Session stats page**: words written this session, session average, current streak. Read-only summary screen, not a dashboard.
- **Idea generator**: AI "unstuck" prompts (writing techniques, what-if questions about current scene/characters).

### M7 — Manuscript organization + export

*From vault "The Manuscript Organizer and Printer.md".*

- **Manuscript ordering in the main screen**: promote drag-reorder of the scene list (with confirm) from deferred.
- **LaTeX export**: combine the manuscript into a template and produce a PDF:
  - **Book layout** — scenes as chapters, beautifully typeset
  - **Manuscript review layout** — double-spaced, line-numbered, for printing/red-pen review
  - Template system so more layouts can be added

### M8 — Beyond novels (exploratory)

*From vault "Additional Items.md". Deliberately not core-roadmap; revisit once
fiction workflow is solid.*

- **Technical documents/textbooks**: figures, tables, captions, and LaTeX equations become the "entities" (first-class linkable, checked for consistency); AI format-consistency checking; figure generation from a figure/table design guide
- **Screenplay mode**: screenplay formatting rules in the editor, same AI toolset, LaTeX screenplay export

### Future direction — Obsidian-like GUI

*From vault "Updated GUI.md":* long-term, an Obsidian-style GUI (markdown that
auto-renders as you type) may be a better writing experience than the TUI.
Noted as a possibility, not a commitment. The `core/` (pure Python) / `tui/`
split exists precisely so a second frontend could reuse project handling,
links, entities, index, and AI features unchanged. Revisit after M4/M7; the
TUI remains the supported interface until then.

## 8. Cost & key management

- BYOK via OpenRouter; `keyring` storage (Secret Service on Linux), config-file fallback `chmod 600`, env var for dev
- Estimated hobbyist cost at 2–5k words/day with all AI features: **~$1.50–3.00/month** mid-tier, <$10–15 on premium models
- Model slugs resolved from `/api/v1/models` at runtime, never hardcoded (catalog churns). Settings has a **Choose…** picker per model field: filterable list of the live catalog (name, id, $/M in/out, context), limited to models with `structured_outputs` for the fast/strong fields (their calls require a strict JSON schema), the whole catalog for the writing field (drafting is plain text); fetched once per session, free-text slug entry still works offline
- **Three model roles**: `fast` (alias finding), `strong` (continuity, story bible), `writing` (drafting, rewrites, style guide). Precedence per role: `project.toml [ai] <role>_model` > user setting `<role>_model` > built-in default. The writing model is a user choice, not hardcoded.
- Per-call cost tracked from `usage.cost` (requests send `usage: {include: true}`) in a session ledger (`ai/usage.py`) and shown in the status bar (`AI $0.0123`) and in each AI call's notification — AI spend is always visible

## 9. Testing strategy

- `core/` is pure Python: full unit tests, no TUI needed (parsing, index, backlinks, entity resolution)
- TUI: `pytest` + `pytest-asyncio` + Textual `Pilot` headless tests (open project, type a link, jump, create note, backlinks update)
- AI: responses mocked at the `openai` client boundary; golden-file tests for prompt assembly and offset validation

## 10. Risks

| Risk | Mitigation |
|---|---|
| Link highlighting uses a private TextArea hook | Isolated subclass + plain fallback; pin Textual version |
| Structured-output compliance varies per OpenRouter endpoint | `provider.require_parameters: true`; app-side offset validation; retry path |
| Large-scene editor performance (tree-sitter reparse) | Debounced handlers; benchmark at 50k-word scenes in M1 |
| Index staleness after external edits | Index is rebuildable (`f9`); mtime check on project open |
| AI scope creep into prose | Hard rule: no AI feature mutates text without explicit per-instance author confirmation |

## 11. Decisions (resolved)

1. Keybindings: `ctrl+j` jump, `ctrl+p` palette, `f9` rebuild, `ctrl+s` explicit save, `ctrl+b` sidebar toggle, `?` help screen.
2. Scene ordering by filename prefix (`01-`, `02-`); drag-reorder deferred.
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
