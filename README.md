# lorewrite

A terminal-native fiction-writing app. Write scenes in a clean Markdown editor,
mark characters and places once — no brackets needed after that — and let AI keep the link
graph and the story's internal consistency up to date — without ever touching
your prose uninvited.

**Status:** early but usable. Milestones M1 (editor + wiki-links), M1.5 (UX
polish), M2 (alias finder), M3 (continuity + story bible) and M4 (style-aware
AI drafting) are implemented and tested. See [SPEC.md](SPEC.md) for the full
design and roadmap.

## Why

- **Your novel is just files.** A project is a folder of plain Markdown —
  greppable, git-friendly, opens in Obsidian. No database, no lock-in.
- **A living story bible.** Characters and places get free-text notes with
  aliases; everything links both ways.
- **AI that suggests, never edits.** Every AI change is proposed in a review
  list. Nothing is applied without your explicit accept.

## Features

- Markdown editor with real syntax highlighting, autosave, and a status bar
  (file, saved/modified, word counts, cursor, link hints)
- No brackets needed: select a name and press `ctrl+j` to make a note for it;
  from then on every mention of that name or its aliases is colored, jumpable
  (`ctrl+j`), and counted in backlinks. `[[Name]]` / `[[Name|alias]]` links
  still work, with their brackets faded; orange means no note yet
- Entity panel with note preview and backlinks to every mentioning scene
- Launch screen with recent projects; command palette with categorized menu
  (`ctrl+p`); scene organization (new / rename / reorder / move)
- **Parts, Unplaced scenes and Trash**: a folder under `manuscript/` is a part
  (the sidebar groups scenes under it); `00-front-matter` is a part that is not
  counted as the book; `manuscript/_unplaced/` holds scenes you wrote but kept out
  of the book (not counted, not in continuity, still indexed for backlinks).
  Deleting a scene (or a research note) moves it to `.trash/` — *Open Trash* restores it,
  deletes it forever or empties the Trash, always after a confirmation.
- **Snapshots**: keep a verbatim copy of a scene (`.snapshots/`), compare it with the
  text as it is now (word by word) and restore it — the text you replace is snapshotted
  first. One is also taken before *Accept/Reject all drafts* and, once a day, before the
  first edit of a scene (Settings → History). *Scene · Snapshots* in the palette; the History
  button in the desktop app.
- **Sync with git (optional, never automatic)**: if the project folder is in a git
  repository the status bar shows `Synced`, `N changes` or `Ahead N`. *Commit changes*
  (message prefilled, editable), *Push* (asks first, names the remote, never forced) and
  *Initialize git for this project* run only when you pick them — palette in the terminal,
  the status-bar item in the desktop app. Needs `git` installed; without it nothing shows.
- **Drafts**: *Start new draft* snapshots the whole book as "end of draft N" and counts
  up (`[manuscript] draft = N` in `project.toml`); the desktop title bar and both status bars
  show "Draft N".
- **Collections** ("Needs continuity pass", "Mara's arc"): group scenes however you like;
  definitions and colours live in `project.toml` `[collections]`, membership in each scene's
  frontmatter. Click one in the desktop binder to see only its scenes (binder, corkboard,
  outline); in the terminal use *Scene · Collections* and the `#name` sidebar filter.
- **Comments**: select a passage and attach a note to it. The note lives in `.comments/` beside
  the scene — never in your prose — and follows the passage when you edit around it (a comment
  whose passage you deleted is kept, listed as "detached"). Desktop: the comment button, a margin
  marker and the Notes tab; terminal: *Scene · Add comment on selection* and *Scene · Comments*.
- **Research**: put reference material in `research/` as plain Markdown notes (any subfolders);
  paste or drop a web link to save it as a note (it is not downloaded). The assistant's
  **Research** action answers a question from those notes and your canon, and tells you which
  notes it used. Terminal: the palette (*Research · …*, *Research question*).
- **Assistant conversations**: chats are kept with the project (`.assistant/chats/`) —
  reopen, rename or delete them from the History button (desktop) or *Saved conversations*
  (terminal, `ctrl+t` in the chat window). Attach scenes, notes, research notes or your comments to a chat with the
  paperclip (desktop; sizes are capped and trimming is always reported), and keep a good
  answer with **Save to notes**, which appends it to `research/assistant-notes.md`.
