import type { BinderNode } from "./types";

/** Nodes that open a document when clicked. */
export const isOpenable = (n: BinderNode) =>
  !n.placeholder && (n.kind === "document" || n.kind === "entity" || n.kind === "style" || n.kind === "dictionary");

/** Rows that do something other than open a document when clicked: a part is focused (and
 * toggled), Trash opens its dialog. */
export const isActionable = (n: BinderNode) => !n.placeholder && (n.kind === "part" || n.kind === "trash");

export function collectExpanded(nodes: BinderNode[], out = new Set<string>()) {
  for (const n of nodes) { if (n.expanded) out.add(n.id); if (n.children) collectExpanded(n.children, out); }
  return out;
}

export function findNode(nodes: BinderNode[], id: string): BinderNode | undefined {
  for (const n of nodes) {
    if (n.id === id) return n;
    const hit = n.children && findNode(n.children, id);
    if (hit) return hit;
  }
}

export function filterTree(nodes: BinderNode[], q: string): BinderNode[] {
  return nodes.flatMap((n) => {
    const kids = n.children ? filterTree(n.children, q) : undefined;
    if (n.title.toLowerCase().includes(q) || (kids && kids.length)) return [{ ...n, children: n.children ? kids : undefined }];
    return [];
  });
}

export function allIds(nodes: BinderNode[], out = new Set<string>()) {
  for (const n of nodes) { out.add(n.id); if (n.children) allIds(n.children, out); }
  return out;
}

export const fmt = (n: number) => n.toLocaleString("en-US");

/** Keep only the documents whose id is in *ids* (and the folders that still hold one). */
export function filterByIds(nodes: BinderNode[], ids: ReadonlySet<string>): BinderNode[] {
  return nodes.flatMap((n) => {
    if (n.kind === "document") return ids.has(n.id) ? [n] : [];
    if (!n.children) return [];
    const kids = filterByIds(n.children, ids);
    return kids.length ? [{ ...n, children: kids }] : [];
  });
}
