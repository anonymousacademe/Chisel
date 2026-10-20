import { describe, expect, it } from "vitest";
import {
  PART_WORDS_CAP, SCENE_WORDS_CAP, TRIMMED_NOTE, acceptAllSentence, batchLabel, cleanProposal, costLine, coverageLine, estimateSentence, leftOutLine, leftOutReason, money,
  afterLine, progressLine, reviewLabel, rowNote, showNotice, statusLabel, statusNote, storySoFarChip, thinkingNote, tolerantNote, wordCount, wordsLine,
  type Estimate, type Pending, type ScaleHint, type SceneProposal, type StatusInfo,
} from "./summaries";
import type { SentReport } from "./types";

const est = (over: Partial<Estimate> = {}): Estimate => ({
  calls: 3, inputTokens: 12000, outputTokens: { low: 900, high: 3000 }, model: "m/x", local: false, reasoningModel: false, reasoning: "default",
  price: { promptPerM: 3, completionPerM: 15 }, cost: { low: 0.0495, high: 0.081 }, costText: "$0.0495 to $0.0810", skipped: [], notes: [], ...over,
});
const proposal = (over: Partial<SceneProposal> = {}): SceneProposal => ({
  id: "manuscript/01-a.md", model: "m/x", replacing: false, proposal: { summary: "S.", characters: [], facts: [], threads: [] },
  dropped: [], tolerant: 0, trimmed: false, sourceHash: "h", cost: 0.002, sent: { feature: "summary", estTokens: 1, window: 2, reserve: 1, overBudget: false, trimmed: false, sections: [], attached: [] }, ...over,
});
const pending = (over: Partial<SceneProposal> = {}, id = "a"): Pending => ({ kind: "scene", id, title: id, result: proposal(over), from: "panel" });

describe("status wording", () => {
  it("names the four states for people", () => {
    expect(["missing", "fresh", "stale", "locked"].map((s) => statusLabel(s as never))).toEqual(["None", "Fresh", "Out of date", "Locked"]);
  });
  it("says plainly that the scene changed after an out-of-date summary", () => {
    expect(statusNote("stale")).toBe("The scene changed after this summary was written.");
    expect(statusNote("locked")).toMatch(/never rewrites/);
    expect(statusNote("locked", true)).toMatch(/scene changed after/);
    expect(statusNote("fresh")).toBe("");
    expect(statusNote("missing")).toBe("No summary yet.");
  });
});

describe("word count", () => {
  it("counts words, not spaces", () => {
    expect(wordCount("")).toBe(0);
    expect(wordCount("  one  two\nthree ")).toBe(3);
  });
  it("shows the count against the cap and says when it is over", () => {
    expect(wordsLine("a b c", SCENE_WORDS_CAP)).toEqual({ text: "3 of 90 words", over: false });
    const long = Array(104).fill("w").join(" ");
    expect(wordsLine(long, SCENE_WORDS_CAP)).toEqual({ text: "104 of 90 words: 14 over", over: true });
    expect(wordsLine(Array(150).fill("w").join(" "), PART_WORDS_CAP).over).toBe(false);
  });
});

describe("coverage line", () => {
  const totals = (missing: number, stale: number, scenes = 41): StatusInfo["totals"] => ({ scenes, counts: { missing, fresh: scenes - missing - stale, stale, locked: 0 }, percent: 0 });
  it("reads like the brief", () => {
    expect(coverageLine(totals(10, 4))).toBe("31 of 41 scenes have a summary; 4 are out of date");
    expect(coverageLine(totals(0, 1, 5))).toBe("5 of 5 scenes have a summary; 1 is out of date");
    expect(coverageLine(totals(40, 0))).toBe("1 of 41 scenes has a summary");
    expect(coverageLine(totals(0, 0, 3), "chapter")).toBe("3 of 3 chapters have a summary");
  });
});

