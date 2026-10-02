# Plan: M4 — AI writing features (+ AI loose ends)

Status: approved for implementation 2026-09-29. Implementer: one agent, on
branch `m4-ai-writing` in worktree `~/lorewrite-m4`. Read `AGENTS.md` (fragile
spots!) and `SPEC.md` §2, §5, §7–§8 before starting.

## Goals

1. The author picks the **writing model** in Settings (user decision: the
   drafting model is a user choice, not hardcoded).
2. AI spend is **visible** (SPEC §8 promises it; it is not implemented).
3. `ctrl+l` stops inserting `[[brackets]]` (the author dislikes them) and
   becomes an **alias finder**.
4. M4 core: **style guide**, **draft at cursor** (prompt window),
   **`{{expand: …}}` markers**, **rewrite selection in my style** — all
   AI-written text visibly marked until the author accepts it.

## Non-negotiables (from SPEC §2 / AGENTS.md)

- AI suggests, never edits unprompted. Every generated span is pending until
  an explicit accept; reject always restores exactly what was there before.
- Plain text: everything lives in Markdown files in the project folder. The
  `.lorewrite/` directory is a disposable cache — never store author content
  (style guide, pending drafts) only there.
- Never hit the network in tests. Mock at the function boundary
  (`monkeypatch.setattr("lorewrite.tui.app.<fn>", fake)`), as
  `tests/test_ai_links.py` does.
- Any user text in a `Label`/`Static` goes through `rich.text.Text(...)`.
- Don't name a Widget method `_render`; widget IDs unique app-wide; ListView
  modals handle `on_list_view_selected`; check key bindings actually reach the
  app (TextArea consumes many `ctrl+` keys; `ctrl+enter` never arrives).
- Keep the suite green after every phase:
  `PYTHONPATH=src ~/lorewrite/.venv/bin/python -m pytest -q`
  (the shared venv's editable install points at the main checkout; the
  `PYTHONPATH=src` prefix makes it use the worktree's code — verify with
  `python -c "import lorewrite; print(lorewrite.__file__)"`).

## Phase 0 — shared AI plumbing + cost tracking

**New `src/lorewrite/ai/usage.py`**
- `UsageLedger` (thread-safe: calls run in `asyncio.to_thread`): `record(model,
  feature, cost: float | None, prompt_tokens, completion_tokens)`,
  `session_total() -> float`, `last() -> entry | None`. Module singleton
  `LEDGER`.
- `record_response(response, model, feature)`: read `response.usage`; OpenRouter
  returns `usage.cost` (USD) when the request includes
  `extra_body={"usage": {"include": True}}`. Tolerate missing fields (cost None).

**`src/lorewrite/ai/client.py`**
- `usage_extra_body(extra: dict | None) -> dict` merging
  `{"usage": {"include": True}}` with existing `provider.require_parameters`.
- Update the three existing call sites (`ai/links.py::suggest_links`,
  `ai/continuity.py::check_scene`, `::propose_canon_updates`) to pass it and to
  call `record_response`. Do NOT change their public signatures/return types
  (tests monkeypatch them).

**TUI**
- Status bar: append `AI $0.0123` (session total, 4 decimals; hide when 0).
- After each AI call's notify, include the call cost when known:
  `"… (AI $0.0031)"`.
- Tests: ledger math + thread safety smoke; `record_response` with/without
  `usage.cost`; status bar shows total after a mocked call records cost.

## Phase 1 — writing model setting

- `client.py`: `DEFAULT_WRITING_MODEL = DEFAULT_STRONG_MODEL`.
- `tui/app.py`: replace `_ai_fast_model`/`_ai_strong_model` duplication with
  `_ai_model(kind)` for kind in `fast | strong | writing` with precedence
  project.toml `[ai] <kind>_model` > user setting `<kind>_model` > default.
  Keep the old two methods as thin wrappers if tests reference them.
- `tui/settingscreen.py`: third row "Writing model (drafting & rewrites):"
  with Input `#writing-model` + `Choose…` button `#pick-writing` (reuse
  `ModelPicker`). Saved/loaded exactly like the other two — including the
  null-safe load (`str(get(...) or "")`, see commit 8b89300).
- Note: `ModelPicker` lists only structured-output models. Drafting uses plain
  text output, so for the writing field pass `structured_only=False` to show the
  whole catalog. `parse_models` gains a `structured_only: bool = True` param;
  `list_models` caches the raw payload and filters per call.