- **Scene details** (POV, place, purpose, status, word target) are the scene's own
  YAML frontmatter — Obsidian-compatible, written only when you set a field, and
  never counted as prose, spell-checked, or sent to the AI as text (the AI does get
  a one-line header of them). *Scene · Edit details* in the palette; the desktop app
  edits them in the inspector. Set `[manuscript] unit = "chapter"` to say
  "Chapter 03" instead of "Scene 03" (wording only).
- **Spell check** (offline, spelling only): misspellings are underlined in
  scenes; `f6` fixes the next one. Names of your characters and places are never
  flagged, and you can teach it words with two plain-text dictionaries — the
  project's `dictionary.txt` and a personal one in `~/.local/state/lorewrite/`
  (one word or phrase per line, `#` comments allowed; edit them by hand or use
  *Action · Open project dictionary*). Toggle in Settings or the palette. The
  desktop app underlines too: click a word for suggestions, *Add to dictionary*
  and *Ignore* (`ctrl+.` also opens it).
- **Session stats and a streak** (your own numbers, kept in `~/.local/state/lorewrite/stats/`,
  never in the project): words you wrote today (accepted AI drafts are counted separately, pending
  ones not at all), active minutes, sessions, a 30-day chart and a streak of days that met your daily
  word target (Settings; default 500, 0 = off). The status bar shows the streak and
  `+N / target words today`; click it (desktop) or pick *Action · Session stats* (terminal).
- **Brainstorm** (AI): when you are stuck, ask for 3-5 ideas drawn from the scene around the cursor,
  your canon and your style — what-ifs, complications, a sense you have not used, a pressure on a
  character. They are suggestions only: *Draft from this* opens the draft prompt with the idea filled
  in (the result is still a pending draft you accept or reject), *Save to notes* keeps it in
  `research/assistant-notes.md`. Desktop: the Brainstorm quick action; terminal: *Action · Brainstorm*.
- **Focus sprints**: 15 / 25 / 45 / custom minutes with a countdown in the status bar, optional
  writer / focus mode, a quiet notice (no sound) with the words you wrote, recorded in your stats.
  Desktop: the timer button in the status bar; terminal: *Action · Focus sprint*.
- Writer mode (`f11`), first-run tour, sidebar filter, focus-friendly
  keybindings (`alt+←/→` to flip scenes)
- **AI alias finder** (`ctrl+l`): finds other ways your prose refers to known
  characters and places ("the old smith" for Borin) and offers them as aliases
  after an accept/reject review — your scene text is never touched, no
  brackets (OpenRouter, BYOK)
- **AI writing, always review-gated**: learn a **style guide** from your own
  prose (`style.md`, plain Markdown you can edit), then `ctrl+g` to draft at the
  cursor (prompt window), expand a `{{expand: note}}` marker, or rewrite the
  selection in your style. Generated text shows in color and stays a draft
  until you accept it (`f7`) or reject it (`f8`, original restored exactly).
  Drafts live in the scene file as short `<!--ai-->…<!--/ai-->` comments;
  the text a rewrite replaced is kept in `.drafts/` (one small file per scene).
- AI spend for the session in the status bar
- Follows the Omarchy system theme automatically (falls back gracefully
  elsewhere)

## Desktop GUI

The same projects open in a desktop app ("LoreWriter"): a live-preview Markdown
editor (link brackets and AI markers hidden, mentions coloured), binder, scene
corkboard and outline (drag a card or row to reorder it or move it to another
part, with a confirmation and an Undo), notes with backlinks, and the AI assistant
panel. Every AI result is still suggest-and-confirm. Parts of the design that do not exist yet
are shown dimmed with the tooltip "Not in LoreWriter yet".

```bash
# a venv that can see the system PyGObject / WebKitGTK 4.1 bindings
python3 -m venv --system-site-packages .venv-gui
.venv-gui/bin/pip install -e ".[dev,gui]"
(cd gui && npm install && npm run build)       # builds gui/dist (Node 20+)
.venv-gui/bin/lorewrite-gui                     # launch screen
.venv-gui/bin/lorewrite-gui --project ~/novels/my-book
```

Details (architecture, dev server, tests): [gui/README.md](gui/README.md) and the
"Desktop GUI" section of [SPEC.md](SPEC.md). The terminal app below is unchanged
and can run on the same project.

## Install

Requires Python 3.11+.

