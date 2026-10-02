/** Shared state for typing sounds and ambience: what the status bar, the panel and Settings show.
 *  Preferences persist through the bridge (user settings); *playing* never does, so the app
 *  always starts silent. */
import { useSyncExternalStore } from "react";
import { api } from "../backend/api";
import { CUSTOM_PREFIX, DEFAULT_PREFS, type AtmosphereInfo, type Prefs, type Station } from "../data/atmosphere";
import { audioContext } from "./context";
import { ambience } from "./ambience";
import { configureTyping, loadCustomPack } from "./typing";

export interface AtmoState {
  loaded: boolean;
  info: AtmosphereInfo;
  /** Layers and loops are audible (the play button). */
  playing: boolean;
  station: "idle" | "loading" | "playing" | "error";
  stationDetail: string;
  error: string;
}

const EMPTY: AtmosphereInfo = { prefs: DEFAULT_PREFS, stations: [], packs: [], loops: [], soundsDir: "", ambienceDir: "" };
let state: AtmoState = { loaded: false, info: EMPTY, playing: false, station: "idle", stationDetail: "", error: "" };
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const set = (patch: Partial<AtmoState>) => { state = { ...state, ...patch }; emit(); };

export const useAtmosphere = (): AtmoState => useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; }, () => state);
export const atmosphereState = () => state;

ambience.onStationState = (s, detail) => set({ station: s, stationDetail: detail ?? "" });

const loopBuffers = new Map<string, AudioBuffer>();
async function loadLoop(id: string): Promise<AudioBuffer | null> {
  const cached = loopBuffers.get(id);
  if (cached) return cached;
  const c = audioContext();
  if (!c) return null;
  const r = await api.ambienceLoop(id);
  if (!r.ok) { set({ error: r.error }); return null; }
  try {
    const buf = await c.decodeAudioData(await (await fetch(r.dataUrl)).arrayBuffer());
    loopBuffers.set(id, buf);
    return buf;
  } catch { set({ error: `Could not play “${id}”` }); return null; }
}

function applyAmbience(): void {
  const a = state.info.prefs.ambience;
  ambience.setMix(state.playing, a.volume, a.layers, a.loops, loadLoop);
}

async function ensureCustomPack(pack: string): Promise<void> {
  if (!pack.startsWith(CUSTOM_PREFIX)) return;
  const r = await api.soundPack(pack.slice(CUSTOM_PREFIX.length));
  if (!r.ok) return set({ error: r.error });
  await loadCustomPack(r.id, r.sounds, r.volume);
}

let saveTimer: ReturnType<typeof setTimeout> | null = null;
function persist(): void {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { void api.setAtmosphere(state.info.prefs).then((r) => { if (!r.ok) set({ error: r.error }); }); }, 400);
}

function update(prefs: Prefs): void {
  set({ info: { ...state.info, prefs } });
  persist();
}

export const atmosphere = {
  async load(): Promise<void> {
    const r = await api.getAtmosphere();
    if (!r.ok) return set({ loaded: true, error: r.error });
    const { typing } = r.prefs;
    set({ loaded: true, info: r, error: "" });
    configureTyping(typing.on, typing.pack, typing.volume);
    if (typing.on) void ensureCustomPack(typing.pack);
  },
  setTyping(patch: Partial<Prefs["typing"]>): void {
    const prefs = state.info.prefs;
    const typing = { ...prefs.typing, ...patch };
    update({ ...prefs, typing });
    configureTyping(typing.on, typing.pack, typing.volume);
    if (typing.on && (patch.pack !== undefined || patch.on !== undefined)) void ensureCustomPack(typing.pack);
  },
  setAmbience(patch: Partial<Prefs["ambience"]>): void {
    const prefs = state.info.prefs;
    update({ ...prefs, ambience: { ...prefs.ambience, ...patch } });
    applyAmbience();
    if (patch.stationVolume !== undefined && state.station !== "idle") ambience.setStation(state.info.prefs.ambience.station, true, patch.stationVolume);
  },
  setLayer(id: string, volume: number): void {
    const a = state.info.prefs.ambience;
    const layers = { ...a.layers };
    if (volume > 0) layers[id] = volume; else delete layers[id];
    // moving a slider up starts the sound: the author asked for it
    this.setAmbience({ layers });
    if (volume > 0 && !state.playing) this.play(true);
  },
  setLoop(id: string, volume: number): void {
    const a = state.info.prefs.ambience;
    const loops = { ...a.loops };
    if (volume > 0) loops[id] = volume; else delete loops[id];
    this.setAmbience({ loops });
    if (volume > 0 && !state.playing) this.play(true);
  },
  play(on: boolean): void {
    set({ playing: on });
    applyAmbience();
  },
  /** Pick a station (its stream starts now) or stop the current one (null). */
  pickStation(url: string | null): void {
    const a = state.info.prefs.ambience;
    update({ ...state.info.prefs, ambience: { ...a, station: url } });
    ambience.setStation(url, true, a.stationVolume);
  },
  stopStation(): void {
    ambience.setStation(null, false, 0);
  },
  /** Pause everything audible; layers and station both. */
  pauseAll(): void {
    set({ playing: false });
    applyAmbience();
    ambience.setStation(null, false, 0);
  },
  savePreset(name: string): void {
    const n = name.trim().slice(0, 40);
    if (!n) return;
    const a = state.info.prefs.ambience;
    update({ ...state.info.prefs, ambience: { ...a, presets: { ...a.presets, [n]: { ...a.layers } } } });
  },
  loadPreset(name: string): void {
    const mix = state.info.prefs.ambience.presets[name];
    if (mix) { this.setAmbience({ layers: { ...mix } }); if (Object.keys(mix).length) this.play(true); }
  },
  deletePreset(name: string): void {
    const a = state.info.prefs.ambience;
    const presets = { ...a.presets };
    delete presets[name];
    update({ ...state.info.prefs, ambience: { ...a, presets } });
  },
  async saveStations(stations: Station[] | null): Promise<string | null> {
    const r = await api.setStations(stations ? stations.map(({ name, url }) => ({ name, url })) : null);
    if (!r.ok) return r.error;
    set({ info: { ...state.info, stations: r.stations } });
    return null;
  },
  async refreshPacks(): Promise<void> {
    const r = await api.getAtmosphere();
    if (r.ok) set({ info: { ...state.info, packs: r.packs, loops: r.loops } });
  },
  async importPack(): Promise<string> {
    const r = await api.importSoundPack();
    if (!r.ok) return r.error;
    set({ info: { ...state.info, packs: r.packs } });
    return r.imported ? `Imported “${r.imported.id}”.` : "";
  },
  async exportPack(pack: string): Promise<string> {
    const r = await api.exportSoundPack(pack);
    if (!r.ok) return r.error;
    return r.path ? `Saved ${r.path}` : "";
  },
  stateChangedHidden(hidden: boolean): void { ambience.setHidden(hidden); },
};

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => atmosphere.stateChangedHidden(document.hidden));
}
