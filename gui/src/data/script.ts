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

/** The sentence after a voice check: what was judged and what was not (Python decides both; this only words it). */
export function voiceNotice(r: { issues: unknown[]; waived: number; checked: string[]; skipped: { speaker: string; lines: number }[]; minLines: number; notFit?: string[] }): string {
  const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const skipped = (r.skipped.length
    ? ` Not judged (fewer than ${r.minLines} lines elsewhere to compare): ${r.skipped.map((s) => `${s.speaker} (${s.lines})`).join(", ")}.`
    : "") + (r.notFit?.length ? ` Not compared (their lines did not fit the model's window): ${r.notFit.join(", ")}.` : "");
  if (!r.checked.length) return `Nothing to compare yet.${skipped}`;
  const waived = r.waived ? ` (${r.waived} waived)` : "";
  const who = `Checked ${r.checked.join(", ")}.`;
  return (r.issues.length
    ? `${plural(r.issues.length, "line")} may be off voice${waived}. ${who}`
    : `Every checked line sounds like its character${waived}. ${who}`) + skipped;
}
