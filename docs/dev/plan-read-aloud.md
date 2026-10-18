# Plan: Read aloud (every project mode, desktop only)

Status: phase 1 (the reading model, no sound) and phase 2 (browser speech playback) are being built on the
`read-aloud` branch (2026-10-19). The terminal app gets nothing: this is a desktop feature, by decision.

## 1. Goal

Hear what is on the page: proofread by ear, hear a scene as a table read, audition how dialogue sounds. Every
project mode (story, research, script) and any open note, with one reader and one playback bar.

## 2. Principles kept

- **Sound only starts from a click.** No autoplay (the same rule as the typing sounds and ambience).
- **Plain text stays the truth.** Audio is derived: never stored in the project. Which voice reads which
  character is a per-machine choice (voice ids differ between machines), so it is kept in the browser's local
  storage for that project, not in `project.toml`.
- **Nothing leaves the machine** in phases 1 and 2: the window's own speech service speaks. Cloud or local-server
  voices (later phases) are explicit per use, with the cost and the text sent shown, as images are.
- **Python decides what is read, the editor only plays it.** The GUI never re-implements parsing: it gets a list
  of utterances from Python (`core/reader.py`) and speaks them.

## 3. The reading model (phase 1; `core/reader.py`, pure)

An **utterance** is one thing spoken by one voice: `kind` (title, heading, scene-heading, narration, quote,
dialogue, direction, transition), `voice` (a role: `narrator`, `quote`, or the speaker's name), `text` (as shown),
`say` (as spoken: markup removed, names respelled by the author's pronunciations), the source range
(code points; the bridge sends UTF-16) and an estimated duration.

One adapter per kind of text, all producing the same list:

| Source | What is read | Voices |
|---|---|---|
| Script scene | scene headings ("Interior, kitchen, day"), action, dialogue; parentheticals and transitions only if asked | narrator; each character by name |
| Story scene | the title, headings, paragraphs; quoted speech split from narration | narrator; `quote` |
| Research section | headings and paragraphs; citations dropped (or "citation"), math as "equation", figure / table references as "the figure", code blocks, tables and captions skipped | narrator |
| Any note | its text, frontmatter skipped | narrator |

Skipped everywhere: scene details (frontmatter), notes and boneyard, pending AI drafts (not accepted, not canon),
`{{expand}}` markers, comments.

**Pronunciations:** a `say:` key in a character / place note (kept verbatim in the note's frontmatter, like other
extra keys) respells its name and aliases for the speech service: `say: "Kee-eth"`.

**Duration:** words at 160 a minute plus short pauses (longer after titles and headings); scaled by the rate. In a
script it is a runtime estimate to hold against the page count.

## 4. Playback (phase 2; desktop, browser speech)

- A transport bar (play / pause / stop / previous / next, rate), opened from a button and the project menu.
- Start from the cursor, the selection, the scene.
- The utterance being read is highlighted in the editor and kept in view; follow is by utterance (browser
  speech reports word positions too unreliably to highlight word by word).
- A voice per role from the system's installed voices, remembered per project on this machine. Defaults spread the
  voices out; narrator and `quote` are always offered; script speakers appear as they are met.
- Toggles: read stage directions / parentheticals, read transitions, skip my character (below).

## 5. Later phases

3. **Table-read features:** "read my part" (the app pauses on a chosen character's lines so you speak them),
   skip directions.
4. **More voices:** an OpenAI-style speech endpoint the author runs (one address, like the Ollama setting), voice
   packs in the user data folder (validated like sound packs), and cloud voices. These return an audio clip per
   utterance, which gives exact highlighting, pause and seek, and audio export per scene or whole script.
5. **Stories:** AI dialogue attribution (a suggestion you review) so story characters get their own voices.

## 6. Risks to check

- Which voices the Windows, macOS and Linux webviews actually expose (Linux is the weak one).
- Browser speech cancels long utterances in some engines: long paragraphs are split at sentence ends before they
  are spoken.
- Pronunciation of invented names is the biggest quality factor; the `say:` key is the lever.
