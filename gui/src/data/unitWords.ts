import type { Unit } from "./types";

/** The project's display word for a manuscript unit (scene / chapter / section). Wording only. */
export interface UnitWords { one: string; many: string; One: string; Many: string }

export function unitWords(unit: string): UnitWords {
  const one = unit === "chapter" || unit === "section" ? unit : "scene";
  const One = one.charAt(0).toUpperCase() + one.slice(1);
  return { one, many: `${one}s`, One, Many: `${One}s` };
}

/** The unit the toggle switches to: story and script flip scene/chapter, research flips section/chapter. */
export function otherUnit(unit: string, mode: string): Unit {
  const first: Unit = mode === "research" ? "section" : "scene";
  return unit === "chapter" ? first : "chapter";
}

/** Rewrite the word "scene(s)" in a fixed sentence to the project's unit; scene projects get the text unchanged. */
export function unitText(text: string, unit: string): string {
  if (unit === "scene" || !unit) return text;
  const w = unitWords(unit);
  return text.replace(/\bscenes\b/g, w.many).replace(/\bscene\b/g, w.one)
    .replace(/\bScenes\b/g, w.Many).replace(/\bScene\b/g, w.One);
}
