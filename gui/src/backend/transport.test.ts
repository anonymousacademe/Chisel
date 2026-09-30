import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { call, getTransport, initTransport } from "./transport";

type W = { pywebview?: unknown; fetch?: unknown };
const g = globalThis as unknown as { window?: W; fetch?: unknown };

describe("transports", () => {
  beforeEach(() => { g.window = Object.assign(new EventTarget(), {}) as unknown as W; });
  afterEach(() => { vi.restoreAllMocks(); delete g.window; });

  it("uses the pywebview bridge when present", async () => {
    const hello = vi.fn(async (...a: unknown[]) => ({ ok: true, echo: a }));
    g.window!.pywebview = { api: { hello } };
    expect(await initTransport()).toBe("pywebview");
    expect(await call("hello", 1, "two")).toEqual({ ok: true, echo: [1, "two"] });
  });

  it("turns a throwing bridge into an error result", async () => {
    g.window!.pywebview = { api: { boom: async () => { throw new Error("bad"); } } };
    await initTransport();
    const r = await call("boom");
    expect(r.ok).toBe(false);
  });

  it("falls back to http (devserver) when /api/ping answers", async () => {
    g.fetch = vi.fn(async (url: string, init?: { body?: string }) => ({
      ok: true,
      json: async () => (url.endsWith("ping") ? { ok: true } : { ok: true, got: JSON.parse(init!.body!).args }),
    }));
    expect(await initTransport()).toBe("http");
    expect(await call("anything", "x")).toEqual({ ok: true, got: ["x"] });
  });

  it("falls back to the in-memory mock when there is no core", async () => {
    g.fetch = vi.fn(async () => { throw new Error("offline"); });
    expect(await initTransport()).toBe("none");
    expect(getTransport()).toBe("none");
    const r = await call<{ workspace: { project: { title: string } } }>("get_workspace");
    expect(r.ok && r.workspace.project.title).toBe("The Meridian Archive");
    const miss = await call("generate");
    expect(miss.ok).toBe(false);
  });
});