- README + SPEC §8: document the three model roles.
- Tests: precedence (project > user > default) for `writing`; settings round
  trip for `#writing-model`; picker for writing field shows a non-structured
  model (mock catalog).

## Phase 2 — `ctrl+l` becomes an alias finder (no brackets)

Plain names/aliases are already recognized (`core.links.find_mentions`). The AI's
remaining value is finding *other* ways the prose refers to known entities
("the old smith" → Borin).

- `ai/links.py`: new prompt: "find descriptive references to the known entities
  that are not already one of their names/aliases". Keep offsets + schema +
  app-side validation. `validate_suggestions` additionally drops: surfaces that
  already match `find_mentions(text, all_names)` at that span; pronouns
  (he/she/they/him/her/them/his/hers/their/it/its/I/me/you, case-insensitive);
  surfaces < 2 chars or > 40 chars; duplicates by (surface.casefold(), entity).
- Delete `apply_suggestions` and its app usage — the scene text is never
  modified by this feature any more. Update/replace its tests.
- `LinkReviewScreen` (or a renamed `AliasReviewScreen`): each row
  `"the old smith" → Borin  (line 12: …context…)`; all pre-checked; `space`
  toggle, `a` all, `enter` apply, `esc` cancel (existing behavior). Accepted →
  `ent.add_alias` for each → `self._entities_changed()` (rebuilds index so every
  scene picks the alias up).
- Palette/footer/help/tour text: "Find aliases" instead of "Link mentions".
  SPEC §7 M2 bullet + README updated.
- Tests: validation drops existing-name spans, pronouns, dupes; accepting adds
  aliases and leaves scene text byte-identical; cancel changes nothing.

## Phase 3 — style guide

- **Storage: `<project>/style.md`** (project root, plain Markdown, author-owned
  and editable; NOT in `.lorewrite/`). Sections: `## Voice` (POV, tense,
  register), `## Rhythm & syntax`, `## Diction`, `## Dialogue`, `## Avoid`,
  `## Exemplars` (2–3 paragraphs quoted verbatim from the manuscript, each as a
  blockquote with its source scene filename).
- `core/style.py` (pure): `style_path(project)`, `load_style(project) -> str |
  None`, `save_style(project, text)` (atomic temp+rename like entities),
  `sample_manuscript(project, max_words=6000) -> list[(scene_rel, paragraph)]`
  (even spread across scenes, skip headings and paragraphs < 25 words),
  `exemplars_section(samples, picks) -> str`.
- `ai/style.py`: `learn_style(samples, model, client=None) -> StyleProposal`
  (JSON schema: `{voice, rhythm, diction, dialogue, avoid, exemplar_indexes}`;
  validate indexes app-side, build the Markdown with `core.style`). Uses the
  **writing** model.
- TUI: palette `Action · AI: learn style guide from manuscript` → worker →
  review modal showing the proposed `style.md` (read-only scrollable Markdown,
  `enter` save / `esc` discard; if a `style.md` exists, say it will be replaced
  and keep a backup `style.md.bak`). Palette `Action · Open style guide` opens
  `style.md` in the editor (create from a stub template if missing). Opening it
  in the editor must not enable plain-name mention highlighting (it isn't a
  scene — `_is_scene` already handles this).
- SPEC §7 M4 bullet: storage decision (`style.md` at root, not `.lorewrite/`).
- Tests: sampling spread/skips; proposal → Markdown; bad indexes dropped;
  save/backup; open-style-guide creates stub.

## Phase 4 — pending AI text (the marking mechanism)

All generated text uses one mechanism, stored **in the scene file** so it
survives saves, reopen, and external editors (Obsidian hides HTML comments):

```
<!--ai-->generated text<!--/ai-->
<!--ai replaces="BASE64"-->generated text<!--/ai-->
```

- `replaces` holds the base64 (urlsafe, UTF-8) of the original text the draft
  replaced (a selection, or an `{{expand: …}}` marker). Absent = pure insertion.
- `core/drafts.py` (pure): `find_pending(text) -> list[Pending(start, end,
  body_start, body_end, original: str | None)]`; `wrap(body, original=None) ->
  str`; `accept(text, pending) -> str` (remove markers, keep body);
  `reject(text, pending) -> str` (restore original or remove);
  `pending_at(text, offset)`. Nested/malformed markers: ignore (treated as plain
  text), never crash.
