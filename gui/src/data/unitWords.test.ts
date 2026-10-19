import { describe, expect, it } from "vitest";
import { otherUnit, unitText, unitWords } from "./unitWords";
import { sceneGroups } from "./reorder";
import { restoredText } from "./restoreText";
import { itemNoun } from "./inspiration";
import { scopeLabel, subjectOf } from "./subject";

describe("unitWords", () => {
  it("scene projects keep scene wording", () => {
    expect(unitWords("scene")).toEqual({ one: "scene", many: "scenes", One: "Scene", Many: "Scenes" });
    expect(unitWords("section").Many).toBe("Sections");
    expect(unitWords("chapter").one).toBe("chapter");
    expect(unitWords("anything").one).toBe("scene");
  });
  it("unitText is the identity for scene and rewrites the words otherwise", () => {
    const t = "Open a scene first. Scenes here; this Scene.";
    expect(unitText(t, "scene")).toBe(t);
    expect(unitText(t, "section")).toBe("Open a section first. Sections here; this Section.");
    expect(unitText("kind scenery", "section")).toBe("kind scenery");
  });
  it("the toggle flips within the mode's pair", () => {
    expect(otherUnit("scene", "story")).toBe("chapter");
    expect(otherUnit("chapter", "script")).toBe("scene");
    expect(otherUnit("section", "research")).toBe("chapter");
    expect(otherUnit("chapter", "research")).toBe("section");
  });
});

describe("research wording in helpers", () => {
  it("parked group, restore text, noun and scope follow the unit", () => {
    expect(sceneGroups([], [], { unplaced: true, parked: "Parked sections" })).toEqual([{ key: "top", partId: null, unplaced: false, title: "", frontMatter: false, scenes: [] }]);
    const un = [{ id: "a", part: null, unplaced: true }] as never;
    expect(sceneGroups(un, [], { unplaced: true, parked: "Parked sections" }).find((g) => g.unplaced)?.title).toBe("Parked sections");
    expect(sceneGroups(un, [], { unplaced: true }).find((g) => g.unplaced)?.title).toBe("Parked scenes");
    // a story project set to chapters keeps the binder's label: one source (labels.parked)
    expect(sceneGroups(un, [], { unplaced: true, parked: "Parked scenes" }).find((g) => g.unplaced)?.title).toBe("Parked scenes");
    const r = { id: "x", kind: "scene", unplaced: true, where: "unplaced" } as const;
    expect(restoredText("T", r)).toBe("Restored “T” to Parked scenes.");
    expect(restoredText("T", r, "Parked sections")).toBe("Restored “T” to Parked sections.");
    expect(itemNoun("scene")).toBe("scene");
    expect(itemNoun("scene", "section")).toBe("section");
    const doc = { id: "m/1.md", kind: "scene", title: "Intro" };
    expect(subjectOf(doc, { scope: "scene", removed: false, researchMode: false })?.label).toBe("About: Intro (scene)");
    expect(subjectOf(doc, { scope: "scene", removed: false, researchMode: false, unit: "section" })?.label).toBe("About: Intro (section)");
    expect(scopeLabel("scene", subjectOf(doc, { scope: "scene", removed: false, researchMode: false }), "section")).toBe("Current section");
  });
});
