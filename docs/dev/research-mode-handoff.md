# Hand-off: Chisel install, window-drag fix and research mode (as of 2026-10-15)

A summary for whoever continues this work (the user, or a lead agent running in herdr). It records what was
done, the state of every branch and tool, what is verified and what is not, and what is still open.

## 1. State at a glance

| Item | State |
|---|---|
| Chisel clone | `%USERPROFILE%\Chisel` (from `https://github.com/anonymousacademe/Chisel.git`), v0.5.0 |
| Install | From source: `.venv` with `pip install -e ".[all]"`, desktop UI built (`npm ci`, `npm run build`), `python -m chisel.selftest` exits 0 |
| Start-menu shortcut | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Chisel.lnk` (runs `pythonw.exe` from the `.venv`; breaks if that folder moves) |
| Current branch | `research-mode` (head `e04c690`), clean |
| `main` | Untouched, at `a1f1d6d` |
| Window-drag fix | Commit `6d0c502` on branch `fix-window-drag` (off `main`), merged into `research-mode`. **Not validated in the full app** |
| Research-mode design | Draft 3, committed; **nothing implemented** |
| herdr | 0.9.5 installed at `%USERPROFILE%\tools\herdr\herdr.exe`; not on PATH; no agents started |
| Pushes | None. Everything is local |

Commits on `research-mode` after `main`: `d8e6682` first plan, `ef71f9e` plan draft 2 and work packages,
`a8c9a00` generated figures and tables, `6d0c502` drag fix (merged via `8c9bdf6`), `ceab88c` plan draft 3 and
contracts, `e04c690` orchestrator brief. (Git prints an LF-to-CRLF warning on these docs; harmless.)

## 2. Window drag bug

**Symptom:** the Chisel desktop window could not be dragged by its title bar unless maximized.

**Root cause (confirmed in a harness copied from pywebview's setup):** two bugs.
1. `begin_window_drag` did `int(form.Handle)`. With pythonnet 3.2.1 the handle is a `System.IntPtr`, so `int()`
   raises `TypeError`. The `@bridge` decorator swallowed it, so the drag code never ran. The old test used a
   plain `int` handle and its comment ("a real System.IntPtr converts with int()") was wrong.
2. `ReleaseCapture` and the caption-drag message ran on a pywebview worker thread. WebView2 holds the mouse
   capture on the UI thread, so from a worker thread the OS never started its move loop. Run through
   `form.Invoke`, the window moved exactly as injected.

**Fix (`src/chisel/gui/window_api.py`):** `_hwnd()` uses `ToInt64()`, the drag runs via `form.Invoke(Action(drag))`
when `InvokeRequired`, and `toggle_maximize` asks `IsZoomed` instead of a flag that goes stale after a caption
drag. Tests added in `tests/test_gui_window.py` (IntPtr handle, UI-thread invoke, stale flag); all three fail
on the old code. `tests/test_requirements.py` now lists `System` as provided by pywebview.

**Not validated:** the full app with the built UI, displays scaled above 100%, dragging across monitors,
Aero-snap from maximized. **Manual test (under a minute):** run `.venv\Scripts\chisel-gui`; restore if
maximized; drag by the empty title bar; click the title-bar buttons (none should start a drag); Maximize, then
drag down (should restore and follow); one click on Maximize should maximize. On failure, see
`%LOCALAPPDATA%\chisel\log\chisel.log` for "bridge method begin_window_drag failed".

**Test suite:** 1235 passed, 4 skipped (excluding `tests/test_tui.py`). One failure,
`tests/test_hardening.py::test_scene_path_and_trash_names_are_capped`, is a Windows path-length limit. It
fails identically on the original code. The TUI tests were not run.

## 3. Research mode: what it is

A project mode (`mode = "research"` in `project.toml`) for papers, proposals and theses. Files stay plain
Markdown; AI only suggests. The documents, in reading order:

1. `docs/dev/plan-research-mode.md`: the design (draft 3).
2. `docs/dev/research-mode-contracts.md`: frozen interfaces (types, signatures, bridge methods) for parallel work.
3. `docs/dev/plan-research-mode-work-packages.md`: packages P0 to P10 (with P4b and P4c), waves, merge order,
   acceptance criteria, usage rules.
4. `docs/dev/research-mode-orchestrator.md`: the lead-agent brief for building it with herdr.

**Scope in brief:** a Zotero connection (web API, local API, Better BibTeX export file, cache; read-only pull,
manual sync); source notes with a marked Zotero block (notes, highlights) plus the author's own notes;
`[[@key]]` citations; figures, tables and equations with cross-references, shown WYSIWYG in the desktop editor;
figures generated from the author's Python code and tables built from CSV with a formatting spec; export to
Word (pandoc reference document) and to LaTeX/PDF. Not in version 1: Zotero write-back, live Word fields,
exact page counts, PDF full-text reading, SVG/PDF figures, Claims, and section templates beyond a starter.

**Decisions made this session** (change them in the plan if you disagree):
- Narrative citations are `[[+@key]]`; parenthetical are `[[@key]]` with pandoc semantics inside.
- Sources are a new entity kind in `entities/sources/`, files named from the key; AI excludes them unless attached.
- Better BibTeX auto-export file is the first backend built; chain order is web, local, file, cache.
- Zotero native `citationKey` is read; keys are not generated by default.
- Script trust and the interpreter setting live in the per-user state folder, never in the project.
- Matplotlib belongs to the chosen interpreter, not to Chisel's own environment.

## 4. Reviews done

Two independent Opus reviews against the code. Draft 2 applied the first (entity kind and folder, AI
exclusion of sources, citation-parser collision, export pipeline stripping math/tables/headings, file naming,
native `citationKey`, CSL JSON storage, pandoc template and MiKTeX caveats, reordered build). Draft 3 applied
the second (trust record location, Windows execution contract for scripts, `code` document kind and `data/`
folder, Python-side table serialiser, generated-table ownership, link-parser exclusions, `Num` display
strings, CodeMirror widget and KaTeX rules, image serving, Word equation-number caveat, math restricted to
research mode). The second review's verdict was "not ready to build" until the contract fixes (B7, B8) were in
place; those are now in the contracts file. A third review has not been run.

## 5. Verified, unverified, and open

**Verified this session:**
- Zotero schema has a native `citationKey`; Better BibTeX on Zotero 8 pins keys and they sync (Zotero docs, schema).
- pandoc 3.9.0.2 on this machine converts TeX math to native Word equations and runs `--citeproc`.
  A relative image path failed ("Could not fetch resource") because pandoc runs from `exports/`.
- MiKTeX with xelatex, lualatex and pdflatex is installed here; Tectonic is not.
- Zotero Web API: `Backoff` on any response, `Retry-After` on 429, 50 keys per request, `limit` max 100.
- Local API notes (versions unrelated to web, `Zotero-Server-ID`, writes need a local key) are documented for
  **Zotero 10+**, not 8.

**Still VERIFY:** local-API annotation routes, `/deleted` and `include=csljson`; Word equation numbering and
right-aligned numbers; how far rich table features (merged headers, decimal alignment) survive into Word;
SVG/PDF figures in Word; whether the web API returns Better BibTeX keys for the user's library.

**Needs the user:**
- Zotero version, and the four cheap checks in plan section 12 (needs the user's API key and library).
- A funder Word template or format spec; the first funder format.
- Which Python the figure scripts use; which table features matter most.
- Terminal-app scope for table and equation editing; multi-panel figures; Zotero write-back later; template location.

## 6. Building it with herdr

herdr 0.9.5 (`ogulcancelik/herdr`; releases at `herdrdev/herdr`). Installed by hand: the release zip was
downloaded from `https://github.com/herdrdev/herdr/releases/download/v0.9.5/`, checked against the SHA-256 in
`https://herdr.dev/latest.json` (same-origin, so it catches corruption, not a compromised release), and unpacked
into `%USERPROFILE%\tools\herdr`. The official installer (`install.ps1`) was read but not run: running it
with `-ExecutionPolicy Bypass` was blocked, and that block was respected. PATH and registry are unchanged.

