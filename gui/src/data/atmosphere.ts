/** Pure helpers and shared types for typing sounds and the ambience radio (audio lives in ../audio). */

export type KeyClass = "key" | "space" | "return" | "backspace";

/** Which sound a keydown makes (null: none, e.g. arrows, shortcuts, IME composition). */
export function keyClass(e: { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; isComposing?: boolean }): KeyClass | null {
  if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return null;
  if (e.key === " ") return "space";
  if (e.key === "Enter") return "return";
  if (e.key === "Backspace" || e.key === "Delete") return "backspace";
  return e.key.length === 1 || (e.key.length === 2 && e.key.codePointAt(0)! > 0xffff) ? "key" : null;
}

export const BUILTIN_PACKS = [
  { id: "typewriter", name: "Typewriter" },
  { id: "clicky", name: "Mechanical — clicky" },
  { id: "thocky", name: "Mechanical — thocky" },
] as const;
export const CUSTOM_PREFIX = "custom:";

export const LAYERS = [
  { id: "rain", name: "Rain" },
  { id: "ocean", name: "Ocean" },
  { id: "wind", name: "Wind" },
  { id: "forest", name: "Forest birds" },
  { id: "fire", name: "Fireplace" },
  { id: "cafe", name: "Café murmur (approximate)" },
  { id: "brown", name: "Brown noise" },
  { id: "pink", name: "Pink noise" },
  { id: "white", name: "White noise" },
  { id: "drone", name: "Meditative drone" },
] as const;
export type LayerId = (typeof LAYERS)[number]["id"];

export interface Station { name: string; url: string; attribution?: { via: string; text: string; link: string } | null }
export interface Prefs {
  typing: { on: boolean; pack: string; volume: number };
  ambience: { volume: number; layers: Record<string, number>; loops: Record<string, number>; station: string | null; stationVolume: number; presets: Record<string, Record<string, number>> };
}
export interface PackRow { id: string; name: string; volume: number; files: number }
export interface LoopRow { id: string; name: string }
export interface AtmosphereInfo {
  prefs: Prefs; stations: Station[]; packs: PackRow[]; loops: LoopRow[]; soundsDir: string; ambienceDir: string;
}

export const DEFAULT_PREFS: Prefs = {
  typing: { on: false, pack: "typewriter", volume: 0.5 },
  ambience: { volume: 0.6, layers: {}, loops: {}, station: null, stationVolume: 0.6, presets: {} },
};

/** http(s) only, mirroring the Python check (core/atmosphere.valid_url). */
export function validStationUrl(raw: string): string | null {
  const url = raw.trim();
  if (!url || url.length > 300 || /\s/.test(url)) return null;
  try {
    const u = new URL(url);
    return (u.protocol === "http:" || u.protocol === "https:") && u.hostname ? url : null;
  } catch { return null; }
}

/** Layers and loops with a volume above zero, in the order they should be listed. */
export function activeCount(a: Prefs["ambience"]): number {
  return Object.values(a.layers).filter((v) => v > 0).length + Object.values(a.loops).filter((v) => v > 0).length;
}

/** Volume as the gain actually applied (squared: perceived loudness is not linear). */
export const gainOf = (v: number) => Math.max(0, Math.min(1, v)) ** 2;

/** What the ambience button says. */
export function ambienceLabel(playing: boolean, stationName: string | null, layers: number): string {
  if (!playing) return "Ambience";
  if (stationName && layers) return `${stationName} + ${layers}`;
  if (stationName) return stationName;
  return layers === 1 ? "1 layer" : `${layers} layers`;
}
