import { leftOutReason, tolerantNote } from "./summaries";
import type { CanonProposal } from "./types";

/** A proposed fact the checks left out (python: ai/continuity.py CanonDropped; the reason is core/summaries.py quote_check's). */
export interface CanonLeftOut { entity: string; fact: string; reason: string }

export const canonLeftOutLine = (d: CanonLeftOut): string => `${d.entity}: ${d.fact}. Left out because ${leftOutReason(d.reason)}.`;

/** The disclosure's summary line ("" when nothing was left out). */
export function canonLeftOutTitle(dropped: CanonLeftOut[]): string {
  return dropped.length ? `Left out (${dropped.length}): Chisel checked these against your scene and did not keep them` : "";
}

/** The quote a fact rests on ("" for a proposal without quotes). */
export const quoteOf = (p: CanonProposal, i: number): string => p.quotes?.[i] ?? "";

/** What the facts the author ticked carry to the bridge: only entity and facts (a quote is for reading, not for saving). */
export function pickedFacts(proposals: CanonProposal[], on: Set<string>, key: (e: string, f: string) => string): { entity: string; facts: string[] }[] {
  return proposals
    .map((p) => ({ entity: p.entity, facts: p.facts.filter((f) => on.has(key(p.entity, f))) }))
    .filter((p) => p.facts.length);
}

export { tolerantNote as canonTolerantNote };
