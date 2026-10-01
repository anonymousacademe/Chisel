import { describe, expect, it } from "vitest";
import { costText, pinAction, replaceImage, splitImages } from "./inspiration";
import type { InspirationImage } from "./types";

const img = (id: string, scene: string, pinned = false): InspirationImage => ({
  id, ext: "jpg", prompt: id, model: "m", scene, created: "2026-10-01T17:53:00", cost: 0.03, pinned, title: "", notes: "", label: id,
});
const A = "manuscript/01-a.md", B = "manuscript/02-b.md";
const all = [img("1", A, true), img("2", B), img("3", A), img("4", "", false), img("5", B, true)];

describe("splitImages", () => {
  it("puts the open scene's pinned pictures first and its others below", () => {
    const s = splitImages(all, A, false);
    expect(s.pinned.map((i) => i.id)).toEqual(["1"]);
    expect(s.rest.map((i) => i.id)).toEqual(["3"]);
  });
  it("switching scenes switches the pinned picture", () => {
    expect(splitImages(all, B, false).pinned.map((i) => i.id)).toEqual(["5"]);
  });
  it("All lists everything else too, never twice", () => {
    const s = splitImages(all, A, true);
    expect(s.pinned.map((i) => i.id)).toEqual(["1"]);
    expect(s.rest.map((i) => i.id)).toEqual(["2", "3", "4", "5"]);
  });
  it("without an open scene nothing is pinned and everything is listed", () => {
    const s = splitImages(all, null, false);
    expect(s.pinned).toEqual([]);
    expect(s.rest).toHaveLength(5);
  });
});

describe("pinAction", () => {
  it("pins, unpins, and is off without a scene", () => {
    expect(pinAction(all[2], A)).toEqual({ label: "Pin to this scene", pin: true, disabled: false });
    expect(pinAction(all[0], A)).toEqual({ label: "Unpin from this scene", pin: false, disabled: false });
    expect(pinAction(all[0], B).pin).toBe(true);          // pinned elsewhere: pinning here moves it
    expect(pinAction(all[0], null).disabled).toBe(true);
  });
});

describe("small helpers", () => {
  it("costText", () => {
    expect(costText(null)).toBe("");
    expect(costText(0.0336)).toBe("$0.034");
    expect(costText(0.0031)).toBe("$0.0031");
  });
  it("replaceImage keeps order", () => {
    const next = { ...all[1], notes: "x" };
    expect(replaceImage(all, next).map((i) => i.notes)).toEqual(["", "x", "", "", ""]);
  });
});
