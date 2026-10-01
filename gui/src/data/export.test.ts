import { describe, expect, it } from "vitest";
import { fitOptions, summaryLine, usableFormat, type ExportInfo, type ExportOptions } from "./export";

const base: ExportOptions = {
  format: "pdf", layout: "manuscript", page_size: "trade", font: "noto-serif", numbering: "words",
  toc: true, include_front_matter: true, include_drafts: false, continuous: false, copyright: "",
};
const info: ExportInfo = {
  options: base,
  formats: [
    { key: "pdf", label: "PDF", ext: "pdf", available: false, reason: "install ReportLab" },
    { key: "md", label: "Markdown", ext: "md", available: true, reason: "" },
  ],
  layouts: [
    { name: "book", label: "Book", description: "", page_sizes: ["trade", "a5"], toc: true, continuous: true, numbering: true,
      fonts: [{ key: "noto-serif", label: "Noto Serif", available: true }] },
    { name: "manuscript", label: "Manuscript", description: "", page_sizes: ["letter"], toc: false, continuous: true, numbering: true,
      fonts: [{ key: "liberation-serif", label: "Liberation Serif", available: false }, { key: "liberation-mono", label: "Liberation Mono", available: true }] },
  ],
};

describe("export dialog helpers", () => {
  it("writes the summary line", () => {
    expect(summaryLine({ scenes: 4, words: 1502, parts: 2, draft_scenes: 1, messages: [] }, "scene"))
      .toBe("4 scenes, 1,502 words, 2 parts; 1 scene has unaccepted AI drafts");
    expect(summaryLine({ scenes: 1, words: 1, parts: 0, draft_scenes: 0, messages: [] }, "chapter")).toBe("1 chapter, 1 word");
  });
  it("forces page size and font into the layout, preferring installed fonts", () => {
    expect(fitOptions(info, base)).toMatchObject({ page_size: "letter", font: "liberation-mono" });
    expect(fitOptions(info, { ...base, layout: "book" })).toMatchObject({ page_size: "trade", font: "noto-serif" });
    expect(fitOptions(info, { ...base, format: "md" })).toEqual({ ...base, format: "md" });
  });
  it("falls back to a format that can run", () => {
    expect(usableFormat(info, "pdf")).toBe("md");
    expect(usableFormat(info, "md")).toBe("md");
  });
});
