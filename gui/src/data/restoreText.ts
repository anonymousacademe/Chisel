export interface RestoreResult {
  id: string; kind: "scene" | "research"; unplaced: boolean;
  where?: "part" | "book" | "unplaced" | "gone"; part?: string;
}

/** The toast after a Trash restore: say where the item went and why. */
export function restoredText(title: string, r: RestoreResult): string {
  if (r.kind === "research") return `Restored the research note “${title}” (${r.id}).`;
  switch (r.where) {
    case "gone": return `Restored “${title}”: its part is gone, so it went to Unplaced Scenes.`;
    case "unplaced": return `Restored “${title}” to Unplaced Scenes.`;
    case "part": return `Restored “${title}” to ${r.part}.`;
    default: return `Restored “${title}”.`;
  }
}
