import { describe, expect, it } from "vitest";
import { droppedOf, fmtTokens, isTrimmed, nameList, sectionNote, sectionTrimmed, sentSummary, truncatedOf, usageLine } from "./sent";
import type { SentReport, SentSection } from "./types";

const sec = (over: Partial<SentSection> = {}): SentSection => ({
  name: "Scene", chars: 400, estTokens: 100, itemsTotal: 1, itemsSent: 1, itemsDropped: [], truncated: [], omitted: false, ...over,
});
const report = (sections: SentSection[], over: Partial<SentReport> = {}): SentReport => ({
  feature: "ask", estTokens: 3200, window: 200000, reserve: 4000, overBudget: false, trimmed: false, sections, attached: [], ...over,
});

describe("fmtTokens", () => {
  it("is plain below a thousand and k / M above", () => {
    expect(fmtTokens(0)).toBe("0");
    expect(fmtTokens(950)).toBe("950");
    expect(fmtTokens(3200)).toBe("3.2k");
    expect(fmtTokens(200000)).toBe("200k");
    expect(fmtTokens(1000000)).toBe("1M");
    expect(fmtTokens(1500000)).toBe("1.5M");
  });
});

describe("report helpers", () => {
  const notes = sec({ name: "Characters and places", itemsTotal: 5, itemsSent: 3, itemsDropped: ["Orin", "Pell"], truncated: ["Mara"] });
  it("says nothing is trimmed for a whole report", () => {
    const r = report([sec()]);
    expect(isTrimmed(r)).toBe(false);
    expect(sentSummary(r)).toBe("sent ~3.2k tokens of 200k");
    expect(usageLine(r)).toBe("~3.2k tokens of 200k");
  });
  it("counts what was dropped and shortened, across sections", () => {
    const r = report([sec(), notes, sec({ name: "Scene titles", itemsTotal: 9, itemsSent: 8, itemsDropped: ["Last"] })]);
    expect(droppedOf(r)).toEqual(["Orin", "Pell", "Last"]);
    expect(truncatedOf(r)).toEqual(["Mara"]);
    expect(isTrimmed(r)).toBe(true);
    expect(sentSummary(r)).toBe("sent ~3.2k tokens of 200k; 3 dropped; 1 trimmed");
  });
  it("flags a request over the window", () => {
    const r = report([sec()], { overBudget: true });
    expect(isTrimmed(r)).toBe(true);
    expect(sentSummary(r)).toContain("over the window");
  });
  it("describes a section by what it sent and what it left out", () => {
    expect(sectionNote(sec())).toBe("");
    expect(sectionNote(notes)).toBe("3 of 5 sent; dropped: Orin, Pell; shortened: Mara");
    expect(sectionNote(sec({ name: "Style guide", omitted: true, itemsSent: 0, itemsDropped: ["Style guide"] }))).toBe("left out");
    expect(sectionTrimmed(notes)).toBe(true);
    expect(sectionTrimmed(sec())).toBe(false);
  });
});

describe("nameList", () => {
  it("lists a few and counts the rest", () => {
    expect(nameList(["a", "b"], 3)).toBe("a, b");
    expect(nameList(["a", "b", "c", "d", "e"], 3)).toBe("a, b, c and 2 more");
  });
});
