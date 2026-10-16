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
