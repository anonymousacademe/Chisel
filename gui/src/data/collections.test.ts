import { describe, expect, it } from "vitest";
import partsFixture from "./fixtures/workspace-parts.json";
import type { Workspace } from "./types";
import { inCollection, memberIds, swatchVar } from "./collections";
import { filterByIds } from "./tree";

const ws = partsFixture as unknown as Workspace;

describe("collections (shape shared with Python)", () => {
  it("the fixture lists defined collections with their members", () => {
    const c = ws.collections.find((x) => x.name === "Needs continuity pass")!;
    expect(c.color).toBe("amber");
    expect(c.declared).toBe(true);
    expect(c.count).toBe(1);
    expect(c.sceneIds).toEqual(ws.scenes.filter((s) => s.details.collections.includes(c.name)).map((s) => s.id));
    expect(ws.collections.find((x) => x.name === "Mara's arc")!.count).toBe(0);
  });

  it("filters scenes and the binder to the members", () => {
    const ids = memberIds(ws.collections, "Needs continuity pass")!;
    expect(inCollection(ws.scenes, "Needs continuity pass").map((s) => s.id)).toEqual([...ids]);
    const tree = filterByIds(ws.binder, ids);
    const leaves: string[] = [];
    const walk = (ns: typeof tree) => ns.forEach((n) => (n.children ? walk(n.children) : leaves.push(n.id)));
    walk(tree);
    expect(leaves).toEqual([...ids]);
    expect(memberIds(ws.collections, null)).toBeNull();
    expect(inCollection(ws.scenes, null)).toBe(ws.scenes);
  });

  it("unknown colours fall back to grey", () => {
    expect(swatchVar("nope" as never)).toBe(swatchVar("gray"));
  });
});
