// Which system voice reads which role (narrator, quoted speech, each script character), and the reader's
// settings. Voices differ from machine to machine, so this lives in the browser's local storage for the project
// (a per-viewer convenience), not in project.toml; a voice that is no longer installed falls back to a default.
import { DEFAULT_READ_OPTIONS, type ReadOptions, type VoiceInfo } from "./types";

const KEY = "chisel.reader";

export interface ReaderPrefs {
  rate: number;
  options: ReadOptions;
  /** project path -> { voice role -> system voice id } */
  casts: Record<string, Record<string, string>>;
}

export const DEFAULT_PREFS: ReaderPrefs = { rate: 1, options: DEFAULT_READ_OPTIONS, casts: {} };

function store(): Storage | null {
  try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; }
}

export function loadPrefs(storage: Pick<Storage, "getItem"> | null = store()): ReaderPrefs {
  try {
    const raw = storage?.getItem(KEY);
    if (!raw) return { ...DEFAULT_PREFS, casts: {} };
    const p = JSON.parse(raw) as Partial<ReaderPrefs>;
    const rate = typeof p.rate === "number" && p.rate >= 0.5 && p.rate <= 3 ? p.rate : 1;
    const options = { ...DEFAULT_READ_OPTIONS };
    for (const k of Object.keys(options) as (keyof ReadOptions)[]) if (typeof p.options?.[k] === "boolean") options[k] = p.options[k];
    const casts: ReaderPrefs["casts"] = {};
    for (const [proj, cast] of Object.entries(p.casts ?? {})) {
      if (cast && typeof cast === "object") casts[proj] = Object.fromEntries(Object.entries(cast).filter(([, v]) => typeof v === "string"));
    }
    return { rate, options, casts };
  } catch {
    return { ...DEFAULT_PREFS, casts: {} };
  }
}

export function savePrefs(p: ReaderPrefs, storage: Pick<Storage, "setItem"> | null = store()): void {
  try { storage?.setItem(KEY, JSON.stringify(p)); } catch { /* private window, quota: the choice is just not remembered */ }
}

/** Voices in the language of the interface first (all of them when none match); the suggested ones (a *rank*)
 * first, then installed-on-this-machine first, then by name. */
export function candidateVoices(voices: VoiceInfo[], lang = typeof navigator !== "undefined" ? navigator.language : "en"): VoiceInfo[] {
  const base = lang.toLowerCase().split("-")[0];
  const mine = voices.filter((v) => v.lang.toLowerCase().startsWith(base));
  const rank = (v: VoiceInfo) => v.rank ?? Number.MAX_SAFE_INTEGER;
  return [...(mine.length ? mine : voices)].sort((a, b) =>
    rank(a) - rank(b) || Number(b.local) - Number(a.local) || a.name.localeCompare(b.name));
}

/** Where a project's cast is kept: the system voices under the project path (as before), others per engine. */
export function castKey(project: string, engine: string): string {
  return engine === "browser" ? project : `${project}\u0000${engine}`;
}

/** A voice for every role: the narrator the first candidate, the other roles the following ones in turn, so
 * the voices differ for as long as the system has enough of them. */
export function defaultCast(roles: string[], voices: VoiceInfo[], lang?: string): Record<string, string> {
  const pool = candidateVoices(voices, lang);
  if (!pool.length) return {};
  const cast: Record<string, string> = {};
  let n = 1;
  for (const role of roles) cast[role] = role === "narrator" ? pool[0].id : pool[(n++) % pool.length].id;
  return cast;
}

/** *saved* choices where that voice is still installed, defaults for every other role. */
export function resolveCast(saved: Record<string, string> | undefined, roles: string[], voices: VoiceInfo[], lang?: string): Record<string, string> {
  const ids = new Set(voices.map((v) => v.id));
  const fallback = defaultCast(roles, voices, lang);
  const cast: Record<string, string> = {};
  for (const role of roles) {
    const pick = saved?.[role];
    if (pick && ids.has(pick)) cast[role] = pick;
    else if (fallback[role]) cast[role] = fallback[role];
  }
  return cast;
}

/** What a role is called in the voices list. */
export function roleLabel(role: string): string {
  return role === "narrator" ? "Narrator" : role === "quote" ? "Quoted speech" : role;
}
