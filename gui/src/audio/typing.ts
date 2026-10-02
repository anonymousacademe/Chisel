/** Typing sounds: synthesised in the browser (Web Audio) or taken from a custom pack folder.
 *  Plays on editor keydown only, off by default, and never blocks typing: every call is
 *  wrapped, and the buffers are made before the first key that needs them. */
import { audioContext, noiseBuffer } from "./context";
import { CUSTOM_PREFIX, gainOf, keyClass, type KeyClass } from "../data/atmosphere";

interface Voice {
  /** Filtered noise burst. */
  noise: { type: BiquadFilterType; hz: number; q: number; decay: number; level: number };
  /** Optional resonant tone (a thunk, a bell). */
  tone?: { type: OscillatorType; hz: number; end: number; decay: number; level: number };
  /** Optional second click (the key bottoming out), seconds after the first. */
  second?: number;
}
type PackVoices = Record<KeyClass, Voice>;

const v = (type: BiquadFilterType, hz: number, q: number, decay: number, level: number, tone?: Voice["tone"], second?: number): Voice =>
  ({ noise: { type, hz, q, decay, level }, tone, second });

export const SYNTH: Record<string, PackVoices> = {
  typewriter: {
    key: v("bandpass", 2600, 1.2, 0.045, 0.9, { type: "sine", hz: 190, end: 110, decay: 0.05, level: 0.5 }),
    space: v("bandpass", 1300, 0.9, 0.07, 1, { type: "sine", hz: 120, end: 70, decay: 0.09, level: 0.7 }),
    return: v("bandpass", 900, 0.7, 0.16, 0.8, { type: "sine", hz: 2350, end: 2350, decay: 0.7, level: 0.22 }, 0.03),
    backspace: v("bandpass", 2000, 1, 0.04, 0.7, { type: "sine", hz: 160, end: 100, decay: 0.045, level: 0.4 }),
  },
  clicky: {
    key: v("highpass", 3600, 0.8, 0.014, 1, { type: "square", hz: 4200, end: 3800, decay: 0.008, level: 0.1 }, 0.035),
    space: v("highpass", 2400, 0.8, 0.02, 1, { type: "square", hz: 3000, end: 2600, decay: 0.012, level: 0.1 }, 0.045),
    return: v("highpass", 2200, 0.8, 0.024, 1, { type: "square", hz: 2800, end: 2400, decay: 0.014, level: 0.12 }, 0.05),
    backspace: v("highpass", 3000, 0.8, 0.012, 0.75, { type: "square", hz: 3600, end: 3200, decay: 0.008, level: 0.08 }, 0.03),
  },
  thocky: {
    key: v("lowpass", 1000, 0.7, 0.05, 0.8, { type: "sine", hz: 150, end: 85, decay: 0.07, level: 0.9 }),
    space: v("lowpass", 700, 0.7, 0.07, 0.9, { type: "sine", hz: 105, end: 62, decay: 0.1, level: 1 }),
    return: v("lowpass", 800, 0.7, 0.075, 0.9, { type: "sine", hz: 118, end: 66, decay: 0.11, level: 1 }),
    backspace: v("lowpass", 900, 0.7, 0.045, 0.7, { type: "sine", hz: 135, end: 80, decay: 0.06, level: 0.75 }),
  },
};

const state = { on: false, pack: "typewriter", volume: 0.5 };
let master: GainNode | null = null;
let noise: AudioBuffer | null = null;
let custom: { id: string; buffers: Partial<Record<KeyClass, AudioBuffer[]>>; volume: number } | null = null;

function ready(): { c: AudioContext; out: GainNode } | null {
  const c = audioContext();
  if (!c) return null;
  if (!master || master.context !== c) {
    master = c.createGain();
    master.connect(c.destination);
    noise = noiseBuffer(c, 0.3, "white");
  }
  master.gain.value = gainOf(state.volume) * (custom && state.pack === CUSTOM_PREFIX + custom.id ? custom.volume : 1);
  return { c, out: master };
}

