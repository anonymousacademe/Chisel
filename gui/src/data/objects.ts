// Pure helpers for figures, tables and equations (wave F1): placement text and where it goes, grid operations,
// file checks. Numbers, validation and every file write stay in Python.
import type { ObjectKind, TableAlign } from "./research";

/** The size hints shown beside the table grid (Python's own caps are larger and are the real limit). */
export const GRID_HINT = { rows: 200, cols: 20 };
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const ALIGNS: TableAlign[] = ["default", "left", "center", "right"];

export const objectId = (kind: ObjectKind, label: string) => `${kind}:${label}`;
export function splitObjectId(id: string): { kind: ObjectKind; label: string } | null {
  const m = /^(fig|tbl|eq):(.+)$/.exec(id);
  return m ? { kind: m[1] as ObjectKind, label: m[2] } : null;
}
/** The placement line: alone on its line, it puts the object in the section. */
export const placementText = (id: string) => `![[${id}]]`;
/** The reference as written in prose. */
export const referenceText = (id: string) => `[[${id}]]`;

const lineAt = (text: string, start: number) => {
  const end = text.indexOf("\n", start);
  return text.slice(start, end < 0 ? text.length : end);
};

/** What to type at [from, to) so the placement sits on its OWN line: a blank line before and after when the
 *  cursor is mid-text or touches a neighbouring line. Pure; the caller replaces [from, to) with `insert`. */
export function placementEdit(text: string, from: number, to: number, id: string): { from: number; to: number; insert: string } {
  const line = placementText(id);
  const lineStart = text.lastIndexOf("\n", from - 1) + 1;
  let lineEnd = text.indexOf("\n", to);
  if (lineEnd < 0) lineEnd = text.length;
  const before = text.slice(lineStart, from);
  const after = text.slice(to, lineEnd);
  let prevBlank = true;
  if (lineStart > 0) {
    const prevStart = text.lastIndexOf("\n", lineStart - 2) + 1;
    prevBlank = text.slice(prevStart, lineStart - 1).trim() === "";
  }
  const nextBlank = lineEnd >= text.length || lineAt(text, lineEnd + 1).trim() === "";
  const prefix = before.trim() !== "" ? "\n\n" : prevBlank ? "" : "\n";
  const suffix = after.trim() !== "" ? "\n\n" : nextBlank ? "" : "\n";
  return { from, to, insert: `${prefix}${line}${suffix}` };
}

/** The slice of the editor handle the insert flows use. */
export interface PlaceTarget { getText(): string; selection(): { from: number; to: number }; replace(from: number, to: number, insert: string): void; focus(): void }

/** Put the placement of *id* at the cursor of the open section. False when there is no section to put it in. */
export function placeObject(ed: PlaceTarget | null | undefined, open: boolean, id: string): boolean {
  if (!ed || !open) return false;
  const { from, to } = ed.selection();
  const e = placementEdit(ed.getText(), from, to, id);
  ed.replace(e.from, e.to, e.insert);
  ed.focus();
  return true;
}

// -- the table grid -------------------------------------------------------------------------------------------

export interface Grid { cells: string[][]; align: TableAlign[] }

export const blankGrid = (rows = 3, cols = 3): Grid => ({
  cells: Array.from({ length: rows }, () => Array.from({ length: cols }, () => "")),
  align: Array.from({ length: cols }, () => "default" as TableAlign),
});
export const withCell = (g: Grid, r: number, c: number, v: string): Grid => ({ ...g, cells: g.cells.map((row, i) => (i === r ? row.map((x, j) => (j === c ? v : x)) : row)) });
export const addRow = (g: Grid, at = g.cells.length): Grid => {
  const cells = g.cells.map((r) => r.slice());
  cells.splice(Math.max(1, Math.min(at, cells.length)), 0, g.align.map(() => ""));
  return { ...g, cells };
};
/** The header row (row 0) is never removed, and a table keeps one body row. */
export const removeRow = (g: Grid, r: number): Grid => (r <= 0 || g.cells.length <= 2 ? g : { ...g, cells: g.cells.filter((_, i) => i !== r) });
export const addCol = (g: Grid, at = g.align.length): Grid => {
  const k = Math.max(0, Math.min(at, g.align.length));
  const ins = <T,>(a: T[], v: T) => [...a.slice(0, k), v, ...a.slice(k)];
  return { cells: g.cells.map((r) => ins(r, "")), align: ins<TableAlign>(g.align, "default") };
};
export const removeCol = (g: Grid, c: number): Grid =>
  g.align.length <= 1 ? g : { cells: g.cells.map((r) => r.filter((_, j) => j !== c)), align: g.align.filter((_, j) => j !== c) };
export const setAlign = (g: Grid, c: number, a: TableAlign): Grid => ({ ...g, align: g.align.map((x, j) => (j === c ? a : x)) });

/** Parse tab-separated text (a spreadsheet copy). Null when it has no tab or newline, so a plain paste is left to the cell. */
export function parseTsv(text: string): string[][] | null {
  const t = text.replace(/\r\n?/g, "\n").replace(/\n+$/, "");
  if (!t.includes("\t") && !t.includes("\n")) return null;
  const rows = t.split("\n").map((l) => l.split("\t").map((c) => c.trim()));
  const width = Math.max(...rows.map((r) => r.length));
  return rows.map((r) => [...r, ...Array.from({ length: width - r.length }, () => "")]);
}

/** Paste tab-separated rows with their top-left at (r, c): the grid grows to fit, existing cells are overwritten. */
export function pasteGrid(g: Grid, r: number, c: number, rows: string[][]): Grid {
  const need = Math.max(g.cells.length, r + rows.length);
  const wide = Math.max(g.align.length, c + Math.max(...rows.map((x) => x.length)));
  const align: TableAlign[] = [...g.align, ...Array.from({ length: wide - g.align.length }, () => "default" as TableAlign)];
  const cells = Array.from({ length: need }, (_, i) => Array.from({ length: wide }, (_, j) => g.cells[i]?.[j] ?? ""));
  rows.forEach((row, i) => row.forEach((v, j) => { cells[r + i][c + j] = v; }));
  return { cells, align };
}

/** Which size hints the grid exceeds (Python refuses far more; these are advice). */
export const gridHints = (g: Grid): string[] => [
  ...(g.cells.length > GRID_HINT.rows ? [`More than ${GRID_HINT.rows} rows is hard to read in a paper.`] : []),
  ...(g.align.length > GRID_HINT.cols ? [`More than ${GRID_HINT.cols} columns will not fit a page.`] : []),
];
export const gridIsBlank = (g: Grid) => g.cells.every((r) => r.every((c) => c.trim() === ""));

// -- figure files ---------------------------------------------------------------------------------------------

/** "PNG or JPG only": decided by the type the browser reports, else the extension (Python checks the bytes). */
export function figureFileProblem(f: { name: string; type: string; size: number }): string {
  const ok = /^image\/(png|jpeg)$/.test(f.type) || (!f.type && /\.(png|jpe?g)$/i.test(f.name));
  if (!ok) return "Only PNG or JPG pictures can be inserted.";
  if (f.size > MAX_IMAGE_BYTES) return "That picture is larger than 10 MB.";
  return "";
}
/** A file name without its extension, as a starting caption / label source. */
export const fileStem = (name: string) => name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();

export const usedIn = (n: number) => (n === 0 ? "Not placed in any section yet." : `Placed in ${n} section${n === 1 ? "" : "s"}.`);
