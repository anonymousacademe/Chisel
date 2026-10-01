import { describe, expect, it } from "vitest";
import { restoredText } from "./restoreText";

const base = { id: "x", kind: "scene" as const };
describe("restoredText", () => {
  it("names the part it went back to", () => {
    expect(restoredText("Rain", { ...base, unplaced: false, where: "part", part: "Part II" }))
      .toBe("Restored “Rain” to Part II.");
  });
  it("says the part is gone only when it is", () => {
    expect(restoredText("Rain", { ...base, unplaced: true, where: "gone" })).toContain("its part is gone");
    expect(restoredText("Rain", { ...base, unplaced: true, where: "unplaced" })).not.toContain("gone");
  });
});
