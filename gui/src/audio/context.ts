/** One shared AudioContext, created lazily from a user gesture (a keydown or a click). */
let ctx: AudioContext | null = null;

export function audioContext(): AudioContext | null {
  try {
    if (!ctx) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) return null;
      ctx = new Ctor({ latencyHint: "interactive" });
    }
    if (ctx.state === "suspended" && !document.hidden) void ctx.resume();
    return ctx;
  } catch { return null; }
}

export function existingContext(): AudioContext | null { return ctx; }

export type NoiseKind = "white" | "pink" | "brown";

/** Seconds of noise as a buffer (pink: Paul Kellet's filter; brown: leaky integration). */
export function noiseBuffer(c: BaseAudioContext, seconds: number, kind: NoiseKind = "white"): AudioBuffer {
  const buf = c.createBuffer(1, Math.max(1, Math.floor(c.sampleRate * seconds)), c.sampleRate);
  const d = buf.getChannelData(0);
  let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, last = 0;
  for (let i = 0; i < d.length; i++) {
    const w = Math.random() * 2 - 1;
    if (kind === "white") d[i] = w;
    else if (kind === "pink") {
      b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.969 * b2 + w * 0.153852;
      b3 = 0.8665 * b3 + w * 0.3104856; b4 = 0.55 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.016898;
      d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11; b6 = w * 0.115926;
    } else { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; }
  }
  // a loop must not click at its seam: fade the last 50 ms into the first samples
  const fade = Math.min(d.length >> 1, Math.floor(c.sampleRate * 0.05));
  for (let i = 0; i < fade; i++) { const t = i / fade; d[d.length - fade + i] = d[d.length - fade + i] * (1 - t) + d[i] * t; }
  return buf;
}
