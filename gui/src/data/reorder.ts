// Pure planning for drag-to-reorder (corkboard cards and outline rows). The
// move itself is done by Python (core.structure.place_scene); this only decides
// which part and position a drop means, and words the confirmation.
import type { PartSummary, SceneSummary } from "./types";

/** Where scenes live: a part, the top level (partId null) or Unplaced. */
export interface Group {
  key: string;                 // "part:manuscript/01-x" | "top" | "unplaced"
  partId: string | null;       // null for the top level and for Unplaced
  unplaced: boolean;
  title: string;
  frontMatter: boolean;
  scenes: SceneSummary[];
}

/** Scenes grouped as the book reads: top level, parts (front matter first), then Unplaced when asked. */
export function sceneGroups(scenes: SceneSummary[], parts: PartSummary[], opts: { unplaced?: boolean; unit?: string } = {}): Group[] {
  const out: Group[] = [];
  const top = scenes.filter((s) => s.part === null && !s.unplaced);
  if (top.length || parts.length === 0) {
    out.push({ key: "top", partId: null, unplaced: false, title: parts.length ? "Manuscript" : "", frontMatter: false, scenes: top });
  }
  for (const p of parts) {
    out.push({
      key: p.id, partId: p.id, unplaced: false, title: p.title, frontMatter: p.frontMatter,
      scenes: scenes.filter((s) => s.part === p.id),
    });
  }
  if (opts.unplaced) {
    const un = scenes.filter((s) => s.unplaced);
    if (un.length) out.push({ key: "unplaced", partId: null, unplaced: true, title: "Parked scenes", frontMatter: false, scenes: un });
  }
  return out;
}

/** A drop: before a card, or at the end of a group. */
export type Drop = { kind: "before"; sceneId: string } | { kind: "end"; groupKey: string };

export interface MovePlan {
  sceneId: string;
  /** Destination: part id (null = top level) or Unplaced. */
  partId: string | null;
  unplaced: boolean;
  /** 0-based index among the destination's scenes without the moved one; null = the end. */
  index: number | null;
  /** 1-based position the scene will have, for the sentence. */
  position: number;
  /** Where it came from, so the move can be undone. */
  from: { partId: string | null; unplaced: boolean; index: number };
  sameGroup: boolean;
  sentence: string;
}

const label = (g: Group) => (g.unplaced ? "Parked scenes" : g.partId ? g.title : "the top level");

/**
 * Plan moving *sourceId* to *drop*, or null when the drop changes nothing
 * (back where it was, or onto itself).
 */
export function planMove(groups: Group[], sourceId: string, drop: Drop): MovePlan | null {
  const src = groups.find((g) => g.scenes.some((s) => s.id === sourceId));
  const scene = src?.scenes.find((s) => s.id === sourceId);
  if (!src || !scene) return null;
  const fromIndex = src.scenes.findIndex((s) => s.id === sourceId);
  let dest: Group | undefined;
  let index: number | null = null;
  if (drop.kind === "before") {
    if (drop.sceneId === sourceId) return null;
    dest = groups.find((g) => g.scenes.some((s) => s.id === drop.sceneId));
    if (!dest) return null;
    index = dest.scenes.filter((s) => s.id !== sourceId).findIndex((s) => s.id === drop.sceneId);
  } else {
    dest = groups.find((g) => g.key === drop.groupKey);
    if (!dest) return null;
  }
  const rest = dest.scenes.filter((s) => s.id !== sourceId).length;
  const sameGroup = dest.key === src.key;
  const at = index ?? rest;
  if (sameGroup && at === fromIndex) return null;
  const position = at + 1;
  const where = sameGroup ? `position ${position} in ${label(dest)}` : `${label(dest)}, position ${position}`;
  return {
    sceneId: sourceId, partId: dest.partId, unplaced: dest.unplaced, index,
    position, from: { partId: src.partId, unplaced: src.unplaced, index: fromIndex }, sameGroup,
    sentence: `Move “${scene.title}” to ${where}?`,
  };
}

/** Follow a scene id through a rename map (the open document keeps the right file). */
export function follow(id: string, remap: Record<string, string> | undefined): string {
  return remap?.[id] ?? id;
}
