import { describe, expect, it } from "vitest";
import { frontmatterRange, pendingAt, softBreaks, specsFor, titleLine, type Span } from "./spans";

const span = (s: Partial<Span> & Pick<Span, "kind" | "start" | "end">): Span => s as Span;

describe("specsFor", () => {
  it("colours plain mentions without hiding anything", () => {
    const out = specsFor([span({ kind: "mention", start: 4, end: 8, entity: "Mara Vale" })], 0, 50);
    expect(out).toEqual([{ from: 4, to: 8, type: "mark", cls: "lw-mention", attrs: { "data-entity": "Mara Vale" } }]);
  });

  it("hides brackets and 'Name|' of a link unless the cursor is inside it", () => {
    // "[[Mara|the archivist]]" at 10..32, visible part 17..31 ("the archivist")
    const link = span({ kind: "link", start: 10, end: 32, innerStart: 17, innerEnd: 30, entity: "Mara Vale", target: "Mara" });
    const away = specsFor([link], 0, 60);
    expect(away.filter((s) => s.type === "hide").map((s) => [s.from, s.to])).toEqual([[10, 17], [30, 32]]);
    expect(away.find((s) => s.type === "mark")).toMatchObject({ from: 17, to: 30, cls: "lw-link-span" });
    const inside = specsFor([link], 20, 60);
    expect(inside.some((s) => s.type === "hide")).toBe(false);
    expect(inside.filter((s) => s.cls === "lw-bracket").map((s) => [s.from, s.to])).toEqual([[10, 17], [30, 32]]);
  });

  it("uses the unresolved colour for links without a note", () => {
    const out = specsFor([span({ kind: "unresolved", start: 0, end: 9, innerStart: 2, innerEnd: 7, target: "Nope" })], 99, 100);
    expect(out.find((s) => s.type === "mark")?.cls).toContain("lw-link-span--unresolved");
  });

  it("hides pending-draft markers entirely and tints the body", () => {
    const pending = span({ kind: "pending", start: 5, end: 40, bodyStart: 14, bodyEnd: 34, id: "abc123" });
    const out = specsFor([pending], 20, 100);
    expect(out.filter((s) => s.type === "hide").map((s) => [s.from, s.to])).toEqual([[5, 14], [34, 40]]);
    expect(out.find((s) => s.type === "mark")).toMatchObject({ from: 14, to: 34, cls: "lw-draft", attrs: { "data-draft": "abc123" } });
  });

  it("styles expand markers as a chip", () => {
    expect(specsFor([span({ kind: "expand", start: 1, end: 9 })], 0, 20)[0].cls).toBe("lw-expand");
  });

  it("drops spans that fall outside the document (stale after an edit)", () => {
    expect(specsFor([span({ kind: "mention", start: 40, end: 60 })], 0, 50)).toEqual([]);
    expect(specsFor([span({ kind: "mention", start: 9, end: 3 })], 0, 50)).toEqual([]);
  });
});

describe("pendingAt", () => {
  const spans = [span({ kind: "mention", start: 0, end: 4 }), span({ kind: "pending", start: 10, end: 30, id: "x" })];
  it("finds the draft containing the position, edges included", () => {
    expect(pendingAt(spans, 10)?.id).toBe("x");
    expect(pendingAt(spans, 30)?.id).toBe("x");
    expect(pendingAt(spans, 31)).toBeUndefined();
  });
});

describe("titleLine / frontmatter", () => {
  it("finds a leading heading, skipping blank lines", () => {
    expect(titleLine("# Title\n\nBody")).toEqual({ from: 0, to: 7, prefix: 2 });
    expect(titleLine("\n\n# Late\nx")).toEqual({ from: 2, to: 8, prefix: 2 });
    expect(titleLine("Body first\n# Not title")).toBeNull();
    expect(titleLine("## Sub")).toBeNull();
    expect(titleLine("")).toBeNull();
  });
  it("finds entity frontmatter", () => {
    const text = "---\nname: A\n---\n\nbody";
    expect(frontmatterRange(text)).toEqual({ from: 0, to: 16 });
    expect(frontmatterRange("no front")).toBeNull();
  });
});

describe("softBreaks (hard-wrapped Markdown shown reflowed)", () => {
  it("softens single newlines inside a paragraph only", () => {
    const text = "# T\n\nline one\nline two\n\nnew para\n> quote\n- item\nmore";
    const at = softBreaks(text);
    expect(at).toHaveLength(1);
    expect(text.slice(at[0] - 4, at[0] + 5)).toBe(" one\nline");
  });
  it("keeps hard breaks, headings, lists, quotes and frontmatter", () => {
    expect(softBreaks("a  \nb")).toEqual([]);
    expect(softBreaks("## H\nbody")).toEqual([]);
    expect(softBreaks("text\n## H")).toEqual([]);
    expect(softBreaks("- a\n- b")).toEqual([]);
    expect(softBreaks("---\nname: A\naliases: []\n---\n\nbody", { from: 0, to: 29 })).toEqual([]);
  });
});
