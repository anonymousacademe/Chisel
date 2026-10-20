import { describe, expect, it } from "vitest";
import {
  addCol, addRow, blankGrid, figureFileProblem, gridHints, parseTsv, pasteGrid, placeObject, placementEdit, placementText, removeCol, removeRow, setAlign, withCell,
  type PlaceTarget,
} from "./objects";
import { isActionable, isOpenable } from "./tree";
import type { BinderNode } from "./types";

const apply = (text: string, from: number, to: number, id = "fig:a") => {
  const e = placementEdit(text, from, to, id);
  return text.slice(0, e.from) + e.insert + text.slice(e.to);
};

describe("placementEdit: the placement sits on its own line", () => {
  it("is just the line on an empty document", () => {
    expect(apply("", 0, 0)).toBe("![[fig:a]]");
    expect(placementText("tbl:x")).toBe("![[tbl:x]]");
  });
  it("mid-text puts blank lines on both sides", () => {
    expect(apply("Before after.", 7, 7)).toBe("Before after.\n\n![[fig:a]]");
  });
  it("at the end of a paragraph keeps the following blank line", () => {
    const t = "One.\n\nTwo.";
    expect(apply(t, 4, 4)).toBe("One.\n\n![[fig:a]]\n\nTwo.");
  });
  it("on the blank line between paragraphs keeps one blank line each side", () => {
    expect(apply("One.\n\nTwo.", 5, 5)).toBe("One.\n\n![[fig:a]]\n\nTwo.");
  });
  it("on the last text line of a block, goes after it with a blank line first", () => {
    const t = "One.\nTwo.";
    const out = apply(t, 5, 5);
    expect(out.split("\n").filter((l) => l.trim() === "![[fig:a]]").length).toBe(1);
    expect(out === "One.\nTwo.\n\n![[fig:a]]").toBe(true);
  });
  it("never replaces a selection: the sentence survives byte for byte", () => {
    const t = "Intro.\n\nThe selected sentence stays. More text here.\n\nEnd.";
    const from = t.indexOf("The selected"), to = t.indexOf(" More");
    const out = apply(t, from, to, "tbl:x");
    expect(out).toBe("Intro.\n\nThe selected sentence stays. More text here.\n\n![[tbl:x]]\n\nEnd.");
    expect(out).toContain(t.slice(from, to));
    const e = placementEdit(t, from, to, "tbl:x");
    expect(e.from).toBe(e.to);
    expect(apply("Say TODO here", 4, 8)).toBe("Say TODO here\n\n![[fig:a]]");
  });
  it("every result has the placement alone between blank lines or document edges", () => {
    for (const [t, at] of [["a", 1], ["a\nb", 1], ["a\n\nb", 2], ["\n", 0], ["a\n", 2], ["x y", 2]] as [string, number][]) {
      const lines = apply(t, at, at).split("\n");
      const i = lines.indexOf("![[fig:a]]");
      expect(i).toBeGreaterThanOrEqual(0);
      if (i > 0) expect(lines[i - 1].trim()).toBe("");
      if (i < lines.length - 1) expect(lines[i + 1].trim()).toBe("");
    }
  });
});

describe("placeObject", () => {
  const fake = (text: string, at: number) => {
    const log = { text, focused: false };
    const ed: PlaceTarget = {
      getText: () => log.text, selection: () => ({ from: at, to: at }),
      replace: (f, t, s) => { log.text = log.text.slice(0, f) + s + log.text.slice(t); }, focus: () => { log.focused = true; },
    };
    return { ed, log };
  };
  it("inserts through the editor handle and focuses it", () => {
    const { ed, log } = fake("Intro text.", 11);
    expect(placeObject(ed, true, "eq:monod")).toBe(true);
    expect(log.text).toBe("Intro text.\n\n![[eq:monod]]");
    expect(log.focused).toBe(true);
  });
  it("does nothing with no section open or no editor", () => {
    const { ed, log } = fake("x", 0);
    expect(placeObject(ed, false, "fig:a")).toBe(false);
    expect(placeObject(null, true, "fig:a")).toBe(false);
    expect(log.text).toBe("x");
  });
});

describe("the table grid", () => {
  it("starts blank with default alignment", () => {
    const g = blankGrid(3, 2);
    expect(g.cells).toHaveLength(3);
    expect(g.align).toEqual(["default", "default"]);
  });
  it("adds and removes rows, never the header and never the last body row", () => {
    let g = withCell(blankGrid(2, 2), 0, 0, "H");
    g = addRow(g);
    expect(g.cells).toHaveLength(3);
    expect(removeRow(g, 0)).toBe(g);
    g = removeRow(g, 2);
    expect(g.cells).toHaveLength(2);
    expect(removeRow(g, 1)).toBe(g);
  });
  it("adds and removes columns with their alignment, keeping one", () => {
    let g = setAlign(blankGrid(2, 2), 1, "right");
    g = addCol(g);
    expect(g.align).toEqual(["default", "right", "default"]);
    expect(g.cells.every((r) => r.length === 3)).toBe(true);
    g = removeCol(g, 1);
    expect(g.align).toEqual(["default", "default"]);
    expect(removeCol(blankGrid(2, 1), 0).align).toHaveLength(1);
  });
  it("parses tab-separated text and leaves plain text alone", () => {
    expect(parseTsv("just words")).toBeNull();
    expect(parseTsv("a\tb\r\nc\td\r\n")).toEqual([["a", "b"], ["c", "d"]]);
    expect(parseTsv("a\tb\nc")).toEqual([["a", "b"], ["c", ""]]);
  });
  it("paste fills from the cell and grows the grid", () => {
    const g = pasteGrid(blankGrid(2, 2), 1, 1, [["x", "y"], ["z", "w"]]);
    expect(g.cells).toEqual([["", "", ""], ["", "x", "y"], ["", "z", "w"]]);
    expect(g.align).toHaveLength(3);
  });
  it("hints name the size caps", () => {
    expect(gridHints(blankGrid(3, 3))).toEqual([]);
    expect(gridHints(blankGrid(201, 31))).toHaveLength(2);
    expect(gridHints(blankGrid(200, 30))).toEqual([]);
    const big = blankGrid(3, 3); big.cells[1][1] = "x".repeat(2001);
    expect(gridHints(big)).toHaveLength(1);
  });
});

describe("figure files", () => {
  it("accepts PNG and JPG only, up to 10 MB", () => {
    expect(figureFileProblem({ name: "a.png", type: "image/png", size: 10 })).toBe("");
    expect(figureFileProblem({ name: "a.jpg", type: "", size: 10 })).toBe("");
    expect(figureFileProblem({ name: "a.gif", type: "image/gif", size: 10 })).toMatch(/PNG or JPG/);
    expect(figureFileProblem({ name: "a.png", type: "image/png", size: 11 * 1024 * 1024 })).toMatch(/10 MB/);
  });
});

describe("binder kinds", () => {
  it("an object row is actionable (opens its card), a group only expands", () => {
    const row: BinderNode = { id: "fig:a", title: "Figure 1: x", kind: "object" };
    const group: BinderNode = { id: "group:figures", title: "Figures", kind: "objects", children: [row] };
    expect(isActionable(row)).toBe(true);
    expect(isOpenable(row)).toBe(false);
    expect(isActionable(group)).toBe(false);
    expect(isOpenable(group)).toBe(false);
  });
});
