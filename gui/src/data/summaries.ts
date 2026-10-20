import type { SentReport } from "./types";

/** Shapes of the summaries bridge (python: gui/summaries_api.py) and the wording the screens use.
 *  Nothing here decides anything about a summary: Python verifies, counts and saves; this only says it in plain words. */

export type SummaryStatus = "missing" | "fresh" | "stale" | "locked";
export type ThinkingSetting = "default" | "low" | "off";

export interface SummaryFact { text: string; quote: string }
export interface SummaryCharacter { name: string; state: string }
/** What a scene summary holds (what `summary_save` takes as its body). */
export interface SummaryBody { summary: string; characters: SummaryCharacter[]; facts: SummaryFact[]; threads: string[] }
export interface PartBody { summary: string; characters: SummaryCharacter[]; threads: string[] }
/** Something verification removed from a proposal. */
export interface LeftOut { kind: "fact" | "character"; text: string; reason: string }

export interface StoredSummary {
  id: string; status: SummaryStatus; summary: SummaryBody | PartBody | null;
  locked: boolean; authorEdited: boolean; changedSince: boolean;
  model?: string; created?: string; cost?: number;
}

export interface SceneProposal {
  id: string; model: string; replacing: boolean; proposal: SummaryBody; dropped: LeftOut[];
  /** Facts kept although the quote differs slightly from the scene's own text. */
  tolerant: number; trimmed: boolean; sourceHash: string; cost: number | null; sent: SentReport;
}
export interface PartProposal {
  id: string; model: string; replacing: boolean; proposal: PartBody; missing: string[]; trimmed: boolean; cost: number | null; sent: SentReport;
}

export interface StatusRow { id: string; title: string; status: SummaryStatus; words: number; part: string | null; changedSince: boolean; facts: number }
export interface PartStatusRow { id: string; title: string; status: SummaryStatus; scenes: number; summarised: number; words: number }
export interface StatusInfo {
  scenes: StatusRow[]; parts: PartStatusRow[];
  totals: { scenes: number; counts: Record<SummaryStatus, number>; percent: number };
}

export interface Estimate {
  calls: number; inputTokens: number; outputTokens: { low: number; high: number };
  model: string; local: boolean; reasoningModel: boolean | null; reasoning: ThinkingSetting;
  price: { promptPerM: number; completionPerM: number } | null;
  cost: { low: number; high: number } | null; costText: string; skipped: string[]; notes: string[];
}

export interface ScaleHint {
  level: "none" | "notice" | "strong"; message: string; dismissed: boolean;
  /** A quiet statement of what the AI still does not see once summaries cover the book (null: the notice speaks, or nothing to say). */
  after: string | null; dismissedLevel: "" | "notice" | "strong"; model: string;
  numbers: { words: number; scenes: number; entities: number; window: number; windowWords: number; ratio: number; coveragePercent: number; summarised: number; missing: number; stale: number };
}

/** The two caps the bridge enforces on saving (python: core/summaries.py SUMMARY_WORDS / PART_SUMMARY_WORDS). */
export const SCENE_WORDS_CAP = 90;
export const PART_WORDS_CAP = 150;

/** Chip text for a status: None / Fresh / Out of date / Locked. */
export const STATUS_LABEL: Record<SummaryStatus, string> = { missing: "None", fresh: "Fresh", stale: "Out of date", locked: "Locked" };
export const statusLabel = (s: SummaryStatus): string => STATUS_LABEL[s] ?? s;

/** The plain sentence under a card for a status ("" when there is nothing to add). */
export function statusNote(s: SummaryStatus, changedSince = false): string {
  if (s === "stale") return "The scene changed after this summary was written.";
  if (s === "locked") return changedSince ? "Locked. The scene changed after this summary was written; it is kept as you left it." : "Locked: Chisel never rewrites it.";
  if (s === "missing") return "No summary yet.";
  return "";
}

