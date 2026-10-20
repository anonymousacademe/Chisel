// In-memory stand-in for the Python core, used only by `npm run dev` in a
// plain browser (no pywebview, no devserver). Same JSON bridge contract as
// chisel.gui.api.Api; methods it does not implement return an error so the
// UI shows "not available" instead of inventing results.
import type { BinderNode, DocumentPayload, EntityInfo, EntitySummary, InspirationImage, SceneMention, SceneSummary, SentReport, Workspace } from "../data/types";
import type { CustomRequirement, SuggestedRequirement } from "../data/research";
import { mockObjectGroups, mockObjectsCall } from "./mockObjects";

const CH07 = [
  "The city woke before Mara did. It moved beneath the floorboards in small electrical sighs, drawing yesterday’s rain back through the copper veins of the building. By three seventeen, every window on Vesper Street had clouded from the inside.",
  "She stood in the kitchen with one hand around a cup gone cold and listened to the municipal archive remembering itself. First came the tram bells from a line decommissioned twenty years ago. Then the market vendors, calling prices in the old coastal dialect. Last, almost too softly to separate from the pipes, came her brother’s voice.",
  "“Mara,” the wall said, in a voice the wall had no right to know. Not a recording. Recordings kept their distance. This breath caught on the second syllable exactly as Elias’s always had.",
  "Mara set the cup down. Across the room, the archive terminal pulsed once behind its smoked glass. The waveform on its display was flat, but the room continued speaking around it: cupboards ticking open, the radiator knocking out a childhood code, rain lifting in silver threads from the sill.",
  "She had spent six years proving that memory was only architecture—rooms built by chemistry, corridors narrowed by grief. Now the city had found the door she had buried and was knocking from the other side.",
].join("\n\n");

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const words = (t: string) => t.split(/\s+/).filter(Boolean).length;
const k = (n: number) => (n < 1000 ? String(n) : `${(n / 1000).toFixed(1)}k`);

const SCENES = [
  ["The Rain Index", ""], ["Blue Hour Protocol", ""], ["The Cartographer", ""], ["Borrowed Weather", ""],
  ["Negative Space", ""], ["The House Below", ""], ["A City That Remembers", CH07], ["Salt in the Signal", ""],
  ["The Other Mara", ""], ["Meridian Zero", ""],
].map(([title, body], i) => {
  const n = String(i + 1).padStart(2, "0");
  const text = `# ${title}\n\n${body || "(Mock scene — connect the Chisel core to see real prose.)"}\n`;
  return { id: `manuscript/${n}-${slug(title)}.md`, number: n, title, text };
});

const ENTITIES: (EntitySummary & { body: string })[] = [
  { id: "entities/characters/mara-vale.md", name: "Mara Vale", type: "character", aliases: ["Mara"], words: 12, body: "Archivist of Lower Meridian." },
  { id: "entities/characters/elias-vale.md", name: "Elias Vale", type: "character", aliases: ["Elias"], words: 10, body: "Mara's brother." },
  { id: "entities/places/lower-meridian.md", name: "Lower Meridian", type: "place", aliases: [], words: 8, body: "The drowned district." },
];
const noteText = (e: (typeof ENTITIES)[number]) =>
  `---\nname: ${e.name}\ntype: ${e.type}\naliases: [${e.aliases.join(", ")}]\n---\n\n${e.body}\n`;

const ph = (id: string, title: string, kind: BinderNode["kind"] = "folder"): BinderNode =>
  ({ id: `ph:${id}`, title, kind, placeholder: true, muted: true });

