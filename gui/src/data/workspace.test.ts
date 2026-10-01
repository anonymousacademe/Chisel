import { describe, expect, it } from "vitest";
import fixture from "./fixtures/workspace.json";
import partsFixture from "./fixtures/workspace-parts.json";
import type { BinderNode, Workspace } from "./types";
import { allIds, collectExpanded, filterTree, findNode, isActionable, isOpenable } from "./tree";
import { sceneGroups } from "./reorder";
import { filterSwitcher, switcherItems } from "./switcher";

// workspace.json is written by the Python side (tests/test_gui_workspace.py
// compares lorewrite.gui.workspace output against it), so this checks that the
// TS types and helpers agree with what Python really produces.
const ws = fixture as unknown as Workspace;

describe("workspace fixture (shape shared with Python)", () => {
  it("has the top-level keys the UI reads", () => {
    expect(Object.keys(ws).sort()).toEqual(["binder", "collections", "entities", "parts", "project", "scenes", "status"]);
    expect(ws.status).toMatchObject({ projectWords: expect.any(Number), hasStyle: false });
  });

  it("marks placeholder nodes and keeps real ones openable", () => {
    const ph = findNode(ws.binder, "ph:research")!;
    expect(ph.placeholder).toBe(true);
    expect(isOpenable(ph)).toBe(false);
    const scene = findNode(ws.binder, ws.scenes[0].id)!;
    expect(isOpenable(scene)).toBe(true);
    expect(scene.title).toBe("01  Arrival");
  });

  it("every scene and entity has a binder node", () => {
    const ids = allIds(ws.binder);
    for (const s of ws.scenes) expect(ids.has(s.id)).toBe(true);
    for (const e of ws.entities) expect(ids.has(e.id)).toBe(true);
  });

  it("collects initially expanded nodes", () => {
    expect([...collectExpanded(ws.binder)].sort()).toEqual(["group:manuscript", "project"]);
  });

  it("filters the tree by title, keeping ancestors", () => {
    const out = filterTree(ws.binder, "arch");
    const flat = [...allIds(out)];
    expect(flat).toContain("manuscript/02-the-archive.md");
    expect(flat).toContain("group:manuscript");
    expect(flat).not.toContain("manuscript/01-arrival.md");
  });
});

describe("quick switcher", () => {
  const items = switcherItems(ws);
  it("lists scenes and notes", () => {
    expect(items.filter((i) => i.category === "Scene")).toHaveLength(2);
    expect(items.filter((i) => i.category === "Note").map((i) => i.title).sort()).toEqual(["Elias Vale", "Lower Meridian", "Mara Vale"]);
  });
  it("matches every word, title hits first, and through aliases", () => {
    expect(filterSwitcher(items, "").length).toBe(items.length);
    expect(filterSwitcher(items, "vale").map((i) => i.title).sort()).toEqual(["Elias Vale", "Mara Vale"]);
    expect(filterSwitcher(items, "mara")[0].title).toBe("Mara Vale");
    expect(filterSwitcher(items, "zzz")).toEqual([]);
  });
});

describe("types", () => {
  it("BinderNode accepts the placeholder flag", () => {
    const n: BinderNode = { id: "x", title: "x", kind: "folder", placeholder: true };
    expect(n.placeholder).toBe(true);
  });
});

describe("dictionary", () => {
  it("is a binder item next to the style guide and opens as a document", () => {
    const node = findNode(ws.binder, "dictionary.txt")!;
    expect(node).toMatchObject({ title: "Dictionary", kind: "dictionary" });
    expect(isOpenable(node)).toBe(true);
    expect(ws.binder.findIndex((n) => n.id === "dictionary.txt")).toBe(ws.binder.findIndex((n) => n.id === "style.md") + 1);
  });

  it("is offered by the quick switcher", () => {
    expect(filterSwitcher(switcherItems(ws), "dictionary")[0]).toMatchObject({ id: "dictionary.txt", category: "Dictionary" });
  });
});


describe("a book with parts (shape shared with Python)", () => {
  const book = partsFixture as unknown as Workspace;

  it("binder shows real parts, front matter muted and first", () => {
    const kids = book.binder[0].children!;
    expect(kids.map((k) => [k.kind, k.title, !!k.muted])).toEqual([
      ["part", "Front Matter", true], ["part", "The Recall", false], ["part", "Ghost", false]]);
    expect(kids.some((k) => k.placeholder)).toBe(false);
    for (const k of kids) expect(isActionable(k)).toBe(true);
    expect(isOpenable(kids[1].children![0])).toBe(true);
  });

  it("Unplaced Scenes and Trash are real rows", () => {
    const un = findNode(book.binder, "group:unplaced")!;
    expect(un.kind).toBe("inbox");
    expect(un.children!.map((c) => c.title)).toEqual(["Capsule"]);
    const trash = findNode(book.binder, "group:trash")!;
    expect(trash).toMatchObject({ kind: "trash", meta: "1" });
    expect(isActionable(trash)).toBe(true);
    expect(isActionable(findNode(book.binder, "ph:research")!)).toBe(false);
  });

  it("scenes carry part, details and the front-matter / unplaced flags", () => {
    const byTitle = Object.fromEntries(book.scenes.map((s) => [s.title, s]));
    expect(byTitle["Title Page"]).toMatchObject({ frontMatter: true, number: "", part: "part:manuscript/00-front-matter" });
    expect(byTitle["Rain"].details).toMatchObject({ pov: "Mara Vale", place: "Lower Meridian", status: "revising", target: 2400 });
    expect(byTitle["Rain"].number).toBe("01");
    expect(byTitle["Capsule"]).toMatchObject({ unplaced: true, part: null });
    expect(book.status.projectWords).toBe(5);       // only Rain counts
    expect(book.status.trashCount).toBe(1);
  });

  it("groups feed the corkboard in book order", () => {
    const groups = sceneGroups(book.scenes, book.parts, { unplaced: true });
    expect(groups.map((g) => [g.title, g.scenes.map((s) => s.title)])).toEqual([
      ["Front Matter", ["Title Page"]], ["The Recall", ["Rain"]], ["Ghost", []], ["Unplaced scenes", ["Capsule"]]]);
  });
});
