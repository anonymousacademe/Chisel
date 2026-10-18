import { describe, expect, it } from "vitest";
import { importedLine } from "./script";
import { isScriptInfo, type ExportInfo, type ExportOptions } from "./export";

describe("script helpers", () => {
  it("says what an import added", () => {
    expect(importedLine({ scenes: 12, parts: 3, first: "manuscript/01-a/01-b.md", filled: [], name: "big-fish.fountain" }))
      .toBe("Imported 12 scenes in 3 parts from big-fish.fountain.");
    expect(importedLine({ scenes: 1, parts: 0, first: "manuscript/01-b.md", filled: [], name: "x.fountain" }))
      .toBe("Imported 1 scene from x.fountain.");
  });

  it("knows a script project from the export formats the server offers", () => {
    const options = {} as ExportOptions;
    const story: ExportInfo = { options, layouts: [], formats: [{ key: "pdf", label: "PDF", ext: "pdf", available: true, reason: "" }] };
    const script: ExportInfo = { ...story, formats: [...story.formats, { key: "fountain", label: "Fountain", ext: "fountain", available: true, reason: "" }] };
    expect(isScriptInfo(story)).toBe(false);
    expect(isScriptInfo(script)).toBe(true);
  });
});
