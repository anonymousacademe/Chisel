import { describe, expect, it } from "vitest";
import { isMacPlatform } from "./platform";

describe("isMacPlatform", () => {
  it("is true for macOS platform strings", () => {
    expect(isMacPlatform("MacIntel")).toBe(true);
    expect(isMacPlatform("MacARM")).toBe(true);
  });
  it("is false for Windows and Linux", () => {
    expect(isMacPlatform("Win32")).toBe(false);
    expect(isMacPlatform("Linux x86_64")).toBe(false);
    expect(isMacPlatform("")).toBe(false);
  });
});
