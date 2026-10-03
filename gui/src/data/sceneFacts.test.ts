import { describe, expect, it } from "vitest";
import { kickerOf, wordsLabel } from "./sceneFacts";

const d = { pov: "", place: "", purpose: "", status: "", when: "", target: null as number | null, collections: [] };

describe("sceneFacts", () => {
  it("words with and without a target", () => {
    expect(wordsLabel({ words: 1942, details: { ...d, target: 2400 } })).toBe("1,942 / 2,400");
    expect(wordsLabel({ words: 1942, details: d })).toBe("1,942");
  });
  it("kicker follows the unit and special groups", () => {
    const base = { number: "07", frontMatter: false, unplaced: false };
    expect(kickerOf(base, "chapter")).toBe("CHAPTER 07");
    expect(kickerOf({ ...base, number: "" }, "scene")).toBe("SCENE");
    expect(kickerOf({ ...base, frontMatter: true }, "scene")).toBe("FRONT MATTER");
    expect(kickerOf({ ...base, unplaced: true }, "scene")).toBe("PARKED");
  });
});
