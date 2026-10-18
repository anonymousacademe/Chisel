# Plan: Read aloud (every project mode, desktop only)

Status: phases 1 (the reading model, no sound) and 2 (browser speech playback) are built on the `read-aloud` branch
(2026-10-19). Phases 3 to 9 below are planned, not built. The terminal app gets nothing: desktop only, by decision.
Built so far: `core/reader.py`, `Api.read_plan`, `gui/src/reader/` (engine, session, chunks, cast), `useReadAloud`,
`ReaderBar`, the editor highlight (`setReading`). Checked in a browser with a stand-in speech service; not yet heard
on real Windows / macOS / Linux voices.

## 1. Goal

Hear what is on the page: proofread by ear, hear a scene as a table read, audition how dialogue sounds, and in the
end make audio worth sharing (a radio play, a podcast episode, a read-through for actors). Every project mode
(story, research, script) and any open note, with one reader and one playback bar.

## 2. Principles (from SPEC §2, applied to sound)

- **Sound only starts from a click.** No autoplay (as with typing sounds and ambience). A download, a recording and a
  cloud call are each a separate click too.
- **Plain text stays the truth.** Audio is derived and lives in a cache or `exports/`, never in the manuscript.
  What belongs to the story (how a name is said, what a character sounds like, the tone of a passage) is plain text
  in the notes and scenes; what belongs to this machine (which installed voice, which engine) is per-machine state.
- **Nothing leaves the machine unless the author asks.** Browser and local voices are offline. A cloud voice is opt-in
  per project, shows the cost before it runs and reports exactly what text was sent (the "What was sent" pattern).
- **Python decides what is read, the editor plays it.** The editor never parses; it speaks the list Python makes.
- **Licences are shown, not assumed.** Every downloadable model and voice shows its licence before download.

## 3. The reading model (phase 1, built; `core/reader.py`, pure)

An **utterance** is one thing spoken by one voice: `kind` (title, heading, scene-heading, narration, quote, dialogue,
direction, transition), `voice` (a role: `narrator`, `quote`, or the speaker's name), `text` (as shown), `say` (as
spoken), the source range (code points; the bridge sends UTF-16) and an estimated duration. One adapter per kind of
text (script, story, research, note). Skipped everywhere: details, notes, boneyard, pending AI drafts, `{{expand}}`.
A `say:` key in a note respells the name. Duration: 160 words a minute plus pauses.

## 4. Playback with browser speech (phase 2, built)

A strip under the editor toolbar: play from the cursor or the start, pause, next / previous passage, stop, speed, time
left; the passage being read is highlighted. A system voice per role, remembered per project on this machine.
Options: parentheticals, transitions, citations. Typing stops the reading. Long passages are spoken in sentence chunks.

Browser speech is the floor, not the ceiling: free and offline, but limited to the operating system's voices, no
control over tone beyond rate / pitch / volume, no reliable word timing, and it cannot save audio.

## 5. Review of the idea

**What holds up.** The split (Python plans, the editor plays) and the utterance list as the one contract are right:
everything wanted next (better voices, tone, pronunciation, export) is a property of an utterance or of how a clip is
made from it. The next structural step is the important one: move from "the browser speaks a string" to **"an
engine renders an utterance to an audio clip"**. Clips give exact highlighting, pause and seek that work everywhere,
prefetch, caching, export, and any engine (local, server, cloud) behind one interface.

**What needs care.**
- **Licences differ per model and per voice.** Kokoro-82M is Apache-2.0; Chatterbox is MIT; Piper's maintained fork
  (OHF-Voice/piper1-gpl) is GPL-3.0 and its voices carry their own model cards; several popular models (XTTS-v2,
  F5-TTS weights, some IndexTTS releases) are non-commercial or have extra conditions. Chisel must not link GPL
  engines (or the GPL espeak-ng phonemizer) into its own package: those run **out of process** (a speech server).
  Every model card is checked again when it is added to the catalogue (they change).
- **Size.** onnxruntime is tens of MB; models are 80 MB (Kokoro, quantized) to several GB (PyTorch models). Models are
  never bundled in the installers; they download on a click into the user data folder. PyTorch is never a Chisel
  dependency: heavy models run in a speech server the author installs (as Ollama is for local language models).
