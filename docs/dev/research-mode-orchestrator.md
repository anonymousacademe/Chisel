# Research mode: orchestrator brief

For the **lead Claude Code agent**, running inside a herdr pane, that builds the `research-mode` branch by
delegating work packages to worker agents. Read this file first, then the three design files:

- [plan-research-mode.md](plan-research-mode.md): the design (draft 3).
- [research-mode-contracts.md](research-mode-contracts.md): the frozen interfaces (P0 output).
- [plan-research-mode-work-packages.md](plan-research-mode-work-packages.md): packages, waves, merge order,
  acceptance criteria, usage rules.

Also read `AGENTS.md` (operational rules for the codebase). Hand workers only the excerpts their package
needs; do not paste the whole file into every worker.

## Kickoff (what the user types in the lead pane)

> Read docs/dev/research-mode-orchestrator.md and follow it. Start with the pre-flight, then Wave 0. Stop at
> the end of each wave and report before starting the next.

## Pre-flight (lead does this, once)

1. Confirm you are inside herdr: `test "$HERDR_ENV" = 1`. If not, say so and stop.
2. Run `herdr --help`, then `herdr agent`, `herdr pane`, `herdr worktree` (print the group, never a bare
   `herdr`), to learn the installed syntax. The installed binary is the authority, not this file.
3. Confirm the repo state: branch `research-mode`, clean tree, `git log` shows the draft 3 plan commit.
4. Run the baseline test suite once and record the result:
   `.venv\Scripts\python.exe -m pytest tests -q -n 4 --ignore=tests/test_tui.py`. **Known pre-existing
   failure on Windows:** `tests/test_hardening.py::test_scene_path_and_trash_names_are_capped` (path length).
   A package is judged on not adding failures beyond that one.
5. Report the baseline to the user before spawning anything.

## Operating rules

- **Branches and worktrees.** One worktree and branch per package, created off `research-mode`:
  `git worktree add ..\Chisel-wt\<pkg> -b rm/<pkg> research-mode` (or `herdr worktree`). Workers only touch
  files their package owns (the "Owns" column). You are the only one who merges, in the documented merge
  order, running the full suite at each merge. Never push to any remote. Never touch `main`.
- **One owner per shared file** (see "Avoiding merge conflicts" in the work-package file). SPEC.md,
  CHANGELOG.md, fixture regeneration are touched only by you or P10.
- **Contracts are frozen.** A worker that needs a contract change stops and reports. You decide, edit the
  contract file in one commit on `research-mode`, and tell affected workers.
- **Approval dialogs belong to the user.** If a worker shows `blocked` (a permission or question dialog), do
  not answer it. Read it with `herdr agent read`, summarise it to the user, and wait. Do not change
  permission settings, hooks or config for any agent.
- **No installs or system changes** by workers (no global pip/npm installs, no PATH or registry edits). A
  package that needs a new dependency reports it; the user decides.
- **No network in tests**, no real keyring, no real Zotero. Zotero tests use scrubbed recorded fixtures.
  Any script-running test uses a temp project and a trivial script.
- **Never run the app or inject mouse or keyboard input** and never capture the screen. The user is at the
  machine. UI behaviour is verified by tests; the user does hands-on checks.
- **Windows.** This is a Windows machine; use the project's `.venv\Scripts\python.exe`. Keep tests
  platform-safe per AGENTS.md.

## Running a wave

For each package in the wave:

1. Create its worktree and branch.
2. Open a sibling pane (`herdr pane split --current --direction right --cwd <worktree> --no-focus`) and start
   a worker: `herdr agent start <pkg> --kind claude --pane <pane-id>`, using the model tier in the package
   table (Opus only where listed).
3. Send the worker its brief with `herdr agent prompt <pkg> "<brief>" --wait --timeout <ms>`. Use the
   template below. Keep it short; point at files rather than pasting them.
4. When it settles, read its final report (`herdr agent read`), run the package's own tests in its worktree
   yourself, and check the stop conditions.
5. Merge in the documented order, run the full suite, then close the pane (`herdr pane close`).

Run a wave's independent packages in parallel; do not start a wave until the previous one is merged and green.

### Worker brief template

```
You are implementing work package <Pn: name> of Chisel's research mode, in this git worktree on branch
rm/<pkg>. Read, in this order: docs/dev/research-mode-contracts.md (the frozen interfaces you must
implement or consume), the <Pn> row of docs/dev/plan-research-mode-work-packages.md, and these sections of
docs/dev/plan-research-mode.md: <sections>. Read only these AGENTS.md paragraphs: <paragraphs>.

Own only: <files>. Do not edit any other file. Do not change a contract; if you need one changed, stop
and report. Add the tests listed for your package and the acceptance criteria. Run only your own tests plus
the linter until done: .venv\Scripts\python.exe -m pytest tests/<your files> -q -x.

Do not install anything, push, run the app, touch the network or the real keyring, or answer a permission
dialog. STOP and report instead of continuing if: the same test fails after 3 fix attempts; you need a file
you do not own; a VERIFY item turns out false; you pass ~40 tool calls or ~60% of your context without green
tests. A report states: what you did, files changed, tests added and their results, anything not done, and
for a stop, what you tried, the last 30 lines of the failure, and a one-paragraph proposal.
Commit your work to your branch when your tests pass; do not merge.
```

## Usage control (lead's responsibilities)

- Prefer Sonnet for standard packages; Opus only for P0, P5 and the three listed reviews; Haiku for P6, P10.
- One fresh worker per package; continue a worker only for its own fix rounds.
- Run cheap checks before expensive ones: baseline tests, then each package's own tests, then the full suite
  only at merge.
- Reviews: start a fresh Opus agent given only the diff, the contract and the acceptance criteria (P1 AI
  exclusion, P3 apply, P4b trust and execution path).
- After each wave, report to the user: packages done, tests, anything blocked, a rough sense of usage spent,
  and the next wave. Then wait for the user.

## Items that need the user (do not guess)

- Zotero version, and the cheap checks in plan section 12 (needs the user's API key and real library), before
  P2's live-fixture work. P2 can build against the Better BibTeX file backend and recorded fixtures first.
- A funder Word template or format spec, before P5's template work beyond the starter reference document.
- Which Python the figure scripts use (P4b settings), and table features that matter.
- Any contract change, new dependency, or decision marked "decision needed" in the plan.

## Done means

Each package's tests green, fiction tests and fiction exports unchanged, acceptance criteria met, merged in
order with the full suite passing (apart from the one known Windows path-length failure), and a short final
report to the user per wave.
