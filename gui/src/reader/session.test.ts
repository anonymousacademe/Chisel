import { describe, expect, it } from "vitest";
import { ReadSession, utteranceIndexAt, type SessionStatus } from "./session";
import type { SpeakHandlers, SpeechEngine } from "./engine";
import type { ReadUtterance } from "./types";

const utt = (voice: string, say: string, start: number, end: number): ReadUtterance =>
  ({ kind: "narration", voice, text: say, say, start, end, row: 0, seconds: 1 });

/** A speech engine that never speaks: the test finishes each chunk by hand. */
function fakeEngine() {
  const spoken: { text: string; voice?: string; rate: number }[] = [];
  let pending: SpeakHandlers | null = null;
  const log: string[] = [];
  const engine: SpeechEngine = {
    voices: async () => [],
    speak(text, opts, h) { spoken.push({ text, voice: opts.voice, rate: opts.rate }); pending = h; },
    pause() { log.push("pause"); },
    resume() { log.push("resume"); },
    cancel() { log.push("cancel"); },
  };
  return { engine, spoken, log, end: () => { const h = pending; pending = null; h?.onend(); },
           fail: (reason: string) => { const h = pending; pending = null; h?.onerror(reason); }, hasPending: () => pending !== null };
}

const three = [utt("narrator", "Alpha one. Alpha two.", 0, 20), utt("Keith", "Bravo.", 22, 28), utt("Mara", "Charlie.", 30, 38)];

function session(fake: ReturnType<typeof fakeEngine>, utterances = three, rate = 1) {
  const changes: [SessionStatus, number][] = [];
  const errors: string[] = [];
  const s = new ReadSession({
    utterances, engine: fake.engine, rate: () => rate,
    voiceFor: (v) => ({ narrator: "v-n", Keith: "v-k" }[v]),
    onChange: (st, i) => changes.push([st, i]), onError: (m) => errors.push(m),
  });
  return { s, changes, errors };
}