function buildWorkspace(): Workspace {
  const scenes: SceneSummary[] = SCENES.map((s) => ({
    id: s.id, number: s.number, title: s.title, words: words(s.text), excerpt: s.text.split("\n\n")[1]?.slice(0, 160) ?? "", headings: [],
    part: null, frontMatter: false, unplaced: false,
    details: { pov: "", place: "", purpose: "", status: "", when: "", target: null, collections: [] },
    when: { value: "", label: "", source: "none", raw: "", invalid: false },
  }));
  const total = scenes.reduce((n, s) => n + s.words, 0);
  const ent = (e: EntitySummary): BinderNode => ({ id: e.id, title: e.name, kind: "entity" });
  return {
    project: { title: "The Meridian Archive", author: "", initials: "LW", path: "/mock", documentCount: scenes.length + ENTITIES.length, unit: "scene", draft: 1, mode: "story", labels: { manuscript: "Manuscript", parked: "Parked scenes", characters: "Characters", world: "World Bible" } },
    binder: [
      { id: "project", title: "The Meridian Archive", kind: "project", meta: k(total), expanded: true, children: [
        { id: "group:manuscript", title: "Manuscript", kind: "folder", meta: k(total), expanded: true,
          children: scenes.map((s) => ({ id: s.id, title: `${s.number}  ${s.title}`, kind: "document" as const, meta: k(s.words) })) },
      ] },
      { id: "group:characters", title: "Characters", kind: "characters", children: ENTITIES.filter((e) => e.type === "character").map(ent) },
      { id: "group:world", title: "World Bible", kind: "world",
        children: ENTITIES.filter((e) => e.type !== "character").map((e) => ({ ...ent(e), meta: e.type })) },
      ph("research", "Notebook", "research"),
      { id: "group:trash", title: "Trash", kind: "trash", muted: true },
    ],
    scenes,
    parts: [], collections: [], research: [],
    timeline: { mode: "reading-order", scenes: 0, sentence: "No story times set; using reading order", era: "", unit: "year" },
    entities: ENTITIES.map(({ body: _b, ...e }) => e),
    status: { projectWords: total, sessionWords: 0, sessionMinutes: 0, aiCost: 0, hasStyle: false, trashCount: 0, stats: null },
  };
}

let workspace: Workspace | null = buildWorkspace();

const mentionsOf = (text: string): SceneMention[] =>
  ENTITIES.flatMap((e) => {
    const count = [e.name, ...e.aliases].reduce((n, name) => n + (text.match(new RegExp(`\\b${name}\\b`, "g"))?.length ?? 0), 0);
    return count ? [{ name: e.name, type: e.type, count, backlinks: count }] : [];
  });

function getEntity(name: string): EntityInfo {
  const e = ENTITIES.find((x) => [x.name, ...x.aliases].some((n) => n.toLowerCase() === name.toLowerCase()));
  if (!e) return { found: false, name };
  return { found: true, id: e.id, name: e.name, type: e.type, aliases: e.aliases, body: e.body, canon: "", summary: e.body, backlinks: [], born: "", bornInvalid: false, ageNow: "" };
}

function readDocument(id: string): DocumentPayload | null {
  const s = SCENES.find((x) => x.id === id);
  if (s) {
    return { id, kind: "scene", title: s.title, kicker: `SCENE ${s.number}`, parent: "Manuscript", text: s.text,
      mtime: "0", words: words(s.text), mentions: mentionsOf(s.text),
      details: { pov: "", place: "", purpose: "", status: "", when: "", target: null, collections: [] }, bodyStart: 0 };
  }
  const e = ENTITIES.find((x) => x.id === id);
  if (e) {
    return { id, kind: "entity", title: e.name, kicker: e.type.toUpperCase(), parent: "Notes", text: noteText(e), mtime: "0", words: e.words, mentions: [] };
  }
  return null;
}

// -- AI jobs (ai_start / ai_poll / ai_cancel): a fake word-by-word stream so the live states work in `npm run dev`.
const WORD_MS = 60;           // one streamed word per tick
const QUIET_MS = 1500;        // non-streaming kinds "think" this long
const REPLY = "Here is a **first thought**: let the *city* answer Mara before she asks.\n\n- Keep the voice in the walls ambiguous.\n- Let Elias's breath catch on the second syllable.\n\n> Memory is architecture.\n\nSee `notes/archive` and [the archive](https://example.com) for more.";
const DRAFT = "The radiator knocked twice, then three times, the way Elias used to when he wanted her awake. Mara did not move. If she answered, the city would know it had found the door.";
interface MockJob { kind: string; args: Record<string, unknown>; started: number; cancelled: boolean; text: string; words: string[]; sent: number }
const jobs = new Map<string, MockJob>();
let jobSeq = 0;
const STREAM_KINDS = ["ask", "research", "brainstorm", "generate"];

/** A sample "what was sent" report (the real one comes from python's ai/budget.py): some notes dropped, one shortened. */
function sampleSent(feature: string): SentReport {
  return {
    feature, estTokens: 3200, window: 32000, reserve: 4000, overBudget: false, trimmed: true, attached: [],
    sections: [
      { name: "Instructions and question", chars: 900, estTokens: 225, itemsTotal: 1, itemsSent: 1, itemsDropped: [], truncated: [], omitted: false },
      { name: "Characters and places", chars: 5200, estTokens: 1300, itemsTotal: 4, itemsSent: 2, itemsDropped: ["Elias Vale", "Lower Meridian"], truncated: ["Mara Vale"], omitted: false },
      { name: "Scene", chars: 6700, estTokens: 1675, itemsTotal: 1, itemsSent: 1, itemsDropped: [], truncated: [], omitted: false },
    ],
  };
}

