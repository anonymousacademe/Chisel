import { describe, expect, it } from "vitest";
import { costText, isUpload, itemNoun, pinAction, replaceImage, splitImages, uploadProblem, UPLOAD_MAX_BYTES } from "./inspiration";
import type { InspirationImage } from "./types";

const img = (id: string, item: string, pinned = false, source = ""): InspirationImage => ({
  id, ext: "jpg", prompt: id, model: "m", for: item, scene: item, created: "2026-10-01T17:53:00", cost: 0.03, pinned, title: "", notes: "", label: id,
  source, unlinked: false,
});
const A = "manuscript/01-a.md", B = "manuscript/02-b.md", MARA = "entities/characters/mara.md", NB = "notebook/tides.md";
const all = [img("1", A, true), img("2", B), img("3", A), img("4", "", false), img("5", B, true), img("6", MARA, true), img("7", NB, false, "upload")];

describe("splitImages", () => {
  it("puts the open item's pinned pictures first and its others below", () => {
    const s = splitImages(all, A);
    expect(s.pinned.map((i) => i.id)).toEqual(["1"]);
    expect(s.rest.map((i) => i.id)).toEqual(["3"]);
  });
  it("switching items switches the pinned picture", () => {
    expect(splitImages(all, B).pinned.map((i) => i.id)).toEqual(["5"]);
  });
  it("works for a character / place / object note and for a notebook note", () => {
    expect(splitImages(all, MARA).pinned.map((i) => i.id)).toEqual(["6"]);
    const nb = splitImages(all, NB);
    expect(nb.pinned).toEqual([]);
    expect(nb.rest.map((i) => i.id)).toEqual(["7"]);
  });
  it("'Show all' is everything that is not for the open item, never twice", () => {
    const s = splitImages(all, A);
    expect(s.others.map((i) => i.id)).toEqual(["2", "4", "5", "6", "7"]);
    expect([...s.pinned, ...s.rest, ...s.others]).toHaveLength(all.length);
  });
  it("without an open item nothing is pinned and everything is listed", () => {
    const s = splitImages(all, null);
    expect(s.pinned).toEqual([]);
    expect(s.rest).toHaveLength(all.length);
    expect(s.others).toEqual([]);
  });
  it("a link that resolves to nothing open stays out of the item's pictures (the grid labels it Unlinked)", () => {
    const orphan = { ...img("9", "manuscript/gone.md"), unlinked: true };
    expect(splitImages([orphan], A).others).toEqual([orphan]);
  });
});

describe("pinAction", () => {
  it("pins, unpins, and is off without an item", () => {
    expect(pinAction(all[2], A)).toEqual({ label: "Pin to this scene", pin: true, disabled: false });
    expect(pinAction(all[0], A)).toEqual({ label: "Unpin from this scene", pin: false, disabled: false });
    expect(pinAction(all[0], B).pin).toBe(true);          // pinned elsewhere: pinning here moves it
    expect(pinAction(all[0], null).disabled).toBe(true);
  });
  it("speaks of the note for a note", () => {
    expect(pinAction(all[5], MARA, itemNoun("entity")).label).toBe("Unpin from this note");
    expect(pinAction(all[6], NB, itemNoun("research")).label).toBe("Pin to this note");
    expect(itemNoun("scene")).toBe("scene");
  });
});

describe("uploads", () => {
  const file = (type: string, size = 100, name = "a.png") => ({ name, type, size });
  it("accepts JPG, PNG and WebP up to the limit", () => {
    for (const t of ["image/jpeg", "image/png", "image/webp"]) expect(uploadProblem(file(t))).toBeNull();
    expect(uploadProblem(file("image/png", UPLOAD_MAX_BYTES))).toBeNull();
  });
  it("refuses GIF, SVG, other types, empty and oversize files", () => {
    for (const t of ["image/gif", "image/svg+xml", "application/pdf", ""]) expect(uploadProblem(file(t))).toMatch(/JPG, PNG or WebP/);
    expect(uploadProblem(file("image/png", 0))).toMatch(/empty/);
    expect(uploadProblem(file("image/png", UPLOAD_MAX_BYTES + 1))).toMatch(/10 MB/);
  });
  it("tells uploads from generated pictures", () => {
    expect(isUpload(all[6])).toBe(true);
    expect(isUpload(all[0])).toBe(false);
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
    expect(replaceImage(all, next).map((i) => i.notes)).toEqual(["", "x", "", "", "", "", ""]);
  });
});
