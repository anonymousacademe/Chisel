import type { Workspace } from "./types";

export interface SwitcherItem { id: string; title: string; detail: string; category: "Scene" | "Note" | "Notebook" | "Style" | "Dictionary" }

/** Everything the quick switcher (Ctrl K) can open: scenes, notes, the style guide. */
export function switcherItems(ws: Workspace): SwitcherItem[] {
  const items: SwitcherItem[] = ws.scenes.map((s) => ({
    id: s.id, title: s.title, detail: s.number ? `Scene ${s.number}` : "Scene", category: "Scene",
  }));
  for (const e of ws.entities) {
    items.push({ id: e.id, title: e.name, detail: [e.type, ...e.aliases].join(" · "), category: "Note" });
  }
  for (const r of ws.research) items.push({ id: r.id, title: r.title, detail: r.folder ? `Notebook · ${r.folder}` : "Notebook", category: "Notebook" });
  if (ws.status.hasStyle) items.push({ id: "style.md", title: "Style guide", detail: "style.md", category: "Style" });
  items.push({ id: "dictionary.txt", title: "Dictionary", detail: "dictionary.txt", category: "Dictionary" });
  return items;
}

/** Case-insensitive: every query word must appear in the title or detail. Title hits rank first. */
export function filterSwitcher(items: SwitcherItem[], query: string): SwitcherItem[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return items;
  const scored = items.flatMap((it) => {
    const title = it.title.toLowerCase();
    const hay = `${title} ${it.detail.toLowerCase()}`;
    if (!words.every((w) => hay.includes(w))) return [];
    return [{ it, score: words.every((w) => title.startsWith(w)) ? 0 : words.every((w) => title.includes(w)) ? 1 : 2 }];
  });
  return scored.sort((a, b) => a.score - b.score).map((s) => s.it);
}