The controlling agent must run inside a herdr pane (`HERDR_ENV=1`). To start:
```
%USERPROFILE%\tools\herdr\herdr.exe
```
In a pane, run `claude` with the working folder `%USERPROFILE%\Chisel`, then paste the kickoff prompt at the
top of `docs/dev/research-mode-orchestrator.md`. The lead runs the pre-flight and baseline tests first, then Wave 0
(P0, Opus), and stops at the end of each wave to report. Workers use one git worktree per package, only the lead
merges, and nothing is pushed. Approval dialogs from workers are the user's to answer.

## 7. Incident and cleanups

- **A simulated click landed on a Zoom meeting window.** During drag testing (the second review agent), one early
  injected click hit the user's Zoom meeting window, which had come in front of the test window. Afterwards every
  run verified the click point was on the test window first. About 6 further injected drags of roughly 1 second
  each, cursor restored each time. The user should check that meeting for any stray effect. Lesson recorded in the
  orchestrator brief: agents never inject input, never run the app, never capture the screen.
- **A screenshot of the user's desktop was taken** during an earlier test (it captured a browser page). It was
  deleted from the scratchpad and not used.
- **Pre-existing process:** a `pythonw.exe` (PID 9608 at the time) was already running and was left alone. It was
  presumably the user's own Chisel window.
- **Changes to the user's machine:** the `.venv` in the clone, `pytest`, `pytest-asyncio` and `pytest-xdist`
  installed into that `.venv` (dev dependencies, not in the user's global Python), the Start-menu shortcut, and
  `%USERPROFILE%\tools\herdr`. Scratch files are under the session scratchpad
  (`...\scratchpad\drag\`, `...\scratchpad\herdr\`) and can be deleted.

## 8. Suggested next steps, in order

1. User: try the drag fix by hand (section 2) and tell us the result. If good, decide whether to merge
   `fix-window-drag` into `main`.
2. User: check the Zoom meeting; answer the Zotero version and API-key question; send a Word template.
3. Optional: a third review of the plan and contracts before spending on Wave 0.
4. User: start herdr, start `claude` in a pane, paste the kickoff prompt; review after each wave.
5. Later: add herdr to PATH; run the Zotero cheap checks; decide on the open questions in plan section 13.
