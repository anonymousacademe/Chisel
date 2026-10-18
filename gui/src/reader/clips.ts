// A SpeechEngine that plays clips: Python renders each chunk to WAV (chisel/speech/: natural voices on this
// computer, or a speech server) and an <audio> element plays it. The next chunk is rendered while this one
// plays, so there is no pause between them once the first is ready.
import type { SpeakHandlers, SpeechEngine } from "./engine";
import type { VoiceInfo } from "./types";

export interface ClipSource {
  voices(): Promise<VoiceInfo[]>;
  /** A playable URL (data URL) for *text*; rejects with a message for the author. */
  clip(text: string, voice: string, rate: number): Promise<string>;
}

/** The bit of HTMLAudioElement we use (a fake in tests). */
export interface ClipPlayer {
  play(): Promise<void> | void;
  pause(): void;
  onended: (() => void) | null;
  onerror: (() => void) | null;
}

const KEEP = 12;     // clips held in memory (Python keeps a disk cache too)

const audioPlayer = (url: string): ClipPlayer => {
  const a = new Audio(url);
  const p: ClipPlayer = { play: () => a.play(), pause: () => a.pause(), onended: null, onerror: null };
  a.onended = () => p.onended?.();
  a.onerror = () => p.onerror?.();
  return p;
};

export function clipEngine(source: ClipSource, makePlayer: (url: string) => ClipPlayer = audioPlayer): SpeechEngine {
  const memo = new Map<string, Promise<string>>();
  let gen = 0;
  let player: ClipPlayer | null = null;
  let paused = false;
  let pending: (() => void) | null = null;          // a clip that arrived while paused

  const get = (text: string, voice: string, rate: number): Promise<string> => {
    const key = `${voice}\u0000${rate}\u0000${text}`;
    let p = memo.get(key);
    if (!p) {
      p = source.clip(text, voice, rate);
      p.catch(() => memo.delete(key));             // a failure is not remembered
      memo.set(key, p);
      while (memo.size > KEEP) memo.delete(memo.keys().next().value as string);
    }
    return p;
  };

  return {
    voices: () => source.voices(),
    speak(text, opts, h: SpeakHandlers) {
      const mine = ++gen;
      paused = false;
      pending = null;
      if (!opts.voice) return h.onerror("Choose a voice for this engine.");
      get(text, opts.voice, opts.rate).then((url) => {
        if (mine !== gen) return;
        const start = () => {
          const p = makePlayer(url);
          player = p;
          p.onended = () => { if (mine === gen) { player = null; h.onend(); } };
          p.onerror = () => { if (mine === gen) { player = null; h.onerror("The clip could not be played."); } };
          try {
            const r = p.play();
            if (r && typeof r.catch === "function") r.catch(() => { if (mine === gen) h.onerror("The window did not allow sound."); });
          } catch {
            h.onerror("The window did not allow sound.");
          }
        };
        if (paused) pending = start; else start();
      }, (err: unknown) => {
        if (mine === gen) h.onerror(err instanceof Error ? err.message : String(err));
      });
    },
    prefetch(text, opts) {
      if (opts.voice) get(text, opts.voice, opts.rate).catch(() => {});
    },
    pause() {
      paused = true;
      player?.pause();
    },
    resume() {
      paused = false;
      if (pending) { const run = pending; pending = null; run(); }
      else void player?.play();
    },
    cancel() {
      gen++;
      paused = false;
      pending = null;
      player?.pause();
      player = null;
    },
  };
}
