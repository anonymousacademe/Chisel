/** Ambience: offline layers generated with Web Audio (no files, no network), optional user loop
 *  files, and one internet station. Nothing starts until the author clicks play or picks a
 *  station; every change fades. */
import { audioContext, existingContext, noiseBuffer, type NoiseKind } from "./context";
import { gainOf, LAYERS } from "../data/atmosphere";

const FADE = 0.8; // seconds

type Stop = () => void;
interface Running { gain: GainNode; stop: Stop; killer?: ReturnType<typeof setTimeout> }

const noises = new Map<NoiseKind, AudioBuffer>();
function noiseOf(c: AudioContext, kind: NoiseKind): AudioBuffer {
  let b = noises.get(kind);
  if (!b || b.sampleRate !== c.sampleRate) { b = noiseBuffer(c, 8, kind); noises.set(kind, b); }
  return b;
}
function loopNoise(c: AudioContext, kind: NoiseKind, out: AudioNode, chain: AudioNode[] = []): AudioBufferSourceNode {
  const s = c.createBufferSource();
  s.buffer = noiseOf(c, kind); s.loop = true;
  let prev: AudioNode = s;
  for (const n of chain) { prev.connect(n); prev = n; }
  prev.connect(out);
  s.start(0, Math.random() * 6);
  return s;
}
const filter = (c: AudioContext, type: BiquadFilterType, hz: number, q = 0.7) => {
  const f = c.createBiquadFilter(); f.type = type; f.frequency.value = hz; f.Q.value = q; return f;
};
const gainNode = (c: AudioContext, v: number) => { const g = c.createGain(); g.gain.value = v; return g; };
/** A slow oscillator that wobbles a parameter around its current value. */
function lfo(c: AudioContext, hz: number, depth: number, target: AudioParam): OscillatorNode {
  const o = c.createOscillator(); o.frequency.value = hz;
  const g = gainNode(c, depth);
  o.connect(g); g.connect(target); o.start();
  return o;
}
/** Run `fn` at random intervals (seconds) until stopped. */
function scheduler(min: number, max: number, fn: () => void): Stop {
  let alive = true;
  let t: ReturnType<typeof setTimeout>;
  const next = () => { t = setTimeout(() => { if (!alive) return; try { fn(); } catch { /* ignore */ } next(); }, (min + Math.random() * (max - min)) * 1000); };
  next();
  return () => { alive = false; clearTimeout(t); };
}
function burst(c: AudioContext, out: AudioNode, type: BiquadFilterType, hz: number, q: number, decay: number, level: number): void {
  const t = c.currentTime;
  const s = c.createBufferSource(); s.buffer = noiseOf(c, "white");
  const f = filter(c, type, hz, q);
  const g = c.createGain();
  g.gain.setValueAtTime(level, t); g.gain.exponentialRampToValueAtTime(0.0001, t + decay);
  s.connect(f); f.connect(g); g.connect(out);
  s.start(t, Math.random() * 6, decay + 0.02);
}
function chirp(c: AudioContext, out: AudioNode): void {
  const t = c.currentTime;
  const o = c.createOscillator(); o.type = "sine";
  const base = 2600 + Math.random() * 2400;
  o.frequency.setValueAtTime(base, t);
  o.frequency.exponentialRampToValueAtTime(base * (1.2 + Math.random() * 0.5), t + 0.07);
  o.frequency.exponentialRampToValueAtTime(base * 0.9, t + 0.12);
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.5, t + 0.015); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.13);
  o.connect(g); g.connect(out); o.start(t); o.stop(t + 0.15);
}

type Builder = (c: AudioContext, out: AudioNode) => Stop;
const stopAll = (nodes: (AudioScheduledSourceNode | Stop)[]): Stop => () => {
  for (const n of nodes) { try { if (typeof n === "function") n(); else n.stop(); } catch { /* already stopped */ } }
};

