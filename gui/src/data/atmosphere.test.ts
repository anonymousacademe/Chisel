import { describe, expect, it } from "vitest";
import { activeCount, ambienceLabel, gainOf, keyClass, validStationUrl, DEFAULT_PREFS } from "./atmosphere";

describe("keyClass", () => {
  it("classifies typing keys", () => {
    expect(keyClass({ key: "a" })).toBe("key");
    expect(keyClass({ key: "é" })).toBe("key");
    expect(keyClass({ key: "😀" })).toBe("key");
    expect(keyClass({ key: " " })).toBe("space");
    expect(keyClass({ key: "Enter" })).toBe("return");
    expect(keyClass({ key: "Backspace" })).toBe("backspace");
    expect(keyClass({ key: "Delete" })).toBe("backspace");
  });
  it("ignores navigation, shortcuts and composition", () => {
    for (const key of ["ArrowLeft", "Shift", "Control", "Escape", "Tab", "F7", "Dead"]) expect(keyClass({ key })).toBeNull();
    expect(keyClass({ key: "s", ctrlKey: true })).toBeNull();
    expect(keyClass({ key: "s", metaKey: true })).toBeNull();
    expect(keyClass({ key: "a", isComposing: true })).toBeNull();
  });
});

describe("validStationUrl", () => {
  it("accepts http(s) only", () => {
    expect(validStationUrl(" https://ice1.somafm.com/fluid-128-mp3 ")).toBe("https://ice1.somafm.com/fluid-128-mp3");
    expect(validStationUrl("http://example.org:8000/x")).toBe("http://example.org:8000/x");
    for (const bad of ["", "ftp://a.org/x", "javascript:alert(1)", "file:///etc/passwd", "https://", "http://a b.org", "somafm.com", "data:audio/wav;base64,AA"]) expect(validStationUrl(bad)).toBeNull();
    expect(validStationUrl("https://a.org/" + "x".repeat(400))).toBeNull();
  });
});

describe("mix helpers", () => {
  it("counts and labels", () => {
    expect(activeCount({ ...DEFAULT_PREFS.ambience, layers: { rain: 0.4, fire: 0 }, loops: { "a.ogg": 0.2 } })).toBe(2);
    expect(ambienceLabel(false, "Fluid", 3)).toBe("Ambience");
    expect(ambienceLabel(true, null, 1)).toBe("1 layer");
    expect(ambienceLabel(true, null, 2)).toBe("2 layers");
    expect(ambienceLabel(true, "Fluid", 0)).toBe("Fluid");
    expect(ambienceLabel(true, "Fluid", 2)).toBe("Fluid + 2");
  });
  it("squares the volume and clamps", () => {
    expect(gainOf(0.5)).toBe(0.25);
    expect(gainOf(3)).toBe(1);
    expect(gainOf(-1)).toBe(0);
  });
});
