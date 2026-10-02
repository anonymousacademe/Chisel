import type { RenameFile, RenamePreview } from "./types";

/** The ids ticked when the preview opens: everything except text inside a pending AI draft. */
export const defaultTicks = (p: RenamePreview): Set<string> =>
  new Set(p.files.flatMap((f) => f.occurrences.filter((o) => o.defaultOn).map((o) => o.id)));

export const countTicked = (files: RenameFile[], ticked: Set<string>): { occurrences: number; files: number } => {
  let occurrences = 0, nFiles = 0;
  for (const f of files) {
    const n = f.occurrences.filter((o) => ticked.has(o.id)).length;
    occurrences += n;
    if (n) nFiles += 1;
  }
  return { occurrences, files: nFiles };
};

/** Aliases the author typed a new spelling for ({old: new}); unchanged or blank ones are not renames. */
export const aliasRenames = (edits: Record<string, string>): Record<string, string> =>
  Object.fromEntries(Object.entries(edits).map(([a, b]) => [a, b.trim()]).filter(([a, b]) => b && b !== a));

export const KIND_LABEL: Record<string, string> = { scene: "Scene", entity: "Note", research: "Research", comment: "Comments" };
