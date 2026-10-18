/** Script mode helpers (the format itself is parsed in Python: core/fountain.py). */

/** What a Fountain import added (Api.import_fountain). */
export interface FountainImport {
  scenes: number;
  parts: number;
  /** Project-relative id of the first imported scene, to open it. */
  first: string;
  /** Fields of the file's title page that filled empty project details (author, contact, copyright). */
  filled: string[];
  name: string;
}

/** "Imported 12 scenes in 3 parts from big-fish.fountain." */
export function importedLine(r: FountainImport): string {
  const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const parts = r.parts ? ` in ${plural(r.parts, "part")}` : "";
  return `Imported ${plural(r.scenes, "scene")}${parts} from ${r.name}.`;
}
