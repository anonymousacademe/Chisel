import { describe, expect, it } from "vitest";
import { mockCall } from "./mock";

type Section = { id: string; title: string; partTitle: string };
const current = () => (mockCall("outline_current", []) as { sections: Section[] }).sections;

describe("mock outline_* contract", () => {
  it("suggest reports an ignored entry", () => {
    const r = mockCall("outline_suggest", []) as { dropped: { reason: string }[] };
    expect(r.dropped.length).toBeGreaterThan(0);
  });
  it("places an add after its anchor and in its part, and a move returns a remap", () => {
    const before = current();
    const intro = before.find((s) => s.title === "Introduction")!;
    const added = mockCall("outline_apply", [[{ id: "a", action: "add", title: "Limitations", part: "Article", after: intro.id }]]) as { created: string[] };
    const mid = current();
    const at = mid.findIndex((s) => s.id === added.created[0]);
    expect(mid[at - 1].id).toBe(intro.id);
    expect(mid[at].partTitle).toBe("Article");
    const disc = mid.find((s) => s.title === "Discussion")!;
    const moved = mockCall("outline_apply", [[{ id: "m", action: "move", title: "Discussion", section: disc.id, part: "", after: "" }]]) as { remap: Record<string, string>; changed: string[] };
    expect(Object.keys(moved.remap)).toEqual([disc.id]);
    expect(current().findIndex((s) => s.title === "Discussion")).toBeLessThan(mid.findIndex((s) => s.title === "Discussion"));
  });
});
