import type { Workspace, BinderNode, ManuscriptDocument } from "./types";

// Sample content taken verbatim from the Figma design, so the default screen
// matches it exactly. Replace it with real project data via the backend.

const chapter = (id: string, n: string, title: string, meta: string, extra: Partial<BinderNode> = {}): BinderNode =>
  ({ id, title: `${n}  ${title}`, kind: "document", meta, ...extra });

const binder: BinderNode[] = [
  {
    id: "project", title: "The Meridian Archive", kind: "project", meta: "42.7k", expanded: true,
    children: [
      { id: "front", title: "Front Matter", kind: "folder", muted: true, children: [
        { id: "title-page", title: "Title Page", kind: "document", meta: "0.1k" },
      ] },
      { id: "part1", title: "Part I — The Recall", kind: "folder", meta: "17k", expanded: true, children: [
        chapter("ch01", "01", "The Rain Index", "2.8k"),
        chapter("ch02", "02", "Blue Hour Protocol", "3.1k"),
        chapter("ch03", "03", "The Cartographer", "2.5k"),
        chapter("ch04", "04", "Borrowed Weather", "3.4k"),
        chapter("ch05", "05", "Negative Space", "2.9k"),
        chapter("ch06", "06", "The House Below", "2.3k"),
      ] },
      { id: "part2", title: "Part II — Ghost Frequency", kind: "folder", meta: "14k", expanded: true, children: [
        chapter("ch07", "07", "A City That Remembers", "1.9k"),
        chapter("ch08", "08", "Salt in the Signal", "2.2k"),
        chapter("ch09", "09", "The Other Mara", "2.7k"),
        chapter("ch10", "10", "Meridian Zero", "1.4k"),
        chapter("ch11", "11", "Memory Palace", "notes", { kind: "notes", muted: true }),
      ] },
      { id: "part3", title: "Part III — Afterimage", kind: "folder", meta: "11k", children: [
        chapter("ch12", "12", "Low Tide Archive", "3.0k"),
      ] },
    ],
  },
  { id: "characters", title: "Characters", kind: "characters", children: [
    { id: "mara", title: "Mara Vale", kind: "document" },
    { id: "elias", title: "Elias Vale", kind: "document" },
  ] },
  { id: "world", title: "World Bible", kind: "world", children: [
    { id: "meridian", title: "Lower Meridian", kind: "document" },
  ] },
  { id: "research", title: "Research", kind: "research", meta: "18", children: [] },
  { id: "unplaced", title: "Unplaced Scenes", kind: "inbox", meta: "4", children: [] },
  { id: "trash", title: "Trash", kind: "trash", muted: true },
];

const ch07: ManuscriptDocument = {
  id: "ch07",
  number: "Chapter Seven",
  shortLabel: "Chapter 07",
  title: "A City That Remembers",
  parentTitle: "Part II — Ghost Frequency",
  sceneMeta: "Mara Vale · Lower Meridian · 03:17 · Thirty-six hours after the recall",
  status: "Revising",
  words: 1942,
  target: 2400,
  paragraphs: [
    { id: "p1", text: "The city woke before Mara did. It moved beneath the floorboards in small electrical sighs, drawing yesterday’s rain back through the copper veins of the building. By three seventeen, every window on Vesper Street had clouded from the inside." },
    { id: "p2", text: "She stood in the kitchen with one hand around a cup gone cold and listened to the municipal archive remembering itself. First came the tram bells from a line decommissioned twenty years ago. Then the market vendors, calling prices in the old coastal dialect. Last, almost too softly to separate from the pipes, came her brother’s voice." },
    { id: "p3", revised: true, text: "“Mara,” the wall said, in a voice the wall had no right to know. Not a recording. Recordings kept their distance. This breath caught on the second syllable exactly as Elias’s always had." },
    { id: "p4", text: "Mara set the cup down. Across the room, the archive terminal pulsed once behind its smoked glass. The waveform on its display was flat, but the room continued speaking around it: cupboards ticking open, the radiator knocking out a childhood code, rain lifting in silver threads from the sill." },
    { id: "p5", text: "She had spent six years proving that memory was only architecture—rooms built by chemistry, corridors narrowed by grief. Now the city had found the door she had buried and was knocking from the other side." },
  ],
  inspector: [
    { label: "Status", value: "Revision · Draft 2", accent: true },
    { label: "POV / Place", value: "Mara · Lower Meridian" },
    { label: "Scene purpose", value: "First contact with Elias signal" },
    { label: "Session", value: "+638 words · 46 min" },
  ],
};

export const mockWorkspace: Workspace = {
  project: { title: "The Meridian Archive", draft: "Draft 2", author: "E. Rourke", initials: "ER", documentCount: 34 },
  binder,
  collections: [
    { id: "c1", title: "Needs continuity pass", color: "var(--lw-warning)", count: 7 },
    { id: "c2", title: "Mara's arc", color: "var(--lw-accent)", count: 12 },
  ],
  activeDocumentId: "ch07",
  documents: { ch07 },
  assistant: {
    insight: {
      title: "Continuity check",
      conflicts: 1,
      body: "Elias’s voice catches on the second syllable here. In Ch. 3, Mara recalls his stammer only appearing on words beginning with M.",
    },
    messages: [
      { id: "m1", role: "user", text: "Give me three ways the city could answer Mara without using another voice." },
      {
        id: "m2", role: "assistant",
        intro: "Three options that preserve the scene’s quiet dread:",
        text: "1. The streetlights blink Elias’s childhood knock pattern.\n2. Condensation writes coordinates on the glass.\n3. Every clock skips backward to his time of death.",
      },
    ],
    sources: [
      { id: "s1", kind: "character", title: "Elias Vale — character sheet", meta: "World Bible · updated yesterday" },
      { id: "s2", kind: "document", title: "Chapter 03 · The Cartographer", meta: "Passage at ¶ 18 · 82% relevant" },
    ],
  },
  status: {
    snapshot: "12 min ago",
    synced: true,
    streakDays: 12,
    sessionWords: 638,
    sessionTarget: 1000,
    sessionMinutes: 46,
    projectWords: 42680,
  },
};

/** Blank document for binder items that have no content in the mock. */
export function placeholderDocument(node: BinderNode, parentTitle: string): ManuscriptDocument {
  const m = node.title.match(/^(\d+)\s+(.*)$/);
  return {
    id: node.id,
    number: m ? `Chapter ${m[1]}` : node.kind === "document" ? "Document" : "Notes",
    shortLabel: m ? `Chapter ${m[1]}` : node.title,
    title: m ? m[2] : node.title,
    parentTitle,
    sceneMeta: "No scene metadata yet",
    status: "Draft",
    words: 0,
    target: 2400,
    paragraphs: [],
    inspector: [
      { label: "Status", value: "Draft", accent: true },
      { label: "POV / Place", value: "—" },
      { label: "Scene purpose", value: "—" },
      { label: "Session", value: "+0 words · 0 min" },
    ],
  };
}
