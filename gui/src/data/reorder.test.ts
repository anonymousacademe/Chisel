import { describe, expect, it } from "vitest";
import { follow, planMove, sceneGroups } from "./reorder";
import type { PartSummary, SceneSummary } from "./types";

const d = { pov: "", place: "", purpose: "", status: "", target: null, collections: [] };
const sc = (id: string, title: string, part: string | null, extra: Partial<SceneSummary> = {}): SceneSummary => ({
  id, number: "", title, words: 10, excerpt: "", headings: [], part, frontMatter: false, unplaced: false, details: d, ...extra,
});
const P1 = "part:manuscript/01-recall", P2 = "part:manuscript/02-ghost";
const scenes = [
  sc("a", "Rain", P1), sc("b", "Capsule", P1), sc("c", "Signal", P2), sc("d", "Salt", P2),
  sc("u", "Spare", null, { unplaced: true }),
];
const parts: PartSummary[] = [
  { id: P1, title: "The Recall", frontMatter: false, words: 20, sceneIds: ["a", "b"] },
  { id: P2, title: "Ghost Frequency", frontMatter: false, words: 20, sceneIds: ["c", "d"] },
];

describe("sceneGroups", () => {
  it("lists parts in book order; no top-level group when it is empty", () => {
    const g = sceneGroups(scenes, parts);
    expect(g.map((x) => x.key)).toEqual([P1, P2]);
    expect(g.map((x) => x.scenes.length)).toEqual([2, 2]);
  });
  it("keeps the top level when scenes sit there, and Unplaced on request", () => {
    const g = sceneGroups([...scenes, sc("t", "Loose", null)], parts, { unplaced: true });
    expect(g.map((x) => x.key)).toEqual(["top", P1, P2, "unplaced"]);
    expect(g[0].title).toBe("Manuscript");
  });
  it("a project without parts is one untitled group", () => {
    const g = sceneGroups([sc("x", "One", null)], []);
    expect(g).toHaveLength(1);
    expect(g[0].title).toBe("");
  });
});

describe("planMove", () => {
  const groups = sceneGroups(scenes, parts, { unplaced: true });
  it("drop before a card in another part", () => {
    const m = planMove(groups, "b", { kind: "before", sceneId: "d" })!;
    expect(m).toMatchObject({ partId: P2, index: 1, position: 2, unplaced: false, sameGroup: false });
    expect(m.sentence).toBe("Move “Capsule” to Ghost Frequency, position 2?");
    expect(m.from).toEqual({ partId: P1, unplaced: false, index: 1 });
  });
  it("drop at the end of a part", () => {
    const m = planMove(groups, "a", { kind: "end", groupKey: P2 })!;
    expect(m).toMatchObject({ partId: P2, index: null, position: 3 });
  });
  it("reordering inside a part counts positions without the moved card", () => {
    const m = planMove(groups, "b", { kind: "before", sceneId: "a" })!;
    expect(m).toMatchObject({ partId: P1, index: 0, position: 1, sameGroup: true });
    expect(m.sentence).toBe("Move “Capsule” to position 1 in The Recall?");
  });
  it("a drop that changes nothing is null", () => {
    expect(planMove(groups, "a", { kind: "before", sceneId: "a" })).toBeNull();
    expect(planMove(groups, "a", { kind: "before", sceneId: "b" })).toBeNull();   // already right before b
    expect(planMove(groups, "b", { kind: "end", groupKey: P1 })).toBeNull();       // already last
  });
  it("to and from Unplaced", () => {
    const m = planMove(groups, "u", { kind: "end", groupKey: P1 })!;
    expect(m.from.unplaced).toBe(true);
    expect(m.partId).toBe(P1);
    const n = planMove(groups, "a", { kind: "end", groupKey: "unplaced" })!;
    expect(n).toMatchObject({ unplaced: true, partId: null });
    expect(n.sentence).toBe("Move “Rain” to Parked scenes, position 2?");
  });
  it("unknown ids are ignored", () => {
    expect(planMove(groups, "zzz", { kind: "end", groupKey: P1 })).toBeNull();
    expect(planMove(groups, "a", { kind: "before", sceneId: "zzz" })).toBeNull();
  });
});

describe("follow", () => {
  it("maps through a remap and leaves other ids alone", () => {
    expect(follow("a", { a: "a2" })).toBe("a2");
    expect(follow("b", { a: "a2" })).toBe("b");
    expect(follow("b", undefined)).toBe("b");
  });
});
