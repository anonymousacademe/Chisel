import type { CustomCheck, CustomRequirement, ObjectKind, SuggestedRequirement } from "./research";

export const DEFAULT_GROUP = "Your requirements";

/** The numbers and fields each check kind needs (everything else is left out of the saved row). */
export type ParamName = "section" | "min" | "max" | "item_chars_max" | "object";
export const CHECK_PARAMS: Record<CustomCheck, ParamName[]> = {
  "section-present": ["section"],
  "section-words-max": ["section", "max"],
  "section-no-citations": ["section"],
  "list-count": ["section", "min", "max", "item_chars_max"],
  "last-section": ["section"],
  "objects-captioned": ["object"],
  "objects-referenced": ["object"],
  "citations-resolved": [],
  "sources-doi": [],
};

/** The short list the "Add a requirement" form offers, in plain words. */
export const CHECK_CHOICES: { value: CustomCheck | "advice"; label: string }[] = [
  { value: "section-present", label: "A section must exist" },
  { value: "section-words-max", label: "A section has a word limit" },
  { value: "section-no-citations", label: "A section has no citations" },
  { value: "list-count", label: "A list has a number of items" },
  { value: "last-section", label: "A section comes last" },
  { value: "objects-captioned", label: "Every figure, table or equation has a caption" },
  { value: "objects-referenced", label: "Every figure, table or equation is cited" },
  { value: "citations-resolved", label: "Every citation matches a source" },
  { value: "sources-doi", label: "Every cited source has a DOI" },
  { value: "advice", label: "A reminder (not checked)" },
];

export const OBJECT_WORD: Record<ObjectKind, string> = { fig: "figure", tbl: "table", eq: "equation" };

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
/** "abstract" or "keywords or key words". */
export const sectionName = (r: Pick<CustomRequirement, "section">) => (r.section ?? []).filter(Boolean).join(" or ");

/** The check a row will run, in plain words: "Abstract: at most 150 words". */
export function describeCheck(r: CustomRequirement): string {
  if (r.kind === "advice" || !r.check) return `Reminder: ${r.title}`;
  const sec = cap(sectionName(r)) || "The section";
  const obj = OBJECT_WORD[r.object ?? "fig"] ?? "figure";
  switch (r.check) {
    case "section-present": return `${sec}: must be present`;
    case "section-words-max": return r.max === undefined ? `${sec}: limit not set` : `${sec}: at most ${plural(r.max, "word")}`;
    case "section-no-citations": return `${sec}: no citations`;
    case "list-count": {
      const lo = r.min ?? 0, hi = r.max;
      if (r.min === undefined && hi === undefined) return `${sec}: limit not set`;
      const n = hi === undefined ? `at least ${plural(lo, "item")}` : lo > 0 ? `${lo} to ${plural(hi, "item")}` : `at most ${plural(hi, "item")}`;
      return `${sec}: ${n}` + (r.item_chars_max !== undefined ? `, each at most ${plural(r.item_chars_max, "character")}` : "");
    }
    case "last-section": return `${sec}: must be the last section`;
    case "objects-captioned": return `Every ${obj} has a caption`;
    case "objects-referenced": return `Every ${obj} is cited in the text`;
    case "citations-resolved": return "Every citation matches a source";
    case "sources-doi": return "Every cited source has a DOI";
  }
  return r.title;
}

/** Only the fields a row's check uses, no empty values: what is sent to requirements_save. */
export function cleanRow(r: CustomRequirement | SuggestedRequirement): CustomRequirement {
  const out: CustomRequirement = { id: r.id, group: r.group.trim() || DEFAULT_GROUP, title: r.title.trim(), kind: r.kind, severity: r.severity };
  if (r.kind === "check" && r.check) {
    out.check = r.check;
    for (const p of CHECK_PARAMS[r.check]) {
      if (p === "section") { const s = (r.section ?? []).map((x) => x.trim()).filter(Boolean); if (s.length) out.section = s; }
      else if (p === "object") out.object = r.object ?? "fig";
      else if (typeof r[p] === "number" && Number.isFinite(r[p])) out[p] = r[p];
    }
  }
  if (r.source) out.source = r.source;
  if (r.quote) out.quote = r.quote;
  return out;
}

/** An id that is not in `taken` (and records it there). */
export function uniqueId(base: string, taken: Set<string>): string {
  const slug = base.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "requirement";
  let id = slug, n = 2;
  while (taken.has(id)) id = `${slug}-${n++}`;
  taken.add(id);
  return id;
}

/** The ticked suggestions, cleaned, appended to the rows already saved (ids kept unique). */
export function rowsToSave(existing: CustomRequirement[], items: SuggestedRequirement[], ticked: Set<string>): CustomRequirement[] {
  const taken = new Set(existing.map((r) => r.id));
  const added = items.filter((i) => ticked.has(i.id)).map((i) => ({ ...cleanRow(i), id: uniqueId(i.id || i.title, taken) }));
  return [...existing, ...added];
}

/** Unverified items start unticked: the quote could not be found in the guideline. */
export const defaultTickedRequirements = (items: SuggestedRequirement[]) => new Set(items.filter((i) => i.verified).map((i) => i.id));

export const addCount = (n: number) => `Add ${n} requirement${n === 1 ? "" : "s"}`;

/** Shown (and every change disabled) while requirements.toml has rows Chisel cannot read. */
export const UNREADABLE_BLOCK = "requirements.toml has rows Chisel cannot read. Fix or remove them in the file (it is in your project folder), then reopen this window.";

export const WHOLE_NUMBER_HINT = "Use a whole number from 0 to 100000";
export const TITLE_HINT = "A title is needed (up to 160 characters)";
export const ORDER_HINT = "Minimum is larger than maximum";

/** Digits only: what a number box may hold while typing (empty clears it). */
export const isWholeText = (text: string) => text === "" || /^\d+$/.test(text);

export type NumberKey = "min" | "max" | "item_chars_max";
export type RowProblems = Partial<Record<NumberKey | "title" | "order", string>>;

/** Client-side hints for a row's fields; Python stays the authority. Empty object = nothing to point out. */
export function rowProblems(r: CustomRequirement | SuggestedRequirement): RowProblems {
  const out: RowProblems = {};
  if (r.title.trim() === "" || r.title.length > 160) out.title = TITLE_HINT;
  if (r.kind !== "check" || !r.check) return out;
  const params = CHECK_PARAMS[r.check];
  for (const key of ["min", "max"] as const) {
    const v = r[key];
    if (!params.includes(key)) continue;
    if (v === undefined) { if (key === "max" && r.check === "section-words-max") out.max = WHOLE_NUMBER_HINT; continue; }
    if (!Number.isInteger(v) || v < 0 || v > 100000) out[key] = WHOLE_NUMBER_HINT;
  }
  const c = r.item_chars_max;
  if (params.includes("item_chars_max") && c !== undefined && (!Number.isInteger(c) || c < 1 || c > 10000)) out.item_chars_max = "Use a whole number from 1 to 10000";
  if (!out.min && !out.max && params.includes("min") && params.includes("max") && r.min !== undefined && r.max !== undefined && r.min > r.max) out.order = ORDER_HINT;
  return out;
}
