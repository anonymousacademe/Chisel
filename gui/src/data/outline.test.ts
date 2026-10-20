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
  it("says what changes, with real titles and destinations", () => {
    expect(describeItem(ITEMS[0], SECTIONS)).toBe("Add “Study area” to the top level, after “Introduction”.");
    expect(describeItem(ITEMS[1], SECTIONS)).toBe("Rename “Methods” to “Materials and methods”.");
    expect(describeItem(ITEMS[2], SECTIONS)).toBe("Move “Discussion” to the top level, after “Results”.");
  });
  it("names the part and the start of a part", () => {
    const move: OutlineItem = { id: "m", action: "move", title: "x", section: "d", part: "Article", after: "r" };
    expect(describeItem(move, SECTIONS)).toBe("Move “Discussion” to Part “Article”, after “Results”.");
    expect(describeItem({ ...move, after: "" }, SECTIONS)).toBe("Move “Discussion” to the start of Part “Article”.");
    expect(describeItem({ ...move, after: undefined }, SECTIONS)).toBe("Move “Discussion” to the end of Part “Article”.");
    const add: OutlineItem = { id: "a", action: "add", title: "Limitations", part: "Article", after: "d" };
    expect(describeItem(add, SECTIONS)).toBe("Add “Limitations” to Part “Article”, after “Discussion”.");
  });
  it("uses the section's real current title, not the AI's", () => {
    const rename: OutlineItem = { id: "r", action: "rename", title: "Method section (AI's name)", section: "m", newTitle: "Materials" };
    expect(describeItem(rename, SECTIONS)).toBe("Rename “Methods” to “Materials”.");
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
  // Part ids ("p-1") differ from titles ("Part One"): an item's part is a TITLE and must match partTitle, never the id.
  const withPart = [sec("a", "Abstract"), sec("x", "Intro", "Part One"), sec("y", "Methods", "Part One"), sec("z", "Results", "Part Two")];
  it("moves a section to the first place of a part by its title and drops the emptied group", () => {
    const move: OutlineItem = { id: "m", action: "move", title: "Results", section: "z", part: "Part One", after: "" };
    const p = previewOutline(withPart, [move]);
    expect(p.after.find((g) => g.part === "Part One")!.rows.map((r) => r.title)).toEqual(["Results", "Intro", "Methods"]);
    expect(p.after.find((g) => g.part === "Part Two")).toBeUndefined();
  });
  it("does not confuse a part id with a part title", () => {
    const byId: OutlineItem = { id: "m", action: "move", title: "Results", section: "z", part: "p-Part One", after: "" };
    const p = previewOutline(withPart, [byId]);
    expect(p.after.find((g) => g.part === "Part One")!.rows.map((r) => r.title)).toEqual(["Intro", "Methods"]);
  });
  it("adds to the end of a part when there is no anchor, and after an anchor otherwise", () => {
    const end: OutlineItem = { id: "e", action: "add", title: "Extra", part: "Part One" };
    expect(previewOutline(withPart, [end]).after.find((g) => g.part === "Part One")!.rows.map((r) => r.title)).toEqual(["Intro", "Methods", "Extra"]);
    const mid: OutlineItem = { id: "f", action: "add", title: "Mid", part: "Part One", after: "x" };
    expect(previewOutline(withPart, [mid]).after.find((g) => g.part === "Part One")!.rows.map((r) => r.title)).toEqual(["Intro", "Mid", "Methods"]);
  });
  it("skips an item whose section is gone", () => {
    expect(titles([{ id: "x", action: "rename", title: "Gone", section: "nope", newTitle: "Other" }])).toEqual(SECTIONS.map((s) => s.title));
  });
});
