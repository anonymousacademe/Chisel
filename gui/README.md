# LoreWriter — desktop GUI

A React/TypeScript UI (from the `LoreWriter_1.fig` design, "The Meridian Archive
workspace") shown in a native **pywebview** window. The UI talks to the Python core
in-process through pywebview's `js_api`; all project logic lives in `core/` and `ai/`
(see the "Desktop GUI" section of [SPEC.md](../SPEC.md)).

## Run

```bash
python3 -m venv --system-site-packages .venv-gui     # needs system PyGObject + WebKit2 4.1
.venv-gui/bin/pip install -e ".[dev,gui]"
cd gui && npm install && npm run build               # writes gui/dist (git-ignored)
.venv-gui/bin/lorewrite-gui [--project PATH]         # --dev URL loads `npm run dev` instead
```

`lorewrite-gui` exits with a clear message when `gui/dist/index.html` is missing.

## Develop

```bash
npm run dev      # the UI alone in a browser (http://localhost:5173) on an in-memory mock core
npm run build    # tsc -b && vite build
npm run lint     # oxlint
npm test         # vitest: decoration mapping, save state machine, transports, ...

# the real core, headless (for screenshots / debugging), on a *copy* of a project:
PYTHONPATH=src .venv-gui/bin/python -m lorewrite.gui.devserver --project /tmp/residual [--mock-ai]
# prints http://127.0.0.1:<port>/ ; open it in Chromium. --mock-ai = canned AI, no network.
```

## Layout

```
src/
  backend/transport.ts   pywebview | http (devserver) | in-memory mock, picked at startup
  backend/api.ts         typed wrappers; method names match lorewrite.gui.api.Api
  backend/mock.ts        the mock core used by `npm run dev`
  data/types.ts          Workspace / document / AI result shapes (mirror workspace.py)
  data/tree.ts switcher.ts noteBlocks.ts   pure helpers (vitest)
  editor/cm.ts           CodeMirror setup: decorations, title block, draft widgets, hover cards
  editor/spans.ts        span -> decoration mapping, soft breaks (pure)
  editor/saveController.ts   autosave + conflict state machine (pure)
  editor/drafts.ts       where generated text lands if the buffer changed meanwhile
  components/            TitleBar ActivityRail Binder Editor EditorPane Assistant NotesPanel
                         StatusBar Launch QuickSwitcher SettingsDialog ReviewDialogs Dialogs Toast
  components/placeholder.ts   the one "Not in LoreWriter yet" treatment
  styles/tokens.css      colours, fonts, radii from the Figma file
src-tauri/               the original Tauri shell from the handoff: kept, unused, not built
design/figma-reference.png
```

## Placeholders

Anything the design shows that LoreWriter does not do yet is rendered as designed but
dimmed, with `aria-disabled` and the tooltip "Not in LoreWriter yet", via
`placeholderProps` / `<Placeholder>` / `IconButton placeholder` / `Tag placeholder`.
Never fake data; never a silent button. Search the source for `placeholder` to list them.

## Notes from the design

- The two empty navigation slots on the activity rail are left empty, as in Figma.
- The assistant disclaimer reads "LoreWriter can be wrong. Review changes before applying."
  (the handoff said "Muse").
- The design's marker icons in the right gutter of the page were mock annotations and
  are not drawn; comments are a placeholder button in the toolbar.
- Icons come from Lucide (`lucide-react`).
