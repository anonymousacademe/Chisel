import { describe, expect, it } from "vitest";
import { importedLine, voiceNotice } from "./script";
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

describe("voiceNotice", () => {
  const base = { issues: [], waived: 0, checked: [], skipped: [], minLines: 5 };
  it("says what was judged and what was not", () => {
    expect(voiceNotice({ ...base, issues: [{}, {}], checked: ["Keith"], skipped: [{ speaker: "Mara", lines: 2 }] }))
      .toBe("2 lines may be off voice. Checked Keith. Not judged (fewer than 5 lines elsewhere to compare): Mara (2).");
    expect(voiceNotice({ ...base, issues: [{}], waived: 1, checked: ["Keith", "Mara"] }))
      .toBe("1 line may be off voice (1 waived). Checked Keith, Mara.");
    expect(voiceNotice({ ...base, checked: ["Keith"] })).toBe("Every checked line sounds like its character. Checked Keith.");
  });
  it("explains an empty check instead of reporting a clean bill of health", () => {
    expect(voiceNotice({ ...base, skipped: [{ speaker: "Keith", lines: 1 }] }))
      .toBe("Nothing to compare yet. Not judged (fewer than 5 lines elsewhere to compare): Keith (1).");
  });
});

describe("voiceNotice when the window was too small", () => {
  it("does not call that 'too few lines'", () => {
    const base = { issues: [], waived: 0, checked: [], skipped: [], minLines: 5 };
    expect(voiceNotice({ ...base, notFit: ["Keith"] }))
      .toBe("Nothing to compare yet. Not compared (their lines did not fit the model's window): Keith.");
    expect(voiceNotice({ ...base, checked: ["Mara"], notFit: ["Keith"] }))
      .toBe("Every checked line sounds like its character. Checked Mara. Not compared (their lines did not fit the model's window): Keith.");
  });
});
