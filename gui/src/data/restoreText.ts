export interface RestoreResult {
  id: string; kind: "scene" | "research" | "inspiration"; unplaced: boolean;
  where?: "part" | "book" | "unplaced" | "gone"; part?: string;
}

/** The toast after a Trash restore: say where the item went and why. */
export function restoredText(title: string, r: RestoreResult): string {
  if (r.kind === "inspiration") return `Restored the inspiration picture “${title}”.`;
  if (r.kind === "research") return `Restored the notebook note “${title}” (${r.id}).`;
  switch (r.where) {
    case "gone": return `Restored “${title}”: its part is gone, so it went to Parked scenes.`;
    case "unplaced": return `Restored “${title}” to Parked scenes.`;
    case "part": return `Restored “${title}” to ${r.part}.`;
    default: return `Restored “${title}”.`;
  }
}
