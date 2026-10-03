# Example projects

## `residual/` — a cyberpunk crime scene

Four scenes and eight entity notes (characters, places, a faction, an object)
for trying every Chisel feature. Rook Tanaka, a data-forensics jockey, and
Wren, the AI construct in his jack, investigate the death of Kessler-Voss ice
architect Imogen Sallow in a capsule hotel.

Open a **copy**, so the original stays pristine (the app autosaves and AI
features write notes, `style.md` and `.drafts/`):

```bash
cp -r examples/residual /tmp/residual
.venv/bin/chisel --project /tmp/residual
```

Things to try:

- **Plain-name mentions** — names and aliases are colored with no brackets;
  put the cursor on one to see its note and backlinks.
- **Make a note** — Lin, the bartender, has none yet: select "Lin" in scene 1
  and press `ctrl+j`.
- **Explicit links** — scene 4 has a faded-bracket `[[Imogen Sallow]]` and an
  unresolved (orange) `[[Tetsuo Brandt]]`.
- **Continuity check** (palette) — two contradictions are planted on purpose:
  Sallow's eyes are grey in her canon but green in scene 2, and Kuroda's
  chrome prosthetic is his left arm in canon but his right hand in scene 3.
- **Story time** (optional) — the scenes carry no `when:` and the characters no `born:`,
  so everything uses reading order. Add `when: 2187` to a scene's details (and `born:` to
  a character) to see story time and ages.
- **What was sent** — after any AI action in the desktop app, open the *What was sent*
  line to see exactly what the request carried.
- **Pictures** — open a scene, a character or a place, then add a picture in the
  Inspiration tab (upload a JPG, PNG or WebP, or generate one); it is linked to that item.
  Pictures are never sent to an AI.
- **Update story bible**, **Find aliases** (`ctrl+l`), **learn style guide**
  and **AI write** (`ctrl+g`) — need an OpenRouter key (Settings).