- **Voice cloning is an ethics and consent question**, not just a feature: only the author's own voice or a voice
  they have the rights to, said plainly in the interface, kept on this machine.
- **Cost.** Cloud voices charge per character; a whole script can cost real money. Estimate first, cache always.
- **Quality is mostly pronunciation and pacing.** The pronunciation work (section 7.4) matters more than the engine.

## 6. Target architecture

```
core/reader.py            utterances (built)               + delivery (tone) and lexicon applied per utterance
speech/                   NEW Python package, no Textual, optional extras
  engine.py               Engine protocol: id, capabilities, voices(), synthesize(Request) -> Clip
  engines/endpoint.py     OpenAI-compatible /v1/audio/speech (local servers and OpenAI cloud): first non-browser engine
  engines/kokoro.py       built-in local engine (onnxruntime + Kokoro ONNX), extra "speech-local"
  engines/elevenlabs.py   cloud, later; engines/google.py, engines/azure.py later still
  models.py               the model catalogue + downloads from Hugging Face (licence, size, sha256), remove
  cache.py                clip cache in the user cache dir, keyed by sha256(engine, model, voice, delivery, lexicon, say)
  lexicon.py              pronunciations: note say: / ipa:, project pronunciations.toml, per-engine rendering
  delivery.py             tone: markers + scene / character defaults -> normalized controls -> per-engine mapping
  recognize.py            recording -> IPA (local phoneme recognizer, optional download)
  export.py               clips -> WAV (pure Python) / MP3 or M4A (ffmpeg if present), chapters
gui/speech_api.py         bridge: engines, voices, synthesize (a job; returns a clip handle), downloads, export
gui/src/reader/engine.ts  + ClipEngine: fetches clips through the bridge, plays them with Web Audio, prefetches
```

- **The Engine protocol** declares capabilities, so features degrade honestly: `phonemes` (accepts IPA), `style_text`
  (free-text tone instructions), `style_tags` (inline tags), `controls` (rate / pitch / volume / exaggeration),
  `cloning`, `word_times` (timestamps for word-level highlighting), `languages`, `offline`, `cost_per_char`.
- **Clips** come back through a bridge job (like exports): audio bytes stored in the cache and served to the page by
  a cache key, so large audio never crosses the bridge as one string. The player prefetches the next two utterances.