function mockResult(kind: string, args: Record<string, unknown>): Record<string, unknown> {
  switch (kind) {
    case "ask": return { reply: REPLY, attached: [], cost: 0.0012, sent: sampleSent("ask") };
    case "research": return { reply: REPLY, sources: [], attached: [], cost: 0.0012, sent: sampleSent("research") };
    case "brainstorm": return { reply: REPLY, ideas: ["The wall speaks first.", "Mara records the voice.", "Elias answers from the archive."], attached: [], cost: 0.0012, sent: sampleSent("brainstorm") };
    case "generate": {
      const at = Number(args.start ?? 0), end = Number(args.end ?? at);
      return { mode: args.mode ?? "draft", insert: `<!--ai-->${DRAFT}<!--/ai-->`, draftId: null, original: null, from: at, to: end, noStyle: false, cost: 0.003, sent: sampleSent(String(args.mode ?? "draft")) };
    }
    case "continuity": return { issues: [], waived: 0, cost: 0.002, sent: sampleSent("continuity") };
    case "canon": return { updates: [], cost: 0.002, sent: sampleSent("canon") };
    case "aliases": return { suggestions: [], cost: 0.002, sent: sampleSent("aliases") };
    case "outline": return { items: mockOutlineItems(), cost: 0.002, model: "mock", sent: sampleSent("outline"), dropped: MOCK_OUTLINE_IGNORED };
    case "latex": return { text: "\\mu = \\mu_{max}\\frac{S}{K_s + S + S^2/K_i}", model: "mock", cost: 0.0004, sent: sampleSent("latex") };
    case "requirements": return mockRequirementsProposal((args.guidelines as string[]) ?? []);
    case "style": return { markdown: "# Style guide\n\nShort, concrete sentences.", replacing: false, samples: 3, cost: 0.004 };
    case "describe_scene": return { prompt: "A rain-lit kitchen at 3 a.m., a terminal glowing behind smoked glass.", model: "mock", cost: 0.001 };
    case "image": case "image_regenerate": return { images: [], cost: 0.03 };
    default: return { cost: null };
  }
}

function aiStart(kind: string, args: Record<string, unknown>): object {
  const id = `mockjob-${++jobSeq}`;
  const body = kind === "generate" ? DRAFT : REPLY;
  jobs.set(id, { kind, args, started: Date.now(), cancelled: false, text: "", words: STREAM_KINDS.includes(kind) ? body.split(/(?<=\s)/) : [], sent: 0 });
  return { ok: true, job: id };
}

function aiPoll(id: string, since: number): object {
  const j = jobs.get(id);
  if (!j) return { ok: false, error: "no such job" };
  const elapsed = (Date.now() - j.started) / 1000;
  if (j.cancelled) return { ok: true, state: "cancelled", text: "", length: j.text.length, elapsed, cost: null };
  let text = "", done: boolean;
  if (j.words.length) {
    const n = Math.min(j.words.length, Math.floor((Date.now() - j.started) / WORD_MS));
    j.text = j.words.slice(0, n).join("");
    text = j.text.slice(since);
    done = n >= j.words.length;
  } else done = Date.now() - j.started >= QUIET_MS;
  const out = { ok: true, state: done ? "done" : "running", text, length: j.text.length, elapsed, cost: done ? 0.002 : null };
  return done ? { ...out, result: mockResult(j.kind, j.args) } : out;
}

function aiCancel(id: string): object {
  const j = jobs.get(id);
  if (j) j.cancelled = true;
  return { ok: true, state: "cancelled" };
}

// -- inspiration pictures: in memory only (the real store is inspiration/ on disk)
const pictures: (InspirationImage & { dataUrl: string })[] = [];
const MOCK_MIME: Record<string, "jpg" | "png" | "webp"> = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" };
const knownDoc = (id: unknown) => typeof id === "string" && (SCENES.some((s) => s.id === id) || ENTITIES.some((e) => e.id === id));
const imageRows = () => pictures.map(({ dataUrl: _d, ...row }) => row);

function uploadPicture(name: string, dataUrl: string, docId: unknown): object {
  const m = /^data:([^;,]*);base64,(.+)$/s.exec(dataUrl ?? "");
  const ext = m ? MOCK_MIME[m[1].toLowerCase()] : undefined;
  if (!ext) return { ok: false, error: "only JPG, PNG and WebP pictures can be added" };
  if (docId && !knownDoc(docId)) return { ok: false, error: `no such document: ${String(docId)}` };
  const title = (name.split(/[\\/]/).pop() ?? "").replace(/\.[A-Za-z0-9]{1,5}$/, "").trim() || "Added picture";
  const image: InspirationImage = {
    id: `${new Date().toISOString().replace(/\D/g, "").slice(0, 14)}-${slug(title) || "image"}-${pictures.length + 1}`, ext, prompt: "", model: "upload",
    for: docId ? String(docId) : "", scene: docId ? String(docId) : "", created: new Date().toISOString().slice(0, 19), cost: null,
    pinned: false, title, notes: "", label: title, source: "upload", unlinked: false,
  };
  pictures.unshift({ ...image, dataUrl });
  return { ok: true, image };
}

