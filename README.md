<p align="center">
  <img src="docs/brand/chisel-icon-1024.png" alt="Chisel logo: an open book, half stone, with a chisel" width="128">
</p>

# Chisel

A fiction-writing app for your desktop and your terminal. Your novel is a folder
of plain Markdown files; characters and places are notes that link both ways; and
AI helps you keep the story consistent, but it only ever **suggests** — it never
changes your prose unless you accept the change.

![Chisel: binder, live-preview editor and assistant panel](docs/screenshots/chisel.png)

Chisel runs on Windows, macOS and Linux. The desktop app (`chisel-gui`)
and the terminal app (`chisel`) open the same projects, so you can use either,
or both.

## Why

- **Your novel is just files.** A project is a folder of Markdown. It is
  greppable, works with git, and opens in Obsidian or any editor. There is no
  database to lose and no lock-in.
- **A living story bible.** Characters and places have free-text notes with
  aliases. Select a name once and make a note; from then on every mention is
  coloured, jumpable and counted in backlinks. No brackets needed (`[[Name]]`
  links still work).
- **AI that suggests, never edits.** Every AI result is a proposal you accept or
  reject. Nothing is applied behind your back, and unaccepted AI text is never
  treated as canon.
- **Optional AI, bring your own key.** Without a key everything but the AI
  features works, offline.

## Features

**Writing**
- Markdown editor with autosave, word counts, writer/focus mode and an offline
  spell check (spelling only; your characters' names are never flagged; personal
  and project dictionaries are plain text files).
- Desktop: live-preview editor (link brackets and AI markers hidden), binder,
  corkboard and outline views with drag-to-reorder, and an inspector for scene
  details. Terminal: sidebar, command palette (`ctrl+p`) and keyboard-first
  editing.
- On Omarchy (Linux) the terminal app follows the system theme; elsewhere it uses
  Textual's built-in themes.
- Session stats, a daily word target with a streak, and focus sprints. These
  numbers stay on your machine, never in the project.

**Organising the book**
- Parts (folders), scenes, *Parked scenes* for scenes you wrote but kept out
  of the book, and a Trash: deleting always moves to `.trash/`.
- Collections ("Needs continuity pass", "Mara's arc"), scene details (POV, place,
  status, word target, and an optional story time with characters' birth years for ages;
  leave it blank and everything uses reading order) as YAML frontmatter, comments on passages (kept beside the
  scene, never in the prose), notebook notes, and snapshots with a word-by-word
  comparison and restore.
- Optional git sync that runs only when you click: commit, push (never forced,
  asks first) and init. Without git installed, nothing shows.

