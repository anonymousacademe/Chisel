# Plan: Phase A — make the repository public-ready (branch `release`)

Approved by the author 2026-10-01. The repository goes public at
https://github.com/anonymousacademe/lorewriter under the pseudonym **Mishkin**
(<anonymousacademe@proton.me>). Same rules as `docs/dev/plan-workspace.md` ("Rules
for every wave"). Phase B (PyInstaller executables, PyPI) comes after this.

## Hard rule: anonymity
The author's real name and institution were scrubbed from the code and the
whole git history. **Never add** a real name, institution, home path
(`/home/...`), personal email or machine-specific path to any file. Use
"Mishkin" for copyright/authorship, `anonymousacademe` for the GitHub owner,
"Jane Writer" for sample people. `git grep -niE` for the real first name, surname, login name and institution (the pattern is not written here, so this file passes the check itself)
must stay empty (except encoded noise inside the PDF, which this plan removes).

## A1. Licence and metadata
- `LICENSE`: MIT, `Copyright (c) 2026 Mishkin`.
- `pyproject.toml`: distribution name **`lorewriter`** (free on PyPI; the import
  package stays `lorewrite`, commands stay `lorewrite` / `lorewrite-gui`),
  version `0.3.0`, `license = "MIT"`, authors Mishkin, description (desktop +
  terminal fiction-writing app), readme, `requires-python >=3.11`, classifiers
  (OS Independent, Topic :: Text Editors, Environment :: Console/X11/Win32/MacOS
  X), `[project.urls]` (Homepage/Issues on the GitHub repo), keywords.
  Extras: keep `dev`, `gui`, `export`; add **`all`** = gui + export.
  `__version__` matches.

## A2. Requirements files
- `requirements.txt`: everything a user needs to run **both** apps and every
  feature from a source checkout: textual[syntax], pyyaml, openai, keyring,
  pyspellchecker, pywebview, reportlab, pyphen, platformdirs (A4) — lower
  bounds like pyproject; plus `-e .` is NOT used (keep it a plain list) —
  instead the README says `pip install -r requirements.txt && pip install -e .`
  or simply `pip install -e ".[all]"`. Platform markers where needed (e.g.
  pywebview's GTK backend pulls nothing on Linux — PyGObject comes from the
  system; on Windows pywebview needs `pythonnet`? check pywebview's docs in its
  installed package metadata, don't guess).
- `requirements-dev.txt`: `-r requirements.txt` + pytest, pytest-asyncio,
  textual-dev.
- A test that every import in `src/lorewrite` resolves to a module listed in
  requirements.txt / stdlib / optional-guarded (cheap static check).

## A3. The GUI must work when installed as a package
`gui/app.py` and `gui/devserver.py` find the UI at `parents[3]/gui/dist`
(repo-relative) — breaks for an installed package. Make the Vite build output
into the package (`src/lorewrite/gui/web/`, git-ignored, included as package
data via `[tool.setuptools.package-data]` and MANIFEST), with a fallback to the
repo `gui/dist` for development; a clear error if neither exists. Update
`gui/vite.config.ts` (`build.outDir`), `.gitignore`, docs, tests.

## A4. Portability (Windows, macOS, Linux)
- **State dir:** `core/recents.default_state_dir()` uses `~/.local/state` —
  switch to `platformdirs.user_state_dir("lorewrite")` (Linux keeps
  `~/.local/state/lorewrite`, so existing users lose nothing — test that);
  `LOREWRITE_STATE_DIR` still wins. Check every other home-relative path
  (`grep -rn "Path.home\|expanduser" src`): `~/novels` default stays but via
  `Path.home()`; Omarchy paths only on Linux and only if present.
- **Opening files:** one helper `core/desktop.open_path(path)`: `os.startfile`
  on Windows, `open` on macOS, `xdg-open` elsewhere; only on a click (existing
  rule). Replace the separate xdg-open calls (inspiration, export, TUI).
- **Fonts for export:** stop depending on `/usr/share/fonts`: vendor OFL fonts
  in the package (`src/lorewrite/core/export/fonts/`: Noto Serif regular /
  italic / bold / bold-italic and a mono, e.g. Noto Sans Mono or Liberation
  Mono; include each font's licence file). Download them once from the
  official Google Fonts / notofonts GitHub release with curl (allowed network
  for this item only), keep total size reasonable (< 5 MB). Keep system
  lookup as a fallback.
- **Atomic writes on Windows:** `tmp.replace(path)` can fail with
  PermissionError when another process has the file open — add a short retry
  (e.g. 5 × 50 ms) in the shared `write_atomic` and use it at the other
  `.replace` sites in core.
- **pandoc** stays optional (DOCX/EPUB/LaTeX greyed out without it); document
  per OS install.
- Line endings: open text files with `newline=""`-safe reading where we
  compare text (saves must not convert `\n` to `\r\n` on Windows) — check
  `write_text` calls use `newline="\n"` or bytes.
- Jev and Omarchy: already optional; make sure nothing errors when absent on
  Windows/macOS (paths with `~/.config` are harmless).

## A5. Docs for the public
- **README.md** rewritten for people who have never seen the project: what it
  is (desktop + terminal; plain Markdown projects), a screenshot (re-capture a
  fresh desktop screenshot headlessly from `examples/residual` with mock AI —
  `docs/screenshots/`), key features (concise, grouped), **Install** (download
  a release once Phase B exists — mark "coming"; pipx/PyPI — mark "coming";
  **from source**: per-OS prerequisites — Python 3.11+, Node 20+ for building
  the UI, Linux system packages for the desktop app: Debian/Ubuntu `apt
  install python3-gi gir1.2-webkit2-4.1`, Fedora `dnf install python3-gobject
  webkit2gtk4.1`, Arch `pacman -S python-gobject webkit2gtk-4.1`, and the
  venv must use `--system-site-packages` on Linux; Windows needs the WebView2
  runtime (preinstalled on Win 10/11); pandoc optional), **Quick start**
  (open the Residual example copy), **AI setup** (OpenRouter key, costs
  examples), **Your files** (project layout summary), **Privacy** (what is sent
  to AI and when), **Documentation** (the user guide PDF — link to the
  Release asset, plus SPEC), **Development** (tests, devserver), **License**.
  Mention honestly that the app was built with AI coding assistants (one line).
- **AGENTS.md / SPEC.md:** replace "the user's global instruction" Jev wording
  with "optional: if you have the Jev CLI…", keep the Omarchy sections but mark
  them optional/Linux-only; remove the stale "Current state" branch mentions
  (everything is on main).
- Move internal planning material to `docs/dev/` (plan-*.md, specification
  guide, ux review, user-guide BRIEF*.md stay with the guide build) and fix
  links.
- `CONTRIBUTING.md` (short: setup, tests, the non-negotiable principles),
  `.github/ISSUE_TEMPLATE/bug_report.md` (minimal).

## A6. The user guide PDF leaves git
Keep `docs/user-guide/` sources, add `lorewrite-users-guide.pdf` to its
`.gitignore`, and `git rm --cached` it. (The managing session will purge old
versions from history before the first push and attach the PDF to the first
Release — do not rewrite history yourself.) README links to the Release.

## A7. Continuous integration
`.github/workflows/ci.yml`: on push/PR — matrix ubuntu-latest, windows-latest,
macos-latest × Python 3.11 and 3.13: `pip install -r requirements-dev.txt`
(+ `-e .`), run pytest (GUI-backend tests are plain Python and should run
everywhere; skip only what truly needs a display/WebKit, with a reason);
a Node job: `npm ci`, `npm run lint`, `npm test`, `npm run build`. You cannot
run Windows/macOS here: make tests platform-safe by reading the code
(paths, `/` in ids, newlines, `os.sep`), and mark anything Linux-only with
`pytest.mark.skipif`. Validate the workflow YAML syntax locally.

## Done
Full pytest + vitest + build + lint green on Linux; `python -m build` produces
an sdist + wheel that contain the web UI and fonts (inspect the wheel; install
it into a fresh venv and run `lorewrite --help`, and start
`python -m lorewrite.gui.devserver` from the installed package headlessly to
prove the UI is found). Anonymity grep clean. Jev per commit. Report to
`/tmp/release-a-report.md`.
