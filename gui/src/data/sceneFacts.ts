import type { SceneSummary } from "./types";
import { fmt } from "./tree";

/** Suggested status values (free text is allowed too). */
export const SUGGESTED_STATUS = ["idea", "draft", "revising", "done"];

/** "1,942 / 2,400" when the scene has a word target, else just the words. */
export function wordsLabel(s: Pick<SceneSummary, "words" | "details">) {
  return s.details.target ? `${fmt(s.words)} / ${fmt(s.details.target)}` : fmt(s.words);
}

/** The small caps label above a card: "SCENE 07", "CHAPTER 07", "FRONT MATTER", "UNPLACED". */
export function kickerOf(s: Pick<SceneSummary, "number" | "frontMatter" | "unplaced">, unit: string) {
  if (s.frontMatter) return "FRONT MATTER";
  if (s.unplaced) return "UNPLACED";
  return s.number ? `${unit.toUpperCase()} ${s.number}` : unit.toUpperCase();
}
