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
export interface ZoteroCollection { key: string; path: string; items: number | null }

/** The Zotero settings. The web API key never comes back over the bridge: only whether one is saved. */
export interface ZoteroSettings { userId: string; webBase: string; local: boolean; localBase: string; file: string; keySet: boolean }

export interface ZoteroBackendStatus { backend: string; ok: boolean; message: string }
export interface ZoteroStatus { backends: ZoteroBackendStatus[]; keySet: boolean }

export type SyncAction = "new" | "changed" | "missing" | "key-mismatch";
export interface SyncRow { id: string; key: string; action: SyncAction; summary: string; blocked: string | boolean }
export interface SyncPlan { rows: SyncRow[]; report: string[]; backend: string }
export interface SyncScope { collection?: string; tag?: string }
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
