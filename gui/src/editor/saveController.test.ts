import { describe, expect, it, vi } from "vitest";
import { SaveController, type SaveDeps, type SaveResult, type SaveState } from "./saveController";

function setup(save: SaveDeps["save"]) {
  const states: SaveState[] = [];
  const timers: { fn: () => void; ms: number; live: boolean }[] = [];
  const saved: SaveResult[] = [];
  const errors: string[] = [];
  const c = new SaveController({
    save, onState: (s) => states.push(s), onSaved: (r) => saved.push(r), onError: (m) => errors.push(m),
    delayMs: 1500,
    setTimer: (fn, ms) => { const t = { fn, ms, live: true }; timers.push(t); return t; },
    clearTimer: (h) => { (h as { live: boolean }).live = false; },
  });
  const fire = () => timers.filter((t) => t.live).forEach((t) => { t.live = false; t.fn(); });
  return { c, states, timers, saved, errors, fire };
}

const ok = (mtime: string, words = 1): SaveResult => ({ ok: true, saved: true, mtime, words });

describe("SaveController", () => {
  it("debounces edits into one save after the delay", async () => {
    const save = vi.fn(async () => ok("2"));
    const { c, timers, fire, states } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("xy"); c.edit("xyz");
    expect(timers.filter((t) => t.live)).toHaveLength(1); // restarted, not stacked
    expect(timers[timers.length - 1].ms).toBe(1500);
    expect(save).not.toHaveBeenCalled();
    fire();
    await c.flush();
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("a.md", "xyz", "1", false);
    expect(states).toEqual(["dirty", "saving", "saved"]);
    expect(c.baseMtime).toBe("2");
  });

  it("flush saves immediately and uses the new mtime next time", async () => {
    const save = vi.fn().mockResolvedValueOnce(ok("2")).mockResolvedValueOnce(ok("3"));
    const { c } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("xa");
    expect(await c.flush()).toBe(true);
    c.edit("xab");
    expect(await c.flush()).toBe(true);
    expect(save.mock.calls.map((a) => a[2])).toEqual(["1", "2"]);
  });

  it("an edit during a save triggers another save and ends clean", async () => {
    let release!: (r: SaveResult) => void;
    const save = vi.fn()
      .mockImplementationOnce(() => new Promise<SaveResult>((r) => { release = r; }))
      .mockResolvedValueOnce(ok("3"));
    const { c, states } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("xa");
    const done = c.flush();
    await Promise.resolve();
    c.edit("xab"); // typed while the first save is in flight
    release(ok("2"));
    expect(await done).toBe(true);
    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[1][1]).toBe("xab");
    expect(states[states.length - 1]).toBe("saved");
    expect(c.isDirty).toBe(false);
  });

  it("stops at a conflict, leaves the buffer dirty, and resolves via keepMine", async () => {
    const save = vi.fn()
      .mockResolvedValueOnce({ ok: true, saved: false, conflict: true, mtime: "9" })
      .mockResolvedValueOnce(ok("10"));
    const { c, states } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("mine");
    expect(await c.flush()).toBe(false);
    expect(c.state).toBe("conflict");
    expect(c.isDirty).toBe(true);
    c.edit("mine more"); // typing during a conflict does not schedule saves
    expect(save).toHaveBeenCalledTimes(1);
    expect(await c.keepMine()).toBe(true);
    expect(save).toHaveBeenLastCalledWith("a.md", "mine more", "9", true);
    expect(states[states.length - 1]).toBe("saved");
  });

  it("reports save errors and keeps the text dirty for a retry", async () => {
    const save = vi.fn().mockResolvedValueOnce({ ok: false, error: "disk full" }).mockResolvedValueOnce(ok("2"));
    const { c, errors } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("xa");
    expect(await c.flush()).toBe(false);
    expect(c.state).toBe("error");
    expect(errors).toEqual(["disk full"]);
    expect(await c.flush()).toBe(true);
  });

  it("a thrown bridge call is an error, not a crash", async () => {
    const { c, errors } = setup(async () => { throw new Error("bridge down"); });
    c.open("a.md", "x", "1");
    c.edit("xa");
    expect(await c.flush()).toBe(false);
    expect(errors[0]).toContain("bridge down");
  });

  it("detach forgets the document: no timer, no save (deleted scene stays deleted)", async () => {
    const save = vi.fn(async () => ok("2"));
    const { c, fire } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("xa");
    c.detach();
    fire();
    expect(await c.flush()).toBe(true);
    expect(save).not.toHaveBeenCalled();
    c.edit("ignored while detached");
    expect(c.isDirty).toBe(false);
  });

  it("ignores a save result that arrives after switching documents", async () => {
    let release!: (r: SaveResult) => void;
    const save = vi.fn(() => new Promise<SaveResult>((r) => { release = r; }));
    const { c } = setup(save);
    c.open("a.md", "x", "1");
    c.edit("xa");
    const done = c.flush();
    await Promise.resolve();
    c.open("b.md", "y", "5");
    release(ok("2"));
    await done;
    expect(c.documentId).toBe("b.md");
    expect(c.baseMtime).toBe("5");
  });

  it("markConflict only applies while dirty", () => {
    const { c } = setup(async () => ok("2"));
    c.open("a.md", "x", "1");
    c.markConflict();
    expect(c.state).toBe("saved");
    c.edit("xa");
    c.markConflict();
    expect(c.state).toBe("conflict");
  });
});
