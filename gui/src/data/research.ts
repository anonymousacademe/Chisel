import type { SentReport } from "./types";

// Research-mode shapes that cross the bridge (docs/dev/research-mode-contracts.md). Placeholders registered
// by P0: P7 fills in the JSON each bridge method returns, and P8a / P8b read only these types.

export type ObjectKind = "fig" | "tbl" | "eq";
export type ObjectStatus = "current" | "stale" | "failed" | "missing";

/** A figure, table or equation, as the editor widgets and the binder see it. */
export interface RefObject {
  kind: ObjectKind;
  label: string;
  path: string;
  caption: string;
  source: "static" | "script" | "data";
  file: string | null;
  width: number | null;
  alt: string;
  status: ObjectStatus;
}

/** "fig:flow-model" -> its number in reading order. */
export type Numbering = Record<string, { seq: number; display: string }>;

/** A research-check finding. */
export interface ResearchFlag {
  kind: string;
  path: string;
  row: number | null;
  message: string;
  blocking: boolean;
}

// -- Zotero (settings, sync review, Sources list) ----------------------------------------------------------

/** One Zotero collection by its full path ("AI and Computing / WRRI"); items is null when Zotero did not say. */
export interface ZoteroCollection { key: string; path: string; items: number | null; parent?: string | null }

/** The Zotero settings. The web API key never comes back over the bridge: only whether one is saved. */
export interface ZoteroSettings { userId: string; webBase: string; local: boolean; localBase: string; file: string; keySet: boolean }

export interface ZoteroBackendStatus { backend: string; ok: boolean; message: string }
export interface ZoteroStatus { backends: ZoteroBackendStatus[]; keySet: boolean }

export type SyncAction = "new" | "changed" | "missing" | "key-mismatch";
export interface SyncRow { id: string; key: string; action: SyncAction; summary: string; blocked: string | boolean }
export interface SyncPlan { rows: SyncRow[]; report: string[]; backend: string; token: string }
export interface SyncScope { collection?: string; collections?: string[]; includeSubcollections?: boolean; tag?: string }
export interface SyncApplied { changed: string[]; skipped: { id: string; reason: string }[]; recorded: boolean }

export interface SourceRow { id: string; name: string; title: string; key: string; status: string }

export const SYNC_ACTION_LABEL: Record<SyncAction, string> = {
  new: "New", changed: "Changed", missing: "Missing in Zotero", "key-mismatch": "Key mismatch",
};
/** blocked is the reason (a non-empty string) or a bare true; "" / false mean not blocked. */
export const blockedReason = (r: SyncRow): string => (r.blocked === true ? "Cannot be applied" : r.blocked || "");
/** Case-insensitive substring filter over collection paths. */
export const filterCollections = (all: ZoteroCollection[], q: string) => {
  const s = q.trim().toLowerCase();
  return s ? all.filter((c) => c.path.toLowerCase().includes(s)) : all;
};

/** Nesting depth of a collection (0 = top level), from the parent keys Python sends. */
export const collectionDepth = (c: ZoteroCollection, all: ZoteroCollection[]): number => {
  const by = new Map(all.map((x) => [x.key, x]));
  let d = 0; let cur = c.parent ?? null;
  while (cur && by.has(cur) && d < 20) { d++; cur = by.get(cur)!.parent ?? null; }
  return d;
};
/** The last part of a collection path ("A / B" -> "B"). */
export const collectionName = (c: ZoteroCollection): string => c.path.split(" / ").pop() || c.path;
/** Case-insensitive search over the rows of a sync preview (summary, key, action). */
export const filterSyncRows = (rows: SyncRow[], q: string): SyncRow[] => {
  const s = q.trim().toLowerCase();
  return s ? rows.filter((r) => `${r.summary} ${r.key} ${r.action}`.toLowerCase().includes(s)) : rows;
};

// -- Citing sources (Cite dialog, [[@ completion, the source card, citation hover) --------------------------

/** One search result of search_sources. */
export interface SourceHit { key: string; display: string; title: string; authors: string; year: string | number; venue: string }

/** source_card: what the Notes panel shows for an open source note. */
export interface SourceCardInfo {
  key: string; citeAs: string; display: string; title: string; authors: string; year: string | number; venue: string;
  doi: string; url: string; zoteroKey: string; noteCount: number; highlightCount: number;
}

/** The text a citation is inserted as: [[@key]] or [[@key, p. 12]]. A bare number is a page; "ch. 3" or "pp. 4-5" is kept. */
export function citeText(key: string, locator = ""): string {
  const loc = locator.trim();
  if (!loc) return `[[@${key}]]`;
  return `[[@${key}, ${/^\d/.test(loc) ? "p. " : ""}${loc}]]`;
}

