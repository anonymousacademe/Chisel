// Typing aids for script scenes. The element rules (what "next element" means, how it is spelled) are in
// Python (core.fountain.cycle_element, via Api.script_cycle); this file only decides where a completion
// list applies and which element a line has, from what the editor already knows.
import type { Span } from "./spans";

export interface ScriptNames { characters: string[]; places: string[] }

/** Where a completion applies on a line: after INT./EXT. a place, at the start of a speech block a character. */
export interface CompletionSpot { kind: "place" | "cue"; from: number }

const HEADING_PREFIX = /^(?:INT\.\/EXT|INT\/EXT|INT|EXT|EST|I\/E)[. ]\s*/i;

/**
 * *before* is the line's text up to the cursor; *prevBlank* whether the line above is blank (or there is none).
 * A cue is only offered for text typed in capitals, so ordinary action that starts a paragraph with a name
 * ("Keith walks in") never gets a list popping up over it.
 */
export function completionSpot(before: string, prevBlank: boolean): CompletionSpot | null {
  const heading = HEADING_PREFIX.exec(before);
  if (heading) return { kind: "place", from: heading[0].length };
  if (prevBlank && /^[A-Z][A-Z .'-]*$/.test(before)) return { kind: "cue", from: 0 };
  return null;
}

/** Names as a cue or heading is written (upper case, sorted, no duplicates). */
export function upperNames(names: string[]): string[] {
  return [...new Set(names.map((n) => n.trim().toUpperCase()).filter(Boolean))].sort();
}

/** The Fountain element of the line [from, to], from the script spans Python sent; "action" when it has none. */
export function elementOfLine(spans: Span[], from: number, to: number): string {
  const hit = spans.find((s) => s.kind === "script" && s.element && s.start >= from && s.start <= to);
  return hit?.element ?? "action";
}
