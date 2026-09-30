# Plan: M4 follow-up fixes (branch `m4-ai-writing`)

Same rules as `docs/plan-m4-ai-writing.md` (non-negotiables, test command,
Pilot verification, no network, commits on this branch only, never `main`,
never push). One commit per numbered item (small items 6 may share one).
Keep the suite green after each. Add a regression test for every fix.

## 1. Story-bible update must never lose canon (serious; bug also on main)

Today `ai/continuity.py::propose_canon_updates` does not send the existing
`## Canon (auto)` text, yet `core/continuity.py::apply_canon_update` replaces
the whole section with the proposal — running it on a later scene can erase
facts established earlier. The review (`tui/noteupdates.py`) truncates each
proposal to ~80 chars, so the author can't see the loss.

Fix: **additions only.**
- Prompt sends, per entity, its existing canon (`get_canon(body)`, capped
  1500 chars) and asks only for NEW facts the scene establishes that are not
  already in the canon. Schema: `{updates: [{entity, new_facts: [string],
  evidence: string}]}` (update `CanonUpdate` accordingly; keep app-side
  validation: unknown entities dropped, empty facts dropped, facts deduped
  case-insensitively against existing canon lines).
- `apply_canon_update(entity, new_facts)` appends `- fact` bullet lines to
  the managed section (creating it if missing); it never removes or rewrites
  existing lines. Author text outside the section untouched (existing rule).
- Review screen shows every new fact in full (wrapped, not truncated), grouped
  by entity, each individually toggleable (space) — the author accepts facts,
  not blobs. Existing canon shown dimmed above each group for context.
- Pending AI drafts are still stripped from the scene before sending.
- Tests: a second update never removes a fact from the first; duplicates
  skipped; long facts displayed untruncated; cancel writes nothing.

## 2. No encoded blobs in the prose

`<!--ai replaces="BASE64"-->` puts a long encoded string in the scene. The
author dislikes visual noise (they asked for bracket-free mentions). Replace
with a short id and a sidecar:

- Marker: `<!--ai id="k3f9q2"-->body<!--/ai-->` (id: 6 lowercase base36
  chars, unique within the project) for drafts that replaced something; pure
  insertions keep `<!--ai-->body<!--/ai-->`.
- Originals live in `<project>/.drafts/<scene-filename>.json`
  (`{"k3f9q2": "original text", …}`), written atomically. This is author data,
  NOT cache: it must not be under `.lorewrite/`, and `.gitignore` must not
  exclude it. Delete an entry on accept or reject; delete the file when empty;
  rename/move/delete it together with its scene (see `core/project.py`
  rename/move/delete).
- If an id's original is missing (sidecar deleted/edited), **reject must
  refuse** with a notify ("Original text for this draft is missing — accept
  it or edit by hand") and change nothing. Never delete prose on a failed
  lookup.
- Drop the `replaces=` form entirely (it never shipped).
- Tests: rewrite → reject restores exactly; accept removes marker and sidecar
  entry; missing original → reject refuses, text unchanged; scene rename/move/
  delete carries the sidecar; nothing written under `.lorewrite/`.

## 3. AI draft color must be unmistakable in every theme

In the author's matte-black theme the draft color is red, nearly the same as
unresolved links (`orange` = `#c63d3d`); `magenta` equals `red` there.
- Draft body style: italic + a subtle background tint
  (`lighter_background`/`selection` from the Omarchy colors, else a dim
  default), plus a hue chosen by a new `theme.distinct_color(colors, avoid)`
  that picks, among candidate hues (green, yellow, magenta, bright_cyan, blue,
  cyan, bright_green…), the one farthest in RGB from foreground, the link
  color (`link_color`) and the unresolved color. Fallback when not on Omarchy:
  a fixed distinct style (e.g. italic + `Style(color="green", bgcolor=…)`).
- Test with the matte-black palette (see `tests/test_theme.py`): chosen hue is
  not within a small RGB distance of orange/red/foreground/link color.

## 4. Command palette results pushed off screen (verify)

On `main`, app CSS `Horizontal { height: 1fr; }` matched the palette's input
row and pushed results below the window. Your `Screen > Horizontal` scoping
likely fixed it. Add a Pilot test: open the palette (`ctrl+p`), type a query,
assert the results list region is inside the screen and has ≥ 1 visible row.
Fix further if it fails.

## 5. Pending drafts must not count as mentions

`core/index.py` builds backlink rows from raw scene text, so names inside an
unaccepted draft appear in backlinks. Index scenes from
`drafts.strip_pending(text)` — but keep row numbers pointing at the real file
lines (strip → offsets differ). Simplest correct approach: replace each
pending span with same-length whitespace preserving newlines before scanning,
so offsets/rows are unchanged. Use the same blanking for the alias-finder
text so its line numbers are right (known limitation in your report).

## 6. Small fixes

- **Help from the editor:** `?` types a character while the editor is
  focused, so help is unreachable while writing. Add `f1` → help (verify it
  reaches the app with the editor focused; if Textual already binds `f1`,
  pick another free key and document it). Keep `?` outside the editor.
  Update HELP_TEXT, footer, tour, README.
- **Un-waive:** palette `Action · Restore waived continuity issues (this
  scene)` clears this scene's waivers from `.lorewrite/waivers.json`; notify
  how many. (Waivers stay in `.lorewrite/` — unchanged decision.)
- **Continuity report:** `enter` jumps to the line and closes the report
  (today it stays open over the editor).
- **Launch screen:** the key hint is cut off at 100 columns ("q: q"); make it
  fit or wrap at 80+ columns.
- **Version:** `pyproject.toml` version → `0.2.0` to match `__version__`.

## Done

Full suite green; Pilot screenshots of: a rewrite draft (short marker, new
color, matte-black palette via a monkeypatched `load_omarchy_colors`), the new
story-bible review, the palette with results. Look at them. Update SPEC.md
(§7 M3 note accumulation now additions-only; M4 marker format + `.drafts/`),
README, AGENTS.md. Jev review per chunk as before; report verdicts. Write the
final report to `/tmp/m4-fixes-report.md` and reply with its path.