/** Two believable sources for the dev-only mock (research mode). */
const MOCK_SOURCES = [
  { key: "daneshgar2024", display: "Daneshgar et al. 2024", title: "Machine learning for wastewater process modeling: a review", authors: "Daneshgar, S.; Callejo, A.; Vanrolleghem, P.", year: 2024, venue: "Water Research", doi: "10.1016/j.watres.2024.00001", url: "https://doi.org/10.1016/j.watres.2024.00001", zoteroKey: "AB12CD34" },
  { key: "smith2023", display: "Smith and Lee 2023", title: "Rainfall-runoff prediction with recurrent networks", authors: "Smith, J.; Lee, K.", year: 2023, venue: "Journal of Hydrology", doi: "10.1016/j.jhydrol.2023.00002", url: "", zoteroKey: "EF56GH78" },
];

const MOCK_PROFILES = [
  { id: "ems", name: "Environmental Modelling & Software", publisher: "Elsevier", kind: "manuscript", source: "https://www.sciencedirect.com/journal/environmental-modelling-and-software/publish/guide-for-authors", readOn: "2026-10-01" },
  { id: "manuscript", name: "Research manuscript (no target journal)", publisher: "", kind: "manuscript", source: "", readOn: "" },
  { id: "proposal", name: "Research proposal (no specific funder)", publisher: "", kind: "proposal", source: "", readOn: "" },
];
const mockResearch = { kind: "manuscript", journal: "ems" };
const mockSettings = () => {
  const p = MOCK_PROFILES.find((x) => x.id === mockResearch.journal && x.kind === mockResearch.kind);
  return { ok: true, kind: mockResearch.kind, journal: p ? p.id : "", journalName: p?.name ?? "", citationStyle: "apa", source: p?.source ?? "", readOn: p?.readOn ?? "" };
};
const mockGuidelines = [
  { name: "ems-guide.pdf", type: "pdf", size: 183200, chars: 41210, extracted: true, message: "" },
  { name: "scanned-call.pdf", type: "pdf", size: 904100, chars: 0, extracted: false, message: "No text could be read from this PDF. It may be a scan." },
];

// -- Custom requirements (wave E): the contract of requirements_* with an in-memory requirements.toml.
let mockCustom: CustomRequirement[] = [];
/** Test hook: when set, requirements_custom returns it as `warning` (Python does that when the file has unreadable rows). */
export const mockCustomControl = { warning: "" };
const PLAIN_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const MOCK_CHECKS = ["section-present", "section-words-max", "section-no-citations", "list-count", "last-section",
  "objects-captioned", "objects-referenced", "citations-resolved", "sources-doi"];