describe("ReadSession", () => {
  it("reads every utterance in turn with its own voice, then is done", () => {
    const f = fakeEngine();
    const { s, changes } = session(f);
    s.play(0);
    expect(f.spoken).toEqual([{ text: "Alpha one. Alpha two.", voice: "v-n", rate: 1 }]);
    f.end();
    expect(f.spoken[1]).toEqual({ text: "Bravo.", voice: "v-k", rate: 1 });
    f.end();
    expect(f.spoken[2]).toEqual({ text: "Charlie.", voice: undefined, rate: 1 });   // no voice chosen for Mara: the default
    f.end();
    expect(s.status).toBe("done");
    expect(changes.map(([st, i]) => `${st}${i}`)).toEqual(["playing0", "playing1", "playing2", "done2"]);
  });

  it("speaks a long utterance in chunks, one after the other", () => {
    const f = fakeEngine();
    const long = utt("narrator", "A sentence that goes on for a while, " + "and on and on, ".repeat(20) + "until it ends.", 0, 300);
    const { s } = session(f, [long]);
    s.play();
    let n = 0;
    while (f.hasPending() && n < 50) { f.end(); n++; }
    expect(n).toBeGreaterThan(1);
    expect(f.spoken.every((c) => c.text.length <= 200)).toBe(true);
    expect(s.status).toBe("done");
  });

  it("pauses and resumes the engine without losing its place", () => {
    const f = fakeEngine();
    const { s } = session(f);
    s.play(1);
    s.pause();
    expect(s.status).toBe("paused");
    s.resume();
    expect(s.status).toBe("playing");
    expect(f.log.filter((l) => l !== "cancel")).toEqual(["pause", "resume"]);
    s.pause(); s.pause();                         // a second pause does nothing
    expect(f.log.filter((l) => l === "pause")).toHaveLength(2);
  });

  it("jumps with next / previous while playing, and stays inside the plan", () => {
    const f = fakeEngine();
    const { s } = session(f);
    s.play(0);
    s.next();
    expect(s.index).toBe(1);
    expect(f.spoken.at(-1)?.text).toBe("Bravo.");
    s.next();
    s.next();                                       // already on the last one
    expect(s.index).toBe(2);
    s.prev();
    expect(s.index).toBe(1);
    s.stop();
    s.prev();                                       // not playing: only moves the place
    expect(s.index).toBe(0);
    expect(s.status).toBe("idle");
  });

  it("ignores the end of a chunk that was cancelled", () => {
    const f = fakeEngine();
    const { s } = session(f);
    s.play(0);
    const stale = f.spoken.length;
    s.stop();
    f.end();                                        // the old chunk's end arrives after stop
    expect(f.spoken).toHaveLength(stale);
    expect(s.status).toBe("idle");
  });

  it("a restart is not confused by the cancelled chunk's late events", () => {
    const f = fakeEngine();
    const { s } = session(f);
    s.play(0);
    s.play(2);                                      // jump: the first chunk is cancelled
    expect(f.spoken.at(-1)?.text).toBe("Charlie.");
    f.fail("interrupted");                          // the engine reports the cancel as an error: ignored
    expect(s.status).toBe("playing");
  });

  it("stops with a message on a real speech error", () => {
    const f = fakeEngine();
    const { s, errors, changes } = session(f);
    s.play(0);
    f.fail("synthesis-failed");
    expect(s.status).toBe("idle");
    expect(errors).toEqual(["Speech stopped: synthesis-failed."]);
    expect(changes.at(-1)).toEqual(["idle", 0]);
    s.play(0);
    f.fail("not-allowed");
    expect(errors.at(-1)).toBe("The window did not allow speech.");
  });

  it("reads at the rate asked for at each chunk, so a change applies from the next one", () => {
    const f = fakeEngine();
    let rate = 1;
    const s = new ReadSession({ utterances: three, engine: f.engine, rate: () => rate, voiceFor: () => undefined, onChange: () => {} });
    s.play(0);
    rate = 1.5;
    f.end();
    expect(f.spoken.map((c) => c.rate)).toEqual([1, 1.5]);
  });

  it("does nothing with nothing to read", () => {
    const f = fakeEngine();
    const { s, changes } = session(f, []);
    s.play();
    expect(s.status).toBe("idle");
    expect(changes).toEqual([]);
    expect(f.spoken).toEqual([]);
  });
});

describe("utteranceIndexAt", () => {
  it("starts at the utterance the cursor is in or before", () => {
    expect(utteranceIndexAt(three, 0)).toBe(0);
    expect(utteranceIndexAt(three, 10)).toBe(0);
    expect(utteranceIndexAt(three, 20)).toBe(1);      // exactly at the end of the first: the next one
    expect(utteranceIndexAt(three, 25)).toBe(1);
    expect(utteranceIndexAt(three, 29)).toBe(2);
    expect(utteranceIndexAt(three, 99)).toBe(0);      // past the last: from the start
    expect(utteranceIndexAt([], 5)).toBe(0);
  });
});

describe("ReadSession with a clip engine", () => {
  it("asks the engine to render the next chunk while one plays, in the next voice", () => {
    const f = fakeEngine();
    const ahead: { text: string; voice?: string }[] = [];
    f.engine.prefetch = (text, opts) => { ahead.push({ text, voice: opts.voice }); };
    const { s } = session(f, [utt("narrator", "Alpha one.", 0, 10), utt("Keith", "Bravo.", 12, 18)]);
    s.play(0);
    expect(ahead).toEqual([{ text: "Bravo.", voice: "v-k" }]);
    f.end();
    expect(ahead).toHaveLength(1);              // nothing after the last one
  });

  it("shows a clip engine's sentence as it is", () => {
    const f = fakeEngine();
    const { s, errors } = session(f);
    s.play(0);
    f.fail("The local voice engine stopped unexpectedly");
    expect(errors).toEqual(["The local voice engine stopped unexpectedly"]);
  });
});
