import { describe, expect, it } from "vitest";
import { CHECK_PARAMS, cleanRow, defaultTickedRequirements, describeCheck, rowsToSave, uniqueId } from "./requirementsCustom";
import type { CustomRequirement, SuggestedRequirement } from "./research";

const row = (over: Partial<CustomRequirement>): CustomRequirement => ({ id: "r", group: "Your requirements", title: "T", kind: "check", severity: "warn", ...over });

describe("describeCheck", () => {
  it("says every check kind in plain words", () => {
    const cases: [Partial<CustomRequirement>, string][] = [
      [{ check: "section-present", section: ["abstract"] }, "Abstract: must be present"],
      [{ check: "section-words-max", section: ["abstract"], max: 150 }, "Abstract: at most 150 words"],
      [{ check: "section-words-max", section: ["abstract"], max: 1 }, "Abstract: at most 1 word"],
      [{ check: "section-no-citations", section: ["abstract", "summary"] }, "Abstract or summary: no citations"],
      [{ check: "list-count", section: ["keywords"], min: 3, max: 6 }, "Keywords: 3 to 6 items"],
      [{ check: "list-count", section: ["keywords"], min: 3 }, "Keywords: at least 3 items"],
      [{ check: "list-count", section: ["highlights"], max: 5, item_chars_max: 85 }, "Highlights: at most 5 items, each at most 85 characters"],
      [{ check: "last-section", section: ["references"] }, "References: must be the last section"],
      [{ check: "objects-captioned", object: "fig" }, "Every figure has a caption"],
      [{ check: "objects-captioned", object: "tbl" }, "Every table has a caption"],
      [{ check: "objects-referenced", object: "eq" }, "Every equation is cited in the text"],
      [{ check: "citations-resolved" }, "Every citation matches a source"],
      [{ check: "sources-doi" }, "Every cited source has a DOI"],
    ];
    for (const [r, text] of cases) expect(describeCheck(row(r))).toBe(text);
  });
  it("covers every kind of the contract and an advice row", () => {
    expect(Object.keys(CHECK_PARAMS).sort()).toEqual([
      "citations-resolved", "last-section", "list-count", "objects-captioned", "objects-referenced",
      "section-no-citations", "section-present", "section-words-max", "sources-doi"]);
    expect(describeCheck(row({ kind: "advice", title: "State the software version" }))).toBe("Reminder: State the software version");
  });
});

describe("cleanRow", () => {
  it("keeps only what the check uses and drops the suggestion fields", () => {
    const s: SuggestedRequirement = { ...row({ check: "section-words-max", section: [" abstract ", ""], max: 150, min: 2, object: "fig", source: "g.pdf", quote: "q" }), why: "w", verified: true };
    expect(cleanRow(s)).toEqual({ id: "r", group: "Your requirements", title: "T", kind: "check", severity: "warn", check: "section-words-max", section: ["abstract"], max: 150, source: "g.pdf", quote: "q" });
  });
  it("leaves out empty numbers", () => {
    const r = cleanRow(row({ check: "list-count", section: ["k"], min: 1, max: undefined }));
    expect("max" in r).toBe(false);
  });
});

describe("rowsToSave", () => {
  const item = (id: string, verified: boolean): SuggestedRequirement => ({ ...row({ id, check: "sources-doi" }), why: "", verified });
  it("appends only ticked rows after the existing ones, with unique ids", () => {
    const existing = [row({ id: "a", check: "sources-doi" })];
    const out = rowsToSave(existing, [item("a", true), item("b", true), item("c", false)], new Set(["a", "b"]));
    expect(out.map((r) => r.id)).toEqual(["a", "a-2", "b"]);
  });
  it("ticks only verified items by default", () => {
    expect([...defaultTickedRequirements([item("a", true), item("b", false)])]).toEqual(["a"]);
  });
  it("makes ids from titles", () => {
    expect(uniqueId("Abstract Length!", new Set())).toBe("abstract-length");
  });
});