- Editor (`tui/editor.py`): style the body with `ai_style` (theme magenta or a
  distinct hue via `theme.link_color`-style fallback, plus italic) and the
  marker comments with `bracket_style` (faded). Reuse the span machinery in
  `refresh_links` (`_spans`); add kind `"ai"`.
- Word counts (status bar + project count) exclude pending AI bodies.
- Keys (verify each reaches the app with a Pilot test; adjust if TextArea eats
  it and document the final choice in HELP_TEXT/README):
  - `ctrl+g` — **generate** (context-sensitive, see Phase 5)
  - `f7` — accept the pending draft under the cursor
  - `f8` — reject the pending draft under the cursor
  - palette: `Action · Accept all AI drafts in this scene`,
    `Action · Reject all AI drafts in this scene`
- Status hint when cursor is in a pending span:
  `AI draft — f7 accept · f8 reject`.
- Continuity check / story-bible update / alias finder must ignore pending AI
  bodies (strip them before sending) — unaccepted AI text is not canon.
- Tests: wrap/find/accept/reject round-trips (incl. unicode, `-->` inside
  original, multiple drafts, malformed markers); editor styles ai span;
  f7/f8 via Pilot; word count excludes pending; teardown with a pending draft
  doesn't crash.

## Phase 5 — generate: draft, expand, rewrite (one key, three modes)

`ctrl+g` decides by context:

1. **Selection present** → *Rewrite*: modal prompt prefilled
   "Rewrite this in my style." (editable instruction). Result replaces the
   selection as `<!--ai replaces=…-->`.
2. **Cursor on `{{expand: instruction}}`** → *Expand*: no modal; instruction
   comes from the marker. Result replaces the marker (reject restores it).
   Parse with `core/drafts.py::find_expand_markers(text)`; editor styles
   markers faded like brackets.
3. **Otherwise** → *Draft*: modal multi-line prompt ("Give me one paragraph
   describing…"). Result inserted at the cursor as `<!--ai-->`.

- `ai/writing.py`: `build_context(scene_text, cursor_offset, entities,
  canon_by_name, style_md) -> str` — style guide (full), ±500 words around the
  cursor (split at word boundaries, with a `<<CURSOR>>` sentinel), notes/canon
  of entities mentioned in the scene (use `find_all_links` with names; cap each
  at 1200 chars, total 6000), pending AI bodies stripped.
  `generate(mode, instruction, context, model, client=None, selection=None)
  -> str` — plain-text output (no JSON schema), system prompt: write only the
  requested prose, match the style guide, no commentary, no Markdown fences,
  never write `<!--`. Post-process: strip fences/quotes/leading labels;
  empty result → error.
- TUI: worker with a status "Drafting… (model)" notify; `esc` in the prompt
  cancels; errors notify (no crash). Missing style guide → still works, with a
  one-time hint "Tip: learn a style guide first (palette)". Uses the
  **writing** model; cost recorded (Phase 0).
- HELP_TEXT, tour page (add a page or extend page 2), README, SPEC §7 M4 marked
  implemented with the final keys.
- Tests (mock `lorewrite.tui.app.generate`): each mode inserts a correctly
  wrapped span at the right place; reject restores selection/marker exactly;
  accept leaves clean text; context builder caps, cursor sentinel, strips
  pending; post-processing.

## Out of scope (do not build)

Inline ghost-text completion; whole-manuscript continuity; hover cards; Q&A;
spell/grammar; idea generator; export.

## Definition of done

- All phases implemented; full suite green; new tests for every bullet above.
- Manual smoke via Pilot against `~/lorewrite-demo` with AI mocked: screenshots
  (`app.save_screenshot` → `rsvg-convert`) of a pending draft, the style-guide
  review, and the alias review; look at them.
- SPEC.md, README.md, AGENTS.md (repo layout + "current state") updated.
- One commit per phase on branch `m4-ai-writing` (message style as in
  `git log`; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`).
  Never commit to `main`, never push.
- Final: run the Jev review over the branch diff vs `main`:
  `git diff main...HEAD -- <files> | ~/.config/jev/jev.py review --task "<M4
  plan>" --files <files>` and report verdict + scores (a `network` HOLD from
  the OpenRouter client is expected and acknowledged).
- Final report: per-phase summary, key bindings chosen, anything deviating
  from this plan and why, known limitations.
