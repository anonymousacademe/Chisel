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
  onChange: (status: SessionStatus, index: number, last: number) => void;
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
  /** The last utterance spoken with *index*: pieces of one paragraph in the same voice are spoken as one. */
  last = 0;
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

  next(): void { this.jump(this.last + 1); }
  prev(): void { this.jump(this.index - 1); }

  private jump(to: number): void {
    const last = this.d.utterances.length - 1;
    if (to < 0 || to > last) return;
    if (this.status === "playing" || this.status === "paused") this.play(to);
    else { this.index = to; this.notify(); }
  }

  private notify(): void { this.d.onChange(this.status, this.index, Math.max(this.last, this.index)); }

  private get maxChunk(): number { return this.d.engine.maxChunk ?? 200; }

  /** Utterance *i* and the ones after it that continue its paragraph in the same voice: one piece of speech, so
   * a quoted phrase inside a sentence does not break the sentence's flow. */
  private group(i: number): { last: number; say: string; role: string } | null {
    const u = this.d.utterances[i];
    if (!u) return null;
    const voice = this.d.voiceFor(u.voice);
    let j = i;
    while (this.d.utterances[j + 1]?.joins && this.d.voiceFor(this.d.utterances[j + 1].voice) === voice) j++;
    // a quote spoken inside its sentence keeps its quotation marks: a cue for the engine's intonation
    const said = (x: ReadUtterance) => (j > i && x.kind === "quote" ? `“${x.say}”` : x.say);
    return { last: j, say: this.d.utterances.slice(i, j + 1).map(said).join(" "), role: u.voice };
  }

  private begin(token: number): void {
    const g = this.group(this.index);
    if (!g) return this.finish();
    this.last = g.last;
    this.queue = chunkSpeech(g.say, this.maxChunk);
    this.notify();
    this.speakNext(token);
  }

  private speakNext(token: number): void {
    if (token !== this.token) return;
    const chunk = this.queue.shift();
    if (chunk === undefined) {                       // the utterance is finished: the next one
      if (this.last + 1 >= this.d.utterances.length) return this.finish();
      this.index = this.last + 1;
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
    const after = this.group(this.last + 1);
    const first = after ? chunkSpeech(after.say, this.maxChunk)[0] : undefined;
    return after && first ? { text: first, role: after.role } : null;
  }

  private finish(): void {
    this.token++;
    this.status = "done";
    this.notify();
  }
}
