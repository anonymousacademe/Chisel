/// <reference types="node" />
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(fileURLToPath(new URL("./editor.css", import.meta.url)), "utf8");

// CodeMirror measures a line or block widget WITHOUT its margins, so vertical space there is space it cannot
// see: every line below drifts by it and clicks land a line off. (Found the hard way: clicking a word on the
// second row of a wrapped line put the caret on the blank line below.) Use padding on lines and widgets.
const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)]
  .map((m) => ({ selector: m[1].trim(), body: m[2] }));

const verticalMargin = (body: string) =>
  /margin-(top|bottom)\s*:\s*(?!0\b)/.test(body) ||
  /(^|;)\s*margin\s*:\s*(?!0\s*(;|$))(?!0\s+\S+\s+0\b)\S+/.test(body.trim());

describe("editor.css and CodeMirror's measuring", () => {
  it("gives lines and the title widget no vertical margin", () => {
    const lineRules = rules.filter((r) => /\.lw-(h\d|sc--|title-line|blank|li|quote|page__meta)(?![\w-])/.test(r.selector) && !r.selector.includes("::after"));
    expect(lineRules.length).toBeGreaterThan(5);
    const offenders = lineRules.filter((r) => verticalMargin(r.body)).map((r) => r.selector);
    expect(offenders).toEqual([]);
  });

  it("keeps the rule under the title inside the measured widget box", () => {
    const meta = rules.find((r) => /\.lw-page__meta$/.test(r.selector));
    expect(meta?.body).toMatch(/display:\s*flow-root/);
    const after = rules.find((r) => /\.lw-page__meta::after$/.test(r.selector));
    expect(after?.body).not.toMatch(/margin:[^;]*\b\d+px\s+0\s+\d*[1-9]\d*px/);   // no bottom margin that could escape the box
  });

  it("uses padding for the space above headings and scene headings", () => {
    for (const sel of [".lw-h1", ".lw-h2", ".lw-sc--scene_heading"]) {
      const r = rules.find((x) => x.selector.endsWith(sel));
      expect(r?.body, sel).toMatch(/padding-top:/);
    }
  });
});