const BUILDERS: Record<string, Builder> = {
  rain: (c, out) => {
    const bed = loopNoise(c, "white", out, [filter(c, "highpass", 700), filter(c, "lowpass", 8000), gainNode(c, 0.35)]);
    const sheet = loopNoise(c, "pink", out, [filter(c, "bandpass", 2500, 0.5), gainNode(c, 0.5)]);
    const drops = scheduler(0.03, 0.15, () => burst(c, out, "bandpass", 3000 + Math.random() * 4000, 3, 0.012, 0.05 + Math.random() * 0.08));
    return stopAll([bed, sheet, drops]);
  },
  ocean: (c, out) => {
    const swell = gainNode(c, 0.5);
    swell.connect(out);
    const n = loopNoise(c, "brown", swell, [filter(c, "lowpass", 650)]);
    const l = lfo(c, 0.09, 0.35, swell.gain);
    const hiss = gainNode(c, 0.06);
    hiss.connect(out);
    const h = loopNoise(c, "pink", hiss, [filter(c, "highpass", 1500)]);
    const l2 = lfo(c, 0.09, 0.05, hiss.gain);
    return stopAll([n, l, h, l2]);
  },
  wind: (c, out) => {
    const band = filter(c, "bandpass", 500, 1.1);
    const g = gainNode(c, 0.8);
    band.connect(g); g.connect(out);
    const n = c.createBufferSource(); n.buffer = noiseOf(c, "pink"); n.loop = true; n.connect(band); n.start(0, Math.random() * 6);
    const a = lfo(c, 0.06, 260, band.frequency);
    const b = lfo(c, 0.11, 0.25, g.gain);
    return stopAll([n, a, b]);
  },
  forest: (c, out) => {
    const breeze = loopNoise(c, "pink", out, [filter(c, "lowpass", 500), gainNode(c, 0.25)]);
    const birds = scheduler(1.2, 5, () => {
      const count = 1 + Math.floor(Math.random() * 3);
      for (let i = 0; i < count; i++) setTimeout(() => { if (c.state === "running") chirp(c, out); }, i * (110 + Math.random() * 90));
    });
    return stopAll([breeze, birds]);
  },
  fire: (c, out) => {
    const rumble = loopNoise(c, "brown", out, [filter(c, "lowpass", 280), gainNode(c, 0.7)]);
    const crackle = scheduler(0.03, 0.5, () => burst(c, out, "bandpass", 1200 + Math.random() * 4500, 1.5, 0.01 + Math.random() * 0.03, 0.15 + Math.random() * 0.5));
    return stopAll([rumble, crackle]);
  },
  cafe: (c, out) => {
    // An approximation of room murmur: noise shaped into the speech band with slow swells, plus
    // the odd cup clink. It is not real conversation.
    const g1 = gainNode(c, 0.55), g2 = gainNode(c, 0.35);
    g1.connect(out); g2.connect(out);
    const a = loopNoise(c, "pink", g1, [filter(c, "bandpass", 500, 0.8)]);
    const b = loopNoise(c, "pink", g2, [filter(c, "bandpass", 1700, 0.6)]);
    const l1 = lfo(c, 0.31, 0.2, g1.gain), l2 = lfo(c, 0.17, 0.15, g2.gain);
    const clink = scheduler(4, 12, () => {
      const t = c.currentTime;
      const o = c.createOscillator(); o.type = "sine"; o.frequency.value = 3800 + Math.random() * 1500;
      const g = c.createGain();
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.06, t + 0.003); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
      o.connect(g); g.connect(out); o.start(t); o.stop(t + 0.2);
    });
    return stopAll([a, b, l1, l2, clink]);
  },
  brown: (c, out) => stopAll([loopNoise(c, "brown", out, [gainNode(c, 0.9)])]),
  pink: (c, out) => stopAll([loopNoise(c, "pink", out, [gainNode(c, 0.8)])]),
  white: (c, out) => stopAll([loopNoise(c, "white", out, [gainNode(c, 0.35)])]),
  drone: (c, out) => {
    const lp = filter(c, "lowpass", 900);
    const g = gainNode(c, 0.16);
    lp.connect(g); g.connect(out);
    const oscs: OscillatorNode[] = [];
    for (const [hz, det] of [[110, 0], [110, 6], [164.81, -4], [220.5, 3], [329.6, -7]] as const) {
      const o = c.createOscillator(); o.type = "sine"; o.frequency.value = hz; o.detune.value = det;
      const og = gainNode(c, hz > 200 ? 0.3 : 1);
      o.connect(og); og.connect(lp); o.start(); oscs.push(o);
    }
    return stopAll([...oscs, lfo(c, 0.05, 0.08, g.gain), lfo(c, 0.03, 250, lp.frequency)]);
  },
};

export const LAYER_IDS: string[] = LAYERS.map((l) => l.id);

export class AmbienceEngine {
  private master: GainNode | null = null;
  private running = new Map<string, Running>();
  private audio: HTMLAudioElement | null = null;
  private stationFade: ReturnType<typeof setInterval> | null = null;
  private wantStation = false;
  onStationState: (s: "idle" | "loading" | "playing" | "error", detail?: string) => void = () => {};