- **The cast** has two layers. *Portable, in the story* (plain text in the character note): `voice:` (a description,
  "gravelly, sixties, Scottish, warm"), `say:` / `ipa:`, optional `delivery:` default. *Per machine* (state dir,
  `speech/<project-id>.json`, honouring `CHISEL_STATE_DIR`; replaces today's local storage so Python engines can use it):
  role -> engine + voice id + rate / pitch. A missing voice on another machine falls back to the closest match to the
  description, and says so.
- **Settings**: the engine per project (browser by default), a cloud engine only after an explicit opt-in per project.

## 7. Features and how to build them

### 7.1 Local voices downloaded from Hugging Face
- A **curated catalogue** (`speech/models.py`), not "any repository": id, Hugging Face repo and file names, sha256,
  size, licence (with a link to the card), languages, voices with tags (gender, age, accent), capabilities. Kokoro-82M
  first (Apache-2.0, 54 voices, 8 languages, ONNX). Every download shows size and licence and needs a click; progress
  runs as a job; files go to `<user data>/speech/models/<id>/`; a model can be removed. Checksums are verified.
- **Built in:** Kokoro through onnxruntime only (light, CPU). Its phonemizer is the open question: Kokoro's `misaki`
  G2P is permissive but falls back to espeak-ng (GPL) for unknown words; if that fallback is needed it runs as a
  separate process, never linked. Measure CPU speed on the author's machine before promising "real time".
- **Everything heavier** (Chatterbox for cloning and an exaggeration dial, Orpheus or Dia for emotive dialogue,
  IndexTTS2 for emotion and duration control, Qwen3-TTS for instruction-driven style) runs in a **local speech server**
  with an OpenAI-compatible endpoint, set by one address like the Ollama setting. Chisel lists the server's voices and
  never installs PyTorch. A short guide covers two servers that work.
- An "advanced: other Hugging Face model" field is deliberately out of scope until the catalogue proves itself.

### 7.2 Cloud voices
- Engines in order of usefulness: **OpenAI** (`gpt-4o-mini-tts`: a free-text `instructions` field for tone; their policy
  asks that AI voices be disclosed when published), **ElevenLabs** (the most natural voices, inline IPA and
  pronunciation dictionaries, v3 delivery tags), then **Google / Azure** (SSML phonemes, speaking styles).
- Keys in the keyring (like the OpenRouter key). Opt-in per project. Before a run: characters, estimated cost and which
  scenes; after: the "What was sent" report. The cache means a passage is never paid for twice. Never automatic.

### 7.3 Voices for characters ("voice modes")
- A **cast sheet** (a dialog, and a section in each character note): every role, its voice, rate, pitch, default
  delivery, "Hear a line", and how much it speaks (lines, minutes).
- **Choosing**: pick from the voices of any configured engine; or **describe** the voice in the note (`voice:`) and let
  Chisel suggest the closest installed voice from catalogue tags, or pass the description to engines that design a
  voice from text. The description is the portable intent; the pick is per machine.
- **Cloning** (only with an engine that supports it, phase 8): record or upload a sample, confirm you own it or have
  the rights, kept in the user data folder (never the project, never uploaded unless a cloud engine is chosen and
  named on the button).
- Narrator and quoted-speech voices too; per-scene override for a flashback narrator.

### 7.4 Pronunciation
Layers, most specific first: a `<!-- say: ... -->` right after a word in one passage; the note's `ipa:` / `say:`;
a project **pronunciation list** `pronunciations.toml` (plain text, author data like `dictionary.txt`: invented words,
place names, abbreviations); the engine default.
- **IPA** is exact and portable for engines that accept phonemes (Kokoro, ElevenLabs, Azure / Google SSML); the
  **respelling** (`say:`) is the fallback for engines that do not (browser speech). The lexicon renders each entry
  the way each engine understands.
- **Teach it by voice** (your idea): press record, say the word two or three times, and a local phoneme recognizer
  (`facebook/wav2vec2-lv-60-espeak-cv-ft`, Apache-2.0, an optional download) proposes IPA; you play it back in your
  chosen voices, adjust if needed (a simple stress / syllable editor), and save it to the note. The recording is
  discarded unless you keep it. The microphone is opened only by the record button.
- **Find what needs teaching**: a pass that lists names and rare words in the text that have no entry yet (entity names
  first), so you teach them once.

### 7.5 Tone for a section (delivery)
- **Where tone is written** (plain text, never read aloud, never exported): a marker `<!-- tone: whispered, urgent -->`
  that holds until the next marker or the end of the scene; a scene detail `tone:`; a script parenthetical (`(softly)`)
  for that speech; the character's default `delivery:`. The reader resolves these into each utterance's `delivery`.
- **What tone becomes**: normalized controls (rate, pitch, volume, intensity 0 to 1) plus the free text, mapped per
  engine: browser speech, rate / pitch / volume only; OpenAI, the `instructions` text; ElevenLabs v3, delivery tags;
  Azure, speaking styles; Chatterbox, the exaggeration dial; Kokoro, speed only. The playback bar says when an engine
  ignores part of it.
- **Setting it**: select a passage, right-click, **Set tone…** (presets plus free text); it inserts the marker, an edit
  the author sees and can undo. "Hear it" plays the passage with and without.

### 7.6 Other things worth having (in rough order of value)
1. **Rehearsal, "read my part"**: the reader pauses on your character's lines (or gives only the cue line before
   them); optional hands-free advance when the microphone hears you finish (local voice-activity detection).
2. **Audio export**: a scene, an act or the whole work to WAV, MP3 or M4A (ffmpeg when installed), with chapter marks
   per scene and a cast list; files go to `exports/` like other exports.
