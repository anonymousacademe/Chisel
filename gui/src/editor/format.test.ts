import { describe, expect, it } from "vitest";
import { markdown } from "@codemirror/lang-markdown";
import { formatSpecs } from "./format";

const tree = (text: string) => markdown().language.parser.parse(text);
const hidden = (text: string, head: number, opts = {}) =>
  formatSpecs(tree(text), text, head, opts).filter((s) => s.type === "hide").map((s) => text.slice(s.from, s.to));

describe("formatSpecs", () => {
  it("hides bold and italic markers while the cursor is away", () => {
    const t = "She said **no** and *left*.";
    expect(hidden(t, 0)).toEqual(["**", "**", "*", "*"]);
  });

  it("shows the markers of the span the cursor is in or touching", () => {
    const t = "She said **no** and *left*.";
    expect(hidden(t, 12)).toEqual(["*", "*"]);          // inside **no**
    expect(hidden(t, 15)).toEqual(["*", "*"]);          // touching its end
    const near = formatSpecs(tree(t), t, 12).filter((s) => s.cls === "lw-syn").map((s) => t.slice(s.from, s.to));
    expect(near).toEqual(["**", "**"]);
  });

  it("handles underscores, bold italic and inline code", () => {
    expect(hidden("__a__ _b_ ***c*** `d`", 99)).toEqual(["__", "__", "_", "_", "*", "**", "**", "*", "`", "`"]);
  });

  it("leaves escaped markers alone", () => {
    expect(hidden("a \\*not italic\\* b", 0)).toEqual([]);
  });

  it("hides heading hashes (and the space) away from the line, not on it", () => {
    const t = "intro\n\n## Place\n\nmore";
    expect(hidden(t, 0)).toEqual(["## "]);
    expect(hidden(t, 10)).toEqual([]);
  });

  it("skips the title line, which the title block handles", () => {
    const t = "# Title\n\ntext";
    expect(hidden(t, 12, { titleFrom: 0 })).toEqual([]);
  });

  it("renders block marks only when asked", () => {
    const t = "> quote\n\n- item";
    expect(hidden(t, 99)).toEqual([]);
    expect(hidden(t, 99, { blocks: true })).toEqual(["> ", "- "]);
    const lines = formatSpecs(tree(t), t, 99, { blocks: true }).filter((s) => s.type === "line");
    expect(lines).toEqual([{ from: 9, to: 9, type: "line", cls: "lw-li" }]);
  });

  it("never changes offsets: hidden ranges lie inside the text", () => {
    const t = "**a** b";
    for (const s of formatSpecs(tree(t), t, 99)) expect(s.to).toBeLessThanOrEqual(t.length);
  });
});
