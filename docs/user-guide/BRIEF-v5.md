# Brief: User's Guide, Fifth Edition (export + inspiration images)

Update the guide to document `main` now (b478f67). Two features landed since
the Fourth Edition (9fd9374): **M7 export** (`docs/plan-export.md`, SPEC "Export")
and **AI inspiration images** (`docs/plan-inspiration.md`, SPEC "Inspiration
images"). Same house style and rules as the earlier briefs (BRIEF.md, BRIEF-M4.md,
BRIEF-v3.md, BRIEF-v4.md); the code is the source of truth.

- New chapter **"Exporting Your Book"**: formats (PDF Book / Manuscript review /
  Plain proof, DOCX, EPUB, Markdown, LaTeX source), every option, what is and is
  not included (Unplaced, Trash, comments, notes, frontmatter; pending AI drafts
  left out by default with a warning; expand markers removed), where files go
  (`exports/`, never overwritten), the GUI dialog and the TUI form side by side,
  layouts as a template mechanism. Include **sample pages** of each PDF layout
  as figures (render with pdftoppm from a real export of a temp copy of the
  Residual example — no AI needed).
- New chapter **"Inspiration Images"**: the idea (reference pictures, never in
  your prose), Describe this scene, Generate, cost (about $0.03 per image; the
  default image model `google/gemini-3.1-flash-lite-image`, changeable),
  pinned picture per scene, gallery, lightbox, regenerate, notes, Trash,
  storage (`inspiration/` + `.md` sidecars), the TUI actions (xdg-open only on
  request), the image model and image style settings. For the figure of a
  real-looking picture you may use the example image at
  `docs/user-guide/build/sample-inspiration.jpg` (generated for real by the
  managing session from the Capsule 7-19 scene; prompt is in the matching
  `.md`); everything else must use the mock AI as before.
- Update: Settings reference (image model row, image style, export options in
  `project.toml [export]`), key/palette reference (generated table), Appendix A
  (exports/, inspiration/, [export], image_model), Messages, Problem Solving,
  Glossary, Index, Tutorial (export the Residual book; make a picture),
  Summary of Changes. Edition: **Fifth Edition (October 2026)**, `LW00-0001-4`.

Rules: write only in `~/lorewrite/docs/user-guide/`; do not commit; no network or
real AI calls; never a desktop window; temp copies + temp LOREWRITE_STATE_DIR;
stop what you start by PID; delete temp browser profiles; render and look at
every page; `qpdf --check`; Jev on your script changes. Report to
`/tmp/guide-v5-report.md` and reply with the path.