3. **Word-level highlighting** with engines that return timestamps (follows your eyes while proofreading).
4. **Listen before you accept**: play a pending AI draft against the text it replaces (A/B), and a snapshot against now.
5. **Proofreading mode**: slower, reads punctuation and spells out unusual words; flags words with no known
   pronunciation.
6. **Text normalization** you can correct: numbers, dates, money, units, abbreviations (Dr., St.), Roman numerals, with
   per-project overrides in the pronunciation list.
7. **Audio drama**: ambience beds and sound cues from action lines (the Atmosphere packs already exist), music stings.
8. **Runtime per character and scene** (casting and budget for a real recording).
9. **Several languages**: a language per character or per marker, voices chosen to match.
10. Comforts: resume where you stopped, Space to play / pause, media keys, a sleep timer, keep reading while you
    browse other notes.

## 8. Phases (each one shippable and useful on its own)

| Phase | What | Engine | Size of work |
|---|---|---|---|
| 3 | Table read and tone basics: read-my-part, cast sheet, per-role rate / pitch, tone markers (browser mapping), cast moved to the state dir | browser | small |
| 4 | The clip pipeline: Engine protocol, OpenAI-compatible endpoint engine (local servers and OpenAI cloud), clip cache, prefetch, Web Audio player, exact highlighting, WAV export | endpoint | medium |
| 5 | Built-in local voices: Kokoro via onnxruntime, the model catalogue and downloader, licences, removal | kokoro | medium |

**Built (phases 4 and 5, first cut, before phase 3 at the author's request):** the endpoint engine, the clip cache,
prefetch, Kokoro (out of process, because espeak-ng is GPL) with its downloader and removal, an engine picker with
cost lines, per-engine casts, cloud spend in the AI ledger. Measured on the author's machine: model load about 3 s,
then about 2 s to render 4.5 s of speech (faster than real time, so prefetch keeps up). Still open from these phases:
exact (word) highlighting, WAV export, a frozen-app worker (`Chisel --speech-worker`), and the `speech` extra split.
| 6 | Cloud: OpenAI (tone instructions) and ElevenLabs (IPA, tags), keys, cost estimate, sent report | cloud | medium |
| 7 | Pronunciation lab: pronunciations.toml, IPA per engine, record-to-IPA, "words to teach" pass | all | medium |
| 8 | Character voices: description-to-voice suggestion, cloning with a consent flow, per-scene overrides | server / cloud | medium |
| 9 | Audio drama export: MP3 / M4A, chapters, ambience and cues, word timing | all | medium |

**Tests** follow the existing rules: fake engines (as `session.test.ts` does), no network (downloads and cloud calls
are mocked at the function boundary, as AI calls are), the cache and lexicon are pure and unit-tested, the export is
checked by decoding the WAV it writes. **Packaging**: optional extras `speech` (endpoint, cache, export) and
`speech-local` (onnxruntime); models never in the installer; `selftest.py` checks that the extras import when present.

## 9. Decisions for the author

1. **Built-in engine**: Kokoro only in-process, everything heavier through a speech server (recommended), or bundle a
   heavier engine and accept a much larger, PyTorch-based install?
2. **First cloud provider**: OpenAI (cheap, tone by instructions) or ElevenLabs (best voices and pronunciation)?
3. **Licence policy**: offer non-commercial models with a warning (fine for personal use), or only permissive ones
   (needed if what you make is sold)?
4. **Cloning**: allow it at all, and only for your own voice?
5. **Where tone and pronunciation live**: markers and note keys as above (plain text, travel with the project), or a
   separate per-project file you never see in the prose?

## 10. Things to verify before each phase

- Which voices the Windows (WebView2), macOS (WKWebView) and Linux webviews expose, and how pause / resume behave.
- Kokoro's CPU speed on the author's machine, and whether its phonemizer needs espeak-ng for the project's names.
- Current licences of each catalogue entry (model cards change), and Piper's licence if it is ever offered.
- ElevenLabs v3 tag syntax and which models accept IPA (their docs have changed over 2025-2026).
- The size and speed of the phoneme recognizer, and whether an ONNX export is good enough for record-to-IPA.
