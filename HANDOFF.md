# HANDOFF — Chisel: open GUI crash bug + pending reviewer guide

Date: 2026-10-04. Repo: `C:\Users\user\OneDrive - North Carolina State University\CoWork\PERSONAL\lorewriter`
(Windows 11, PowerShell). Read AGENTS.md first — it is the operational guide; SPEC.md is the design doc.

## State of the code (all uncommitted, working tree)

The **character relationships feature is complete and verified** — do not rework it:

- `src/chisel/core/relationships.py` — parse/render `## Relationships` sections, `rows()` with derived inverses.
- `src/chisel/ai/relationships.py` — `plan_suggestions` (budget) / `suggest_relationships` (network) / `apply_suggestions`.
- Wired in `gui/api.py` (`suggest_relationships`, `apply_relationships`, AI_JOBS kind `"relationships"`),
  `gui/entities_api.py` (`get_entity` now carries `relationships` rows), `gui/mockai.py`, `tui/app.py`,
  `tui/relationreview.py`, `tui/commands.py`, and the React side (`NotesPanel`, `ReviewDialogs`, `useAiActions`,
  `App.tsx`, `data/types.ts`, `data/dialog.ts`, `backend/api.ts`).
- Tests: full pytest **1233 passed, 12 skipped**; `npm run lint/test/build` green.
- Docs updated: SPEC.md §14, CHANGELOG.md (Unreleased), AGENTS.md, README.md, docs/dev/plan-relationships.md.

Untracked files that are NOT feature work: `Chisel-Screen Jitter.mp4`, `Logos/` (user media — leave alone),
and `gui/src/components/NotesPanel.keith.test.tsx` (a debug test written during the crash hunt below — keep or fold
into a proper test).

## THE OPEN BUG (top priority)

**Reported by the user:** "When I click the Character sheet for the 'Keith' story, the screen goes blank."
Project: `C:\Users\user\novels\keiths-book` (DO NOT write to it — always work on a copy).

**Reproduced.** Working repro script: `%TEMP%\opencode\uitest\binder.mjs` (Playwright + Chromium already installed
there; run `node binder.mjs http://<devserver-url>/`). To serve the UI:
`.venv\Scripts\python.exe -m chisel.gui.devserver --project <COPY> --mock-ai` (prints its URL on stdout; no
`--port` flag; `--port` is silently ignored).

**Findings so far:**

1. The Python bridge is healthy for this exact case (verified via `POST /api/<method>` with body `{"args": [...]}`):
   `get_workspace`, `read_document("entities/characters/keith.md")`, `get_entity("Keith")` all return `ok: true`.
   The Keith note is frontmatter-only with an **empty body**, no relationships, 2 backlinks.
2. `NotesPanel` renders that exact payload fine in vitest/jsdom
   (`gui/src/components/NotesPanel.keith.test.tsx` passes).
3. Repro sequence in the real UI: the devserver opens the project with scene "Opening" loaded. Clicking the
   **binder** item "Keith" does nothing bad; clicking the **`lw-mention` spans of "Keith" inside the editor
   text** blanks the whole page (innerText → 0) with a **React error #301** thrown from
   `renderWithHooksAgain` — i.e. **"Rendered more hooks than during the previous render"**: some component
   conditionally calls hooks. The click path to audit: mention click → `showNote(name)` in `gui/src/App.tsx`
   (~line 319) → note fetch effect → Assistant panel switches/updates; also whatever the editor does when a
   mention is clicked (editor/cm.ts decorations, `editor/spans.ts`).
4. It is currently unknown whether this bug predates the relationships work (the Keith note may never have been
   opened this way before). Check by `git stash`-ing the uncommitted changes and re-running the repro — but the
   stash includes untracked feature files, so stash with `-u` carefully or test on a separate worktree.

**Tooling trap that burned time:** the devserver kept serving a stale/minified bundle, so the crash error stayed
"Minified React error #301". `src/chisel/gui/web/assets` held only the old `index-Dm7z6o9E.js` after rebuild
attempts. If you rebuild, verify `src/chisel/gui/web/index.html` actually references the NEW asset hash, and
restart the devserver after every build. To get a readable React error, the bundle must be built with React in
development mode (a plain `vite build --minify false` is NOT enough — React bakes its own minified strings).
Suggested next steps, in order:

1. Get the unminified error (e.g. temporary `define: { 'process.env.NODE_ENV': '"development"' }` in
   `gui/vite.config.ts` build config, verify the new hash is served, restart devserver, re-run repro).
2. Or skip the message entirely and audit for conditional-hook violations in every component that mounts or
   re-renders on `showNote` — early `return`s that sit **before** a `useState`/`useEffect` in the same component,
   or a component that renders a hook-ful child only in some branches.
3. Write the failing case as a vitest (mount Assistant with the note flow) so the fix is locked.
4. After fixing: `npm run build` in `gui/`, confirm the served hash changed, re-run `binder.mjs` — the click must
   not blank the page and the note panel should show Keith's info.

## ALSO PENDING (user request, not started)

Build a **printable reviewer guide** the user will print on paper and fill in by hand while exercising the whole
app: every major feature (projects, scenes, parts, editor, wiki links + ctrl+click, alias finder, relationships,
continuity + waivers, canon, style guide, drafts ctrl+g, spell check f6, snapshots, git sync, collections,
comments, notebook, chats/attachments, inspiration images, export, settings/models, stats/sprints, atmosphere,
trash/rename) as numbered checklist sections, each with ruled blank note space ("what I saw", "what went wrong"),
a cover page with project/app/version fields, and print-friendly CSS (page breaks per section). The user prints
it literally — optimize for A4/Letter ink, not screen. Deliver as an HTML file they can print from a browser
(and/or a PDF). No emojis. Store it under `docs/` (e.g. `docs/reviewer-guide.html`) and tell the user where it is.

## Environment notes

- Tests: `.venv\Scripts\python.exe -m pytest -q` (~8 min full suite). Frontend: `npm run lint|test|build` in `gui/`.
- App state dir: `C:\Users\user\AppData\Local\chisel` (recents in `recent.json` — the user's projects:
  keiths-book, ellville-1, upstate...). Test copies go to `%TEMP%\opencode\`.
- Scratch tooling: `%TEMP%\opencode\uitest` has playwright + chromium installed (package.json there is scratch;
  do NOT add playwright to the repo's gui/package.json without asking).
- A devserver may still be running (check `netstat` for 58462/62610 or python processes) — kill before rebuilding.
- Never hit the network in tests; AI is mocked (`gui/mockai.py`, monkeypatch `chisel.tui.app.suggest_relationships`).
- Do not commit unless the user asks. `Chisel-Screen Jitter.mp4` and `Logos/` are untracked user media.