/** Python's rules, roughly: a plain message naming the row, or "" when every row is fine. */
function validateCustom(rows: unknown): string {
  if (!Array.isArray(rows)) return "The requirements must be a list.";
  if (rows.length > 100) return "At most 100 requirements are allowed.";
  const seen = new Set<string>();
  for (const raw of rows as Partial<CustomRequirement>[]) {
    const name = `"${raw.title || raw.id || "a requirement"}"`;
    if (!raw.id || typeof raw.id !== "string" || !PLAIN_ID.test(raw.id) || seen.has(raw.id)) return `${name}: the id is missing, not plain or used twice.`;
    seen.add(raw.id);
    if (!raw.title || raw.title.length > 160 || raw.title.includes("\n")) return `${name}: the title must be one line of 1 to 160 characters.`;
    if (raw.kind === "advice") continue;
    if (raw.kind !== "check" || !raw.check || !MOCK_CHECKS.includes(raw.check)) return `${name}: this kind of check is not available.`;
    const need = ["section-present", "section-words-max", "section-no-citations", "list-count", "last-section"].includes(raw.check);
    if (need && (!raw.section || raw.section.length < 1 || raw.section.length > 6 || raw.section.some((s) => !s || s.length > 60)))
      return `${name}: give 1 to 6 section names of up to 60 characters.`;
    for (const key of ["min", "max"] as const) {
      const v = raw[key];
      if (v !== undefined && (!Number.isInteger(v) || v < 0 || v > 100000)) return `${name}: ${key} must be a whole number from 0 to 100000.`;
    }
    if (raw.item_chars_max !== undefined && (!Number.isInteger(raw.item_chars_max) || raw.item_chars_max < 1 || raw.item_chars_max > 10000))
      return `${name}: the character limit must be a whole number from 1 to 10000.`;
    if (raw.check === "section-words-max" && raw.max === undefined) return `${name}: a word limit is needed.`;
  }
  return "";
}
const mockCustomGroups = () => {
  const by = new Map<string, { id: string; title: string; status: string; message: string }[]>();
  for (const r of mockCustom) {
    const g = r.group || "Your requirements";
    by.set(g, [...(by.get(g) ?? []), r.kind === "advice"
      ? { id: r.id, title: r.title, status: "advice", message: r.title }
      : { id: r.id, title: r.title, status: "na", message: "Checked by the app against your paper." }]);
  }
  return [...by].map(([title, items]) => ({ title, items }));
};
/** A believable proposal; the last item's quote is not in any guideline, so the unverified path shows. */
function mockRequirementsProposal(names: string[]) {
  const source = names[0] ?? "ems-guide.pdf";
  const base = { group: "Your requirements", kind: "check" as const, severity: "warn" as const, source };
  const items: SuggestedRequirement[] = [
    { ...base, id: "abstract-150", title: "Abstract length", check: "section-words-max", section: ["abstract"], max: 150,
      quote: "The abstract must not exceed 150 words.", why: "The guide sets a hard limit on the abstract.", verified: true },
    { ...base, id: "keywords-count", title: "Keywords", check: "list-count", section: ["keywords"], min: 3, max: 6, item_chars_max: 40,
      quote: "Provide 3 to 6 keywords, each at most 40 characters.", why: "The guide asks for a short keyword list.", verified: true },
    { ...base, id: "figures-captioned", title: "Figure captions", check: "objects-captioned", object: "fig",
      quote: "Every figure needs a descriptive caption.", why: "The guide asks for captions on all figures.", verified: true },
    { ...base, id: "highlights-count", title: "Highlights", check: "list-count", section: ["highlights"], min: 3, max: 5,
      quote: "Include three to five highlights of at most 85 characters each.", why: "Journals of this publisher usually ask for highlights.", verified: false },
  ];
  return {
    items, cost: 0.003, model: "mock", sent: sampleSent("requirements"),
    dropped: [{ id: "tone", title: "Writing style", reason: "Not something the app can check (kind: tone)." }],
  };
}

// -- Outline assistant (wave D): the contract of outline_* with a small in-memory manuscript.
let mockScope = "";
const mockOutline = [
  ["abstract", "Abstract"], ["introduction", "Introduction"], ["methods", "Methods"], ["results", "Results"], ["discussion", "Discussion"],
].map(([slugName, title], i) => ({
  id: `manuscript/${String(i + 1).padStart(2, "0")}-${slugName}.md`, title, part: "", partTitle: "", frontMatter: i === 0, position: i + 1,
  words: 120 * (i + 1), purpose: "",
}));
const MOCK_OUTLINE_IGNORED = [{ title: "Appendix B", reason: "That section does not exist in the outline." }];
const mockOutlineItems = () => {
  const intro = mockOutline.find((s) => s.title === "Introduction");
  const results = mockOutline.find((s) => s.title === "Results");
  const discussion = mockOutline.find((s) => s.title === "Discussion");
  return [
    { id: "o1", action: "add", title: "Study area and data", part: "", after: intro?.id ?? "", purpose: "Describe the catchment and the data sets used.", why: "The scope names a data set the outline never introduces." },
    { id: "o2", action: "rename", title: "Methods", section: mockOutline.find((s) => s.title === "Methods")?.id ?? "", newTitle: "Materials and methods", why: "The target journal uses this heading." },
    { id: "o3", action: "move", title: "Discussion", section: discussion?.id ?? "", part: "", after: results?.id ?? "", why: "Discussion follows Results." },
    { id: "o4", action: "advice", title: "Consider a short limitations paragraph", why: "Reviewers for this journal usually ask for one." },
    { id: "o5", action: "keep", title: "Introduction", section: intro?.id ?? "", why: "Already fits." },
  ];
};
function mockOutlineApply(items: { id: string; action: string; title: string; section?: string; newTitle?: string; part?: string; after?: string; purpose?: string }[]) {
  const changed: string[] = [], created: string[] = [], skipped: { id: string; reason: string }[] = [], remap: Record<string, string> = {};
  type Row = (typeof mockOutline)[number];
  const place = (row: Row, part: string, after: string | undefined) => {
    row.partTitle = part; row.part = part ? `part-${slug(part)}` : "";
    const anchor = after ? mockOutline.findIndex((s) => s.id === after) : -1;
    if (anchor >= 0) mockOutline.splice(anchor + 1, 0, row);
    else if (!after) { const first = mockOutline.findIndex((s) => s.partTitle === part); mockOutline.splice(first >= 0 ? first : mockOutline.length, 0, row); }
    else mockOutline.push(row);
  };
  const renumber = () => mockOutline.forEach((s, n) => { s.position = n + 1; });
  for (const i of items) {
    const at = mockOutline.findIndex((s) => s.id === i.section);
    if (i.action === "add") {
      const id = `manuscript/${String(mockOutline.length + 1).padStart(2, "0")}-${slug(i.title)}.md`;
      place({ id, title: i.title, part: "", partTitle: "", frontMatter: false, position: 0, words: 0, purpose: i.purpose ?? "" }, i.part ?? "", i.after);
      created.push(id);
    } else if (at < 0) skipped.push({ id: i.id, reason: "That section no longer exists." });
    else if (i.action === "rename") { mockOutline[at].title = i.newTitle ?? mockOutline[at].title; changed.push(mockOutline[at].id); }
    else if (i.action === "move") {
      const [row] = mockOutline.splice(at, 1);
      const old = row.id;
      place(row, i.part ?? "", i.after);
      renumber();
      row.id = `manuscript/${String(row.position).padStart(2, "0")}-${slug(row.title)}.md`;
      remap[old] = row.id; changed.push(row.id);
    }
    renumber();
  }
  return { ok: true, changed, remap, skipped, created };
}

