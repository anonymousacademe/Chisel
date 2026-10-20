import { describe, expect, it } from "vitest";
import { mockCall, mockCustomControl } from "./mock";

describe("mock requirements_* contract", () => {
  it("suggest returns an unverified item and a dropped one, and changes nothing", () => {
    const r = mockCall("requirements_suggest", ["", ["ems-guide.pdf"]]) as { items: { verified: boolean }[]; dropped: { reason: string }[] };
    expect(r.items.some((i) => !i.verified)).toBe(true);
    expect(r.items.some((i) => i.verified)).toBe(true);
    expect(r.dropped.length).toBeGreaterThan(0);
    expect((mockCall("requirements_custom", []) as { rows: unknown[] }).rows).toEqual([]);
  });
  it("saves, refuses an invalid row by name, and removes", () => {
    const ok = { id: "a", group: "Your requirements", title: "Abstract", kind: "check", check: "section-words-max", section: ["abstract"], max: 150, severity: "warn" };
    expect((mockCall("requirements_save", [[ok]]) as { ok: boolean }).ok).toBe(true);
    const bad = mockCall("requirements_save", [[{ ...ok, max: -1 }]]) as { ok: boolean; error: string };
    expect(bad.ok).toBe(false);
    expect(bad.error).toContain("Abstract");
    expect((mockCall("requirements_custom", []) as { rows: unknown[] }).rows).toHaveLength(1);
    expect((mockCall("requirements_remove", ["a"]) as { rows: unknown[] }).rows).toEqual([]);
  });
  it("matches Python: unknown remove fails, ids must be plain, a warning can be simulated", () => {
    const r = mockCall("requirements_remove", ["nope"]) as { ok: boolean; error: string };
    expect(r.ok).toBe(false);
    expect(r.error).toBe("There is no such requirement.");
    const row = { id: "../x", group: "Your requirements", title: "T", kind: "advice", severity: "info" };
    expect((mockCall("requirements_save", [[row]]) as { ok: boolean }).ok).toBe(false);
    expect(mockCall("requirements_custom", [])).not.toHaveProperty("warning");
    mockCustomControl.warning = "1 row could not be read.";
    try { expect((mockCall("requirements_custom", []) as { warning: string }).warning).toBe("1 row could not be read."); }
    finally { mockCustomControl.warning = ""; }
  });
});
