import { isTrimmed, sectionNote, sectionTrimmed, sentSummary, usageLine, fmtTokens } from "../data/sent";
import type { SentReport as Report } from "../data/types";

/** "What was sent": a small disclosure under an AI result. It lists every part of the request with its
 *  estimated size, what was left out or cut short (by name) and the size against the model's window.
 *  Warning style when anything was dropped or shortened: nothing is trimmed without being listed here. */
export function SentReport({ report, open }: { report: Report | null | undefined; open?: boolean }) {
  if (!report) return null;
  const warn = isTrimmed(report);
  const attached = report.attached.filter((a) => a.skipped || a.truncated);
  return (
    <details className={`lw-sent${warn ? " is-warn" : ""}`} open={open}>
      <summary className="lw-sent__summary" title="What was sent to the AI for this answer">
        <span>What was sent</span>
        <span className="lw-sent__line">{sentSummary(report)}</span>
      </summary>
      <div className="lw-sent__body">
        <ul className="lw-sent__list">
          {report.sections.map((s) => {
            const note = sectionNote(s);
            return (
              <li key={s.name} className={sectionTrimmed(s) ? "is-warn" : ""}>
                <span className="lw-sent__name">{s.name}</span>
                <span className="lw-faint"> ~{fmtTokens(s.estTokens)} tokens</span>
                {note && <span className="lw-sent__note"> · {note}</span>}
              </li>
            );
          })}
        </ul>
        {attached.length > 0 && (
          <p className="lw-sent__note">
            {attached.map((a) => (a.skipped ? `${a.title}: not attached (${a.reason ?? "skipped"})` : `${a.title}: shortened`)).join("; ")}
          </p>
        )}
        <p className="lw-faint lw-sent__total">
          {usageLine(report)}, with {fmtTokens(report.reserve)} kept free for the reply. Sizes are estimates.
          {report.overBudget ? " Over the window: nothing was sent." : ""}
        </p>
      </div>
    </details>
  );
}
