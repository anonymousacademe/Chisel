# Plan: spell check with a personal dictionary (TUI + GUI)

Status: approved 2026-10-01. Branch `gui` in `~/lorewrite-gui`. Same rules as
`docs/dev/plan-gui.md` (core is the single source of truth, no network, commit per
phase on `gui` only, never `main`, never push, suite green after each phase).
**Spelling only — no grammar checking** (author's decision).

## Engine

- `pyspellchecker` (pure Python, bundled English frequency dictionary,
  offline, MIT). Add `pyspellchecker>=0.8` to `pyproject.toml` core
  dependencies; install into `~/lorewrite-gui/.venv-gui` (already done:
  0.9.0) — the TUI on the same branch uses it too. Measured: load 0.15 s,
  `unknown()` microseconds, `candidates()` ~1 ms. Load once, lazily, cache the
  instance (thread-safe; GUI calls arrive on worker threads).
- Hide the engine behind `core/spelling.py` so it can be swapped later (e.g.
  Hunspell if the author installs `hunspell-en_us`).

## `core/spelling.py` (pure, no UI)

- `check(text, accepted) -> list[Misspelling(start, end, word)]` in document
  order. Tokenize words with a Unicode-aware regex allowing internal
  apostrophes (straight and curly) and hyphens.
  - **Possessives/contractions:** strip a trailing `'s` / `’s` / `s'` before
    lookup (`Rook's` → `Rook`, NOT `str.strip("'s")`, which eats letters);
    otherwise look the token up as-is (pyspellchecker knows `don't`,
    `wasn't`); normalise curly apostrophes to `'` for lookup.
  - **Hyphenated words:** check each part (`noodle-stall` ok if both parts ok,
    or if the whole compound is in the dictionary).
  - **Skip:** Markdown headings' `#` markers (but check heading words), the
    YAML frontmatter block, inline code / code fences, URLs, e-mail
    addresses, tokens with digits, single letters, ALL-CAPS tokens of ≤ 5
    letters (acronyms: `K-V`, `NYPD`), the inside of `<!--…-->` comments
    (pending-draft markers and the style.md provenance line), `{{expand: …}}`
    marker syntax (check the instruction words? no — skip the whole marker).
  - **Pending AI drafts are checked too** (the author reviews them; misspelled
    AI text should show) — only their marker comments are skipped.
  - Case: a word in the dictionary in lowercase matches any capitalisation;
    a capitalised dictionary entry (`Kessler`) matches only capitalised forms.
- `suggestions(word, n=5) -> list[str]` ranked by the engine's probability,
  preserving the original's capitalisation pattern (`Recieve` → `Receive`).
- `accepted_terms(project) -> AcceptedTerms`: union of
  1. **entity names and aliases** (every word of each, and each whole name as
     a phrase) — never flag your own characters/places;
  2. the **project dictionary** `<project>/dictionary.txt`;
  3. the **personal dictionary** `<state dir>/dictionary.txt` (honours
     `LOREWRITE_STATE_DIR`, like `recents.py`/`settings.py`);
  4. **ignored this session** (in memory, per project, not persisted).
- **Phrases:** an entry with a space (`maglev spur`, `Kowloon Low`) accepts
  the words inside every occurrence of that phrase (case-insensitive match
  on whitespace-normalised text), even if a word alone would be flagged.
- Dictionary files: plain UTF-8, one word or phrase per line; `#` comments
  and blank lines ignored; preserved when adding (append; dedupe
  case-insensitively unless the case differs meaningfully — keep it simple:
  dedupe exact lines). Functions: `load_dictionary(path)`,
  `add_to_dictionary(path, term)` (atomic write via `write_atomic`),
  `remove_from_dictionary(path, term)`. `dictionary.txt` is author data:
  NOT in `.lorewrite/`, NOT git-ignored. It is not a scene and not an entity
  (make sure project scanning ignores it).

## TUI (`tui/`)

- Live underline: misspellings in scenes get a red underline via the existing
  span machinery in `editor.py` (new span kind `"misspelled"`, lowest
  priority: links/mentions/drafts styling wins where they overlap — they
  never coincide anyway since names are accepted). Recompute on the same
  debounce as links; must stay fast on the 51k-word stress scene (only check
  visible + nearby lines if needed; measure).
- Toggle: user setting `spellcheck` (default on), in the Settings screen
  (checkbox "Underline misspellings") and palette `Action · Toggle spell
  check`.
- `f6` → jump to the next misspelling after the cursor (wrap around) and open
  a small modal: the word, up to 5 suggestions (`1`–`5` or enter to replace),
  `a` add to project dictionary, `p` add to personal dictionary, `i` ignore
  this session, `esc` cancel. Verify `f6` reaches the app with the editor
  focused (Pilot test); pick another free key if not, and document it.
- Palette: `Action · Add selection to dictionary` (word or phrase; project),
  `Action · Open project dictionary` (opens `dictionary.txt` in the editor,
  creating it with a short comment header).
- Entity notes and `style.md` are not spell-checked in v1 (scenes only).

## GUI (`gui/`)

- Api (`gui/api.py`): `spelling(id, text)` → misspelled spans in UTF-16
  offsets (or fold into `link_spans` as kind `"misspelled"` — pick one;
  debounced like link spans); `spelling_suggestions(word)`;
  `add_to_dictionary(term, scope)` with scope `"project" | "personal"`;
  `ignore_word(word)`; `open_dictionary()`. Never raise across the bridge.
- Editor: CodeMirror decoration — wavy red underline (`text-decoration:
  underline wavy`), design tokens, only in scenes. Clicking a misspelled word
  (or right-click / `ctrl+.`) opens a small popover in the design's style:
  suggestions (click to replace — a normal undoable edit), **Add to
  dictionary**, **Add to my dictionary (all projects)**, **Ignore**. With a
  multi-word selection, the toolbar / popover offers **Add phrase to
  dictionary**.
- Settings dialog: "Underline misspellings" toggle (same `spellcheck`
  setting as the TUI).
- Status bar: misspelling count for the open scene (e.g. `3 spelling`),
  clicking it jumps to the next one.
- Binder: show `Dictionary` (project `dictionary.txt`) next to the Style
  Guide item so it can be edited by hand.

## Docs

SPEC (M6 spell check: engine, dictionaries, keys), README (keys, dictionary
files), AGENTS.md (new module, fragile spots if any), HELP_TEXT / tour line /
GUI help where keys are listed. Do not touch the PDF user guide (it is
rebuilt later from `main`).

## Tests

- core: tokenizer cases (possessives straight/curly, contractions,
  hyphenation, acronyms, digits, URLs, headings, frontmatter, comments,
  expand markers, pending drafts' markers skipped but bodies checked),
  case rules, phrase acceptance, entity names accepted, dictionary
  add/remove/dedupe/comments/atomicity, personal dictionary honours
  `LOREWRITE_STATE_DIR`, suggestions keep capitalisation, performance
  (`check` on a 50k-word text under ~300 ms).
- TUI Pilot: underline rendered on a misspelling; toggle off removes it;
  `f6` modal replace / add / ignore; add-selection-as-phrase; teardown safe.
- GUI: api tests (spans, UTF-16 offsets with non-ASCII text, add both scopes,
  ignore), vitest for the decoration mapping; a headless screenshot of the
  popover on a copy of `examples/residual` (with a misspelling inserted) —
  look at it.

## Done

Full pytest + vitest + `npm run build` + `npm run lint` (no new warnings)
green; screenshots viewed; Jev review per chunk with verdicts reported; final
report to `/tmp/spelling-report.md` (what was built, keys, deviations,
limitations, Jev table), reply with the path.
