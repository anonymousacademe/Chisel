import { describe, expect, it } from "vitest";
import { clipEngine, type ClipPlayer, type ClipSource } from "./clips";

/** A clip source whose requests are resolved by hand, and players we can end. */
function harness() {
  const asked: string[] = [];
  const waiting = new Map<string, { resolve: (url: string) => void; reject: (e: Error) => void }>();
  const source: ClipSource = {
    voices: async () => [],
    clip: (text) => { asked.push(text); return new Promise((resolve, reject) => waiting.set(text, { resolve, reject })); },
  };
  const players: (ClipPlayer & { url: string; playing: boolean })[] = [];
  const engine = clipEngine(source, (url) => {
    const p = { url, playing: false, onended: null, onerror: null, play() { p.playing = true; }, pause() { p.playing = false; } } as
      ClipPlayer & { url: string; playing: boolean };
    players.push(p);
    return p;
  });
  const tick = () => new Promise((r) => setTimeout(r, 0));
  return { engine, asked, waiting, players, tick };
}

describe("clipEngine", () => {
  it("plays the clip when it arrives and ends through the player", async () => {
    const h = harness();
    const events: string[] = [];
    h.engine.speak("One.", { voice: "af_heart", rate: 1 }, { onend: () => events.push("end"), onerror: (r) => events.push(r) });
    h.waiting.get("One.")!.resolve("data:1");
    await h.tick();
    expect(h.players[0].url).toBe("data:1");
    expect(h.players[0].playing).toBe(true);
    h.players[0].onended!();
    expect(events).toEqual(["end"]);
  });

  it("prefetches once and reuses the clip", async () => {
    const h = harness();
    h.engine.prefetch!("Two.", { voice: "af_heart", rate: 1 });
    h.engine.speak("Two.", { voice: "af_heart", rate: 1 }, { onend: () => {}, onerror: () => {} });
    expect(h.asked).toEqual(["Two."]);
    h.waiting.get("Two.")!.resolve("data:2");
    await h.tick();
    expect(h.players).toHaveLength(1);
  });

  it("ignores a clip that arrives after cancel", async () => {
    const h = harness();
    const events: string[] = [];
    h.engine.speak("Late.", { voice: "v", rate: 1 }, { onend: () => events.push("end"), onerror: (r) => events.push(r) });
    h.engine.cancel();
    h.waiting.get("Late.")!.resolve("data:late");
    await h.tick();
    expect(h.players).toHaveLength(0);
    expect(events).toEqual([]);
  });

  it("holds a clip that arrives while paused until resume", async () => {
    const h = harness();
    h.engine.speak("Wait.", { voice: "v", rate: 1 }, { onend: () => {}, onerror: () => {} });
    h.engine.pause();
    h.waiting.get("Wait.")!.resolve("data:w");
    await h.tick();
    expect(h.players).toHaveLength(0);
    h.engine.resume();
    expect(h.players[0].playing).toBe(true);
  });

  it("pauses and resumes the playing clip", async () => {
    const h = harness();
    h.engine.speak("Go.", { voice: "v", rate: 1 }, { onend: () => {}, onerror: () => {} });
    h.waiting.get("Go.")!.resolve("data:g");
    await h.tick();
    h.engine.pause();
    expect(h.players[0].playing).toBe(false);
    h.engine.resume();
    expect(h.players[0].playing).toBe(true);
  });

  it("reports a failed clip with its message, and asks again next time", async () => {
    const h = harness();
    const errors: string[] = [];
    h.engine.speak("Bad.", { voice: "v", rate: 1 }, { onend: () => {}, onerror: (r) => errors.push(r) });
    h.waiting.get("Bad.")!.reject(new Error("The local voice engine stopped unexpectedly"));
    await h.tick();
    expect(errors).toEqual(["The local voice engine stopped unexpectedly"]);
    h.engine.speak("Bad.", { voice: "v", rate: 1 }, { onend: () => {}, onerror: () => {} });
    expect(h.asked).toEqual(["Bad.", "Bad."]);
  });

  it("needs a voice", () => {
    const h = harness();
    const errors: string[] = [];
    h.engine.speak("x", { rate: 1 }, { onend: () => {}, onerror: (r) => errors.push(r) });
    expect(errors[0]).toMatch(/Choose a voice/);
    expect(h.asked).toEqual([]);
  });
});
