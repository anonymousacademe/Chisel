# Packaging: installable apps for Windows, macOS and Linux

Plan: [plan-packaging.md](plan-packaging.md) (historical). Everything lives in `packaging/`;
the workflow is `.github/workflows/release.yml`.

Naming: the app is called Chisel, so the desktop executable, the bundle folder, `Chisel.app` and every
release file are `Chisel*`. The packaging sources keep their old names (`lorewriter.spec`,
`lorewriter.iss`), and the terminal executable, the package and the commands stay `lorewrite`.

## What a build contains

PyInstaller (onedir) bundles the Python core, the terminal app and the desktop app.
One spec (`packaging/lorewriter.spec`, OS branches; the file name did not change) makes **two executables** from one
entry script (`packaging/entry.py`) that share one set of libraries:

| Executable | Starts | Console |
|---|---|---|
| `Chisel` (`Chisel.exe`) | the desktop app (`lorewrite.gui.app`) | none (windowed) |
| `lorewrite` (`lorewrite.exe`) | the terminal app (`lorewrite.tui.app`) | yes |

The entry script picks by the executable's own name. Bundled data: the built web UI
(`lorewrite/gui/web`), export fonts, spell-check and hyphenation dictionaries, Textual
and Rich data, tree-sitter grammars, ReportLab data, the TLS roots, keyring backends
(Windows / macOS / Secret Service) and pywebview's platform module for that OS.

| OS | Webview | Package |
|---|---|---|
| Windows x64 | WebView2 (EdgeChromium, `pythonnet`) | Inno Setup installer + portable zip |
| macOS | WKWebView (Cocoa, pyobjc), one build per CPU (arm64 required; x86_64 best effort) | `Chisel.app` in a DMG |
| Linux x86-64 | **Qt WebEngine** (PySide6 + qtpy; WebKitGTK cannot be bundled reliably) | AppImage (`AppRun` also starts the terminal app: `--terminal`, or a link named `lorewrite`) |

From-source Linux runs keep using GTK; only the bundle uses Qt (`PYWEBVIEW_GUI=qt`
is set by `entry.py` on Linux).

pandoc is not bundled (licence, size); DOCX / EPUB / LaTeX export stay greyed out
until it is on the PATH. The unused `gui/src-tauri/` is an abandoned alternative shell;
only its icons are used (`icon.ico`, `icon.icns`, `icon.png`).

## Icons

The artwork is the Chisel logo (supplied by the project author; vector and PNG sources in
[`docs/brand/`](../brand/README.md)). Where each copy is used:

| File | Used for |
|---|---|
| `gui/src-tauri/icons/icon.ico` | the Windows executable and installer |
| `gui/src-tauri/icons/icon.icns` | the macOS `Chisel.app` |
| `gui/src-tauri/icons/icon.png` and the sized PNGs beside it | the Linux AppImage and the other sizes |
| `src/lorewrite/gui/icon.ico` | the desktop **window** icon on Windows (from source and bundled) |
| `src/lorewrite/gui/icon.png` | the window icon on macOS and Linux |
| `gui/src/assets/logo.svg` (copy: `gui/public/logo.svg`, `favicon.png`) | the logo inside the app |

pywebview's WinForms backend loads the window icon with `System.Drawing.Icon`, which only accepts an
`.ico`, so `src/lorewrite/gui/app.py` passes `icon.ico` when `sys.platform == "win32"` and `icon.png`
otherwise. Both files are package data (`pyproject.toml`). `gui/scripts/make-icons.sh` regenerates the
PNGs, `.ico` and `.icns` from `gui/src/assets/logo.svg` (needs `rsvg-convert` and Pillow); it does not write
`src/lorewrite/gui/icon.ico`, so copy `gui/src-tauri/icons/icon.ico` over it afterwards.
`tests/test_packaging_files.py` checks that the icons exist and that the window-icon rule holds.

Artifacts in `dist/release/`: `Chisel-<version>-windows-setup.exe`, `Chisel-<version>-windows-portable.zip`,
`Chisel-<version>-macos-arm64.dmg` (and `-x86_64.dmg`), `Chisel-<version>-x86_64.AppImage`, plus the sdist and
wheel (`lorewriter-<version>...`, the Python package name).

## The self-test

`lorewrite-gui --self-test` and `lorewrite --self-test` (code: `src/lorewrite/selftest.py`)
open no window and use no network. They check that the web UI is found, the fonts are
present, the spell checker flags a typo, pyphen hyphenates, Textual and the TUI import,
the keyring backend resolves, TLS roots exist, the export layouts register, a PDF of a
tiny temp project is written, and pywebview's platform module for the OS imports. They
print a JSON report and exit 0 or 1; `--report FILE` also writes it to a file (a windowed
Windows exe has no stdout). With `LOREWRITE_SELFTEST_RENDER=1` (Linux bundle) it also loads
the built UI in QtWebEngine on Qt's offscreen platform and reads the page title back, which
proves the bundled Chromium starts and guards the list of Qt parts the spec strips
(`slim_qt`). CI runs it on every bundle, on the installed Windows copy and on the app inside
the DMG: this is the main guard, since nobody clicks through a Mac or a Windows machine.

## Building locally

```bash
python3 -m venv .venv-build && . .venv-build/bin/activate
(cd gui && npm ci && npm run build)             # the UI goes into src/lorewrite/gui/web
pip install ".[all]" -r packaging/requirements-build.txt
python packaging/build.py all                    # bundle + self-test + package -> dist/release/
```

Stages can be run alone: `bundle`, `selftest [--gui EXE --tui EXE]`, `package`. Linux
needs the system libraries QtWebEngine loads (see the `linux` job in the workflow) and
downloads `appimagetool` into `build/`; Windows needs Inno Setup (`choco install innosetup`);
macOS needs nothing extra (`LOREWRITE_TARGET_ARCH=arm64|x86_64` picks the CPU). Headless
checks: `QT_QPA_PLATFORM=offscreen LOREWRITE_SELFTEST_RENDER=1 python packaging/build.py selftest`,
and `Chisel-*.AppImage --appimage-extract-and-run --terminal --help`. Do not start the
desktop app from a test script.

## Cutting a release

1. Bump `__version__` in `src/lorewrite/__init__.py`; update the docs if needed; merge to `main`.
2. `git tag vX.Y.Z && git push --tags`. The workflow refuses a tag that differs from the version.
3. Wait for the `Release` workflow: web UI, sdist + wheel, Linux AppImage, Windows installer + zip,
   macOS arm64 DMG, each self-tested; then a **draft** release with `SHA256SUMS.txt`. The macOS Intel (x86_64)
   DMG is **best effort**: its job runs too, but the release job does not need it to succeed; the DMG is
   attached only if that job passed, and `SHA256SUMS.txt` covers whatever is attached. If it fails, rerun
   just that job, or ship without it.
4. Look at the draft, download one file per system if you can, then publish it. The workflow only ever
   creates a **draft** (`gh release create --draft`); nothing is public until a person publishes it.
5. The User's Guide PDF is built separately (`python docs/user-guide/build_guide.py`; the output is git-ignored).
   The workflow copies any `docs/user-guide/*.pdf` that exists in the checkout into the release; a fresh
   checkout has none, so attach the built PDF to the draft by hand before publishing.

## Not done yet

Code signing and notarization (Windows Authenticode, Apple Developer ID), auto-update, a PyPI
upload (needs the author's PyPI account), universal2 macOS builds (two per-CPU DMGs instead).
Unsigned apps trigger SmartScreen / Gatekeeper; the README explains the first launch.
