// Shape of the data the UI renders. The backend (mock or Tauri) returns a Workspace.

export type BinderKind =
  | "project" | "folder" | "document" | "notes"
  | "characters" | "world" | "research" | "inbox" | "trash";

export interface BinderNode {
  id: string;
  title: string;
  kind: BinderKind;
  /** Right-aligned mono label: word count ("2.8k"), item count, or "notes". */
  meta?: string;
  /** Dimmed rows (e.g. Front Matter, Trash, notes-only docs). */
  muted?: boolean;
  children?: BinderNode[];
  expanded?: boolean;
}

export interface Collection { id: string; title: string; color: string; count: number }

export interface Paragraph {
  id: string;
  text: string;
  /** Marked as a revised passage (violet rule on the left). */
  revised?: boolean;
}

export interface ManuscriptDocument {
  id: string;
  number: string;          // "Chapter Seven"
  shortLabel: string;      // "Chapter 07"
  title: string;
  parentTitle: string;
  sceneMeta: string;
  status: string;          // tag in the context bar, e.g. "Revising"
  words: number;
  target: number;
  paragraphs: Paragraph[];
  inspector: { label: string; value: string; accent?: boolean }[];
}

export interface ContinuityInsight { title: string; conflicts: number; body: string }

export interface RetrievedSource { id: string; kind: "character" | "document"; title: string; meta: string }

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; intro?: string; text: string };

export interface Workspace {
  project: { title: string; draft: string; author: string; initials: string; documentCount: number };
  binder: BinderNode[];
  collections: Collection[];
  activeDocumentId: string;
  documents: Record<string, ManuscriptDocument>;
  assistant: {
    insight?: ContinuityInsight;
    messages: ChatMessage[];
    sources: RetrievedSource[];
  };
  status: {
    snapshot: string;
    synced: boolean;
    streakDays: number;
    sessionWords: number;
    sessionTarget: number;
    sessionMinutes: number;
    projectWords: number;
  };
}
