import type { CollectionColor, CollectionSummary, SceneSummary } from "./types";

export const COLLECTION_COLORS: CollectionColor[] = ["violet", "amber", "green", "red", "gray"];

const VARS: Record<CollectionColor, string> = {
  violet: "var(--lw-accent)", amber: "var(--lw-warning)", green: "var(--lw-success)",
  red: "var(--lw-danger)", gray: "var(--lw-text-muted)",
};
export const swatchVar = (c: CollectionColor) => VARS[c] ?? VARS.gray;

/** Ids of the scenes in the collection named *name* (empty when it does not exist). */
export function memberIds(collections: CollectionSummary[], name: string | null): Set<string> | null {
  if (name === null) return null;
  return new Set(collections.find((c) => c.name === name)?.sceneIds ?? []);
}

/** The scenes that stay visible under a collection filter. */
export const inCollection = (scenes: SceneSummary[], name: string | null) =>
  name === null ? scenes : scenes.filter((s) => s.details.collections.includes(name));
