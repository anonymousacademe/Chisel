import { describe, expect, it } from "vitest";
import { canonLeftOutLine, canonLeftOutTitle, canonTolerantNote, pickedFacts, quoteOf } from "./canon";
import type { CanonProposal } from "./types";

const proposal = (over: Partial<CanonProposal> = {}): CanonProposal => ({
  entity: "Luzhin", facts: ["is forty-five", "wears a copper cross"], evidence: "a / b", existing: "",
  quotes: ["Luzhin was forty-five", "wore a copper cross on a cord"], kinds: ["age", "possession"], ...over,
});

describe("canon left-out helpers", () => {
  it("says in plain words why a fact was left out", () => {
    expect(canonLeftOutLine({ entity: "Luzhin", fact: "is forty-five", reason: "its quote is not in the scene" }))
      .toBe("Luzhin: is forty-five. Left out because the passage it quoted is not in your scene.");
    expect(canonLeftOutLine({ entity: "Dounia", fact: "has black eyes", reason: "it has no quote" }))
      .toBe("Dounia: has black eyes. Left out because it came without a quote from your scene.");
  });

  it("titles the disclosure with the count, and is empty for none", () => {
    expect(canonLeftOutTitle([])).toBe("");
    const d = { entity: "L", fact: "f", reason: "it has no quote" };
    expect(canonLeftOutTitle([d, d])).toMatch(/^Left out \(2\): /);
  });

  it("reads the quote of a fact by position, and copes with an old reply without quotes", () => {
    expect(quoteOf(proposal(), 1)).toBe("wore a copper cross on a cord");
    expect(quoteOf(proposal({ quotes: undefined }), 0)).toBe("");
    expect(quoteOf(proposal(), 9)).toBe("");
  });

  it("notes the facts kept on the looser check", () => {
    expect(canonTolerantNote(0)).toBe("");
    expect(canonTolerantNote(2)).toMatch(/^2 facts were kept/);
  });

  it("sends only the ticked facts, without quotes", () => {
    const key = (e: string, f: string) => `${e}|${f}`;
    const on = new Set([key("Luzhin", "wears a copper cross")]);
    expect(pickedFacts([proposal(), proposal({ entity: "Dounia", facts: ["x"] })], on, key))
      .toEqual([{ entity: "Luzhin", facts: ["wears a copper cross"] }]);
  });
});
