# Plan: Script mode (screenplay, TV, stage and audio scripts in Fountain)

Status: phases S0 to S4 are built (2026-10-18); AI features are deliberately later. See "Not built".

## 1. Goal

A third project mode, `script`, for film, TV, stage and audio (radio, podcast) scripts. It is a **variant of
story mode**: the same notes (characters, places, props), `[[links]]`, aliases, relationships, rename-everywhere,
story time, snapshots, comments, collections, continuity tooling and scene structure. What differs is the text of
a scene (Fountain), how it is drawn, counted and exported.

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| File format | Scenes stay `.md`; the body is Fountain | One scene model, so structure, Trash, snapshots, drafts and comments need no change |
| Interchange | Export to `.fountain`; import a `.fountain` | The format other screenwriting tools read; files still live in the project as Markdown |
| Fountain notes `[[text]]` | Written `<!-- text -->` in a scene; converted both ways | `[[Name]]` is a Chisel link; a Fountain note would look like a link to a missing note |
| Scene title | The first `# Title` line, as in story mode | Binder, corkboard and outline work unchanged |
| Forms | One set of elements for film, TV, stage and audio | Stage and audio use forced headings (`.ACT ONE`) and action for sound cues; form-specific layouts are later |
| Page count | Estimated from the layout (55 lines, Courier 12), shown in eighths | One page is about a minute; exact pagination is a layout problem, so it is an estimate |
| Mode switch | Chosen when the project is created (as research mode) | Same rule as research mode |

## 3. What is built

- `core/fountain.py`: parser (`parse`), elements (`blocks`), layout and pagination (`layout`, `paginate`,
  `estimate_pages`), inline emphasis, title page, note conversion, `import_text`, `export_text`.
- `core/fountainio.py`: read a file (UTF-8, BOM or Windows-1252, 5 MB cap) and write parts and scenes into a project.
- Mode plumbing: `MODES`, binder labels (Script, Locations and props), a Fountain starter scene,
  `[project] mode = "script"`.
- Editor (desktop): each line is classified in Python and drawn as scene heading, cue, dialogue,
  parenthetical, transition, centered, lyrics, synopsis, note, boneyard or page break; a monospaced 60-character
  column; reflow is off. The page estimate is in the status bar (`projectPages`, `pagesLabel`).
- Awareness: speaker cues count as mentions of the character (case-insensitive, aliases included) in the editor,
  the scene context and the retrieved-context list; spell check skips headings, cues, transitions and notes.
- Export: `Fountain` and a `Screenplay` PDF layout (`core/export/layouts/screenplay.py`: Courier-metric 12 pt, standard
  positions, title page, page numbers from page 2). A script can export only these two formats.
- Import: *Import a Fountain file* (desktop project menu; terminal palette). Sections become parts, scene headings
  become scenes, a synopsis above a heading names the scene, a leading `FADE IN:` starts the first scene, the title
  page fills author, contact and copyright only where the project has none.
- Terminal app: project creation, the export form, the import command and spell check; the editor does not
  format Fountain (the terminal text area has no per-line styling hook that is safe to use).

## 4. Not built (in order)

1. **AI**: script-aware draft / expand / rewrite prompts that emit valid Fountain; continuity that reads speakers;
   dialogue voice checks per character. These go through the same context budget and review UI as story mode.
2. **Typing aids, remaining part**: an auto-added `(CONT'D)` and `(MORE)`. (Built since: Tab / Shift-Tab cycle a
   line's element through action, scene heading, character, parenthetical, transition, with the rules in
   `fountain.cycle_element` behind `Api.script_cycle`; a completion list offers character names for capitals typed
   at the start of a block and place names after `INT.` / `EXT.`, from the notes the project already has.)
3. **Dual dialogue** drawn side by side (it prints one speaker after the other now) and the pagination rules
   for it.
4. **Form-specific layouts**: stage play (centered cues), audio drama (sound cues and a timing estimate).
5. **Production features**: scene numbers (the `#12#` suffix is read and kept, not generated), revision colours,
   locked pages, FDX export.
6. **Terminal editor formatting.**
7. Reports: per-character line counts and scenes, per-location lists (a plain query over the parse).
