import { describe, expect, it } from "vitest";
import { agoText, deltaText, identical, labelText, sides } from "./snapshots";

const NOW = new Date("2026-10-01T12:00:00");
const at = (ms: number) => new Date(NOW.getTime() - ms).toISOString();

describe("agoText", () => {
  it("mirrors the Python wording", () => {
    expect(agoText(at(5_000), NOW)).toBe("just now");
    expect(agoText(at(12 * 60_000), NOW)).toBe("12 min ago");
    expect(agoText(at(3 * 3_600_000), NOW)).toBe("3 h ago");
    expect(agoText(at(86_400_000), NOW)).toBe("1 day ago");
    expect(agoText(at(3 * 86_400_000), NOW)).toBe("3 days ago");
    expect(agoText("2026-08-22T09:00:00", NOW)).toBe("2026-08-22");
  });
  it("ignores garbage", () => expect(agoText("nope", NOW)).toBe(""));
});

describe("labels and deltas", () => {
  it("explains the automatic labels", () => {
    expect(labelText("")).toBe("Snapshot");
    expect(labelText("auto")).toContain("first edit");
    expect(labelText("end-of-draft-2")).toBe("End of draft 2");
    expect(labelText("my label")).toBe("my label");
  });
  it("signs word changes", () => {
    expect(deltaText(12)).toBe("+12");
    expect(deltaText(-3)).toBe("−3");
    expect(deltaText(0)).toBe("±0");
  });
});

describe("sides", () => {
  const segs = [
    { op: "equal" as const, old: "The rain ", new: "The rain " },
    { op: "replace" as const, old: "fell ", new: "poured " },
    { op: "delete" as const, old: "slowly ", new: "" },
    { op: "insert" as const, old: "", new: "all night" },
  ];
  it("rebuilds both texts and marks only the changes", () => {
    const { left, right } = sides(segs);
    expect(left.map((p) => p.text).join("")).toBe("The rain fell slowly ");
    expect(right.map((p) => p.text).join("")).toBe("The rain poured all night");
    expect(left.filter((p) => p.mark).map((p) => p.mark)).toEqual(["del", "del"]);
    expect(right.filter((p) => p.mark).map((p) => p.mark)).toEqual(["ins", "ins"]);
  });
  it("knows when nothing changed", () => {
    expect(identical([{ op: "equal", old: "a", new: "a" }])).toBe(true);
    expect(identical(segs)).toBe(false);
  });
});
