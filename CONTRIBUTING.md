# Contributing to Chisel

Thanks for helping. Bug reports, fixes and small improvements are welcome; for a larger
feature, please open an issue first so we can agree on the shape of it.

## Set up

```bash
git clone https://github.com/anonymousacademe/lorewriter && cd lorewriter
python3 -m venv .venv                      # Linux desktop app: add --system-site-packages
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt && pip install -e .
(cd gui && npm ci)                         # only if you work on the desktop UI
```

The desktop app on Linux needs the system WebKitGTK packages; see the README.

## Run the tests

```bash
python -m pytest                           # must stay green; no test touches the network
(cd gui && npm run lint && npm test && npm run build)
```

TUI tests drive the app headlessly with Textual's Pilot; the GUI backend is plain Python.
AI calls are mocked at the function boundary — never call a real model in a test.

## The principles (do not break these)

1. **Plain text, always.** A project is a folder of Markdown; no database blobs.
2. **The index is a cache.** The SQLite index can be rebuilt; the files are the truth.
3. **AI suggests, never edits.** Every AI feature ends in an accept/reject step.
4. **Entity notes** are free text plus minimal YAML frontmatter (name, type, aliases; any other keys are kept as written).

Naming: the app is called Chisel in anything a user reads. The package (`lorewrite`), its commands,
state folders, `LOREWRITE_*` variables and the repository name stay as they are.

Icons and the logo: the artwork and its sources are in [docs/brand/](docs/brand/README.md); which file is used
where (the Windows window needs an `.ico`) is in [docs/dev/packaging.md](docs/dev/packaging.md#icons).

Also: project logic lives in `core/` and `ai/` (pure Python, no UI), and both front ends
use it. The desktop UI never re-implements logic in TypeScript.

## Before you open a pull request

- Read [AGENTS.md](AGENTS.md): it lists the fragile spots and conventions in detail.
- Keep the change small and in the style of the code around it; add or update tests.
- Update [SPEC.md](SPEC.md) when you change design or behaviour, and add a line to
  [CHANGELOG.md](CHANGELOG.md) under Unreleased for anything a user would notice.
- Do not commit personal data: real names, home paths or e-mail addresses.
- No emojis in the UI or the docs.

By contributing you agree that your work is released under the [MIT licence](LICENSE).

## Releases

Maintainers only. The version lives in one place, `src/lorewrite/__init__.py`
(`__version__`); the wheel, the Windows file version, the macOS `Info.plist` and
the AppImage desktop file all read it. To cut a release: bump it, merge to `main`,
then `git tag vX.Y.Z && git push --tags`. The `Release` workflow builds the
installers on all three systems, runs `--self-test` on each, and attaches
everything to a **draft** GitHub Release for a person to review and publish.
`Actions > Release > Run workflow` makes a test build without a release. Details
and local builds: [docs/dev/packaging.md](docs/dev/packaging.md).
