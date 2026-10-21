# Long-project stress test (October 2026)

Chisel's AI features were tried on three long public-domain novels (Crime and Punishment, The Brothers
Karamazov, War and Peace) with planted contradictions, to see whether a summary / memory layer is needed.
The plain-language report is [Chisel_long_project_report.pdf](Chisel_long_project_report.pdf) (29 pages,
seven rounds, about 3.3 USD of cheap-model spend, never more than the 5 USD cap).

## What came out of it

- Chisel sends one scene plus character notes whatever the model window; the 40-entity rule is a cliff.
- Summaries (`.summaries/`, story so far, facts ledger) are shipped, but did not help catch the planted
  contradictions: most of the contradicted facts were in no summary.
- The canon tool now keeps one verified quote per fact and a stable-details prompt: 95% of facts kept (was 2%).
  The check still raises false alarms on untouched chapters.
- Tried and dropped: telling the check that silence is not a contradiction (made false alarms worse).
- Built but not adopted (branch `two-quote`, not in this PR): findings that carry two verified quotes cut false
  alarms from 7.4 to 4.4 of 8 chapters but lowered catches from 1.8 to 1.0 of 6.
- Model and provider behaviour drifts between sessions; compare only runs interleaved in one session.
- Do not claim book-scale continuity checking. Use the free "ceiling check" (is the contradicted fact in the
  context?) before paying for any model run.

Like the other files here, this is a historical record; SPEC.md and AGENTS.md win where they differ.