describe("what was left out", () => {
  it("turns Python's reasons into plain words", () => {
    expect(leftOutReason("its quote is not in the scene")).toBe("the passage it quoted is not in your scene");
    expect(leftOutReason("it has no quote")).toMatch(/without a quote|came without/);
    expect(leftOutReason("a piece of its quote (between ...) is shorter than 8 characters")).toMatch(/too short/);
    expect(leftOutReason("the pieces of its quote are not in the scene in that order")).toMatch(/in that order/);
    expect(leftOutReason("the pieces of its quote are more than 2000 characters apart in the scene")).toMatch(/far apart/);
    expect(leftOutReason("the name does not occur in the scene")).toBe("the name does not appear in your scene");
    expect(leftOutReason("something new")).toBe("something new");
  });
  it("makes one sentence per item", () => {
    expect(leftOutLine({ kind: "fact", text: "Elias had a gun", reason: "its quote is not in the scene" }))
      .toBe("Fact: Elias had a gun. Left out because the passage it quoted is not in your scene.");
    expect(leftOutLine({ kind: "character", text: "Rook", reason: "the name does not occur in the scene" })).toMatch(/^Character: Rook\./);
  });
  it("says what the looser quote check did, without jargon", () => {
    expect(tolerantNote(0)).toBe("");
    expect(tolerantNote(1)).toMatch(/^1 fact was kept/);
    expect(tolerantNote(3)).toMatch(/^3 facts were kept/);
    expect(tolerantNote(2)).not.toMatch(/tolerant|hash/i);
    expect(TRIMMED_NOTE).toMatch(/cut it after the last whole sentence/);
  });
});

describe("money and cost", () => {
  it("formats small prices", () => {
    expect(money(0)).toBe("free");
    expect(money(0.00001)).toBe("less than $0.0001");
    expect(money(0.0031)).toBe("$0.0031");
    expect(money(0.5)).toBe("$0.50");
    expect(costLine(null)).toBe("");
    expect(costLine(0.0123)).toBe("cost $0.0123");
  });
});

