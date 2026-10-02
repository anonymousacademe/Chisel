/** Types and pure helpers for the Export dialog (the work happens in Python: core/export). */

export type ExportFormatKey = "pdf" | "docx" | "epub" | "md" | "tex";

export type ExportOptions = {
  format: ExportFormatKey; layout: string; page_size: string; font: string;
  numbering: "words" | "numbers" | "titles-only";
  toc: boolean; include_front_matter: boolean; include_drafts: boolean; continuous: boolean;
  copyright: string;
};

export type ExportFormat = { key: ExportFormatKey; label: string; ext: string; available: boolean; reason: string };
export type ExportLayout = {
  name: string; label: string; description: string; page_sizes: string[];
  fonts: { key: string; label: string; available: boolean }[];
  toc: boolean; continuous: boolean; numbering: boolean;
};
export type ExportInfo = { formats: ExportFormat[]; layouts: ExportLayout[]; options: ExportOptions; project_copyright?: string };

export type ExportSummary = {
  scenes: number; words: number; parts: number; draft_scenes: number; messages: string[];
};
export type ExportResult = { rel: string; name: string; format: ExportFormatKey; pages: number | null; words: number; scenes: number; warnings: string[] };
export type ExportStatus =
  | { state: "running"; stage: string; fraction: number }
  | { state: "done"; stage: string; fraction: number; result: ExportResult }
  | { state: "error"; stage: string; fraction: number; error: string };

export const PAGE_SIZE_LABEL: Record<string, string> = {
  trade: "Trade 6 × 9 in", a5: "A5", letter: "US Letter", a4: "A4",
};

/** "4 scenes, 1,502 words, 2 parts; 1 scene has unaccepted AI drafts" */
export function summaryLine(s: ExportSummary, unit: string): string {
  const plural = (n: number, w: string) => `${n.toLocaleString("en-US")} ${w}${n === 1 ? "" : "s"}`;
  const bits = [plural(s.scenes, unit), plural(s.words, "word")];
  if (s.parts) bits.push(plural(s.parts, "part"));
  let line = bits.join(", ");
  if (s.draft_scenes) line += `; ${plural(s.draft_scenes, unit)} ${s.draft_scenes === 1 ? "has" : "have"} unaccepted AI drafts`;
  return line;
}

/** The layout an options set uses (PDF only). */
export function layoutOf(info: ExportInfo, o: ExportOptions): ExportLayout | null {
  return o.format === "pdf" ? info.layouts.find((l) => l.name === o.layout) ?? info.layouts[0] ?? null : null;
}

/** *o* with the page size and font forced into what its layout offers, as the server does. */
export function fitOptions(info: ExportInfo, o: ExportOptions): ExportOptions {
  const l = layoutOf(info, o);
  if (!l) return o;
  const usable = l.fonts.filter((f) => f.available);
  const fonts = usable.length ? usable : l.fonts;
  return {
    ...o, layout: l.name,
    page_size: l.page_sizes.includes(o.page_size) ? o.page_size : l.page_sizes[0],
    font: fonts.some((f) => f.key === o.font) ? o.font : fonts[0].key,
  };
}

/** Formats the server can run now, first usable one if *key* cannot. */
export function usableFormat(info: ExportInfo, key: ExportFormatKey): ExportFormatKey {
  return info.formats.find((f) => f.key === key && f.available)?.key
    ?? info.formats.find((f) => f.available)?.key ?? key;
}
