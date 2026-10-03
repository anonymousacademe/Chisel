import { describe, expect, it } from "vitest";
import { inheritedHint, whenHelp } from "./storyTime";
import type { WhenInfo } from "./types";

const info = (over: Partial<WhenInfo>): WhenInfo => ({ value: "", label: "", source: "none", raw: "", invalid: false, ...over });

describe("storyTime helpers", () => {
  it("hints an inherited time only while the field is blank", () => {
    const inherited = info({ source: "inherited", value: "2187", label: "2187 AE" });
    expect(inheritedHint(inherited, "")).toBe("inherits 2187 AE");
    expect(inheritedHint(inherited, "  ")).toBe("inherits 2187 AE");
    expect(inheritedHint(inherited, "2190")).toBe("");
  });
  it("shows nothing for explicit, none, unknown or a scene that has its own text", () => {
    expect(inheritedHint(info({ source: "explicit", raw: "2187", value: "2187", label: "2187" }), "")).toBe("");
    expect(inheritedHint(info({}), "")).toBe("");
    expect(inheritedHint(undefined, "")).toBe("");
    expect(inheritedHint(info({ source: "inherited", raw: "soon", label: "2187" }), "")).toBe("");
  });
  it("flags a value that is not a story time, otherwise states the rule", () => {
    expect(whenHelp("later", false)).toMatch(/Not a story time/);
    expect(whenHelp("2187", true)).toBe("Optional. Leave blank to use reading order.");
    expect(whenHelp("", false)).toBe("Optional. Leave blank to use reading order.");
    expect(whenHelp("2187", null)).toBe("Optional. Leave blank to use reading order.");
  });
});
