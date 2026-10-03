import type { SentReport, SentSection } from "./types";

/** Display helpers for the "what was sent" report (python: ai/budget.py). Sizes are estimates. */

/** 950 -> "950", 3200 -> "3.2k", 200000 -> "200k", 1000000 -> "1M". */
export function fmtTokens(n: number): string {
  if (n < 1000) return String(Math.max(0, Math.round(n)));
  const m = n >= 1_000_000;
  return `${(n / (m ? 1_000_000 : 1000)).toFixed(1).replace(/\.0$/, "")}${m ? "M" : "k"}`;
}

/** Names left out of the whole request. */
export const droppedOf = (r: SentReport): string[] => r.sections.flatMap((s) => s.itemsDropped);
/** Names sent cut short. */
export const truncatedOf = (r: SentReport): string[] => r.sections.flatMap((s) => s.truncated);

/** True when something was left out or cut short, or the request is over the window. */
export const isTrimmed = (r: SentReport): boolean => r.overBudget || droppedOf(r).length > 0 || truncatedOf(r).length > 0;

/** "~3.2k tokens of 200k". */
export const usageLine = (r: SentReport): string => `~${fmtTokens(r.estTokens)} tokens of ${fmtTokens(r.window)}`;

/** One line for a toast or a status bar: "sent ~3.2k tokens of 200k; 2 dropped; 1 trimmed". */
export function sentSummary(r: SentReport): string {
  const out = [`sent ${usageLine(r)}`];
  const dropped = droppedOf(r).length, cut = truncatedOf(r).length;
  if (dropped) out.push(`${dropped} dropped`);
  if (cut) out.push(`${cut} trimmed`);
  if (r.overBudget) out.push("over the window");
  return out.join("; ");
}

/** A list of names for display: the first few, then "and N more" (the full list stays in the report). */
export function nameList(names: string[], max = 8): string {
  if (names.length <= max) return names.join(", ");
  return `${names.slice(0, max).join(", ")} and ${names.length - max} more`;
}

/** What a section says about itself, or "" for one that is simply sent whole:
 *  "3 of 40 notes sent; dropped: A, B; shortened: C". */
export function sectionNote(s: SentSection): string {
  if (s.omitted && s.itemsTotal <= 1 && s.itemsDropped.length <= 1) return "left out";
  const parts: string[] = [];
  if (s.itemsTotal > 1 || s.itemsDropped.length) parts.push(`${s.itemsSent} of ${s.itemsTotal} sent`);
  if (s.itemsDropped.length) parts.push(`dropped: ${nameList(s.itemsDropped)}`);
  if (s.truncated.length) parts.push(`shortened: ${nameList(s.truncated)}`);
  return parts.join("; ");
}

/** Whether a section needs the warning style. */
export const sectionTrimmed = (s: SentSection): boolean => s.omitted || s.itemsDropped.length > 0 || s.truncated.length > 0;