/** What to type for a chosen completion: the key, the closing brackets unless they are already there, and the cursor offset. */
export function citeCompletion(after: string, key: string): { insert: string; cursor: number } {
  const insert = after.startsWith("]]") ? key : `${key}]]`;
  return { insert, cursor: key.length + 2 };
}

/** The hover card for a citation span (Python decided resolved / unresolved and the label). */
export function citationCard(span: { status?: string; keys?: string[]; label?: string; title?: string }) {
  if (span.status === "resolved") {
    return { title: span.label || (span.keys ?? []).join("; "), kind: "source", body: span.title || "This source has no title." };
  }
  return {
    title: (span.keys ?? []).join("; "), kind: "no source", missing: true,
    body: "No source with this key. Sync from Zotero, or check the key.",
  };
}

/** Plain-words fallback when the paper's Zotero collections cannot be read. */
export const COLLECTIONS_FALLBACK = "Zotero's collections could not be read. Is Zotero running?";

// -- Journal profiles, requirements and guidelines (project settings, Journal requirements, Guidelines) ----

export type ResearchKind = "manuscript" | "proposal";

export interface JournalProfile { id: string; name: string; publisher: string; kind: ResearchKind; source: string; readOn: string }

/** research_get_settings / research_set_settings. journal "" means no target journal. */
export interface ResearchSettings {
  kind: ResearchKind; journal: string; journalName: string; citationStyle: string; source: string; readOn: string;
}

export type RequirementStatus = "ok" | "warn" | "info" | "na" | "advice";
export interface RequirementItem { id: string; title: string; status: RequirementStatus; message: string }
export interface RequirementGroup { title: string; items: RequirementItem[] }
export interface RequirementsReport {
  journal: string; name: string; source: string; readOn: string;
  summary: { ok: number; warn: number; info: number; advice: number };
  groups: RequirementGroup[];
}

export type GuidelineType = "pdf" | "docx" | "md" | "txt" | "note";
export interface GuidelineFile { name: string; type: GuidelineType; size: number; chars: number; extracted: boolean; message: string }
export interface GuidelineText { name: string; text: string; truncated: boolean; chars: number }

/** Profiles of one kind, in the order Python sent them (Environmental Modelling & Software first). */
export const profilesOf = (all: JournalProfile[], kind: ResearchKind) => all.filter((p) => p.kind === kind);
/** Real journals of a kind: the generic "manuscript" / "proposal" profiles (id equal to the kind, no publisher) are the "no journal" case. */
export const journalsOf = (all: JournalProfile[], kind: ResearchKind) =>
  profilesOf(all, kind).filter((p) => p.id !== p.kind && p.publisher !== "");
/** The journal a project of this kind starts with: the first real journal of a manuscript; a proposal (or no list) starts with none. */
export const defaultJournal = (all: JournalProfile[], kind: ResearchKind) =>
  kind === "manuscript" ? journalsOf(all, kind)[0]?.id ?? "" : "";

/** Words shown for each requirement status (text, not colour alone). */
export const REQUIREMENT_LABEL: Record<RequirementStatus, string> = {
  ok: "Ok", warn: "Needs attention", info: "Note", na: "Not applicable", advice: "Reminder",
};

/** "12 ok, 3 need attention, 14 reminders". */
export function requirementSummary(s: RequirementsReport["summary"]): string {
  const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  return [`${s.ok} ok`, n(s.warn, "needs attention", "need attention"), n(s.advice, "reminder", "reminders")].join(", ");
}

/** A readable size: "1.2 MB". */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// -- Outline assistant (wave D). Python decides what is proposed and applies it; this is only the shape. ----

export type OutlineAction = "add" | "rename" | "move" | "keep" | "advice";
/** One proposed change. For add: `title` is the new section; for rename / move / keep: the existing section's current title. */
export interface OutlineItem {
  id: string; action: OutlineAction; title: string;
  section?: string; newTitle?: string; part?: string; after?: string; purpose?: string; why?: string;
}
export interface OutlineSection {
  id: string; title: string; part: string; partTitle: string; frontMatter: boolean; position: number; words: number; purpose: string;
}
export interface OutlineCurrent { kind: ResearchKind; journal: string; journalName: string; sections: OutlineSection[] }
export interface OutlineIgnored { title?: string; reason: string }
/** outline_suggest: `dropped` lists reply items Python dropped as invalid (Python's key), with the reason (optional field). */
export interface OutlineProposal { items: OutlineItem[]; sent: SentReport; cost: number | null; model: string; dropped?: OutlineIgnored[] }
export interface OutlineStandard { name: string; items: OutlineItem[] }
export interface OutlineApplied { changed: string[]; remap: Record<string, string>; skipped: { id: string; reason: string }[]; created: string[] }
