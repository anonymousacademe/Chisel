# AGENTS.md — guide for AI assistants working on lorewrite

Read this before changing anything. [SPEC.md](SPEC.md) is the source of truth
for design; this file is the operational guide.

## Project in one paragraph

lorewrite is a terminal fiction-writing app (Python 3.11+, Textual). Scenes
are plain Markdown files; characters/places are Markdown notes with small YAML
frontmatter; `[[wiki-links]]` connect them; a SQLite index (a rebuildable
cache, never the truth) powers backlinks; AI features go through OpenRouter
and are **suggest-and-confirm only — AI never edits prose unprompted**.

## Repo layout

```
SPEC.md                 # master design doc — update it when design changes
README.md               # user-facing intro
src/lorewrite/
  core/                 # pure Python, no Textual — fully unit-testable
    links.py            # [[link]] parsing, plain-name mentions, offset<->rowcol
    entities.py         # entity notes: frontmatter, aliases, resolve, add_alias
    project.py          # project layout, scenes (order/rename/move/delete), settings
    index.py            # SQLite backlink index; no-ops after close()
    recents.py          # recent projects; LOREWRITE_STATE_DIR env override
    settings.py         # user settings (tour_seen, ...)
  ai/
    client.py           # OpenRouter via openai SDK; keyring/env key resolution
    links.py            # M2 link suggestions: prompt, schema, validate, apply
  tui/                  # everything Textual
    app.py              # LorewriteApp: layout, save, status, actions, AI wiring
    editor.py           # LinkedTextArea — see "fragile spots" below
    sidebar.py panels.py launch.py commands.py linkreview.py tour.py theme.py
tests/                  # pytest; asyncio_mode=auto; Pilot for TUI tests
docs/ux-review-glm.md   # independent UX review (source of the M1.5 polish)
docs/specification-guide.md  # M3–M8 implementation guide for parallel agent
                             # execution (contracts, workstreams, ownership)
```

## Commands

```bash
.venv/bin/pip install -e ".[dev]"   # after pulling
.venv/bin/python -m pytest          # full suite (must stay green)
.venv/bin/lorewrite                 # run the app
```

## Non-negotiable principles (from SPEC §2)

1. Plain text, always — a project is a folder of Markdown; no database blobs.
2. The index is a rebuildable cache (`f9`); files are the truth.
3. AI suggests, never edits — every AI feature ends in an accept/reject UI.
4. Entity notes = free text + minimal YAML frontmatter (name, type, aliases).

## Fragile spots — read before touching

- **`tui/editor.py` uses private Textual APIs** (`_render_line`, `_line_cache`,
  `wrapped_document._offset_to_line_info`) to highlight `[[links]]`. Every use
  is wrapped in try/except with a plain-TextArea fallback.
  `tests/test_tui.py::test_link_highlighting_styles` locks the behavior — if it
  fails after a Textual upgrade, the internals moved.
- **Never name a method `_render` on a Widget** — it shadows Textual's
  internal `Widget._render()` and crashes rendering (bit us in the sidebar;
  the filter helper is `_render_lists`).
- **Widget IDs must be unique app-wide** — two `id="empty-hint"` items broke
  the DOM; use CSS classes for repeated things.
- **Rich markup eats brackets**: any dynamic label containing user text
  (`[character]`, `[[link]]`) must be wrapped in `rich.text.Text(...)`, never
  passed as a plain string to `Label(...)`.
- **Teardown races**: autosave timers can fire during shutdown. Widgets are
  held as direct refs (no `query_one` in save paths), timers are stopped in
  `on_unmount`, the final save skips UI updates, and `Index` no-ops after
  `close()`. Regression: `test_teardown_with_pending_autosave_does_not_crash`.
- **Deleting the open scene**: detach `current_path` BEFORE calling
  `open_file`, or autosave resurrects the deleted file (regression-tested).
- **ListView swallows Enter** — modal screens with a ListView must handle
  `on_list_view_selected` if Enter should confirm (see LinkReviewScreen).
- **Terminal key limits**: `ctrl+[` IS Escape; `ctrl+enter` doesn't reach most
  terminals. Scene nav is `alt+←/→`, writer mode is `f11`.
- **Command palette**: providers must implement `discover()` (else the palette
  opens empty) and treat empty queries as match-all (`Matcher.match("")`
  raises). Wrap entry generation in try/except so one bad provider can't blank
  the palette (`_Provider._safe_entries`).

## Testing conventions

- `tests/conftest.py` isolates app state per test via `LOREWRITE_STATE_DIR`
  and pre-marks the tour as seen. New user-state features must honor the env
  override.
- TUI tests use `app.run_test(size=(120, 40))` + `pilot`; call
  `await pilot.pause()` after actions before asserting.
- Mock AI at the function boundary: monkeypatch `lorewrite.tui.app.<ai_fn>`
  (see `tests/test_ai_links.py`). Never hit the network in tests.

## Workflow requirements

- **Keep SPEC.md current** when design/scope/decisions change (it's the master
  document; README mirrors it for users).
- **jev review before reporting code tasks done** (user's global instruction):
  diff only the files you changed into `~/.config/jev/jev.py review --task
  "..." --files ...`. HOLDs on `network` (OpenRouter client) and
  `out_of_scope` (state files in ~/.local/state, ~/.config/omarchy) are
  standing, expected, and acknowledged by the user — report scores, don't
  reword to dodge.
- No emojis in the UI or docs unless the user asks. Category prefixes use
  `Scene · / Entity · / Link · / Action ·` text.
- Commits only when the user asks. Match existing style; minimal diffs.

## Current state & what's next (2026-09-29)

Done: M1 (editor+links), M1.5 (UX polish from the GLM review), M2 (AI
auto-linking), M3 (continuity + Contextual Tracker), settings screen, model
picker, bracket-free implicit mentions (SPEC §5). **Next: M4** (style-aware
drafting, AI text visually marked until accepted).
Known concern: user is unconvinced by the command palette as primary UI
(SPEC §11b).
