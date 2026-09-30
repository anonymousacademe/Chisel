// Shape of the data the UI renders. Produced by lorewrite.gui.workspace (Python)
// or, for `npm run dev` without a core, by backend/mock.ts. Keep in sync with
// workspace.py; data/fixtures/workspace.json is checked on both sides.

export type BinderKind =
  | "project" | "folder" | "document" | "entity" | "style"
  | "characters" | "world" | "research" | "inbox" | "trash";

export interface BinderNode {
  id: string;
  title: string;
  kind: BinderKind;
  /** Right-aligned mono label: word count ("2.8k"), or an entity type. */
  meta?: string;
  /** Dimmed rows (e.g. Front Matter, Trash). */
  muted?: boolean;
  /** Shown as designed but not implemented: disabled, tooltip "Not in LoreWriter yet". */
  placeholder?: boolean;
  children?: BinderNode[];
  expanded?: boolean;
}

export interface SceneSummary {
  id: string;            // project-relative path: manuscript/02-blue-hour.md
  number: string;        // "02" (filename prefix, may be empty)
  title: string;
  words: number;
  excerpt: string;
  headings: string[];
}

export type EntityType = "character" | "place" | "object" | "faction";

export interface EntitySummary {
  id: string;            // project-relative path of the note
  name: string;
  type: EntityType;
  aliases: string[];
  words: number;
}

export type DocKind = "scene" | "entity" | "style";

/** One open file: the whole Markdown text plus what the title block needs. */
export interface DocumentPayload {
  id: string;
  kind: DocKind;
  title: string;
  kicker: string;        // "SCENE 02", "CHARACTER", "STYLE GUIDE"
  parent: string;        // breadcrumb parent: "Manuscript"
  text: string;
  mtime: string;         // ns since epoch, as a string (exceeds 2^53)
  words: number;
  mentions: SceneMention[];
}

/** An entity a scene mentions: how often here, and how many lines link to it project-wide. */
export interface SceneMention { name: string; type: EntityType; count: number; backlinks: number }

export interface Backlink {
  sourceId: string; sourceKind: "scene" | "entity"; sourceTitle: string; row: number; line: string;
}

/** What get_entity returns; `found: false` for a name with no note. */
export type EntityInfo =
  | { found: false; name: string }
  | {
    found: true; id: string; name: string; type: EntityType; aliases: string[];
    body: string; canon: string; summary: string; backlinks: Backlink[];
  };

export interface Workspace {
  project: { title: string; author: string; initials: string; path: string; documentCount: number };
  binder: BinderNode[];
  scenes: SceneSummary[];
  entities: EntitySummary[];
  status: {
    projectWords: number;
    /** Net words since the project was opened (may be negative). */
    sessionWords: number;
    sessionMinutes: number;
    aiCost: number;
    hasStyle: boolean;
  };
}

export interface RecentProject { path: string; title: string; openedAt: number; exists: boolean }

export interface ContinuityInsight { title: string; conflicts: number; body: string }

export interface RetrievedSource { id: string; kind: "character" | "document"; title: string; meta: string }

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; intro?: string; text: string };