```bash
git clone <repo-url> lorewrite
cd lorewrite
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run

```bash
.venv/bin/lorewrite            # launch screen (recents / open / new)
.venv/bin/lorewrite --project ~/novels/my-book   # open directly
```

To try everything on a sample story, open a copy of the bundled example
project (see [examples/README.md](examples/README.md)):

```bash
cp -r examples/residual /tmp/residual && .venv/bin/lorewrite --project /tmp/residual
```

First launch shows a 4-page tour. Core keys:

| Key | Action |
|---|---|
| `ctrl+n` | new scene |
| `ctrl+p` | command palette — everything lives here |
| `ctrl+j` | open the note for the name under the cursor; with a name selected (or on an unresolved link), create it |
| `ctrl+l` | AI: find aliases ("the old smith") for your characters/places in this scene |
| `ctrl+g` | AI write: draft at cursor / expand `{{expand: …}}` / rewrite selection |
| `f7` / `f8` | accept / reject the AI draft under the cursor (`f5` = select all) |
| `f6` | spell check: fix the next misspelled word (add it to a dictionary, or ignore it) |
| `alt+←/→` | previous / next scene |
| `f11` | writer mode |
| `ctrl+s` | save (autosave is always on) |
| `f1` | all keybindings (`?` also works outside the editor) |

## AI setup (optional, for `ctrl+l` and the other AI features)

Uses [OpenRouter](https://openrouter.ai) (bring your own key). Either:

- In the app: `ctrl+p` → *Action · Set OpenRouter API key* (stored in your OS
  keyring), or
- Set the `OPENROUTER_API_KEY` environment variable.

Three model roles, each chosen in *Settings* (type a slug or **Choose…** from
the live catalog) or per project in `project.toml` (project wins):

| Role | Used for | Default |
|---|---|---|
| fast | alias finding | `google/gemini-2.5-flash` |
| strong | continuity checks, story-bible updates | `anthropic/claude-sonnet-4.5` |
| writing | drafting, rewrites, style guide | `anthropic/claude-sonnet-4.5` |

```toml
[ai]
fast_model = "google/gemini-2.5-flash"
strong_model = "anthropic/claude-sonnet-4.5"
writing_model = "anthropic/claude-sonnet-4.5"
```

AI spend for the session is shown in the status bar (`AI $0.0123`).

### AI writing

1. `ctrl+p` → *Action · AI: learn style guide from manuscript* — reviews a
   proposed `style.md` (voice, rhythm, diction, dialogue, avoid, verbatim
   exemplars) before saving; *Open style guide* lets you edit it by hand.
2. `ctrl+g` in a scene: with text selected it rewrites it; on a
   `{{expand: describe the rain}}` marker it expands it; otherwise it opens a
   prompt window (submit with `ctrl+g`, cancel with `esc`) and inserts the
   result at the cursor.
3. The result is a **pending draft** (colored italics, faded
   `<!--ai-->` marker comments). `f7` accepts, `f8` rejects; the palette has
   *Accept/Reject all AI drafts in this scene*. Word counts, continuity checks
   and the alias finder ignore pending text.

## Your project on disk

```
my-novel/
├── project.toml          # title + [editor] and [ai] settings
├── manuscript/
│   ├── 01-opening.md     # scenes, numbered; reorder via the palette
│   ├── 02-tavern.md
│   ├── 03-the-recall/    # optional: a folder is a part (title in _part.md)
│   │   ├── _part.md      #   "# The Recall" + your notes on the part
│   │   └── 01-rain.md    #   scene numbering continues across parts
│   └── _unplaced/        # optional: written, but not in the book
├── .trash/               # deleted scenes wait here (restore from the app)
├── .drafts/              # text pending AI drafts replaced, one file per scene
├── .snapshots/           # History: a folder of snapshots per scene (plain copies)
├── .comments/            # your comments on passages, one small JSON file per scene
├── research/             # reference notes (plain Markdown, any subfolders)
├── .assistant/chats/     # saved assistant conversations, one JSON file per chat
└── entities/
    ├── characters/elara-vance.md   # free-text note + YAML frontmatter
    └── places/thornwick.md         #   (name, type, aliases)
```

## Roadmap

M3 lore/continuity checking ("the Contextual Tracker") → M4 style-aware AI
drafting (review-gated) → M6 writing aids (spellcheck, focus timer, session
stats) → M7 LaTeX export → M8 beyond-novels modes. Details in
[SPEC.md](SPEC.md).

## Development

```bash
.venv/bin/python -m pytest    # pure core units + headless TUI (Pilot)
```

Design document: [SPEC.md](SPEC.md). Agent/contributor guide:
[AGENTS.md](AGENTS.md). Independent UX review:
[docs/ux-review-glm.md](docs/ux-review-glm.md).
