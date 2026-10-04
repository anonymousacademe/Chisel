import type { ChatMessage, EntityType, SceneSummary } from "./types";

export const NOTE_TYPES: EntityType[] = ["character", "place", "object", "faction"];

/** "SCENE" -> "Scene" (kickers come upper-cased from Python). */
export const sentence = (s: string) => s[0] + s.slice(1).toLowerCase();

/** Messages worth saving: failed answers are never stored. */
export const keptMessages = (messages: ChatMessage[]): ChatMessage[] =>
  messages.filter((m) => !(m.role === "assistant" && m.error));

/** The scene to open when there is none current: the first real placed scene, else the first of any kind. */
export function firstScene<T extends Pick<SceneSummary, "frontMatter" | "unplaced">>(scenes: T[] | undefined): T | undefined {
  return scenes?.find((s) => !s.frontMatter && !s.unplaced) ?? scenes?.[0];
}

/** The " (AI $0.0123)" suffix of a notice; nothing when the call reported no cost. */
export const cost = (c: number | null | undefined) => (c != null ? ` (AI $${c.toFixed(4)})` : "");

/** How a running AI job is shown: a pending draft, a streamed chat answer, or a plain progress strip. */
export const aiRunMode = (kind: string, streamingKinds: readonly string[]): "draft" | "chat" | "strip" =>
  kind === "generate" ? "draft" : streamingKinds.includes(kind) ? "chat" : "strip";

/** The assistant message shown when a request failed or was stopped (never saved: it carries `error`). */
export const failedMessage = (id: string, stopped: boolean): ChatMessage => (stopped
  ? { id, role: "assistant", text: "(stopped)", error: true, stopped: true }
  : { id, role: "assistant", text: "That request failed. Nothing was changed.", error: true });