  private ctx(): AudioContext | null {
    const c = audioContext();
    if (!c) return null;
    if (!this.master || this.master.context !== c) {
      this.master = c.createGain(); this.master.connect(c.destination);
    }
    return c;
  }

  /** Bring the layers to *levels* (id -> 0..1); layers at 0 fade out and stop. `loopLevels` likewise for loop files. */
  setMix(on: boolean, volume: number, levels: Record<string, number>, loopLevels: Record<string, number>, loadLoop: (id: string) => Promise<AudioBuffer | null>): void {
    const c = this.ctx();
    if (!c || !this.master) return;
    this.master.gain.setTargetAtTime(gainOf(volume), c.currentTime, 0.1);
    const wanted = new Map<string, number>();
    if (on) {
      for (const [id, v] of Object.entries(levels)) if (BUILDERS[id] && v > 0) wanted.set(id, v);
      for (const [id, v] of Object.entries(loopLevels)) if (v > 0) wanted.set(`loop:${id}`, v);
    }
    for (const [key, r] of this.running) {
      if (!wanted.has(key)) {
        r.gain.gain.setTargetAtTime(0, c.currentTime, FADE / 3);
        r.killer = setTimeout(() => { r.stop(); r.gain.disconnect(); }, FADE * 1000 + 100);
        this.running.delete(key);
      }
    }
    for (const [key, v] of wanted) {
      const level = gainOf(v);
      const have = this.running.get(key);
      if (have) { have.gain.gain.setTargetAtTime(level, c.currentTime, FADE / 3); continue; }
      const g = c.createGain(); g.gain.value = 0; g.connect(this.master);
      if (key.startsWith("loop:")) {
        const id = key.slice(5);
        const placeholder: Running = { gain: g, stop: () => {} };
        this.running.set(key, placeholder);
        void loadLoop(id).then((buf) => {
          if (!buf || this.running.get(key) !== placeholder) return;
          const s = c.createBufferSource(); s.buffer = buf; s.loop = true; s.connect(g); s.start();
          placeholder.stop = () => { try { s.stop(); } catch { /* stopped */ } };
          g.gain.setTargetAtTime(level, c.currentTime, FADE / 3);
        });
        continue;
      }
      const stop = BUILDERS[key](c, g);
      g.gain.setTargetAtTime(level, c.currentTime, FADE / 3);
      this.running.set(key, { gain: g, stop });
    }
  }

  /** Play (url) or fade out and stop (null) the internet station. Only ever called from a click. */
  setStation(url: string | null, on: boolean, volume: number): void {
    const want = on && !!url;
    if (!want) {
      this.wantStation = false;
      if (this.audio) this.fadeStation(0, () => { if (this.audio && !this.wantStation) { this.audio.pause(); this.audio.removeAttribute("src"); this.audio.load(); } });
      this.onStationState("idle");
      return;
    }
    this.wantStation = true;
    const a = this.audio ?? (this.audio = new Audio());
    a.preload = "none";
    a.onerror = () => { if (this.wantStation) this.onStationState("error", "The station could not be reached"); };
    a.onplaying = () => this.onStationState("playing");
    a.onwaiting = () => { if (this.wantStation) this.onStationState("loading"); };
    if (a.getAttribute("src") !== url) {
      a.src = url!; a.volume = 0;
      this.onStationState("loading");
      a.play().catch((e) => { if (this.wantStation) this.onStationState("error", e instanceof Error ? e.message : "could not play"); });
    } else if (a.paused) {
      a.play().catch(() => this.onStationState("error", "could not play"));
    }
    this.fadeStation(gainOf(volume));
  }

  private fadeStation(target: number, done?: () => void): void {
    const a = this.audio;
    if (!a) return;
    if (this.stationFade) clearInterval(this.stationFade);
    const start = a.volume, steps = 16;
    let i = 0;
    this.stationFade = setInterval(() => {
      i++;
      a.volume = Math.max(0, Math.min(1, start + (target - start) * (i / steps)));
      if (i >= steps) { clearInterval(this.stationFade!); this.stationFade = null; done?.(); }
    }, (FADE * 1000) / steps);
  }

  /** The window was hidden or shown again: stop spending CPU/network while nobody is listening. */
  setHidden(hidden: boolean): void {
    const c = existingContext();
    if (c) void (hidden ? c.suspend() : c.resume());
    if (this.audio && this.wantStation) {
      if (hidden) this.audio.pause();
      else this.audio.play().catch(() => this.onStationState("error", "could not resume"));
    }
  }
}

export const ambience = new AmbienceEngine();
