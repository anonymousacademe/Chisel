// Shape of the data the UI renders. Produced by lorewrite.gui.workspace (Python)
// or, for `npm run dev` without a core, by backend/mock.ts. Keep in sync with
// workspace.py; data/fixtures/workspace.json is checked on both sides.

export type BinderKind =
  | "project" | "folder" | "part" | "document" | "entity" | "style" | "dictionary"
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

/** A scene's own details, stored as its YAML frontmatter ("" / null = unset). */
export interface SceneDetails {
  pov: string; place: string; purpose: string; status: string;
  target: number | null;
  collections: string[];
}
export type DetailsPatch = Partial<Omit<SceneDetails, "target">> & { target?: number | string | null };

export interface SceneSummary {
  id: string;            // project-relative path: manuscript/02-blue-hour.md
  number: string;        // "02": global across parts; empty for front matter / unplaced
  title: string;
  words: number;
  excerpt: string;
  headings: string[];
  part: string | null;   // "part:manuscript/01-the-recall", null = top level or unplaced
  frontMatter: boolean;
  unplaced: boolean;
  details: SceneDetails;
}

/** A part of the book (a folder under manuscript/), in book order. */
export interface PartSummary {
  id: string;            // "part:manuscript/01-the-recall"
  title: string;
  frontMatter: boolean;
  words: number;
  sceneIds: string[];
}

export type Unit = "scene" | "chapter";

/** A note in the project's research/ folder (`folder` = its subfolder, "" at the top). */
export interface ResearchSummary { id: string; title: string; words: number; folder: string }

/** The design's swatch tokens (core/collections.py COLORS). */
export type CollectionColor = "violet" | "amber" | "green" | "red" | "gray";
/** A named group of scenes; membership is each scene's own frontmatter. */
export interface CollectionSummary {
  name: string; color: CollectionColor;
  /** false = scenes use the name but project.toml does not define it (grey until recoloured). */
  declared: boolean; count: number; sceneIds: string[];
}

export type EntityType = "character" | "place" | "object" | "faction";

export interface EntitySummary {
  id: string;            // project-relative path of the note
  name: string;
  type: EntityType;
  aliases: string[];
  words: number;
}

export type DocKind = "scene" | "entity" | "style" | "dictionary" | "research";

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
  // scenes only
  details?: SceneDetails;
  /** UTF-16 offset where the prose starts: [0, bodyStart) is the hidden frontmatter block. */
  bodyStart?: number;
  partId?: string | null;
  frontMatter?: boolean;
  unplaced?: boolean;
  /** ISO local time of the scene's latest snapshot, null if none. */
  snapshotAt?: string | null;
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

export type RenameScope = "scenes" | "entities" | "research" | "comments";
export interface RenameOccurrence { id: string; kind: string; line: number; pre: string; before: string; after: string; post: string; inDraft: boolean; defaultOn: boolean }
export interface RenameFile { file: string; kind: string; title: string; occurrences: RenameOccurrence[] }
/** rename_preview: nothing is written until rename_apply. */
export interface RenamePreview { plan: string; name: string; newName: string; aliases: string[]; files: RenameFile[]; newId: string }
export interface RenameDone { undoId: string; replacements: number; scenes: number; changed: string[]; remap: Record<string, string>; id: string; name: string }
export interface RenameUndone { restored: string[]; skipped: string[]; id: string }

export interface Workspace {
  project: { title: string; author: string; initials: string; path: string; documentCount: number; unit: Unit; draft: number };
  binder: BinderNode[];
  scenes: SceneSummary[];
  parts: PartSummary[];
  collections: CollectionSummary[];
  /** Research notes (research/**.md) in folder order; the binder shows them as a tree. */
  research: ResearchSummary[];
  entities: EntitySummary[];
  status: {
    projectWords: number;
    /** Net words since the project was opened (may be negative). */
    sessionWords: number;
    sessionMinutes: number;
    aiCost: number;
    hasStyle: boolean;
    trashCount: number;
    /** Writing stats for the status bar (null without a project). */
    stats: StatsBrief | null;
  };
}

/** A focus sprint in progress (core.stats.Tracker.sprint_state); times are epoch seconds. */
export interface SprintState { minutes: number; startedAt: number; endsAt: number; remaining: number; words: number; done: boolean }
/** A finished sprint as recorded in the day's stats. */
export interface SprintRecord { at: string; minutes: number; elapsed: number; words: number; completed: boolean }

export interface StatsBrief {
  /** Daily word target; 0 = off. */
  target: number;
  streak: number;
  todayMet: boolean;
  /** Net words written today, all sessions (accepted AI drafts are not counted). */
  todayWords: number;
  sprint: SprintState | null;
}

/** The Session stats page (core.stats.Tracker.summary). */
export interface StatsSummary {
  target: number; streak: number; todayMet: boolean;
  today: { words: number; aiWords: number; minutes: number; sessions: number };
  session: { words: number; aiWords: number; minutes: number; startedAt: number };
  chart: { date: string; words: number }[];
  averagePerSession: number;
  bestDay: { date: string; words: number } | null;
  daysWritten: number; totalWords: number; projectWords: number;
  sprints: SprintRecord[];
  sprint: SprintState | null;
}

