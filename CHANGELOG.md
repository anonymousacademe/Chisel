# Changelog

All notable changes to Chisel are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Fixed
- **Clicking in the manuscript puts the cursor where you click.** The extra space above the title rule and above
  headings (and scene headings in scripts) was margin, which the editor cannot measure, so everything below the
  title drifted and a click on the second row of a wrapped line landed on the line below. Right-click had the
  same offset, which is why it often found nothing. That space is padding now.
- **The desktop window no longer jitters or overshoots when dragged.** Dragging the title bar now
  uses the native Windows move loop instead of repositioning the window on every mouse move (the
  old way also mishandled display scaling, so the window raced ahead of the cursor on scaled
  displays and flickered a ghost title bar). Title-bar buttons stay clickable.
- **No more console windows flashing over the desktop app on Windows.** The installed app checks git
  status in the background, and every check briefly opened a console window on top of the app. git,
  pandoc and the other helper programs now run hidden.
- **The launch screen has a title bar.** Before a project was open, the desktop window had nothing to drag
  it by and no minimise / maximise / close buttons, so it could not be moved.
- **Dragging the desktop window with the left mouse button works again (Windows).** The native drag
  failed on every press, so the window only moved with a right-button drag (the old, jittery way). The
  title bar now ignores the right button.

### Added
- **A right-click menu in the editor (desktop).** A misspelled word still shows its suggestions. On a character
  or place you have a note for, "Go to note" opens that note's page; on a `[[link]]` with no note yet, or on any
  word, "Create note…" opens the new-note dialog (character, place, object or faction). A selection adds Send to
  notebook and Add to dictionary. Cut, Copy, Paste and Select all are there too, and the cursor moves to where
  you right-clicked.
- **Script mode** for screenplays, TV, stage and audio scripts. Start a project and choose *Script*: it is a
  story (characters, places, links, relationships, story time, snapshots and comments all work) whose scenes
  are written in Fountain, the plain-text screenplay format. The desktop editor draws scene headings, character
  cues, dialogue, parentheticals and transitions at the standard positions in a monospaced column, the status
  bar shows an estimated page count, a character cue counts as a mention of that character, and spell check
  skips headings, cues and notes. *Export* writes a Fountain file or a screenplay PDF (Courier 12, standard
  margins, title page, numbered pages); *Import a Fountain file* (project menu; terminal palette) adds a
  `.fountain` script's parts and scenes after the ones you have. Scenes stay Markdown files; a Fountain note is
  written `<!-- like this -->` because `[[double brackets]]` are links here. In the desktop editor, Tab and
  Shift-Tab turn the current line into the next or previous element (action, scene heading, character,
  parenthetical, transition), and a list offers your characters for capital letters at the start of a block
  and your places after `INT.` / `EXT.`. In a script project the assistant writes Fountain: draft at the cursor,
  expand a placeholder and rewrite a selection produce scene headings, action and dialogue in screenplay
  form, a draft starts on a new line of its own, and the chat proposes script text you can paste in. A new
  **Voices** check (assistant quick action; "Check dialogue voices" in the terminal app) compares what each
  character says in the open scene with what the same character says in the rest of the script, nearest scenes
  first, and flags lines that do not sound like them: a quote of the line, what differs, and a rewrite in their
  voice. A character with fewer than five lines elsewhere is not judged, and the check says so. Findings are
  suggestions (dismiss one and it is not reported again); the script is never changed.
