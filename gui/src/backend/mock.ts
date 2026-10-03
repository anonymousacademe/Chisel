// In-memory stand-in for the Python core, used only by `npm run dev` in a
// plain browser (no pywebview, no devserver). Same JSON bridge contract as
// lorewrite.gui.api.Api; methods it does not implement return an error so the
// UI shows "not available" instead of inventing results.
import type { BinderNode, DocumentPayload, EntityInfo, EntitySummary, InspirationImage, SceneMention, SceneSummary, SentReport, Workspace } from "../data/types";

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
    project: { title: "The Meridian Archive", author: "", initials: "LW", path: "/mock", documentCount: scenes.length + ENTITIES.length, unit: "scene", draft: 1 },
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

/** URLs passed to open_external in the mock (read by tests). */
export const openedUrls: string[] = [];

export function mockCall(method: string, args: unknown[]): object {
  switch (method) {
    case "ping": return { ok: true };
    case "open_external": openedUrls.push(String(args[0])); return { ok: true };
    case "ai_start": return aiStart(String(args[0]), (args[1] ?? {}) as Record<string, unknown>);
    case "ai_poll": return aiPoll(String(args[0]), Number(args[1] ?? 0));
    case "ai_cancel": return aiCancel(String(args[0]));
    case "get_workspace": return { ok: true, workspace: structuredClone(workspace) };
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
    default: return { ok: false, error: `${method} is not available without the Chisel core` };
  }
}