export function configureTyping(on: boolean, pack: string, volume: number): void {
  state.on = on; state.pack = pack; state.volume = volume;
  if (master) master.gain.value = gainOf(volume) * (custom && pack === CUSTOM_PREFIX + custom.id ? custom.volume : 1);
}

export const typingConfig = () => ({ ...state });

/** Decode a custom pack's data URLs ahead of use. */
export async function loadCustomPack(id: string, sounds: Partial<Record<KeyClass, string[]>>, volume: number): Promise<void> {
  const c = audioContext();
  if (!c) return;
  const buffers: Partial<Record<KeyClass, AudioBuffer[]>> = {};
  for (const [klass, urls] of Object.entries(sounds) as [KeyClass, string[]][]) {
    const out: AudioBuffer[] = [];
    for (const url of urls) {
      try {
        const raw = await (await fetch(url)).arrayBuffer();
        out.push(await c.decodeAudioData(raw));
      } catch { /* an undecodable file is skipped; the pack still works with the rest */ }
    }
    if (out.length) buffers[klass] = out;
  }
  custom = { id, buffers, volume };
  if (master && state.pack === CUSTOM_PREFIX + id) master.gain.value = gainOf(state.volume) * volume;
}

const rand = (spread: number) => 1 + (Math.random() * 2 - 1) * spread;

function playSynth(c: AudioContext, out: AudioNode, voice: Voice): void {
  const t = c.currentTime;
  const pitch = rand(0.07), level = rand(0.15);
  const strike = (at: number, scale: number) => {
    const n = c.createBufferSource();
    n.buffer = noise;
    const f = c.createBiquadFilter();
    f.type = voice.noise.type; f.frequency.value = voice.noise.hz * pitch; f.Q.value = voice.noise.q;
    const g = c.createGain();
    g.gain.setValueAtTime(voice.noise.level * level * scale, at);
    g.gain.exponentialRampToValueAtTime(0.0001, at + voice.noise.decay);
    n.connect(f); f.connect(g); g.connect(out);
    n.start(at, Math.random() * 0.2, voice.noise.decay + 0.02);
    if (voice.tone) {
      const o = c.createOscillator();
      o.type = voice.tone.type;
      o.frequency.setValueAtTime(voice.tone.hz * pitch, at);
      if (voice.tone.end !== voice.tone.hz) o.frequency.exponentialRampToValueAtTime(voice.tone.end * pitch, at + voice.tone.decay);
      const og = c.createGain();
      og.gain.setValueAtTime(voice.tone.level * level * scale, at);
      og.gain.exponentialRampToValueAtTime(0.0001, at + voice.tone.decay);
      o.connect(og); og.connect(out);
      o.start(at); o.stop(at + voice.tone.decay + 0.02);
    }
  };
  strike(t, 1);
  if (voice.second) strike(t + voice.second, 0.6);
}

function playCustom(c: AudioContext, out: AudioNode, klass: KeyClass): void {
  const set = custom?.buffers[klass] ?? custom?.buffers.key;
  if (!set?.length) return;
  const src = c.createBufferSource();
  src.buffer = set[Math.floor(Math.random() * set.length)];
  src.playbackRate.value = rand(0.03);
  src.connect(out);
  src.start();
}

/** Called from the editor's keydown handler. Cheap when off; never throws. */
export function typingKeydown(e: KeyboardEvent): void {
  if (!state.on) return;
  try {
    const klass = keyClass(e);
    if (!klass) return;
    const r = ready();
    if (!r) return;
    if (state.pack.startsWith(CUSTOM_PREFIX)) {
      if (custom && state.pack === CUSTOM_PREFIX + custom.id) playCustom(r.c, r.out, klass);
      return;
    }
    playSynth(r.c, r.out, (SYNTH[state.pack] ?? SYNTH.typewriter)[klass]);
  } catch { /* sound must never get in the way of typing */ }
}

/** The settings "Try it" button: one key and one return at the current pack. */
export function previewTyping(): void {
  const was = state.on;
  state.on = true;
  typingKeydown({ key: "a" } as KeyboardEvent);
  setTimeout(() => { typingKeydown({ key: "Enter" } as KeyboardEvent); state.on = was; }, 220);
}