describe("estimate sentence", () => {
  it("says calls, size, model and price, and explains tokens once", () => {
    const s = estimateSentence(est());
    expect(s).toMatch(/3 scenes to m\/x/);
    expect(s).toMatch(/12,000 tokens \(small pieces of text/);
    expect(s).toMatch(/900 to 3,000 tokens back/);
    expect(s).toMatch(/about \$0\.0495 to \$0\.0810/);
  });
  it("says the price is unknown rather than inventing one", () => {
    const s = estimateSentence(est({ cost: null, price: null }));
    expect(s).toMatch(/The price is unknown/);
    expect(s).not.toMatch(/\$/);
  });
  it("a local model costs nothing; a single scene is singular; nothing to do is said", () => {
    expect(estimateSentence(est({ local: true, cost: { low: 0, high: 0 } }))).toMatch(/costs nothing/);
    expect(estimateSentence(est({ calls: 1 }))).toMatch(/send 1 scene to/);
    expect(estimateSentence(est({ calls: 0 }))).toMatch(/Nothing to write/);
    expect(estimateSentence(est({ calls: 0, skipped: ["x"] }))).toMatch(/locked or edited/);
  });
  it("says a thinking model is slower and dearer, and what the setting is", () => {
    expect(thinkingNote(est({ reasoningModel: true }))).toMatch(/thinks before it answers.*slower and dearer.*setting is the model’s own choice/);
    expect(thinkingNote(est({ reasoningModel: true, reasoning: "off" }))).toMatch(/setting is off, so it will answer straight away/);
    expect(thinkingNote(est({ reasoningModel: null, reasoning: "low" }))).toMatch(/does not know whether.*low/);
    expect(thinkingNote(est({ reasoningModel: false }))).toBe("");
    expect(thinkingNote(est({ local: true, reasoningModel: null }))).toBe("");
  });
});

describe("batch helpers", () => {
  it("only a proposal with nothing left out and nothing cut is clean", () => {
    expect(cleanProposal(pending())).toBe(true);
    expect(cleanProposal(pending({ trimmed: true }))).toBe(false);
    expect(cleanProposal(pending({ dropped: [{ kind: "fact", text: "x", reason: "r" }] }))).toBe(false);
    expect(cleanProposal({ ...pending(), kind: "part" })).toBe(false);
  });
  it("the accept-all sentence says exactly what will happen", () => {
    const list = [pending({}, "a"), pending({}, "b"), pending({ trimmed: true }, "c")];
    const s = acceptAllSentence(list);
    expect(s).toMatch(/^Save 2 summaries exactly as proposed/);
    expect(s).toMatch(/The other 1 has something left out or shortened; it stays in the list/);
    expect(s).toMatch(/checked again against your text/);
    expect(acceptAllSentence([pending({ trimmed: true })])).toMatch(/None of these proposals is free/);
    expect(acceptAllSentence([pending()])).toMatch(/^Save 1 summary exactly as proposed: it had/);
  });
  it("the batch button says what it writes", () => {
    expect(batchLabel(5, 0)).toBe("Write the missing summaries");
    expect(batchLabel(0, 6)).toBe("Write the out of date summaries again");
    expect(batchLabel(2, 6)).toBe("Write the missing and out of date summaries");
  });
  it("the row note is short and says when the scene changed", () => {
    expect(rowNote({ status: "fresh", changedSince: false })).toBe("");
    expect(rowNote({ status: "stale", changedSince: false })).toBe("scene changed since");
    expect(rowNote({ status: "locked", changedSince: true }, true)).toBe("proposal waiting · scene changed since");
    expect(rowNote({ status: "missing", changedSince: false }, true)).toBe("proposal waiting");
  });
  it("progress and review labels", () => {
    expect(progressLine(0, 12, "Chapter I")).toBe("Writing summary 1 of 12: Chapter I");
    expect(progressLine(12, 12, "End")).toBe("Writing summary 12 of 12: End");
    expect(reviewLabel(12)).toBe("Review 12 proposals");
    expect(reviewLabel(1)).toBe("Review 1 proposal");
  });
});

describe("the growth notice", () => {
  const hint = (over: Partial<ScaleHint> = {}): ScaleHint => ({
    level: "notice", message: "This project is getting long.", dismissed: false, dismissedLevel: "", model: "m/x", after: null,
    numbers: { words: 1, scenes: 1, entities: 0, window: 1, windowWords: 1, ratio: 1, coveragePercent: 0, summarised: 0, missing: 1, stale: 0 }, ...over,
  });
  it("shows for notice and strong, never for none or a closed one", () => {
    expect(showNotice(hint())).toBe(true);
    expect(showNotice(hint({ level: "strong" }))).toBe(true);
    expect(showNotice(hint({ level: "none", message: "" }))).toBe(false);
    expect(showNotice(hint({ dismissed: true }))).toBe(false);
    expect(showNotice(null)).toBe(false);
  });
});

describe("what the AI still does not see", () => {
  const base: ScaleHint = {
    level: "none", message: "", dismissed: false, dismissedLevel: "", model: "m/x", after: null,
    numbers: { words: 1, scenes: 1, entities: 0, window: 1, windowWords: 1, ratio: 1, coveragePercent: 100, summarised: 1, missing: 0, stale: 0 },
  };
  it("is a plain line, never shown for nothing, and has no unexplained jargon", () => {
    const text = "Summaries cover your whole book. When you check a scene, Chisel sends a short story so far (about 5,000 tokens, roughly 3,800 words, for your last scene) and what is recorded about the characters in it, not the full text of earlier chapters.";
    expect(afterLine({ ...base, after: ` ${text} ` })).toBe(text);
    expect(afterLine({ ...base, after: null })).toBeNull();
    expect(afterLine({ ...base, after: "  " })).toBeNull();
    expect(afterLine(null)).toBeNull();
    expect(text).not.toMatch(/hash|tolerant|fixes/i);
    expect(text).toMatch(/tokens, roughly [\d,]+ words/);      // "token" always comes with words
  });
  it("is not a notice: showNotice stays false when only the line is set", () => {
    expect(showNotice({ ...base, after: "x" })).toBe(false);
  });
});

describe("the assistant chip", () => {
  const sent = (names: string[]): SentReport => ({
    feature: "ask", estTokens: 1, window: 2, reserve: 1, overBudget: false, trimmed: false, attached: [],
    sections: names.map((name) => ({ name, chars: 1, estTokens: 1, itemsTotal: 1, itemsSent: 1, itemsDropped: [], truncated: [], omitted: false })),
  });
  it("appears only when the reply was sent the story so far", () => {
    expect(storySoFarChip(sent(["Scene", "Story so far"]))).toBe("Story so far included");
    expect(storySoFarChip(sent(["Scene"]))).toBeNull();
    expect(storySoFarChip(null)).toBeNull();
    const dropped = sent(["Story so far"]);
    dropped.sections[0].omitted = true;
    expect(storySoFarChip(dropped)).toBeNull();
  });
});
