# Chisel roadmap: research mode and what comes next

Written 2026-10-21, with `main` at the research-mode checklist commit (c44a14d) plus the pull requests merged after it.
This is a plan, not a promise: items move when you test the app and tell us what is wrong. Design detail lives in
`docs/dev/` (research-mode-status.md is the build log, the plan-research-*.md files are the designs, and
research-mode-test-checklist.md is the hands-on test list).

## Where things stand

Built, reviewed and merged for research mode: the project mode chosen at creation (Story, Script, Research); paper kind
(manuscript or proposal) and target journal profiles (Environmental Modelling & Software built in, plus generic manuscript
and proposal); the starter outline; Zotero sources (local API, web API, Better BibTeX file) with a review-then-apply sync;
readable source notes; citations that read as (Name et al., year) in the editor; journal requirements checks; guideline
documents; the outline assistant; AI-suggested requirements from guidelines (each rule must quote the guideline); and
figures, tables and equations with binder groups, insert dialogs, an object card and editor widgets. Python suite:
2044 passed; front end: 420 passed.

Not yet seen in a running window by anyone who wrote it. The look and feel of the citation text, the source notes, the
dialogs and the figure widgets is unverified.

## 1. Do next (in order)

1. **Your hands-on test (about 35 minutes).** Work through `docs/dev/research-mode-test-checklist.md` and tell us what is
   confusing, ugly or wrong. Everything below is ordered assuming this finds a round of fixes; budget one polish wave.
2. **Check the GitHub CI run.** The workflow (`.github/workflows/ci.yml`) runs on Linux, Windows and macOS. We have only run
   the suite on this Windows machine. Look at the Actions tab and fix what fails (symlink tests that are skipped here are
   the likeliest).
3. **Polish wave from your test.** Fix the confusing and broken things from item 1. The editor changes (citation widget,
   source-note hiding, figure and table widgets) are the likeliest to need a second pass.
4. **Export screen for research papers** (Word, LaTeX, PDF). The backend exists and assembles sections, numbered figures,
   tables, equations, citations and a bibliography through pandoc, but no screen calls it. Needs: the screen (format, journal
   style, a Word reference document, the explicit "export anyway" override for unresolved citations), a bundled CSL file for
   the Environmental Modelling & Software citation style (we bundle APA, Chicago and IEEE only), and real runs against
   pandoc 3.9 and a TeX engine. Neither is installed on this machine; decide whether to install them here.
5. **Data-aware review of Results and Discussion.** The idea you described: Chisel understands what each figure and table
   means and checks whether the text fits the data. Steps: a "Reading" for each object (what it shows, confirmed by you); a
   per-object "let the assistant use this" tick, off by default (pictures and data never reach an AI unless ticked); a
   check that flags unsupported claims, mismatched numbers, backwards trends and unmentioned figures; vision for static
   figures only when ticked. Builds on the object cards and the AI patterns used by the outline assistant.

## 2. Decisions we need from you

- **Install pandoc 3.9 and MiKTeX on this machine?** Without them we cannot verify Word equations, numbering or PDF output.
- **A Word template or funder format spec** (a `.docx`), when you want Word export tuned.
- **First proposal funder.** The proposal profile is generic. Which funder's call should we model first (and can you save
  its guide the way you did for the journal)?
- **Next journals.** Profiles are small TOML files restated from a journal's guide. Name the next one or two journals and
  save their guides; we build the profile from the real text.
- **Release.** When this is stable enough, cut 0.6.0 with research mode in it? (CHANGELOG and SPEC already have the
  research-mode entries; installers and the frozen selftest still need a run.)

## 3. Later

- **Summaries for research** (idea from the fiction summaries feature that just landed in `.summaries/`): a short
  summary per section and per source, checked against the text, feeding the outline assistant and the data-aware review.
  A suggest-only "summarise this paper" for source notes from their abstract, notes and highlights; this may fit better
  on the Zotero side.
- **Zotero:** more backends are not needed; consider showing a paper's PDF page from a highlight and Better BibTeX file
  verification (not yet tried).
- **Terminal app parity:** the desktop app has the research screens; the terminal can create and edit a research project
  but has no sync, citation picker, requirements or object screens. Decide how much of that the terminal should get.
- **Profile tooling:** a way to build a profile from a guide inside the app (the requirements suggester is the first piece).
- **Script mode** continues in its own sessions; keep its commits and this work on separate branches or worktrees.

## 4. Known issues and loose ends

- The `html_to_markdown` converter still drops characters inside text it treats as HTML (for example `<p>if a<b and c>d</p>`).
- Sync dialog: the remembered collections are saved from the preview-time ticks, so changing ticks between Preview and Apply
  can leave the saved selection different from what the dialog shows.
- `link_spans` still reads every object note on each span request (only the numbering is cached); cache it if a paper with
  many objects feels slow. The numbering cache has no test.
- `docs/dev/plan-research-mode.md` section 7.2 still says references render as "Figure 2"; the code writes "Fig. 2".
- A few terminal strings may still say "scene" in research projects where no test covers them.
- One terminal git-sync test file fails occasionally under heavy parallel load and passes alone.
- The `npm audit` output lists dependency advisories that predate this work and have not been reviewed.
- Leftover merged worktrees under `.claude/worktrees/` and `%TEMP%\chisel-oc` can be removed.

## 5. How we build (so the next session can pick it up)

- Plan, then build in small packages: Sonnet workers in git worktrees, an Opus reviewer for every branch, fixes back to the
  worker, then the lead merges. Cheap OpenCode agents (DeepSeek flash via OpenRouter) take small, fully specified tasks;
  the lead reviews every diff and runs the tests. Cheap agents never see your Zotero data, keys, guide PDFs or projects, and
  each is launched in a verified working folder with the brief's full path (a wrong folder once exposed folder names).
- Gate on the full build: `npm run build` (which runs `tsc -b`), `npx vitest run`, `npm run lint`, then the whole Python
  suite on a clean checkout. `npx tsc --noEmit -p .` alone checks nothing here.
- New worktrees must fast-forward to the latest pushed commit first.
- Commit specific files, never `git add -A`; other sessions edit the same tree.
- Plain files, AI suggests and never edits, and nothing from guidelines, sources, pictures or data reaches an AI unless you
  choose it. Reviewers check data-loss paths first.
