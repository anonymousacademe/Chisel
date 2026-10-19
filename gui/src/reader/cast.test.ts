import { describe, expect, it } from "vitest";
import { candidateVoices, defaultCast, loadPrefs, resolveCast, roleLabel, savePrefs, DEFAULT_PREFS } from "./cast";

const v = (id: string, lang = "en-US", local = true) => ({ id, name: id, lang, local });
const voices = [v("zira"), v("david"), v("hazel", "en-GB"), v("denise", "fr-FR"), v("cloud", "en-US", false)];

describe("voices and the cast", () => {
  it("prefers voices in the interface language, installed ones first", () => {
    expect(candidateVoices(voices, "en-US").map((x) => x.id)).toEqual(["david", "hazel", "zira", "cloud"]);
    expect(candidateVoices(voices, "fr").map((x) => x.id)).toEqual(["denise"]);
    expect(candidateVoices(voices, "de-DE").map((x) => x.id)).toHaveLength(5);      // none match: all of them
    expect(candidateVoices([], "en")).toEqual([]);
  });

  it("gives the narrator the first voice and the other roles the following ones, so they differ", () => {
    expect(defaultCast(["narrator", "quote", "Keith", "Mara"], voices, "en-US")).toEqual(
      { narrator: "david", quote: "david", Keith: "hazel", Mara: "zira" });
    expect(defaultCast(["Keith", "narrator"], voices, "en-US")).toEqual({ Keith: "hazel", narrator: "david" });
    const many = defaultCast(["narrator", "a", "b", "c", "d"], voices.slice(0, 2), "en-US");
    expect(Object.values(many)).toHaveLength(5);                                        // wraps round with few voices
    expect(defaultCast(["narrator"], [], "en")).toEqual({});
  });

  it("keeps a saved choice only while that voice is still installed", () => {
    const cast = resolveCast({ narrator: "zira", Keith: "gone-voice" }, ["narrator", "Keith"], voices, "en-US");
    expect(cast.narrator).toBe("zira");
    expect(cast.Keith).toBe(defaultCast(["narrator", "Keith"], voices, "en-US").Keith);
    expect(resolveCast(undefined, ["narrator"], voices, "en-US")).toEqual({ narrator: "david" });
    expect(resolveCast({ narrator: "zira" }, ["narrator"], [], "en")).toEqual({});
  });

  it("names the roles", () => {
    expect([roleLabel("narrator"), roleLabel("quote"), roleLabel("Keith")]).toEqual(["Narrator", "Quoted speech", "Keith"]);
  });
});

describe("reader settings", () => {
  const fake = () => {
    const data: Record<string, string> = {};
    return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, val: string) => { data[k] = val; } };
  };

  it("round-trips the rate, options and the cast of each project", () => {
    const s = fake();
    savePrefs({ rate: 1.25, options: { ...DEFAULT_PREFS.options, directions: true }, casts: { "/p/a": { narrator: "zira" } } }, s);
    const back = loadPrefs(s);
    expect(back.rate).toBe(1.25);
    expect(back.options.directions).toBe(true);
    expect(back.casts["/p/a"]).toEqual({ narrator: "zira" });
  });

  it("falls back to the defaults for anything missing or wrong", () => {
    expect(loadPrefs({ getItem: () => null })).toEqual(DEFAULT_PREFS);
    expect(loadPrefs({ getItem: () => "{not json" })).toEqual(DEFAULT_PREFS);
    const odd = loadPrefs({ getItem: () => JSON.stringify({ rate: 99, options: { directions: "yes", titles: false }, casts: { p: { a: 5, b: "ok" }, q: 3 } }) });
    expect(odd.rate).toBe(1);
    expect(odd.options).toEqual({ ...DEFAULT_PREFS.options, titles: false });
    expect(odd.casts).toEqual({ p: { b: "ok" } });
  });

  it("works without any storage at all (a private window)", () => {
    expect(loadPrefs(null)).toEqual(DEFAULT_PREFS);
    expect(() => savePrefs(DEFAULT_PREFS, null)).not.toThrow();
    expect(() => savePrefs(DEFAULT_PREFS, { setItem: () => { throw new Error("quota"); } })).not.toThrow();
  });
});

describe("ranked voices", () => {
  it("puts suggested voices first and keeps engines' casts apart", async () => {
    const { candidateVoices: cv, castKey } = await import("./cast");
    const ranked = [{ id: "am_adam", name: "Adam", lang: "en-us", local: true, rank: 20 },
      { id: "af_heart", name: "Heart", lang: "en-us", local: true, rank: 0 },
      { id: "bf_emma", name: "Emma", lang: "en-gb", local: true, rank: 2 }];
    expect(cv(ranked, "en-US").map((x) => x.id)).toEqual(["af_heart", "bf_emma", "am_adam"]);
    expect(castKey("/p", "browser")).toBe("/p");
    expect(castKey("/p", "kokoro")).not.toBe(castKey("/p", "endpoint"));
  });
});
