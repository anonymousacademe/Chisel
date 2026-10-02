# Contributing to LoreWriter

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
4. **Entity notes** are free text plus minimal YAML frontmatter (name, type, aliases).

Also: project logic lives in `core/` and `ai/` (pure Python, no UI), and both front ends
use it. The desktop UI never re-implements logic in TypeScript.

## Before you open a pull request

- Read [AGENTS.md](AGENTS.md): it lists the fragile spots and conventions in detail.
- Keep the change small and in the style of the code around it; add or update tests.
- Update [SPEC.md](SPEC.md) when you change design or behaviour.
- Do not commit personal data: real names, home paths or e-mail addresses.
- No emojis in the UI or the docs.

By contributing you agree that your work is released under the [MIT licence](LICENSE).
