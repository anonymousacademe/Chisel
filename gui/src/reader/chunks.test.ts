import { describe, expect, it } from "vitest";
import { chunkSpeech } from "./chunks";

describe("chunkSpeech", () => {
  it("keeps short text whole", () => {
    expect(chunkSpeech("One short sentence.")).toEqual(["One short sentence."]);
    expect(chunkSpeech("  \n ")).toEqual([]);
  });

  it("joins short sentences up to the limit and cuts at sentence ends", () => {
    const text = "First one. Second one! Third one? Fourth one.";
    expect(chunkSpeech(text, 200)).toEqual([text]);
    expect(chunkSpeech(text, 24)).toEqual(["First one. Second one!", "Third one? Fourth one."]);
  });

  it("splits a long sentence at commas, then spaces, and never loses a word", () => {
    const long = "alpha beta gamma, delta epsilon zeta eta theta, iota kappa lambda mu nu xi omicron pi rho sigma tau";
    const chunks = chunkSpeech(long, 40);
    expect(chunks.every((c) => c.length <= 40)).toBe(true);
    expect(chunks.join(" ").replace(/\s+/g, " ")).toBe(long);
    expect(chunks[0]).toBe("alpha beta gamma,");
  });

  it("breaks one unbroken word longer than the limit", () => {
    const chunks = chunkSpeech("x".repeat(95), 40);
    expect(chunks.map((c) => c.length)).toEqual([40, 40, 15]);
  });

  it("keeps closing quotes with their sentence and treats an ellipsis as an end", () => {
    expect(chunkSpeech("“Stop,” she said. Then silence… Then more.", 22)).toEqual(
      ["“Stop,” she said.", "Then silence…", "Then more."]);
  });

  it("copes with text that has no punctuation at all", () => {
    expect(chunkSpeech("no punctuation here at all", 200)).toEqual(["no punctuation here at all"]);
  });
});
