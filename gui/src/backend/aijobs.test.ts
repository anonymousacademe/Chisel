import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AiCancelled, runAiJob } from "./aijobs";

beforeAll(async () => { await import("./mock"); }); // the transport imports it lazily; real I/O must not happen under fake timers
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

describe("runAiJob (mock backend)", () => {
  it("streams text, then resolves with the result", async () => {
    const seen: string[] = [];
    const job = runAiJob<{ reply: string }>("ask", { prompt: "hi" }, { onText: (_d, total) => seen.push(total) });
    await vi.advanceTimersByTimeAsync(5000);
    const r = await job.promise;
    expect(r.reply).toContain("first thought");
    expect(seen.length).toBeGreaterThan(3);
    expect(seen[seen.length - 1]).toBe(r.reply);
  });
  it("non-streaming kinds give no text", async () => {
    const onText = vi.fn();
    const job = runAiJob("continuity", {}, { onText });
    await vi.advanceTimersByTimeAsync(3000);
    expect(await job.promise).toMatchObject({ ok: true, issues: [] });
    expect(onText).not.toHaveBeenCalled();
  });
  it("cancel rejects with AiCancelled and returns no result", async () => {
    const job = runAiJob("generate", { mode: "draft" });
    const caught = job.promise.catch((e) => e);
    await vi.advanceTimersByTimeAsync(300);
    await job.cancel();
    await vi.advanceTimersByTimeAsync(300);
    expect(await caught).toBeInstanceOf(AiCancelled);
    await job.cancel(); // idempotent
  });
  it("cancelling before the id arrives still stops the job", async () => {
    const job = runAiJob("ask", {});
    const caught = job.promise.catch((e) => e);
    void job.cancel();
    await vi.advanceTimersByTimeAsync(500);
    expect(await caught).toBeInstanceOf(AiCancelled);
  });
});

describe("backend extras", () => {
  it("openExternal reaches the mock and is recorded", async () => {
    vi.useRealTimers();
    const { api } = await import("./api");
    const { openedUrls } = await import("./mock");
    expect(await api.openExternal("https://example.com")).toMatchObject({ ok: true });
    expect(openedUrls).toContain("https://example.com");
  });
  it("reports the backend's elapsed seconds", async () => {
    const seen: number[] = [];
    const job = runAiJob("describe_scene", {}, { onElapsed: (s) => seen.push(s) });
    await vi.advanceTimersByTimeAsync(3000);
    await job.promise;
    expect(seen.length).toBeGreaterThan(1);
  });
});
