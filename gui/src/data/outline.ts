// Pure helpers for the outline assistant's review: which items start ticked, what each one says, and the
// before / after preview. Python validated the items and applies them; this only draws what the ticked ones would do.
import type { OutlineAction, OutlineItem, OutlineSection } from "./research";

/** Items the author can tick: advice is text only and keep changes nothing. */
export const isActionable = (i: OutlineItem) => i.action === "add" || i.action === "rename" || i.action === "move";
/** Everything add / rename / move starts ticked. */
export const defaultTicked = (items: OutlineItem[]): Set<string> => new Set(items.filter(isActionable).map((i) => i.id));
/** The items the review shows: keep is hidden. */
export const visibleItems = (items: OutlineItem[]) => items.filter((i) => i.action !== "keep");
/** The full item objects for the ticked ids, in the reply's order (this is what outline_apply gets). */
export const tickedItems = (items: OutlineItem[], ticked: Set<string>) => items.filter((i) => isActionable(i) && ticked.has(i.id));

export const ACTION_LABEL: Record<OutlineAction, string> = { add: "Add", rename: "Rename", move: "Move", keep: "Keep", advice: "Advice" };

const q = (t: string) => `“${t}”`;

/** Where an item puts a section: its part (a part TITLE, "" = top level) and its anchor (`after` is a SECTION id). */
function destination(i: OutlineItem, sections: OutlineSection[]): string {
  const part = i.part ? `Part ${q(i.part)}` : "the top level";
  const anchor = i.after ? sections.find((s) => s.id === i.after) : undefined;
  if (anchor) return `to ${part}, after ${q(anchor.title)}`;
  if (!i.after) return `to the start of ${part}`;   // Python: no anchor means the start of the part
  return `to ${part}`;
}

/** One line saying what ticking this item will change. Titles are the sections' real current ones (looked up by section id). */
export function describeItem(i: OutlineItem, sections: OutlineSection[] = []): string {
  const current = (i.section ? sections.find((s) => s.id === i.section)?.title : undefined) ?? i.title;
  switch (i.action) {
    case "add": return `Add ${q(i.title)} ${destination(i, sections)}.`;
    case "rename": return `Rename ${q(current)} to ${q(i.newTitle ?? "")}.`;
    case "move": return `Move ${q(current)} ${destination(i, sections)}.`;
    case "keep": return `Keep ${q(current)} as it is.`;
    default: return i.title;
  }
}

export type PreviewState = "same" | "new" | "renamed" | "moved";
export interface PreviewRow { key: string; title: string; part: string; state: PreviewState; words?: number }
export interface PreviewGroup { part: string; rows: PreviewRow[] }

const rowOf = (s: OutlineSection): PreviewRow => ({ key: s.id, title: s.title, part: s.partTitle, state: "same", words: s.words });

/** `part` is a part TITLE (rows carry titles; section.part is an id and is never compared), `after` a section id. */
function insertAt(rows: PreviewRow[], row: PreviewRow, part: string, after: string | undefined) {
  row.part = part;
  const at = after ? rows.findIndex((r) => r.key === after) : -1;
  if (at >= 0) { rows.splice(at + 1, 0, row); return; }
  const first = rows.findIndex((r) => r.part === part);
  if (!after && first >= 0) { rows.splice(first, 0, row); return; }   // no anchor: the start of the part, as Python places it
  let last = -1;                                                     // an unknown anchor: the end of the part
  rows.forEach((r, n) => { if (r.part === part) last = n; });
  if (last >= 0) rows.splice(last + 1, 0, row); else rows.push(row);
}

/** The outline as the ticked items would leave it, in order. Items whose section is missing are skipped, as Python skips them. */
export function previewRows(sections: OutlineSection[], items: OutlineItem[]): PreviewRow[] {
  const rows = sections.map(rowOf);
  for (const i of items) {
    const at = i.section ? rows.findIndex((r) => r.key === i.section) : -1;
    if (i.action === "rename" && at >= 0) {
      rows[at] = { ...rows[at], title: i.newTitle ?? rows[at].title, state: rows[at].state === "moved" ? "moved" : "renamed" };
    } else if (i.action === "move" && at >= 0) {
      const [row] = rows.splice(at, 1);
      row.state = "moved";
      insertAt(rows, row, i.part ?? "", i.after);
    } else if (i.action === "add") {
      insertAt(rows, { key: `new:${i.id}`, title: i.title, part: "", state: "new" }, i.part ?? "", i.after);
    }
  }
  return rows;
}

/** Rows grouped by part, parts in order of first appearance. */
export function groupRows(rows: PreviewRow[]): PreviewGroup[] {
  const groups: PreviewGroup[] = [];
  for (const r of rows) {
    let g = groups.find((x) => x.part === r.part);
    if (!g) { g = { part: r.part, rows: [] }; groups.push(g); }
    g.rows.push(r);
  }
  return groups;
}

/** Before and after for the review. */
export function previewOutline(sections: OutlineSection[], ticked: OutlineItem[]) {
  return { before: groupRows(sections.map(rowOf)), after: groupRows(previewRows(sections, ticked)) };
}

export const changeCount = (n: number) => `Apply ${n} change${n === 1 ? "" : "s"}`;
