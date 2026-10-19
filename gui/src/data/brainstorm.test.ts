import { describe, expect, it } from "vitest";
import { focusExcerpt, focusPrompt } from "./brainstorm";

describe("focused brainstorm wording", () => {
  it("keeps a short passage whole, on one line", () => {
    expect(focusExcerpt("He grew up\n  in Tulsa.")).toBe("He grew up in Tulsa.");
  });

  it("cuts a long passage at a word", () => {
    const long = "Derek learned the phrase from his father, who said it about everything from storms to supper.";
    const out = focusExcerpt(long, 40);
    expect(out.endsWith("…")).toBe(true);
    expect(out.length).toBeLessThanOrEqual(41);
    expect(long.startsWith(out.slice(0, -1))).toBe(true);
  });

  it("puts the direction after the passage, when there is one", () => {
    expect(focusPrompt({ text: "He never calls home.", direction: "  why not? " }))
      .toBe("Brainstorm about “He never calls home.”: why not?");
    expect(focusPrompt({ text: "He never calls home.", direction: "" })).toBe("Brainstorm about “He never calls home.”");
  });
});