- **Character relationships.** A character note can declare its relationships in a `## Relationships`
  section (`- [[Rook Tanaka]] — father; estranged`); the app reads it wherever the note is shown. The
  note panel (desktop) lists what the note declares, what the other notes say about it ("from their
  note"), and links that have no note yet. The assistant can propose relationships from the note's own
  point of view: you tick the ones to keep, and only the ticked rows are written into the note's
  section — the prose is never touched, and the other notes are never changed (their side is shown by
  reading them). Terminal app: the same flow from the command palette ("Entity · Suggest relationships").
- **Local AI models (Ollama and OpenAI-compatible servers).** Pick any model installed on your own
  computer for the fast, strong or writing roles: the model pickers in Settings can list what is
  installed (the desktop app has an "Installed (local)" source, the terminal app toggles with
  `ctrl+l`), and the address of the server is configurable (default: Ollama at
  `http://127.0.0.1:11434/v1`). Local models cost nothing and nothing is sent anywhere; picture
  generation still uses OpenRouter.

## 0.5.0 - 2026-10-03

Version 0.4.0 was tagged but never published, so 0.5.0 is the first release with these changes: it includes
everything listed under 0.4.0 below, and it is the first release to carry the new command names.

### Changed
- **Renamed internals and commands to match the app's name.** The commands are now `chisel` (terminal) and
  `chisel-gui` (desktop); the Python package is `chisel` (installed as `chisel-writer`); the repository is
  `anonymousacademe/Chisel`. The old command names (`lorewrite`, `lorewrite-gui`) are gone and have no aliases.
- The per-user folders are now named `chisel` (for example `%LOCALAPPDATA%\chisel`), the keyring entry is
  `chisel`, and a project's hidden cache folder is `.chisel/` instead of `.lorewrite/`.
- Environment variables are `CHISEL_STATE_DIR`, `CHISEL_DATA_DIR` (the old `LOREWRITE_STATE_DIR` and
  `LOREWRITE_DATA_DIR` still work, as deprecated aliases) and, for builds and tests, `CHISEL_SELFTEST_RENDER`,
  `CHISEL_TARGET_ARCH`, `CHISEL_REGEN_FIXTURE`.
- The terminal program in the installers is `chisel-tui` (`chisel-tui.exe`), because `chisel.exe` and `Chisel.exe`
  cannot share a folder on Windows or macOS. The Start-menu entry is still "Chisel (terminal)". The macOS bundle
  identifier is now `io.github.anonymousacademe.chisel`; the Windows installer keeps its identity and upgrades
  in place.

### Migration notes
- On first start the app copies your old `lorewrite` settings and sound-pack folders to the new `chisel` ones
  (never overwriting, never deleting the old ones), copies the OpenRouter key from the old keyring entry to the
  new one, and renames each project's `.lorewrite/` to `.chisel/` when you open it, adding `.chisel/` to a
  `.gitignore` that listed `.lorewrite/`. See "Upgrading from LoreWriter" in the README.
- After upgrading from source: `pip install -e .` again and `pip uninstall lorewriter`.

## 0.4.0 - 2026-10-03 (not published; included in 0.5.0)

### Added
- **A new logo and icons.** Chisel has its own mark, an open book that is half stone with a chisel working
  on it. It is the window icon, the installer and app icons on every system, the favicon, and the logo in the
  app and on the README. The artwork is in `docs/brand/`.
- **Menu-aware AI.** The assistant, Brainstorm and *Describe this scene* now know which character, place,
  object or note you have open. A removable **About:** chip in the assistant header shows it whenever it is
  used; remove the chip and that chat is not about the open item.
- **What was sent.** Under assistant replies, in the review dialogs and after a draft, a *What was sent* line
  shows every part of an AI request with its estimated size, and by name anything that did not fit and was
  left out or shortened. The terminal app adds a one-line summary to each AI notification.
- **Pictures for any item.** An inspiration picture can be linked to a scene, a character, a place, an object
  or a notebook note, and follows it when it is renamed or moved.
- **Picture upload.** Add your own JPG, PNG or WebP (up to 10 MB). Uploaded pictures are never sent to an AI.
- **Optional story time.** Give a scene a `when:` (a year, optionally month and day) and a character a
  `born:`; the app then shows ages in the notes. Leave it blank and everything uses reading order, and says
  so. The book is never reordered by story time.
- **Optional `context_window` setting** (tokens) for models whose size the app cannot look up.
- Note frontmatter keys other than name, type and aliases (for example Obsidian `tags:`) are kept as written.
- This changelog.

### Changed
- **The app is now called Chisel** in everything you read: window, installers, menus, README and guide.
  The commands (`lorewrite`, `lorewrite-gui`), the Python package, your settings folder and the
  `LOREWRITE_*` environment variables keep their names, so nothing you set up needs changing.
- Release files are named `Chisel-<version>-...` (installer, portable zip, DMG, AppImage).
- **Parked scenes** is the desktop name for what was Unplaced Scenes; the group is hidden while it is empty.
  The folder (`manuscript/_unplaced/`) and the terminal app are unchanged.
- For a book with 40 or more characters and places, continuity checks, story-bible updates and the alias
  finder send only the notes of the entities the scene is about; smaller projects send exactly what they did.
- A request too large for the model's context window is refused with a clear message before anything is
  sent, instead of failing at the provider.

### Fixed
- **Windows window icon crash.** Running `lorewrite-gui` from source on Windows no longer fails to start the
  window: Windows now gets an `.ico` icon, which is what its window toolkit accepts.
- Scene and part titles that contain quotes, colons or other TOML-special characters no longer break
  `project.toml`.
- A rename that is interrupted is rolled back, and leftover `.mv*` files from an earlier interruption are
  recovered when the project opens.
- Character and place names with accents, non-Latin letters or curly quotes now get proper file names and are
  matched in your prose.
- A new alias can no longer take over a name or alias that already belongs to another note.
- Very long titles, names and notes are capped instead of producing unusable files.

### Security and privacy
- **Files that are not valid UTF-8 are never overwritten.** Chisel opens them so you can read them, but it
  will not save over them.
- With AI features, only what the *What was sent* line shows leaves your machine; pictures are never sent;
  the *About:* note is sent only while the chip is on.
