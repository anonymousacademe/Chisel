# Character relationships (2026-10)

Design record for the character-relationships feature. SPEC §14 listed it as
planned item 1; the section below is what was built.

## The data

A note declares its relationships in a `## Relationships` section of its body
(`core/relationships.py`):

```
## Relationships

- [[Rook Tanaka]] — father; estranged
- [[Imogen Sallow]] -- employer
```

- The section is plain Markdown. The author edits it like any other prose;
  the app only rewrites it when the author accepts an AI suggestion
  (`set_section` replaces the first section in place, appends one at the end,
  or removes it when the list is empty).
- One relationship per line: the first `[[link]]` of a list item is the
  target, everything after a separator (`—`, `–`, `--`, `-`, `:`) is the
  label — free text, from this note's point of view ("father", "owes her a
  favour"). Junk lines are skipped, never raised; duplicate targets are
  deduped (case-insensitive).
- **Inverses are derived at read time, never written**: when another note's
  section links here, `rows()` shows that side as `side: "derived"` labelled
  with the other note's words. Nothing is ever added to the other note.
- An unresolved `[[link]]` (Trash, or not created yet) is kept and reported
  `resolved: false` with the raw target.
- Targets resolve by name or alias through `core.entities.resolve`.

## The AI feature

`ai/relationships.py`, shaped exactly like the alias finder:

- `plan_suggestions(entity, entities, budget)` decides what is sent before
  any network call: the note itself (never dropped) plus a roster of the
  other notes ranked by `ai.relevance.rank` (shared mentions). Runs through
  `fit()`/`preflight()`; raises `BudgetError` when even the note does not
  fit; the report goes out as `sent`.
- `suggest_relationships(entity, others, model, client=None)` is the network
  call (structured output, `require_parameters` — same as the alias finder;
  cost recorded under the `relationships` feature). Validates the reply:
  unknown targets, self-references, repeats of what the note already
  declares, empty/absurd labels are dropped.
- `apply_suggestions(entity, accepted, save)` merges the accepted rows
  (declared first, new ones after) via `set_section` and saves with
  `save_entity` (frontmatter round trip holds — the Entity is mutated, never
  reconstructed). **No snapshot is taken**: like the canon apply, it is one
  author-visible file rewrite confirmed item by item, and snapshots are
  scene-keyed.

## The front ends

- GUI bridge (`gui/api.py`): `suggest_relationships(name)` (plan inside the
  lock, network outside; an AI job kind `"relationships"`) and
  `apply_relationships(name, items)`. `get_entity` carries a
  `relationships` rows field (`gui/entities_api.py`).
- GUI: a Relationships section in the note panel (declared first, then
  derived; unresolved marked "no note yet") and a tick-the-rows review
  dialog with the sent report. The open note is flushed before the apply and
  force-reopened after; `noteVersion` is a live state so the panel refetches.
- TUI: `RelationshipReviewScreen` (`tui/relationreview.py`) + the
  `Suggest relationships` palette entry (Entity ·). After an apply the open
  buffer is re-read from disk (`_collection_op` pattern, never `open_file`
  with a stale buffer; the queued `Changed` event of the programmatic load is
  cleared afterwards so the reload is not counted as typing or left dirty).

## Tests

`tests/test_relationships.py` (parse/render/set_section/rows),
`tests/test_ai_relationships.py` (plan/parse/apply, budget window),
`tests/test_gui_ai.py` (bridge rows, suggest with a mocked fake, apply),
`tests/test_tui_relationships.py` (screen flow, guards, buffer re-read).
Mock points: `chisel.tui.app.suggest_relationships`,
`chisel.gui.api.suggest_relationships` (faked in `gui/mockai.py`).
