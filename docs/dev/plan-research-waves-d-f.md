# Plan: research mode waves D to F (2026-10-20)

Author's request: outline assistant, journal guidelines (AI-assisted requirements), figure and table screens, "etc.".
Decisions already taken are in plan-research-usability-2.md ("Decisions taken"): pictures and data are excluded from
AI unless the author ticks them; outline from a scope paragraph plus guidelines, else a standard structure.

## Who does what
- Workflow workers (Sonnet, one git worktree each) build features; an Opus reviewer checks every branch before merge;
  fixes go back to the worker; the lead merges, runs the full suite on a clean checkout and pushes.
- Cheap OpenCode agents (DeepSeek flash through OpenRouter, started in herdr tabs, each in its own git worktree of the
  repository) do small, fully specified tasks: documentation drafts, wording sweeps, extra tests. The lead gives each a
  written brief, runs the tests itself (OpenCode refuses commands outside its folder), reads the whole diff, and merges
  or rejects. They never see the author's Zotero data, keys, guide PDF or project folders.

## Wave D: outline assistant
- Scope statement: `scope.md` in the project root (plain file; never sent anywhere except an outline call).
- `ai/outline.py`: `suggest_outline(...)`: plan with budget Sections (scope, kind and journal requirements, guideline
  text capped, current outline with purposes and word counts), network call, app-side validation of the reply. Items:
  add / rename / move / keep / advice. Nothing is ever deleted. Reported in "What was sent".
- Standard structures when no guidelines: from the journal profile or the generic manuscript/proposal profile.
- Apply: ticked items only, snapshot of affected sections first; adds create new sections (with the purpose as detail),
  renames and moves use the existing structure functions; remap returned to the client.
- Screen: "Outline assistant..." (Outline view and project menu, research only): scope box, Suggest outline (AI job with
  Stop), review list with before/after, Apply. Offline fallback: "Use the standard structure".

## Wave E: guidelines to requirements
- `ai/requirements.py`: `suggest_requirements(...)`: reads the chosen guideline documents (capped, reported) and proposes
  rows in the same schema as the profile requirements (only the check kinds Chisel implements, plus advice).
- The author edits and confirms; saved to `requirements.toml` in the project; `requirements.evaluate` runs them after the
  journal profile's own rows. A manual "Add a requirement" form uses the same schema.
- Screen: a "Suggest from guidelines" button in the Guidelines dialog and an editable list in the Requirements dialog.

## Wave F: figure, table and equation screens
- F0 (Python): spans for `![[fig:x]]` placements and `[[fig:x]]` references with the number as display text ("Fig. 2"),
  numbering from core.objects; bridge already exists (research_objects_api).
- F1 (React): binder group Figures / Tables / Equations; insert figure (file picker, drag-drop), table grid editor,
  equation editor; object cards (caption, source, status).
- F2 (React, CodeMirror): block widgets for figures and tables, KaTeX equations, reference widgets. Highest risk: Opus
  reviews the StateField change closely; widget DOM must not be rebuilt while typing.
- AI use of figures and tables: per-object "let the assistant use this" tick, off by default (later wave).

## Housekeeping (cheap agents, in parallel with wave D)
SPEC.md research section and CHANGELOG lines; a research-mode section for the user guide; remaining "scene" labels in
the terminal app (footer shortcuts, AI status label); extra edge-case tests for requirements.py and guidelines.py.

## Gates
Every wave: Opus review, full suite on a clean checkout, push, then a short report with a manual test list. Anything
that touches the author's files gets a data-loss review. Stop and report instead of looping (3 failed fixes).
