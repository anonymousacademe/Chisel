import type { DiffSegment } from "./types";
import { signedWords } from "./stats";

/** "just now", "12 min ago", "3 h ago", "2 days ago", else the date (mirrors chisel.core.snapshots.ago). */
export function agoText(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const secs = Math.floor((now.getTime() - when.getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  if (secs < 86400 * 14) { const d = Math.floor(secs / 86400); return `${d} day${d === 1 ? "" : "s"} ago`; }
  const p = (n: number) => String(n).padStart(2, "0");
  return `${when.getFullYear()}-${p(when.getMonth() + 1)}-${p(when.getDate())}`;
}

/** "Mon 1 Oct, 14:05" in local time. */
export function whenText(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** "+120", "−35" or "±0": the change in words from a snapshot to the current text. */
export function deltaText(n: number): string {
  return signedWords(n);
}

/** A snapshot's label for people: auto and before-… labels get a plain explanation. */
export function labelText(label: string): string {
  if (!label) return "Snapshot";
  if (label === "auto") return "Automatic (first edit of the day)";
  if (label === "before-restore") return "Before a restore";
  if (label === "before-accept-all") return "Before accepting all AI drafts";
  if (label === "before-reject-all") return "Before rejecting all AI drafts";
  const m = /^end-of-draft-(\d+)$/.exec(label);
  if (m) return `End of draft ${m[1]}`;
  return label;
}

export interface Piece { text: string; mark: "del" | "ins" | null }

/** The two sides of a word diff: the snapshot (deletions marked) and the current text (insertions marked). */
export function sides(segments: DiffSegment[]): { left: Piece[]; right: Piece[] } {
  const left: Piece[] = [], right: Piece[] = [];
  for (const s of segments) {
    if (s.op === "equal") {
      left.push({ text: s.old, mark: null });
      right.push({ text: s.new, mark: null });
      continue;
    }
    if (s.old) left.push({ text: s.old, mark: "del" });
    if (s.new) right.push({ text: s.new, mark: "ins" });
  }
  return { left, right };
}

/** True when the diff holds no change at all. */
export const identical = (segments: DiffSegment[]) => segments.every((s) => s.op === "equal");