/** URLs passed to open_external in the mock (read by tests). */
export const openedUrls: string[] = [];

export function mockCall(method: string, args: unknown[]): object {
  switch (method) {
    case "ping": return { ok: true };
    case "research_profiles": return { ok: true, profiles: MOCK_PROFILES.map((p) => ({ ...p })) };
    case "research_get_settings": return mockSettings();
    case "research_set_settings": {
      const [kind, journal] = args as [string, string];
      const p = MOCK_PROFILES.find((x) => x.id === journal);
      if (journal && !p) return { ok: false, error: "Unknown journal profile." };
      if (p && p.kind !== kind) return { ok: false, error: "That profile is for a different kind of project." };
      mockResearch.kind = kind; mockResearch.journal = journal;
      return mockSettings();
    }
    case "research_requirements": return { ok: true, journal: "ems", name: "Environmental Modelling & Software", source: MOCK_PROFILES[0].source, readOn: "2026-10-01",
      summary: { ok: 2, warn: 1, info: 0, advice: 1 }, groups: [
        { title: "Structure", items: [
          { id: "abstract-words", title: "Abstract length", status: "ok", message: "The abstract has 218 words (limit 250)." },
          { id: "highlights", title: "Highlights", status: "warn", message: "No Highlights section found." },
        ] },
        { title: "Submission", items: [
          { id: "keywords", title: "Keywords", status: "ok", message: "5 keywords." },
          { id: "software-availability", title: "Software availability", status: "advice", message: "State where the software can be obtained, with its version." },
        ] },
      ].concat(mockCustomGroups()) };
    case "requirements_custom": return { ok: true, rows: structuredClone(mockCustom), ...(mockCustomControl.warning ? { warning: mockCustomControl.warning } : {}) };
    case "requirements_save": {
      const bad = validateCustom(args[0]);
      if (bad) return { ok: false, error: bad };
      mockCustom = structuredClone(args[0] as CustomRequirement[]);
      return { ok: true, rows: structuredClone(mockCustom) };
    }
    case "requirements_remove": {
      if (!mockCustom.some((r) => r.id === args[0])) return { ok: false, error: "There is no such requirement." };
      mockCustom = mockCustom.filter((r) => r.id !== args[0]);
      return { ok: true, rows: structuredClone(mockCustom) };
    }
    case "requirements_suggest": return { ok: true, ...mockRequirementsProposal((args[1] as string[]) ?? []) };
    case "guidelines_list": return { ok: true, files: mockGuidelines.map((g) => ({ ...g })) };
    case "guidelines_add": return { ok: true, added: [], skipped: [] };
    case "guidelines_add_text": {
      const text = String(args[1]);
      const name = String(args[0]).trim().replace(/\s+/g, "-") + ".md";
      mockGuidelines.push({ name, type: "note", size: text.length, chars: text.length, extracted: true, message: "" });
      return { ok: true, name };
    }
    case "guidelines_read": return { ok: true, name: String(args[0]), text: "Sample guideline text.", truncated: false, chars: 22 };
    case "outline_get_scope": return { ok: true, text: mockScope };
    case "outline_set_scope": mockScope = String(args[0] ?? ""); return { ok: true };
    case "outline_current": return { ok: true, kind: mockResearch.kind, journal: mockResearch.journal, journalName: mockSettings().journalName, sections: mockOutline.map((s) => ({ ...s })) };
    case "outline_standard": {
      const have = new Set(mockOutline.map((s) => s.title.toLowerCase()));
      const items = ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusions"].filter((t) => !have.has(t.toLowerCase()))
        .map((title, n) => ({ id: `s${n + 1}`, action: "add", title, part: "", after: mockOutline[mockOutline.length - 1].id, purpose: `The ${title.toLowerCase()} of the paper.`, why: "Part of the standard structure." }));
      return { ok: true, name: "Environmental Modelling & Software", items };
    }
    case "outline_suggest": return { ok: true, items: mockOutlineItems(), sent: sampleSent("outline"), cost: 0.002, model: "mock", dropped: MOCK_OUTLINE_IGNORED };
    case "outline_apply": return mockOutlineApply(args[0] as Parameters<typeof mockOutlineApply>[0]);
    case "guidelines_remove": { const i = mockGuidelines.findIndex((g) => g.name === args[0]); if (i >= 0) mockGuidelines.splice(i, 1); return { ok: true }; }
    case "zotero_collections": return { ok: true, collections: [
      { key: "AB12CD34", path: "AI and Computing / WRRI - AI and Process Modeling", items: 42, parent: null },
      { key: "EF56GH78", path: "Hydrology / Rainfall-runoff", items: null, parent: null },
    ] };
    case "zotero_saved_collections": return { ok: true, keys: [] };
    case "zotero_get_settings": case "zotero_set_settings": return { ok: true, userId: "", webBase: "https://api.zotero.org", local: true, localBase: "http://127.0.0.1:23119", file: "", keySet: false };
    case "zotero_set_key": return { ok: true, keySet: true };
    case "zotero_clear_key": return { ok: true, keySet: false };
    case "zotero_status": return { ok: true, keySet: false, backends: [
      { backend: "local", ok: true, message: "Zotero on this computer answered." },
      { backend: "web", ok: false, message: "No web API key is saved." },
    ] };
    case "zotero_sync_plan": return { ok: true, backend: "local", token: "mock-1", report: ["Read 3 items from Zotero on this computer."], rows: [
      { id: "src-1", key: "AB12CD34", action: "new", summary: "Add “Process modeling with machine learning” (Smith 2023)", blocked: "" },
      { id: "src-2", key: "EF56GH78", action: "changed", summary: "Title and year changed in Zotero", blocked: "" },
      { id: "src-3", key: "IJ90KL12", action: "key-mismatch", summary: "The note’s citation key differs from Zotero’s", blocked: "Fix the key in the note first" },
    ] };
    case "zotero_sync_apply": return { ok: true, changed: args[0] as string[], skipped: [], recorded: true };
    case "list_sources": return { ok: true, sources: MOCK_SOURCES.map((s) => ({ id: "entities/sources/" + s.key + ".md", name: s.display, title: s.title, key: s.key, status: "" })) };
    case "search_sources": {
      const words = String(args[0] ?? "").toLowerCase().split(/\s+/).filter(Boolean);
      const hit = (s: (typeof MOCK_SOURCES)[number]) => words.every((w) => [s.display, s.title, s.authors, String(s.year), s.key].join(" ").toLowerCase().includes(w));
      return { ok: true, sources: MOCK_SOURCES.filter(hit).slice(0, Number(args[1] ?? 30)) };
    }
    case "source_card": {
      const s = MOCK_SOURCES.find((x) => String(args[0]).includes(x.key));
      if (!s) return { ok: false, error: "No such source." };
      return { ok: true, ...s, citeAs: "[[@" + s.key + "]]", zoteroKey: s.zoteroKey, noteCount: 2, highlightCount: 5 };
    }
    case "zotero_item_collections": return { ok: true, collections: ["AI and Computing / WRRI - AI and Process Modeling"] };
    case "open_in_zotero": return { ok: true };
    case "open_external": openedUrls.push(String(args[0])); return { ok: true };
    case "ai_start": return aiStart(String(args[0]), (args[1] ?? {}) as Record<string, unknown>);
    case "ai_poll": return aiPoll(String(args[0]), Number(args[1] ?? 0));
    case "ai_cancel": return aiCancel(String(args[0]));
    case "get_workspace": {
      const ws = structuredClone(workspace);
      // research projects only: the Figures / Tables / Equations groups sit after the Notebook (Concepts) group
      if (ws?.project.mode === "research") {
        const at = ws.binder.findIndex((n) => n.id === "group:research" || n.id === "ph:research");
        ws.binder.splice(at < 0 ? ws.binder.length : at + 1, 0, ...mockObjectGroups());
      }
      return { ok: true, workspace: ws };
    }
    case "read_document": {
      const doc = readDocument(String(args[0]));
      return doc ? { ok: true, ...doc } : { ok: false, error: "no such document" };
    }
    case "save_document": {
      const scene = SCENES.find((x) => x.id === args[0]);
      if (scene) scene.text = String(args[1]);
      return { ok: true, saved: true, mtime: String(Date.now()), words: words(String(args[1])) };
    }
    case "document_mtime": return { ok: true, mtime: "0" };
    case "link_spans": return { ok: true, spans: [] };
    case "spelling": return { ok: true, enabled: false, spans: [] };
    case "spelling_suggestions": return { ok: true, suggestions: [] };
    case "add_to_dictionary": return { ok: true, added: true };
    case "ignore_word": return { ok: true };
    case "open_dictionary": return { ok: true, id: "dictionary.txt" };
    case "scene_context": {
      const scene = SCENES.find((x) => x.id === args[0]);
      return { ok: true, mentions: mentionsOf(String(args[1] ?? scene?.text ?? "")) };
    }
    case "list_entities": return { ok: true, entities: ENTITIES.map(({ body: _b, ...e }) => e) };
    case "get_entity": return { ok: true, ...getEntity(String(args[0])) };
    case "get_settings": return { ok: true, hasKey: true, keySource: "environment", editor: { zoom: 100, reflow: true }, spellcheck: true, autoSnapshot: true, dailyTarget: 500,
      imageStyle: "cinematic, atmospheric, no text, no watermark", imageStyleDefault: "cinematic, atmospheric, no text, no watermark",
      models: Object.fromEntries(["fast", "strong", "writing", "image"].map((k) => [k, { value: "", default: "default/model", effective: "default/model", projectOverride: "" }])) };
    case "set_settings": return { ok: true };
    case "get_atmosphere": return { ok: true, prefs: { typing: { on: false, pack: "typewriter", volume: 0.5 },
      ambience: { volume: 0.6, layers: {}, loops: {}, station: null, stationVolume: 0.6, presets: {} } },
      stations: [{ name: "Fluid (SomaFM): lo-fi, instrumental hip-hop", url: "https://ice1.somafm.com/fluid-128-mp3",
        attribution: { via: "SomaFM", text: "via SomaFM - listener-supported, consider supporting them", link: "https://somafm.com/support/" } }],
      packs: [], loops: [], soundsDir: "", ambienceDir: "" };
    case "set_atmosphere": return { ok: true, prefs: args[0] };
    case "ai_status": return { ok: true, hasKey: true, models: { fast: "", strong: "", writing: "", image: "" } };
    case "recent_projects": return { ok: true, recents: [] };
    case "list_inspiration": {
      if (args[0] && !knownDoc(args[0])) return { ok: false, error: `no such document: ${String(args[0])}` };
      const rows = imageRows();
      return { ok: true, images: rows, model: "", style: "", ...(args[0] ? { mine: rows.filter((i) => i.for === args[0]).map((i) => i.id) } : {}) };
    }
    case "upload_inspiration": return uploadPicture(String(args[0] ?? ""), String(args[1] ?? ""), args[2]);
    case "inspiration_image": {
      const p = pictures.find((x) => x.id === args[0]);
      return p ? { ok: true, dataUrl: p.dataUrl } : { ok: false, error: "no such inspiration image" };
    }
    case "style_status": return { ok: true, exists: false, learned: null, sampledWords: null,
      manuscriptWordsThen: null, manuscriptWords: 0, scenes: 0, stale: false };
    case "suggest_project_path": {
      const slug = String(args[0] ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      return { ok: true, path: slug ? `~/novels/${slug}` : "" };
    }
    case "open_project": case "new_project": workspace = buildWorkspace(); return { ok: true };
    case "choose_folder": return { ok: true, path: null };
    case "minimize": case "toggle_maximize": case "close": return { ok: true };
    default: return mockObjectsCall(method, args) ?? { ok: false, error: `${method} is not available without the Chisel core` };
  }
}

/** Dev / tests: make the mock project a research project, so the object groups appear in the binder. */
export function makeMockResearchProject() {
  if (workspace) workspace.project.mode = "research";
}
