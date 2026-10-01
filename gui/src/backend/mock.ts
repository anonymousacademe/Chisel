// In-memory stand-in for the Python core, used only by `npm run dev` in a
// plain browser (no pywebview, no devserver). Same JSON bridge contract as
// lorewrite.gui.api.Api; methods it does not implement return an error so the
// UI shows "not available" instead of inventing results.
import type { BinderNode, DocumentPayload, EntityInfo, EntitySummary, SceneMention, SceneSummary, Workspace } from "../data/types";

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
  const text = `# ${title}\n\n${body || "(Mock scene — connect the LoreWriter core to see real prose.)"}\n`;
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
  }));
  const total = scenes.reduce((n, s) => n + s.words, 0);
  const ent = (e: EntitySummary): BinderNode => ({ id: e.id, title: e.name, kind: "entity" });
  return {
    project: { title: "The Meridian Archive", author: "", initials: "LW", path: "/mock", documentCount: scenes.length + ENTITIES.length },
    binder: [
      { id: "project", title: "The Meridian Archive", kind: "project", meta: k(total), expanded: true, children: [
        ph("front", "Front Matter"),
        { id: "group:manuscript", title: "Manuscript", kind: "folder", meta: k(total), expanded: true,
          children: scenes.map((s) => ({ id: s.id, title: `${s.number}  ${s.title}`, kind: "document" as const, meta: k(s.words) })) },
        ph("part1", "Part I"), ph("part2", "Part II"), ph("part3", "Part III"),
      ] },
      { id: "group:characters", title: "Characters", kind: "characters", children: ENTITIES.filter((e) => e.type === "character").map(ent) },
      { id: "group:world", title: "World Bible", kind: "world",
        children: ENTITIES.filter((e) => e.type !== "character").map((e) => ({ ...ent(e), meta: e.type })) },
      ph("research", "Research", "research"), ph("unplaced", "Unplaced Scenes", "inbox"), ph("trash", "Trash", "trash"),
    ],
    scenes,
    entities: ENTITIES.map(({ body: _b, ...e }) => e),
    status: { projectWords: total, sessionWords: 0, sessionMinutes: 0, aiCost: 0, hasStyle: false },
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
  return { found: true, id: e.id, name: e.name, type: e.type, aliases: e.aliases, body: e.body, canon: "", summary: e.body, backlinks: [] };
}

function readDocument(id: string): DocumentPayload | null {
  const s = SCENES.find((x) => x.id === id);
  if (s) {
    return { id, kind: "scene", title: s.title, kicker: `SCENE ${s.number}`, parent: "Manuscript", text: s.text,
      mtime: "0", words: words(s.text), mentions: mentionsOf(s.text) };
  }
  const e = ENTITIES.find((x) => x.id === id);
  if (e) {
    return { id, kind: "entity", title: e.name, kicker: e.type.toUpperCase(), parent: "Notes", text: noteText(e), mtime: "0", words: e.words, mentions: [] };
  }
  return null;
}

export function mockCall(method: string, args: unknown[]): object {
  switch (method) {
    case "ping": return { ok: true };
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
    case "scene_context": {
      const scene = SCENES.find((x) => x.id === args[0]);
      return { ok: true, mentions: mentionsOf(String(args[1] ?? scene?.text ?? "")) };
    }
    case "list_entities": return { ok: true, entities: ENTITIES.map(({ body: _b, ...e }) => e) };
    case "get_entity": return { ok: true, ...getEntity(String(args[0])) };
    case "get_settings": return { ok: true, hasKey: false, keySource: "none", editor: { zoom: 100, reflow: true },
      models: Object.fromEntries(["fast", "strong", "writing"].map((k) => [k, { value: "", default: "default/model", effective: "default/model", projectOverride: "" }])) };
    case "set_settings": return { ok: true };
    case "ai_status": return { ok: true, hasKey: false, models: { fast: "", strong: "", writing: "" } };
    case "recent_projects": return { ok: true, recents: [] };
    case "style_status": return { ok: true, exists: false, learned: null, sampledWords: null,
      manuscriptWordsThen: null, manuscriptWords: 0, scenes: 0, stale: false };
    case "suggest_project_path": {
      const slug = String(args[0] ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      return { ok: true, path: slug ? `~/novels/${slug}` : "" };
    }
    case "open_project": case "new_project": workspace = buildWorkspace(); return { ok: true };
    case "choose_folder": return { ok: true, path: null };
    case "minimize": case "toggle_maximize": case "close": return { ok: true };
    default: return { ok: false, error: `${method} is not available without the LoreWriter core` };
  }
}