/** What the "Your style" card shows (lorewrite.core.style.style_info). */
export interface StyleStatus {
  exists: boolean; learned: string | null; sampledWords: number | null;
  manuscriptWordsThen: number | null; manuscriptWords: number; scenes: number; stale: boolean;
}

export interface RecentProject { path: string; title: string; openedAt: number; exists: boolean }

/** One continuity problem the AI reported for a scene. */
export interface Issue {
  key: string;            // stable id, used to waive it
  type: string;           // physical_attribute, timeline, ...
  severity: "error" | "warning" | "note";
  entity: string;
  evidence: string;       // quoted from the scene
  fix: string;
  row: number | null;     // 0-based line of the evidence in the editor text, if found
}

export interface AliasSuggestion { entity: string; surface: string; alias: string; before: string; after: string }

export interface CanonProposal { entity: string; facts: string[]; evidence: string; existing: string }

export interface GenerateResult {
  mode: "draft" | "expand" | "rewrite";
  insert: string;         // the wrapped <!--ai--> text to put in the editor
  draftId: string | null;
  original: string | null;
  from: number;           // range of the editor text that `insert` replaces (UTF-16)
  to: number;
  noStyle: boolean;
  model: string;
  cost: number | null;
}

export interface DraftEdit { from: number; to: number; insert: string }

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string; error?: boolean; stopped?: boolean; sources?: ChatSource[]; ideas?: string[] };
/** A saved conversation (.assistant/chats/), newest activity first in lists. */
export interface ChatSummary { id: string; title: string; created: string; updated: string; count: number }
export interface SavedChat {
  id: string; title: string; created: string; updated: string; scope: "scene" | "project";
  attachments: { kind: AttachKind; id: string }[];
  messages: { id: string; role: "user" | "assistant"; text: string; error?: boolean; sources?: ChatSource[]; ideas?: string[] }[];
}
export type AttachKind = "scene" | "note" | "research" | "comments";
/** Something the paperclip can add to a chat's context; `words` is approximate. */
export interface AttachItem { kind: AttachKind; id: string; title: string; words: number; count?: number; detail?: string }
/** What the chat reports back about its attachments: nothing is trimmed or dropped silently. */
export interface AttachReport { kind: AttachKind; id: string; title: string; chars: number; truncated: boolean; skipped: boolean; reason?: string }

/** A research note a Research answer was given; `index` is its citation number [n]. */
export interface ChatSource { id: string; title: string }

export type ModelKind = "fast" | "strong" | "writing" | "image";
export interface EditorPrefs { zoom: number; reflow: boolean }
export interface ModelChoice { value: string; default: string; effective: string; projectOverride: string }
export interface SettingsInfo {
  hasKey: boolean;
  keySource: "environment" | "keyring" | "none";
  models: Record<ModelKind, ModelChoice>;
  editor: EditorPrefs;
  /** Underline misspellings (shared with the terminal app). */
  spellcheck: boolean;
  /** Snapshot a scene the first time it is edited each day. */
  autoSnapshot: boolean;
  /** Daily word target; 0 = off. */
  dailyTarget: number;
  /** Appended to every image prompt (empty = off) and the built-in default. */
  imageStyle: string;
  imageStyleDefault: string;
}
export interface ModelOption { id: string; name: string; promptPerM: number | null; completionPerM: number | null; context: number | null; imagePrice?: number | null }

/** An inspiration picture (inspiration/<id>.jpg|png + its .md sidecar); `scene` is a scene id or "". */
export interface InspirationImage {
  id: string; ext: "jpg" | "png" | "webp"; prompt: string; model: string; scene: string;
  created: string; cost: number | null; pinned: boolean; title: string; notes: string; label: string;
}

/** An author comment anchored to a passage (core.comments); offsets are UTF-16, null when detached. */
export interface CommentRow {
  id: string; quote: string; prefix: string; suffix: string; body: string;
  created: string; resolved: boolean; detached: boolean;
  start: number | null; end: number | null; row: number | null;
}

/** A scene or research note in the Trash; `original` is its path in the part (scene) or in the project (research). */
export interface TrashItem { name: string; title: string; kind: "scene" | "research" | "inspiration"; original: string; deleted: string }

/** One snapshot of a scene (`delta` = words now minus words then). */
export interface SnapshotRow { id: string; label: string; when: string; words: number; delta: number }

/** A run of a word diff (`old` joined = the snapshot, `new` joined = the current text). */
export interface DiffSegment { op: "equal" | "delete" | "insert" | "replace"; old: string; new: string }

/** Git state of the project folder; `null` (no git installed) hides the status item. */
export type SyncInfo =
  | { repo: false; canInit: boolean; label: string }
  | {
    repo: true; canInit: false; state: "synced" | "changes" | "ahead"; label: string;
    changes: number; scenes: number; ahead: number; behind: number; branch: string;
    remote: string | null; canPush: boolean; remoteUrl: string; toplevel: string; defaultMessage: string;
  };

/** {old id: new id} of files a rename/move touched, so open documents can follow. */
export type Remap = Record<string, string>;
