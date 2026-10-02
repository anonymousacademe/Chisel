# Plan: Phase B — installable apps for Windows, macOS and Linux

Approved by the author 2026-10-01 ("I'd like to make this more of an app you
can install"). The repo is public: https://github.com/anonymousacademe/lorewriter
(pseudonym **Mishkin**; the anonymity rule in `docs/dev/plan-release.md`
still applies — never add a real name, institution or home path).
Same rules as `docs/dev/plan-workspace.md` ("Rules for every wave").

## B0. First: make CI green on all three systems

The first CI run (run 36949845746) failed. Logs: `/tmp/ci-run1/*.log`.
- **All OSes:** `tests/test_theme.py::test_editor_draft_style_uses_distinct_hue_and_tint`
  passes locally only because it reads the developer's real Omarchy theme
  (`~/.local/state/omarchy`); make it hermetic (inject the colours / point the
  theme lookup at a temp dir), and audit other tests for the same leak.
- **Windows (10 failures):** fixtures written with `write_text` (CRLF on
  Windows) compared with the app's LF saves (`test_ai_links`) — write
  fixtures with `newline="\n"` and decide/document what the app does with a
  CRLF file the author made in another editor (preserve vs normalise: keep LF on
  save, but never report a "change" for CRLF-only differences; test it);
  export tests require Liberation Serif/Sans which Windows lacks and we don't
  bundle — tests must use the bundled Noto/Liberation Mono or skip with a reason,
  and the app's fallback must pick a bundled font with a warning;
  `core/sync.py` on Windows: compare paths as `Path`s (not `C:/` vs `C:\`
  strings), commit-message mismatch (check encoding of the em dash in the
  prefilled message via git on Windows: pass `-c i18n.commitEncoding=utf-8` /
  use `--file` with UTF-8 bytes), and status after push showing `Ahead 1`
  (remote-tracking / path issue — reproduce by reading the code).
- You cannot run Windows/macOS: fix by reading, keep Linux green, commit;
  the managing session pushes a branch to run CI and sends you the results.

## Deliverables (built by GitHub Actions, attached to a GitHub Release)

| OS | Artifact | Notes |
|---|---|---|
| Windows 10/11 x64 | `LoreWriter-<ver>-windows-setup.exe` (Inno Setup installer: Start-menu + optional desktop shortcut, uninstaller, per-user install, no admin) and `LoreWriter-<ver>-windows-portable.zip` | pywebview's EdgeChromium (WebView2) backend; WebView2 runtime is on Win 10/11 |
| macOS (arm64 + x64, or universal2 if PyInstaller allows) | `LoreWriter-<ver>-macos.dmg` containing `LoreWriter.app` | pywebview Cocoa (pyobjc). Unsigned: README explains right-click → Open (or `xattr -d com.apple.quarantine`) |
| Linux x86_64 | `LoreWriter-<ver>-x86_64.AppImage` | WebKitGTK cannot be bundled reliably → use pywebview's **Qt backend** (PySide6 QtWebEngine) inside the AppImage; the from-source path keeps GTK |
| any | sdist + wheel (`lorewriter-<ver>…`) | for pip/pipx; PyPI upload comes later (needs the author's PyPI account) |

Every bundle contains **both** apps: the desktop app (default, windowed — no
console window on Windows) and the terminal app (`lorewrite`, a console
executable next to it). Name in menus/docks: **LoreWriter**; icon from
`gui/src-tauri/icons/` (convert as needed: .ico for Windows, .icns for macOS,
.png for Linux).

## Build (PyInstaller, onedir)

- `packaging/lorewriter.spec` (one spec, OS branches) + `packaging/build.py`
  (one entry point per OS used by CI and locally): collects
  `lorewrite/gui/web/**`, bundled fonts, `pyspellchecker` dictionaries,
  `pyphen` dictionaries, Textual CSS/assets and tree-sitter grammars
  (`textual[syntax]`), reportlab data, `certifi` CA bundle (openai/httpx
  HTTPS), keyring backends (hidden imports: Windows `keyring.backends.Windows`,
  macOS `keyring.backends.macOS`, Linux `SecretService`), pywebview platform
  module for that OS. Prefer onedir (fast start); the installer/DMG/AppImage
  wraps the folder.
- `lorewrite-gui --self-test` (new): loads every subsystem that needs bundled
  data (web root found, fonts present, spell checker loads and checks a
  word, pyphen hyphenates, Textual imports, keyring backend resolves, export
  layouts register, PDF export of a tiny temp project succeeds) and prints a
  JSON report; exit 0/1. **No window, no network.** CI runs it on every built
  bundle — this is the main guard, since nobody can click through a Mac here.
- Version: single source (`lorewrite.__version__`), stamped into the Windows
  file version, macOS `Info.plist` (`CFBundleShortVersionString`,
  `CFBundleIdentifier` = `io.github.mishkin.lorewriter`, `NSHighResolutionCapable`),
  and the AppImage desktop file.
- pandoc is NOT bundled (licence + size); DOCX/EPUB/LaTeX stay greyed out with
  "install pandoc" unless it is on PATH. Document it.
- The unused `gui/src-tauri/` stays untouched (documented as an unused
  alternative shell).

## CI: `.github/workflows/release.yml`

- Triggers: `workflow_dispatch` (test builds → uploaded as workflow
  artifacts, no release) and tags `v*` (→ a **draft** GitHub Release with all
  artifacts; the managing session publishes it after review).
- Jobs: build the web UI once (Node) → artifact; per-OS PyInstaller jobs
  (windows-latest, macos-latest arm64 + macos-13 x64 or universal2,
  ubuntu-22.04 for an older-glibc AppImage) → run `--self-test` on the built
  bundle → package (Inno Setup via `choco install innosetup` or the
  preinstalled one; `hdiutil create` for the DMG; `appimagetool` for the
  AppImage) → upload. sdist/wheel job with `python -m build`.
- Checksums file (`SHA256SUMS.txt`) attached to the release.
- Use pinned action versions; no secrets needed (no signing yet).

## Local verification (this Linux machine)

Build the Linux bundle locally (PyInstaller in a throwaway venv with the Qt
backend), run `--self-test` from the bundle, build the AppImage, run the
AppImage's `--self-test`, and run the AppImage's terminal app `--help`.
**Do not open a window on the author's desktop.** Validate the workflow YAML
(`actionlint` if you can install it, else a YAML parse + careful review).
Windows/macOS jobs are verified by the managing session through a
`workflow_dispatch` run on GitHub after you finish.

## Docs

README "Install": the download table with real file names, per-OS first-launch
notes (Windows SmartScreen "More info → Run anyway"; macOS Gatekeeper
right-click → Open; Linux `chmod +x` and run), where settings live per OS,
pandoc as optional. `docs/dev/packaging.md`: how to build locally, how to cut a
release (`git tag vX.Y.Z && git push --tags` → draft release → publish).
CONTRIBUTING: release section.

## Rules

Branch `packaging` (worktree `~/lorewrite-packaging`). Commit per logical step,
never on main, never push, never create tags or releases, never run `gh`.
Network only for pip/npm and downloading build tools (PyInstaller, appimagetool,
actionlint). No AI calls. Headless only; stop what you start by PID; never close
windows/processes you did not start; never use wildcard deletes after `cd`
(delete temp dirs by absolute path; create them with `mktemp -d`). Jev per
commit. Report to `/tmp/packaging-report.md`.