export const wordCount = (text: string): number => text.split(/\s+/).filter(Boolean).length;

/** "47 of 90 words", or "104 of 90 words: 14 over" when the text is longer than the cap. */
export function wordsLine(text: string, cap: number): { text: string; over: boolean } {
  const n = wordCount(text);
  return n > cap ? { text: `${n} of ${cap} words: ${n - cap} over`, over: true } : { text: `${n} of ${cap} words`, over: false };
}

/** "31 of 41 scenes have a summary; 4 are out of date" (the part after the semicolon only when something is). */
export function coverageLine(t: StatusInfo["totals"], unit = "scene"): string {
  const have = t.scenes - t.counts.missing;
  const plural = t.scenes === 1 ? unit : `${unit}s`;
  const stale = t.counts.stale ? `; ${t.counts.stale} ${t.counts.stale === 1 ? "is" : "are"} out of date` : "";
  return `${have} of ${t.scenes} ${plural} ${have === 1 ? "has" : "have"} a summary${stale}`;
}

/** The plain reason a fact or a name was left out (python: core/summaries.py quote_check / name_found). */
export function leftOutReason(reason: string): string {
  const r = reason.trim();
  if (r === "its quote is not in the scene") return "the passage it quoted is not in your scene";
  if (r === "it has no quote") return "it came without a quote from your scene";
  if (r.startsWith("a piece of its quote")) return "one of the pieces it quoted was too short to prove anything";
  if (r === "the pieces of its quote are not in the scene in that order") return "the pieces it quoted are not in your scene in that order";
  if (r.includes("characters apart in the scene")) return "the pieces it quoted are far apart in your scene";
  if (r === "the name does not occur in the scene") return "the name does not appear in your scene";
  return r;
}

export const leftOutLine = (d: LeftOut): string => `${d.kind === "character" ? "Character" : "Fact"}: ${d.text}. Left out because ${leftOutReason(d.reason)}.`;

/** One sentence about the facts that passed only the looser quote check ("" for none). */
export function tolerantNote(n: number): string {
  if (n <= 0) return "";
  return `${n} ${n === 1 ? "fact was" : "facts were"} kept although its quote is not letter for letter your text (quote marks, dashes, capitals, or two passages joined with “…”). Check ${n === 1 ? "it" : "them"} against the scene.`;
}

export const TRIMMED_NOTE = "The summary was longer than the limit, so Chisel cut it after the last whole sentence that fits. Check that nothing important was lost.";

/** "$0.0031", "less than $0.0001", "free" for zero. */
export function money(v: number): string {
  if (v === 0) return "free";
  if (v < 0.0001) return "less than $0.0001";
  return `$${v < 0.1 ? v.toFixed(4) : v.toFixed(2)}`;
}
export const costLine = (cost: number | null | undefined): string => (cost == null ? "" : `cost ${money(cost)}`);

const tokenGloss = (n: number) => `about ${n.toLocaleString("en-US")} tokens (small pieces of text, roughly four letters each)`;

/** What the estimate dialog says before anything is sent. */
export function estimateSentence(e: Estimate, unit = "scene"): string {
  const plural = e.calls === 1 ? unit : `${unit}s`;
  if (e.calls === 0) return `Nothing to write: every ${unit} here already has a summary${e.skipped.length ? " or one you locked or edited" : ""}.`;
  const out = e.outputTokens.low === e.outputTokens.high ? `${e.outputTokens.low}` : `${e.outputTokens.low.toLocaleString("en-US")} to ${e.outputTokens.high.toLocaleString("en-US")}`;
  const send = `This will send ${e.calls} ${plural} to ${e.model}, ${tokenGloss(e.inputTokens)} in all, and the AI will write about ${out} tokens back.`;
  if (e.local) return `${send} The model runs on your own computer: it costs nothing.`;
  const price = e.cost ? `The price should be about ${money(e.cost.low)} to ${money(e.cost.high)}.` : "The price is unknown: Chisel has not read this model’s price list yet.";
  return `${send} ${price}`;
}

