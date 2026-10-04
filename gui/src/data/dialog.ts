import type { AliasSuggestion, AttachItem, CanonProposal, SentReport as SentInfo, SettingsInfo, SyncInfo } from "./types";
import type { MovePlan } from "./reorder";

/** The one open modal dialog of the app (null: none). */
export type Dialog =
  | { kind: "new-scene" }
  | { kind: "rename" }
  | { kind: "delete" }
  | { kind: "new-part" }
  | { kind: "rename-part"; id: string; title: string }
  | { kind: "delete-part"; id: string; title: string }
  | { kind: "pick-part"; sceneId: string; unplaced: boolean }
  | { kind: "move"; plan: MovePlan }
  | { kind: "trash" }
  | { kind: "details" }
  | { kind: "snapshots" }
  | { kind: "export" }
  | { kind: "stats" }
  | { kind: "sound" }
  | { kind: "sprint" }
  | { kind: "stop-sprint" }
  | { kind: "collections" }
  | { kind: "new-research" }
  | { kind: "notebook" }
  | { kind: "chats" }
  | { kind: "attach"; items: AttachItem[]; maxWords: number; maxItems: number }
  | { kind: "research-url"; url: string }
  | { kind: "delete-research" }
  | { kind: "add-comment"; from: number; to: number; quote: string }
  | { kind: "scene-collections" }
  | { kind: "new-draft" }
  | { kind: "sync-commit"; info: Extract<SyncInfo, { repo: true }> }
  | { kind: "sync-push"; info: Extract<SyncInfo, { repo: true }> }
  | { kind: "sync-init" }
  | { kind: "new-note"; name: string; openAfter: boolean }
  | { kind: "generate"; mode: "draft" | "rewrite"; from: number; to: number; title: string; label: string; initial: string }
  | { kind: "aliases"; items: AliasSuggestion[]; sent?: SentInfo }
  | { kind: "sent"; report: SentInfo }
  | { kind: "rename-note"; name: string; aliases: string[] }
  | { kind: "canon"; items: CanonProposal[]; sent?: SentInfo }
  | { kind: "style"; markdown: string; replacing: boolean }
  | { kind: "settings"; info: SettingsInfo }
  | null;
