import { describe, expect, it } from "vitest";
import { mockCall } from "./mock";

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
});
