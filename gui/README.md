# LoreWriter — desktop GUI (v0.2.0)

A Tauri 2 + React/TypeScript front end for LoreWriter, built from `LoreWriter_1.fig`
("The Meridian Archive workspace"). It replaces the TUI's presentation layer. The
existing LoreWriter logic plugs in behind three backend calls.

## Run

```bash
# Linux build deps (Ubuntu/Debian)
sudo apt install libwebkit2gtk-4.1-dev libxdo-dev libssl-dev librsvg2-dev build-essential
# plus Rust (https://rustup.rs) and Node 20+

npm install
npm run dev          # UI only, in a browser at http://localhost:5173 (mock data)
npm run tauri dev    # native window
npm run tauri build  # release bundles (.deb/.rpm/.AppImage) in src-tauri/target/release/bundle
```

A prebuilt `LoreWriter_0.2.0_amd64.deb` comes with this handoff: `sudo apt install ./LoreWriter_0.2.0_amd64.deb`.

## Layout

```
src/
  styles/tokens.css      colors, fonts and radii taken from the Figma file
  data/types.ts          the Workspace model the UI renders
  data/mock.ts           sample project (the design's content, verbatim)
  backend/index.ts       Backend interface: mock in the browser, Tauri invoke() in the app
  components/            TitleBar, ActivityRail, Binder, Editor, Assistant, StatusBar
  App.tsx                state and wiring
src-tauri/
  src/lib.rs             command stubs: get_workspace, save_document, ask_assistant
  tauri.conf.json        frameless 1600×1000 window (min 1280×760); custom title bar
```

## Connecting the existing LoreWriter core

The UI only needs these calls (see `src/backend/index.ts`):

| Command          | Args                         | Returns                                  |
|------------------|------------------------------|------------------------------------------|
| `get_workspace`  | —                            | `Workspace` JSON (see `data/types.ts`)   |
| `save_document`  | `id`, `paragraphs: string[]` | —                                        |
| `ask_assistant`  | `prompt`, `scope`            | reply text                               |

Each stub in `lib.rs` returns an error right now, and the UI then falls back to mock data.
If the TUI is Python, the simplest route is to package its core as a
[Tauri sidecar](https://v2.tauri.app/develop/sidecar/) that reads and writes JSON on
stdin/stdout, and have the three commands forward to it.

## Interactive now (mock backend)

- Binder: expand and collapse items, select a document, arrow and Enter keys. The Search rail icon filters the tree
- Editor: Manuscript, Corkboard and Outline views. Paragraphs are editable, and "Continue the scene…" appends a new one. Undo, redo, bold and italic work
- Live word counts: the target, session and project totals update as you type
- Focus mode hides both side panels
- Assistant: the quick actions pre-fill the composer, and Ctrl/⌘+J focuses it. Send, regenerate, copy and like work. The Context and Notes tabs work. Review passage scrolls to the flagged paragraph and Dismiss clears the insight
- Custom title bar: the window controls work and the bar drags the window
- The zoom control in the status bar changes the prose size

## Not wired yet

- Bold and italic change how text looks, but only plain text is saved
- These controls are placeholders: link, new document, conversation history, settings, snapshots and collections

## Notes from the design

- Two navigation slots on the activity rail are empty in the Figma file, so they are left empty here too.
- The assistant disclaimer says "Muse can be wrong…" while the panel is titled "LoreWriter". This is kept as designed, but you probably want to fix it.
- In Figma the active tab's label sits at the top of the tab, and the other labels are centered. Here all tab labels are centered.
- Icons come from Lucide (lucide-react), matching the Lucide icon names the design uses.
