// The speech engine behind the reader. Today there is one: the window's own speech service (browser speech),
// which is free, offline and needs nothing installed, but offers whatever voices the operating system has and
// cannot save audio. Later engines (a speech server, voice packs) implement the same interface and return audio
// clips (docs/dev/plan-read-aloud.md, phase 4).
import type { VoiceInfo } from "./types";

export interface SpeakHandlers {
  onend: () => void;
  /** *reason* is the engine's word for it ("canceled" / "interrupted" are our own cancel()). */
  onerror: (reason: string) => void;
}

export interface SpeechEngine {
  /** Installed voices; waits briefly for the list to arrive (some webviews fill it late). */
  voices(): Promise<VoiceInfo[]>;
  /** Speak one chunk (short enough for the engine); exactly one of the handlers is called. */
  speak(text: string, opts: { voice?: string; rate: number }, handlers: SpeakHandlers): void;
  pause(): void;
  resume(): void;
  cancel(): void;
}

/** Browser speech (`window.speechSynthesis`). *synth* is injectable for tests. */
export function browserEngine(synth: SpeechSynthesis | undefined = typeof window !== "undefined" ? window.speechSynthesis : undefined): SpeechEngine {
  const live = new Set<SpeechSynthesisUtterance>();     // kept reachable: some engines drop events from a collected utterance
  const toInfo = (v: SpeechSynthesisVoice): VoiceInfo => ({ id: v.voiceURI, name: v.name, lang: v.lang, local: v.localService });
  return {
    voices() {
      if (!synth) return Promise.resolve([]);
      const now = synth.getVoices();
      if (now.length) return Promise.resolve(now.map(toInfo));
      return new Promise((resolve) => {
        const done = () => { synth.removeEventListener?.("voiceschanged", done); clearTimeout(timer); resolve(synth.getVoices().map(toInfo)); };
        const timer = setTimeout(done, 1500);
        synth.addEventListener?.("voiceschanged", done);
      });
    },
    speak(text, opts, h) {
      if (!synth) return h.onerror("unavailable");
      const u = new SpeechSynthesisUtterance(text);
      u.rate = Math.min(Math.max(opts.rate, 0.5), 3);
      if (opts.voice) {
        const v = synth.getVoices().find((x) => x.voiceURI === opts.voice);
        if (v) { u.voice = v; u.lang = v.lang; }
      }
      u.onend = () => { live.delete(u); h.onend(); };
      u.onerror = (e) => { live.delete(u); h.onerror(e.error || "error"); };
      live.add(u);
      synth.speak(u);
    },
    pause() { synth?.pause(); },
    resume() { synth?.resume(); },
    cancel() { synth?.cancel(); },
  };
}
