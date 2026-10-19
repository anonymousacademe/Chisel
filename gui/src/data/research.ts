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
export interface SyncPlan { rows: SyncRow[]; report: string[]; backend: string }
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
