# Plan: AI inspiration images (branch `inspiration`)

Status: approved by the author 2026-10-01. SPEC.md "Future — AI inspiration
images" describes the idea: describe a setting ("a dark subway platform,
flickering lights") and get a picture to keep on screen while writing.
**Reference only — never inserted into the prose.** Same rules as
`docs/dev/plan-workspace.md` ("Rules for every wave") — read them. Another agent
builds M7 export in parallel on branch `export`; keep edits to shared files
(`gui/src/App.tsx`, `gui/api.py`, `tui/app.py`, `tui/commands.py`, settings
screens) small and self-contained. Put new code in new files.

## The API (verified with a real call by the managing session)

OpenRouter chat completions with image output:
```python
r = client.chat.completions.create(
    model="google/gemini-3.1-flash-lite-image",
    messages=[{"role": "user", "content": prompt}],
    extra_body={"modalities": ["image", "text"], "usage": {"include": True}},
)
msg = r.choices[0].message            # openai SDK object
images = msg.model_dump().get("images")  # [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]
```
Measured: 3.8 s, one 1408×768 JPEG (148 KB), `usage.cost` = **$0.034**
(1,120 completion tokens). `content` may be empty. Handle: no images in the
reply (show the text/refusal), several images (keep all), PNG or JPEG data
URLs, timeouts (the client already has a 180 s timeout). Record cost through
the existing `ai/usage.py` ledger (feature `"image"`). Do not use
`provider.require_parameters` (image models don't take JSON schemas).

## Model setting

A fourth model role **image** (`image_model` user setting and
`project.toml [ai] image_model`), default **`google/gemini-3.1-flash-lite-image`**
(the cheapest image model; the author prefers cheap models). Settings in both
UIs get an "Image model" row; the model picker for it lists only models
whose `architecture.output_modalities` contains `"image"` (extend
`ai/client.py` catalog parsing; cache like the others). Show the price the
catalog gives, plus the note "about $0.03 per image".

## Storage (`core/inspiration.py`, pure)

`<project>/inspiration/<YYYYMMDD-HHMMSS>-<slug>.<jpg|png>` plus a sidecar
`<same stem>.md`:
```
---
prompt: A dark subway platform at night, flickering fluorescent lights
model: google/gemini-3.1-flash-lite-image
scene: manuscript/02-part-ii/03-the-tunnel.md     # optional
created: 2026-10-01T17:53:00
cost: 0.0336
pinned: true          # shown with that scene
---
Optional notes by the author.
```
Plain author data, not git-ignored, never in `.lorewrite/`. Functions:
`save(project, image_bytes, ext, meta)`, `list(project, scene=None)`,
`update(meta)` (pin/unpin, rename, notes), `delete` → **to the project
Trash** like research notes (`Project.trash_*`; restore puts it back),
scene renames/moves keep the `scene:` link (update it in the same places the
other sidecars are moved — see `core/structure.py`).

## AI (`ai/images.py`)

- `generate(prompt, model, client=None) -> list[(bytes, ext)]` as above.
- `suggest_prompt(scene_context, model)` — **"Describe this scene"**: the
  writing model (or fast model; pick and justify) turns the passage around
  the cursor + the place/character notes into a one-paragraph visual prompt
  (setting, light, mood, era; no text in the image; no named real people).
  The author edits the prompt before generating — two clicks, never automatic.
- Prompt hygiene: append a short style suffix the author can change in
  Settings (default "cinematic, atmospheric, no text, no watermark").
- Mock: extend `gui/mockai.py` with canned functions that return a small
  generated placeholder image (e.g. a PIL- or pure-python PNG with the
  prompt's first words; no network) so `devserver --mock-ai` works; the
  signature test in `tests/test_gui_shell.py` must cover them.

## GUI

- A new **Inspiration** tab in the Assistant panel (next to Assistant /
  Context / Notes), in the design's style:
  - prompt box with **Describe this scene** (fills it from the open scene)
    and **Generate** (shows "about $0.03"); a busy state;
  - the current scene's pinned images large at the top (the "on screen
    while you write" part), the rest as a grid of thumbnails for this scene,
    with a toggle "This scene / All";
  - per image: open large (lightbox), **Pin to this scene** / unpin,
    **Regenerate** (same prompt), edit notes, copy prompt, **Move to Trash**,
    reveal file.
- The pinned image follows the open scene; switching scenes switches it.
- Optional: in focus mode, a small floating pinned image in a corner (toggle);
  skip if it complicates layout.
- Serve image files safely to the webview: add an Api method that returns a
  data URL or a token-checked local URL for files **inside**
  `<project>/inspiration/` only (path traversal tests).

## TUI

Terminals can't show images well. Palette: `Action · Inspiration image…`
(prompt form with "describe this scene"), saves the image and notifies with
the path; `Action · Open inspiration folder` and "open last image" use
`xdg-open` **only when chosen**. List images for the scene in a small modal
(prompt, date, pinned) with open / pin / trash.

## Tests and verification

- Unit: storage round-trip, sidecar parsing, pin per scene, scene rename keeps
  links, trash/restore, catalog filter for image models, `generate` parsing of
  data URLs (JPEG/PNG/multiple/none) with a fake client, cost recording,
  path-traversal protection, mock signatures.
- GUI: headless screenshots of the Inspiration tab with mock images; TUI Pilot.
- **No real image generation in tests or screenshots** (the managing session
  will run one real call when reviewing).
- Docs: SPEC (move from "Future" to implemented), README, AGENTS.md.

Report to `/tmp/inspiration-report.md` with Jev per commit.
