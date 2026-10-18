// Plays a ReadPlan's utterances one after another through a SpeechEngine. No React, no DOM: the engine is
// injected, so this is tested with a fake one. A generation token makes every callback of a cancelled chunk
// harmless (speech services fire "end" or "error" for a chunk you cancelled, in either order).
import { chunkSpeech } from "./chunks";
import type { SpeechEngine } from "./engine";
import type { ReadUtterance } from "./types";

export type SessionStatus = "idle" | "playing" | "paused" | "done";

export interface SessionDeps {
  utterances: ReadUtterance[];
  engine: SpeechEngine;
  /** The system voice id for a voice role (undefined: the engine's default). */
  voiceFor: (voice: string) => string | undefined;
  rate: () => number;
  /** Called when the status or the current utterance changes. */
  onChange: (status: SessionStatus, index: number) => void;
  onError?: (message: string) => void;
}

/** Index of the first utterance that ends after *pos* (where reading from a cursor starts); 0 past the end. */
export function utteranceIndexAt(utterances: ReadUtterance[], pos: number): number {
  const i = utterances.findIndex((u) => u.end > pos);
  return i === -1 ? 0 : i;
}

export class ReadSession {
  status: SessionStatus = "idle";
  index = 0;
  private token = 0;
  private queue: string[] = [];

  private d: SessionDeps;

  constructor(deps: SessionDeps) { this.d = deps; }

  /** Start (or restart) reading at utterance *from*. */
  play(from = this.index): void {
    if (!this.d.utterances.length) return;
    this.index = Math.min(Math.max(from, 0), this.d.utterances.length - 1);
    this.status = "playing";
    this.d.engine.cancel();
    this.begin(++this.token);
  }

  pause(): void {
    if (this.status !== "playing") return;
    this.status = "paused";
    this.d.engine.pause();
    this.notify();
  }

  resume(): void {
    if (this.status !== "paused") return;
    this.status = "playing";
    this.d.engine.resume();
    this.notify();
  }

  stop(): void {
    this.token++;
    this.d.engine.cancel();
    this.queue = [];
    this.status = "idle";
    this.notify();
  }

  next(): void { this.jump(this.index + 1); }
  prev(): void { this.jump(this.index - 1); }

  private jump(to: number): void {
    const last = this.d.utterances.length - 1;
    if (to < 0 || to > last) return;
    if (this.status === "playing" || this.status === "paused") this.play(to);
    else { this.index = to; this.notify(); }
  }

  private notify(): void { this.d.onChange(this.status, this.index); }

  private begin(token: number): void {
    const u = this.d.utterances[this.index];
    if (!u) return this.finish();
    this.queue = chunkSpeech(u.say);
    this.notify();
    this.speakNext(token);
  }

  private speakNext(token: number): void {
    if (token !== this.token) return;
    const chunk = this.queue.shift();
    if (chunk === undefined) {                       // the utterance is finished: the next one
      if (this.index + 1 >= this.d.utterances.length) return this.finish();
      this.index += 1;
      return this.begin(token);
    }
    const u = this.d.utterances[this.index];
    const ahead = this.ahead();          // worked out now: a fake engine may end the chunk synchronously
    this.d.engine.speak(chunk, { voice: this.d.voiceFor(u.voice), rate: this.d.rate() }, {
      onend: () => this.speakNext(token),
      onerror: (reason) => {
        if (token !== this.token) return;            // we cancelled it ourselves
        if (reason === "canceled" || reason === "interrupted") return;
        this.token++;
        this.status = "idle";
        this.notify();
        // a clip engine's reason is a sentence for the author; the window's speech gives a code
        this.d.onError?.(reason === "not-allowed" ? "The window did not allow speech."
          : /\s/.test(reason) ? reason : `Speech stopped: ${reason}.`);
      },
    });
    // after speak, so a clip engine renders the chunk being spoken first
    if (ahead && token === this.token) this.d.engine.prefetch?.(ahead.text, { voice: this.d.voiceFor(ahead.role), rate: this.d.rate() });
  }

  /** The chunk that follows the one about to be spoken (in this utterance or the next), for clip engines. */
  private ahead(): { text: string; role: string } | null {
    if (!this.d.engine.prefetch) return null;
    if (this.queue.length) return { text: this.queue[0], role: this.d.utterances[this.index].voice };
    const after = this.d.utterances[this.index + 1];
    const first = after ? chunkSpeech(after.say)[0] : undefined;
    return after && first ? { text: first, role: after.voice } : null;
  }

  private finish(): void {
    this.token++;
    this.status = "done";
    this.notify();
  }
}
