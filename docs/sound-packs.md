# Typing-sound packs

LoreWriter can play a small sound as you type in the editor (off by default). It ships three
synthesised packs (Typewriter, Mechanical - clicky, Mechanical - thocky). You can add your own: record
a few key sounds, put them in a folder, and the pack shows up under **Sound -> Sound pack**.
Packs are plain files, so they are easy to share.

## Format

A pack is a folder of short sound files and an optional `pack.toml`:

```
My Pack/
  key-1.wav          any number of letter sounds: key-*.wav|ogg|mp3|flac (one is chosen at random)
  key-2.wav
  space.wav          optional; missing classes fall back to a key-* sound
  return.ogg         optional
  backspace.wav      optional
  pack.toml          optional
```

- Sound classes: `key` (every printable key), `space`, `return` (Enter), `backspace` (Backspace and
  Delete). A file belongs to the class its name starts with (`space-soft.wav` is a `space` sound).
- Formats: WAV, OGG, MP3 or FLAC. The type is checked from the file contents, not the extension.
- Keep them short (well under half a second) and trimmed at the start: the sound plays on keydown, and any
  silence at the start is heard as lag. Mono is fine; leave a little headroom so keys are not clipped.
- `pack.toml` (all optional):

```toml
name = "My Pack"     # shown in the list (up to 60 characters); also names the folder on import
volume = 0.8         # 0 to 1, a gain applied on top of the volume slider
```

## Where packs live

`sounds/<pack>/` inside LoreWriter's data folder (Linux `~/.local/share/lorewrite`, macOS
`~/Library/Application Support/lorewrite`, Windows `%LOCALAPPDATA%\lorewrite`). **Sound -> Open sounds
folder** opens it (and creates it). Packs there are listed automatically. Your own ambience loops go in
`ambience/` next to it (wav/ogg/mp3/flac, up to 30 MB each).

## Sharing

- **Export pack...** (Sound panel) saves the selected pack as `<name>.zip`. It never overwrites a file.
- **Import sound pack...** adds a `.zip`. The zip is checked first and nothing is written if any check
  fails. Rules:
  - only sound files named as above (`key-*`, `space*`, `return*`, `backspace*`, with a
    wav/ogg/mp3/flac extension) and `pack.toml`; anything else (executables, scripts, text files,
    sub-folders of sub-folders) is refused;
  - every sound file must really be WAV, OGG, MP3 or FLAC by its first bytes;
  - at most 200 files and 20 MB in total (counted as actually unpacked, not as the zip header claims);
  - files at the top of the zip or inside exactly one folder; no absolute paths, `..`, backslashes,
    drive letters or links.
  - an existing pack is never replaced: a clash is imported as `Name 2`.

To publish a pack, attach the zip to a GitHub Release or a discussion thread and say what it was
recorded on. Only share sounds you recorded yourself, or that carry a licence allowing it, and say
which. There is no in-app download store; importing is always a file you chose.
