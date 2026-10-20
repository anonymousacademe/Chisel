import { describe, expect, it } from "vitest";
import { defaultTicked, describeItem, previewOutline, previewRows, tickedItems, visibleItems } from "./outline";
import type { OutlineItem, OutlineSection } from "./research";

const sec = (id: string, title: string, partTitle = "", frontMatter = false): OutlineSection =>
  ({ id, title, part: partTitle ? `p-${partTitle}` : "", partTitle, frontMatter, position: 1, words: 10, purpose: "" });
const SECTIONS = [sec("a", "Abstract"), sec("i", "Introduction"), sec("m", "Methods"), sec("r", "Results"), sec("d", "Discussion")];
const ITEMS: OutlineItem[] = [
  { id: "1", action: "add", title: "Study area", part: "", after: "i", purpose: "p", why: "w" },
  { id: "2", action: "rename", title: "Methods", section: "m", newTitle: "Materials and methods" },
  { id: "3", action: "move", title: "Discussion", section: "d", part: "", after: "r" },
  { id: "4", action: "advice", title: "Add a limitations paragraph" },
  { id: "5", action: "keep", title: "Introduction", section: "i" },
];

describe("defaultTicked", () => {
  it("ticks add, rename and move only", () => {
    expect([...defaultTicked(ITEMS)]).toEqual(["1", "2", "3"]);
  });
  it("hides keep and sends only ticked, actionable items as full objects", () => {
    expect(visibleItems(ITEMS).map((i) => i.id)).toEqual(["1", "2", "3", "4"]);
    const sent = tickedItems(ITEMS, new Set(["1", "4", "5"]));
    expect(sent).toEqual([ITEMS[0]]);
  });
});

describe("describeItem", () => {
  it("says what changes", () => {
    expect(describeItem(ITEMS[0])).toBe("Add a new section “Study area” at the top level.");
    expect(describeItem(ITEMS[1])).toBe("Rename “Methods” to “Materials and methods”.");
    expect(describeItem({ ...ITEMS[2], part: "Part One" })).toBe("Move “Discussion” in “Part One”.");
  });
});

describe("previewOutline", () => {
  const titles = (items: OutlineItem[]) => previewRows(SECTIONS, items).map((r) => r.title);
  it("leaves the outline alone with nothing ticked", () => {
    const p = previewOutline(SECTIONS, []);
    expect(p.before[0].rows.map((r) => r.title)).toEqual(p.after[0].rows.map((r) => r.title));
    expect(previewRows(SECTIONS, []).every((r) => r.state === "same")).toBe(true);
  });
  it("applies add, rename and move in place", () => {
    expect(titles([ITEMS[0], ITEMS[1], ITEMS[2]])).toEqual(["Abstract", "Introduction", "Study area", "Materials and methods", "Results", "Discussion"]);
    const rows = previewRows(SECTIONS, [ITEMS[0], ITEMS[1]]);
    expect(rows.find((r) => r.title === "Study area")?.state).toBe("new");
    expect(rows.find((r) => r.title === "Materials and methods")?.state).toBe("renamed");
  });
  it("moves a section to the first place of a part and creates the part group", () => {
    const withPart = [sec("a", "Abstract"), sec("x", "Intro", "Part One"), sec("y", "Methods", "Part One"), sec("z", "Results", "Part Two")];
    const move: OutlineItem = { id: "m", action: "move", title: "Results", section: "z", part: "Part One", after: "" };
    const p = previewOutline(withPart, [move]);
    expect(p.after.find((g) => g.part === "Part One")!.rows.map((r) => r.title)).toEqual(["Results", "Intro", "Methods"]);
    expect(p.after.find((g) => g.part === "Part Two")).toBeUndefined();
  });
  it("skips an item whose section is gone", () => {
    expect(titles([{ id: "x", action: "rename", title: "Gone", section: "nope", newTitle: "Other" }])).toEqual(SECTIONS.map((s) => s.title));
  });
});