/** A plain sentence about a model that thinks before it answers, and the setting that controls it ("" when it does not matter). */
export function thinkingNote(e: Estimate): string {
  if (e.local || e.reasoningModel === false) return "";
  const setting = { default: "the model’s own choice", low: "low", off: "off" }[e.reasoning];
  if (e.reasoningModel === null) return `Chisel does not know whether this model thinks before it answers. The thinking setting is ${setting}.`;
  if (e.reasoning === "off") return "This model can think before it answers; the thinking setting is off, so it will answer straight away (cheaper and faster, with shorter summaries).";
  return `This model thinks before it answers, which makes every call slower and dearer than the summary itself. The thinking setting is ${setting}; “off” avoids it, with shorter summaries.`;
}

export interface Pending {
  kind: "scene" | "part";
  id: string;
  title: string;
  result: SceneProposal | PartProposal;
  /** Where Back and the end of the review lead: the card or the Summaries panel. */
  from: "card" | "panel";
}

/** True when a proposal can be accepted in one batch step: nothing was left out and nothing was cut. */
export function cleanProposal(p: Pending): boolean {
  if (p.kind !== "scene") return false;
  const r = p.result as SceneProposal;
  return r.dropped.length === 0 && !r.trimmed;
}

/** The sentence on the "Accept all that had nothing left out" button's confirmation. */
export function acceptAllSentence(pending: Pending[]): string {
  const clean = pending.filter(cleanProposal).length;
  const rest = pending.length - clean;
  if (clean === 0) return "None of these proposals is free of left-out facts, so none can be accepted in one step. Review them one by one.";
  const tail = rest ? ` The other ${rest} ${rest === 1 ? "has" : "have"} something left out or shortened; ${rest === 1 ? "it stays" : "they stay"} in the list for you to read.` : "";
  return `Save ${clean} ${clean === 1 ? "summary" : "summaries"} exactly as proposed: ${clean === 1 ? "it" : "they"} had no fact left out and nothing cut.${tail} Every quote is checked again against your text as it is saved.`;
}

/** The progress line while the missing summaries are written one by one. */
export function progressLine(done: number, total: number, title: string): string {
  return `Writing summary ${Math.min(done + 1, total)} of ${total}: ${title}`;
}

/** The button (and the estimate's title) that writes what is missing or out of date. */
export function batchLabel(missing: number, stale: number): string {
  if (missing && stale) return "Write the missing and out of date summaries";
  if (stale) return "Write the out of date summaries again";
  return "Write the missing summaries";
}

/** The short note after a scene's word count in the Summaries panel ("" when there is nothing to say). */
export function rowNote(s: { status: SummaryStatus; changedSince: boolean }, waiting = false): string {
  const parts = [];
  if (waiting) parts.push("proposal waiting");
  if (s.status === "stale") parts.push("scene changed since");
  else if (s.status === "locked" && s.changedSince) parts.push("scene changed since");
  return parts.join(" · ");
}

/** "Review 12 proposals". */
export const reviewLabel = (n: number): string => `Review ${n} ${n === 1 ? "proposal" : "proposals"}`;

/** Whether the growth notice should show: a level other than none, and not closed for this project. */
export const showNotice = (h: ScaleHint | null): h is ScaleHint => !!h && h.level !== "none" && !!h.message && !h.dismissed;

/** The muted line at the top of the Summaries panel: what the AI still does not see (null when there is none). Never a banner. */
export const afterLine = (h: ScaleHint | null): string | null => (h && h.after && h.after.trim() ? h.after.trim() : null);

/** The word the assistant header chip uses when the story so far is part of a request ("Story so far"), or null. */
export function storySoFarChip(sent: SentReport | null | undefined): string | null {
  const s = sent?.sections.find((x) => x.name === "Story so far");
  return s && !s.omitted ? "Story so far included" : null;
}
