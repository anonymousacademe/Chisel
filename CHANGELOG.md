# Changelog

All notable changes to Chisel are listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

## 0.4.0 - 2026-10-03

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