**AI, always review-gated** (OpenRouter today; local models are planned)
- *Alias finder*: finds other ways your prose refers to known characters ("the
  old smith") and offers them as aliases.
- *Continuity check* and *story-bible updates*: flags contradictions with canon.
- *Style guide*: learns your voice from your own prose into an editable
  `style.md`; then draft at the cursor, expand a `{{expand: note}}` marker or
  rewrite a selection. Results are pending drafts you accept or reject.
- *Assistant chat* with attachments (scenes, notes, notebook notes, your comments),
  *Ask my notebook* questions answered from your own notes, *Brainstorm*, and
  *Inspiration images* for reference while you write. The assistant knows which
  character, place or note you have open, shows it as a removable **About:** chip,
  and a **What was sent** line shows what every request carried.
- *Pictures* (generated or uploaded: JPG, PNG, WebP up to 10 MB) can be linked to
  any scene, character, place or note. They are reference only and never sent to an AI.

**Export**
- A typeset PDF book, a double-spaced manuscript-review PDF with line numbers, a
  plain proof PDF, Markdown, and DOCX / EPUB / LaTeX through pandoc. Files go to
  `exports/` and are never overwritten.

## Install

Download the installer for your system from the
[Releases page](https://github.com/anonymousacademe/Chisel/releases). Every
download contains **both** apps: the desktop app (Chisel) and the terminal app
(`chisel`). Replace `<version>` with the number of the release.

| System | Download | Notes |
|---|---|---|
| Windows 10 / 11 (64-bit) | `Chisel-<version>-windows-setup.exe` | Installs for you only (no administrator rights), adds a Start-menu entry and, if you tick it, a desktop shortcut; remove it from Settings > Apps. |
| Windows, no install | `Chisel-<version>-windows-portable.zip` | Unzip anywhere and run `Chisel\Chisel.exe`. |
| macOS, Apple silicon (M1 or newer) | `Chisel-<version>-macos-arm64.dmg` | Open it, drag Chisel to Applications. |
| macOS, Intel | `Chisel-<version>-macos-x86_64.dmg` | Best effort: built when the Intel build runner works, so a release may not have it. Otherwise install from source. |
| Linux (x86-64) | `Chisel-<version>-x86_64.AppImage` | `chmod +x` it and run it. |
| Any system with Python | `pipx install chisel-writer` (PyPI) | coming; see "From source" for now. |

`SHA256SUMS.txt` on the release page lets you check a download.

The apps are **not signed** yet, so the first launch needs one extra step:

- **Windows**: SmartScreen says "Windows protected your PC". Click **More info**, then **Run anyway**.
- **macOS**: Gatekeeper refuses an unsigned app. **Right-click** (or control-click) Chisel in Applications,
  choose **Open**, then **Open** again. If macOS still refuses, run
  `xattr -dr com.apple.quarantine /Applications/Chisel.app` in Terminal once.
- **Linux**: `chmod +x Chisel-*.AppImage && ./Chisel-*.AppImage`. To start the terminal app from the
  same file: `./Chisel-*.AppImage --terminal` (or link the file as `chisel`). The AppImage carries its
  own web engine (Qt WebEngine), so it needs no extra packages; it does need FUSE 2 to mount itself, or run it
  with `--appimage-extract-and-run`.
- **Terminal app on Windows / macOS**: it is `chisel-tui.exe` next to `Chisel.exe` in the install folder
  (Start menu: "Chisel (terminal)"), and `Chisel.app/Contents/MacOS/chisel-tui` on macOS.

Your settings, recent projects and writing stats live in a per-user folder (never in your project):
`%LOCALAPPDATA%\chisel` on Windows, `~/Library/Application Support/chisel` on macOS,
`~/.local/state/chisel` on Linux. Your projects are ordinary folders you choose (default `~/novels`).
Your OpenRouter key is kept in the system's keyring (Credential Manager, Keychain, Secret Service).

**pandoc** is optional and is not included: only DOCX, EPUB and LaTeX export need it (they stay greyed out
until it is on your PATH: `winget install pandoc`, `brew install pandoc`, `apt install pandoc`). PDF and
Markdown export work without it.

### From source (any system with Python)

You need **Python 3.11+**. To build the desktop UI you also need **Node 20+**.
The terminal app needs neither Node nor a graphical environment.

**Linux** — the desktop app uses the system WebKitGTK, so install the system
packages and create the virtual environment with `--system-site-packages`:

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-webkit2-4.1
# Fedora
sudo dnf install python3-gobject webkit2gtk4.1
# Arch
sudo pacman -S python-gobject webkit2gtk-4.1
```

**Windows** — the desktop app uses the WebView2 runtime, which is preinstalled on
Windows 10 and 11. **macOS** needs nothing extra.

```bash
git clone https://github.com/anonymousacademe/Chisel
cd Chisel

python3 -m venv .venv                      # Linux: add --system-site-packages
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -e ".[all]"                    # or: pip install -r requirements.txt && pip install -e .

(cd gui && npm ci && npm run build)        # builds the desktop UI into the package

chisel-gui                              # the desktop app
chisel                                  # the terminal app
```

`pip install -e .` alone gives the terminal app. Extras: `gui` (pywebview), `export`
(PDF export), `all` (both). **pandoc** is optional and only needed for DOCX, EPUB and
LaTeX export (the options are greyed out without it): `apt install pandoc`,
`dnf install pandoc`, `pacman -S pandoc`, `brew install pandoc`, or `winget install pandoc`.

## Quick start

Open a copy of the bundled example, a short cyberpunk story with a story bible
(see [examples/README.md](examples/README.md)):

```bash
cp -r examples/residual ~/residual         # Windows: xcopy /E /I examples\residual %USERPROFILE%\residual
chisel-gui --project ~/residual         # or: chisel --project ~/residual
```

Or start your own: both apps open on a launch screen with your recent projects,
*Open folder* and *New project* (default location `~/novels/<title>`).

Terminal keys (the desktop app shows its own in the UI; `f1` lists them all):

| Key | Action |
|---|---|
| `ctrl+p` | command palette — everything lives here |
| `ctrl+n` | new scene |
| `ctrl+j` | open the note under the cursor; with a name selected, create it |
| `ctrl+l` | AI: find aliases in this scene |
| `ctrl+g` | AI write: draft at cursor / expand a marker / rewrite the selection |
| `f7` / `f8` | accept / reject the AI draft under the cursor |
| `f6` | spell check: fix the next misspelled word |
| `alt+←/→` | previous / next scene |
| `f11` | writer mode |

## AI setup (optional)

AI features use [OpenRouter](https://openrouter.ai) with your own key. Either set
the `OPENROUTER_API_KEY` environment variable, or enter the key in the app
(Settings, or *Action · Set OpenRouter API key* in the terminal palette); it is
stored in your operating system's keyring, never in a project file.

Models are chosen per role in Settings (type a slug, or pick from the live catalogue),
or per project in `project.toml`, where the project wins:

| Role | Used for | Default |
|---|---|---|
| fast | alias finding | `google/gemini-2.5-flash` |
| strong | continuity checks, story-bible updates | `anthropic/claude-sonnet-4.5` |
| writing | drafting, rewrites, style guide | `anthropic/claude-sonnet-4.5` |
| image | inspiration images | `google/gemini-3.1-flash-lite-image` |

```toml
[ai]
fast_model = "google/gemini-2.5-flash"
strong_model = "anthropic/claude-sonnet-4.5"
writing_model = "anthropic/claude-sonnet-4.5"
```

**Costs.** You pay OpenRouter's per-model prices directly; Chisel adds nothing.
The status bar shows the running total for the session (for example `AI $0.0123`)
and each AI call reports its own cost. An inspiration image costs about $0.03 with
the default image model, and images are only ever generated when you click.

## Your files

```
my-novel/
├── project.toml          # title, [editor] and [ai] settings
├── manuscript/
│   ├── 01-opening.md     # scenes, numbered; reorder in the app
│   ├── 03-the-recall/    # a folder is a part (title in _part.md)
│   └── _unplaced/        # Parked scenes: written, but not in the book
├── entities/
│   ├── characters/elara-vance.md   # free-text note + YAML frontmatter
│   └── places/thornwick.md         #   (name, type, aliases; other keys such as born: are kept)
├── notebook/             # your Notebook: notes about anything (plain Markdown, any subfolders; was research/)
├── inspiration/          # pictures, each with a .md sidecar (prompt, notes, link to an item)
├── exports/              # files you exported
├── style.md              # your learned style guide (editable)
├── dictionary.txt        # words to accept in spell check
└── .trash/ .drafts/ .snapshots/ .comments/ .assistant/   # app data, plain files
```

A SQLite index under `.chisel/` powers backlinks. It is a rebuildable cache
(`f9` in the terminal): your files are always the truth.

## Privacy

- Your project never leaves your machine unless you use an AI feature, push with
  git, or copy it yourself. Chisel has no accounts and no telemetry.
- AI calls go to OpenRouter (and from there to the model you chose) **only when
  you trigger them**. What is sent depends on the feature: the alias finder and the
  continuity check send the scene you have open and the relevant character and place
  notes; drafting also sends your style guide and the text around the cursor; the
  assistant sends your question, the context it retrieved, and anything you attached;
  *Describe this scene* sends the passage around the cursor, and image generation
  sends only the prompt you approved.
- What each AI request carried is shown, not hidden: the desktop app has a **What was sent** line under
  assistant replies, review dialogs and drafts (every part of the request with its estimated size, and by
  name any note that did not fit and was left out or shortened); the terminal app adds a one-line summary to
  each AI notification. For a long book, only the notes of the characters and places a scene is about are sent,
  and a request too big for the model's context window is refused before anything leaves your machine.
- With AI features, only what the **What was sent** line shows is sent. When the
  **About:** chip is on, the text of that open note is sent with your request;
  remove the chip and it is not.
- Never sent: scenes you did not open or attach, your comments (unless you attach
  them), pictures (generated or uploaded; images are never sent), unaccepted AI text
  as if it were your prose, scene details frontmatter as text, and your spelling
  dictionaries. Spell check, stats and search are fully local.
- The only other network request is the public OpenRouter model catalogue, fetched
  when you open a model picker.

## Upgrading from LoreWriter / lorewrite

Chisel was called LoreWriter (command `lorewrite`) before. From the first release after 0.4.0 the commands
are **`chisel`** (terminal app) and **`chisel-gui`** (desktop app); the old command names are gone, with no
aliases. Your files are not lost: the first start copies what it can.

- **Copied (once, the old folders stay where they are):** your settings, recent projects, writing stats and
  typing-sound packs, from `%LOCALAPPDATA%\lorewrite` (Windows), `~/Library/Application Support/lorewrite`
  (macOS) or `~/.local/state/lorewrite` and `~/.local/share/lorewrite` (Linux) to the same place named
  `chisel`. A new folder is never overwritten.
- **Your OpenRouter key:** read from the old keyring entry when the new one is empty, and stored under the new
  name; the old entry stays.
- **Projects:** when a project opens, its hidden `.lorewrite/` folder (the index cache, continuity waivers and
  the rename undo list) is renamed to `.chisel/`. If the project's `.gitignore` listed `.lorewrite/`, the line
  `.chisel/` is added, so git does not suddenly show the cache as new files. Scenes, notes and everything else
  in the project are never touched.
- **Not copied:** anything outside those folders. Projects are not moved, and nothing is deleted.
- **Environment variables:** `CHISEL_STATE_DIR` and `CHISEL_DATA_DIR` replace `LOREWRITE_STATE_DIR` and
  `LOREWRITE_DATA_DIR`. The old names still work, as deprecated aliases, when the new ones are not set. When
  either is set, the platform folders are not copied.
- **Installer and shortcuts:** the Windows installer upgrades the old install in place. The terminal program
  is now `chisel-tui.exe` (Start menu: "Chisel (terminal)"); a Windows or macOS folder cannot hold both
  `chisel.exe` and `Chisel.exe`. Pin or script it by the new name. From source, run `pip install -e .` again
  (the package is `chisel-writer`, imported as `chisel`) and uninstall `lorewriter`.

When you are happy with Chisel, you can delete the old `lorewrite` folders and, in each project, any leftover
`.lorewrite/` folder.

## Status

Chisel is pre-1.0: formats and
screens can still change. Your files are plain Markdown, so you are never locked in. The name changed
from LoreWriter to Chisel (see "Upgrading from LoreWriter" above). Next on the
roadmap (see [SPEC.md](SPEC.md)): character relationships, talking as a character, local models,
per-scene summaries and a timeline view.

## Documentation

- **User's Guide** (PDF with screenshots): attached to each
  [GitHub Release](https://github.com/anonymousacademe/Chisel/releases).
  Its sources are in [docs/user-guide/](docs/user-guide/).
- [CHANGELOG.md](CHANGELOG.md): what changed, in plain words.
- [SPEC.md](SPEC.md): the design document and roadmap.
- [examples/README.md](examples/README.md): things to try in the sample project.
- [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md): working on the code.

## Development

```bash
pip install -r requirements-dev.txt && pip install -e .
python -m pytest                          # pure core units, headless TUI, GUI backend
(cd gui && npm ci && npm run lint && npm test && npm run build)
python -m chisel.gui.devserver --project COPY --mock-ai   # the UI in any browser, canned AI
```

The desktop UI is built with Vite into `src/chisel/gui/web/` (git-ignored, shipped
as package data). Architecture notes: [gui/README.md](gui/README.md).

This project was built with the help of AI coding assistants, which wrote much of
the code under the author's direction.

## License

[MIT](LICENSE) © 2026 Mishkin. Bundled export fonts: Noto Serif (SIL OFL 1.1) and
Liberation Mono (SIL OFL 1.1); their licences are in
`src/chisel/core/export/fonts/`.
