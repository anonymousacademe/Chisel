import { describe, expect, it } from "vitest";
import { chartBars, clock, dayLabel, remaining, signedWords, sprintNotice } from "./stats";

describe("stats helpers", () => {
  it("signs words", () => {
    expect(signedWords(1240)).toBe("+1,240");
    expect(signedWords(-35)).toBe("−35");
    expect(signedWords(0)).toBe("+0");
  });
  it("labels a day without time zone shifts", () => {
    expect(dayLabel("2026-10-01")).toBe("Oct 1");
  });
  it("scales bars to the best day, keeping tiny days visible", () => {
    const bars = chartBars([
      { date: "2026-10-01", words: 0 }, { date: "2026-10-02", words: 2 },
      { date: "2026-10-03", words: 100 }, { date: "2026-10-04", words: -20 },
    ], 50);
    expect(bars.map((b) => b.height)).toEqual([0, 4, 100, 0]);
    expect(bars.map((b) => b.met)).toEqual([false, false, true, false]);
  });
  it("formats the countdown", () => {
    expect(clock(1500)).toBe("25:00");
    expect(clock(61.2)).toBe("1:02");
    expect(clock(-3)).toBe("0:00");
  });
  it("computes remaining from the server's end time", () => {
    expect(remaining({ endsAt: 1000 }, 400_000)).toBe(600);
    expect(remaining({ endsAt: 1000 }, 2_000_000)).toBe(0);
  });
  it("words the sprint notice", () => {
    expect(sprintNotice(25, 1312, false)).toBe("Sprint done: 25 minutes, +1,312 words.");
    expect(sprintNotice(1, 1, true)).toBe("Sprint stopped: 1 minute, +1 word.");
    expect(sprintNotice(15, -4, false)).toBe("Sprint done: 15 minutes, −4 words.");
  });
});
