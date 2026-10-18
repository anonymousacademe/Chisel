import { describe, expect, it } from "vitest";
import { progressLabel, timeLeft } from "./format";

const u = (seconds: number) => ({ kind: "narration", voice: "narrator", text: "", say: "", start: 0, end: 1, row: 0, seconds });

describe("timeLeft", () => {
  it("adds up what is left and scales by the rate", () => {
    const list = [u(60), u(60), u(60), u(60)];
    expect(timeLeft(list, 0, 1)).toBe("about 4 min");
    expect(timeLeft(list, 2, 1)).toBe("about 2 min");
    expect(timeLeft(list, 0, 2)).toBe("about 2 min");
    expect(timeLeft(list, 3, 4)).toBe("under a minute");
    expect(timeLeft([], 0, 1)).toBe("under a minute");
    expect(timeLeft([u(3600), u(1800)], 0, 1)).toBe("about 1 h 30 min");
    expect(timeLeft([u(7200)], 0, 1)).toBe("about 2 h");
  });
});

describe("progressLabel", () => {
  it("says where the reading is", () => {
    expect(progressLabel("idle", 0, 24)).toBe("24 passages");
    expect(progressLabel("idle", 0, 1)).toBe("1 passage");
    expect(progressLabel("playing", 2, 24)).toBe("Reading 3 of 24");
    expect(progressLabel("paused", 4, 24)).toBe("Paused at 5 of 24");
    expect(progressLabel("done", 23, 24)).toBe("Finished");
    expect(progressLabel("idle", 0, 0)).toBe("Nothing to read");
  });
});

describe("costLine", () => {
  it("says free, the published price, or to check", async () => {
    const { costLine, megabytes } = await import("./format");
    expect(costLine({ local: true, pricePerMillion: 0, perHour: 0 })).toMatch(/no cost/);
    expect(costLine({ local: false, pricePerMillion: 15, perHour: 0.81 }, 0.012)).toBe(
      "Cloud service: about $15 per million characters, about $0.81 per hour of listening (estimate; clips heard again are free). This session: about $0.012.");
    expect(costLine({ local: false, pricePerMillion: null, perHour: null })).toMatch(/check its price/);
    expect(megabytes(92_361_116)).toBe("92 MB");
  });
});
