import { describe, expect, it } from "vitest";
import { anchorDraft } from "./drafts";

describe("anchorDraft", () => {
  const snap = "One two three four.";
  it("draft: original spot when the buffer is unchanged, the cursor otherwise", () => {
    const r = { mode: "draft" as const, from: 7, to: 7, original: null };
    expect(anchorDraft(snap, snap, r, 0)).toEqual({ from: 7, to: 7 });
    expect(anchorDraft("Edited. " + snap, snap, r, 12)).toEqual({ from: 12, to: 12 });
  });
  it("rewrite: same range if the selected text is unchanged", () => {
    const r = { mode: "rewrite" as const, from: 4, to: 7, original: "two" };
    expect(anchorDraft(snap, snap, r, 0)).toEqual({ from: 4, to: 7 });
  });
  it("rewrite: re-finds the text when it moved, refuses when ambiguous or gone", () => {
    const r = { mode: "rewrite" as const, from: 4, to: 7, original: "two" };
    expect(anchorDraft("Intro. " + snap, snap, r, 0)).toEqual({ from: 11, to: 14 });
    expect(anchorDraft("two " + snap, snap, r, 0)).toBeNull();          // now occurs twice
    expect(anchorDraft("One 2 three four.", snap, r, 0)).toBeNull();    // edited away
  });
  it("expand behaves like rewrite (the marker is the original)", () => {
    const r = { mode: "expand" as const, from: 2, to: 15, original: "{{expand: x}}" };
    const cur = "A {{expand: x}} b";
    expect(anchorDraft(cur, cur, r, 0)).toEqual({ from: 2, to: 15 });
  });
});
