# lorewrite

A terminal-native fiction-writing app. Write scenes in a clean Markdown editor,
mark characters and places with `[[wiki-links]]`, and let AI keep the link
graph and the story's internal consistency up to date — without ever touching
your prose uninvited.

**Status:** early but usable. Milestones M1 (editor + wiki-links), M1.5 (UX
polish), and M2 (AI auto-linking) are implemented and tested. See
[SPEC.md](SPEC.md) for the full design and roadmap (M3 lore-checking is next).

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
- `[[Character]]` / `[[Place|alias]]` links — cyan when the note exists,
  orange when it doesn't; `ctrl+j` jumps to (or creates) the note
- Entity panel with note preview and backlinks to every mentioning scene
- Launch screen with recent projects; command palette with categorized menu
  (`ctrl+p`); scene organization (new / rename / reorder / delete)
- Writer mode (`f11`), first-run tour, sidebar filter, focus-friendly
  keybindings (`alt+←/→` to flip scenes)
- **AI auto-linking** (`ctrl+l`): proposes `[[links]]` for unlinked mentions —
  including aliases like "the old smith" — with an accept/reject review and
  alias learning (OpenRouter, BYOK)
- Follows the Omarchy system theme automatically (falls back gracefully
  elsewhere)

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

First launch shows a 4-page tour. Core keys:

| Key | Action |
|---|---|
| `ctrl+n` | new scene |
| `ctrl+p` | command palette — everything lives here |
| `ctrl+j` | jump to the `[[link]]` under the cursor (creates the note if missing) |
| `ctrl+l` | AI: propose links for unlinked mentions in this scene |
| `alt+←/→` | previous / next scene |
| `f11` | writer mode |
| `ctrl+s` | save (autosave is always on) |
| `?` | all keybindings |

## AI setup (optional, for `ctrl+l` and future features)

Uses [OpenRouter](https://openrouter.ai) (bring your own key). Either:

- In the app: `ctrl+p` → *Action · Set OpenRouter API key* (stored in your OS
  keyring), or
- Set the `OPENROUTER_API_KEY` environment variable.

Default models are cheap-tier; override per project in `project.toml`:

```toml
[ai]
fast_model = "google/gemini-2.5-flash"
```

## Your project on disk

```
my-novel/
├── project.toml          # title + [editor] and [ai] settings
├── manuscript/
│   ├── 01-opening.md     # scenes, numbered; reorder via the palette
│   └── 02-tavern.md
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
.venv/bin/python -m pytest    # 75 tests: pure core units + headless TUI (Pilot)
```

Design document: [SPEC.md](SPEC.md). Agent/contributor guide:
[AGENTS.md](AGENTS.md). Independent UX review:
[docs/ux-review-glm.md](docs/ux-review-glm.md).
