import { describe, expect, it } from "vitest";
import { completionSpot, elementOfLine, upperNames } from "./script";
import type { Span } from "./spans";

describe("completionSpot", () => {
  it("offers places right after a scene prefix", () => {
    expect(completionSpot("INT. ", false)).toEqual({ kind: "place", from: 5 });
    expect(completionSpot("ext. KIT", false)).toEqual({ kind: "place", from: 5 });
    expect(completionSpot("INT./EXT. CA", true)).toEqual({ kind: "place", from: 10 });
  });
  it("offers characters for capitals typed at the start of a block", () => {
    expect(completionSpot("KE", true)).toEqual({ kind: "cue", from: 0 });
    expect(completionSpot("MRS. AL", true)).toEqual({ kind: "cue", from: 0 });
  });
  it("stays out of the way of action and mid-block text", () => {
    expect(completionSpot("Keith walks", true)).toBeNull();
    expect(completionSpot("Ke", true)).toBeNull();
    expect(completionSpot("KE", false)).toBeNull();
    expect(completionSpot("", true)).toBeNull();
  });
});

describe("upperNames", () => {
  it("writes names as cues are written, once each", () => {
    expect(upperNames(["Keith", "mara vale", "KEITH", " "])).toEqual(["KEITH", "MARA VALE"]);
  });
});

describe("elementOfLine", () => {
  const span = (element: string, start: number): Span => ({ kind: "script", element, start, end: start + 5 });
  it("reads the element of the line, defaulting to action", () => {
    const spans = [span("character", 10), span("dialogue", 20)];
    expect(elementOfLine(spans, 10, 15)).toBe("character");
    expect(elementOfLine(spans, 20, 30)).toBe("dialogue");
    expect(elementOfLine(spans, 40, 50)).toBe("action");
  });
});
