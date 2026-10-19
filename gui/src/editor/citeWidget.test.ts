// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { EditorState } from "@codemirror/state";
import { CiteWidget, commentsField, decoField, kindFacet, readingField, setSpans, spansField, spellingField } from "./cm";
import { citeReplaced, specsFor, type Span } from "./spans";

const DOC = "As shown [[@wang2026]] here.";
const cite = (over: Partial<Span> = {}): Span => ({
  kind: "citation", start: 9, end: 21, status: "resolved", keys: ["wang2026"], label: "Wang 2026",
  title: "A paper", display: "(Wang et al., 2026)", ...over,
});

function make(doc: string, spans: Span[], anchor = 0, kind = "scene") {
  const state = EditorState.create({
    doc, selection: { anchor },
    extensions: [kindFacet.of(kind), spansField, spellingField, commentsField, readingField, decoField],
  });
  return state.update({ effects: setSpans.of(spans) }).state;
}

function widgets(state: EditorState) {
  const out: { from: number; to: number; w: CiteWidget }[] = [];
  const it = state.field(decoField).all.iter();
  while (it.value) {
    const w = (it.value.spec as { widget?: unknown }).widget;
    if (w instanceof CiteWidget) out.push({ from: it.from, to: it.to, w });
    it.next();
  }
  return out;
}

function citeMarks(state: EditorState) {
  const out: string[] = [];
  const it = state.field(decoField).all.iter();
  while (it.value) {
    const c = (it.value.spec as { class?: string }).class;
    if (c?.startsWith("lw-cite")) out.push(c);
    it.next();
  }
  return out;
}

describe("citation display", () => {
  it("the Span type carries display and specsFor still marks the raw range", () => {
    const s = cite();
    expect(s.display).toBe("(Wang et al., 2026)");
    expect(specsFor([s], 0, DOC.length)[0]).toMatchObject({ cls: "lw-cite lw-cite--resolved" });
  });

  it("replaces a resolved citation with its display text and keeps the keys attribute", () => {
    const w = widgets(make(DOC, [cite()]));
    expect(w).toHaveLength(1);
    expect([w[0].from, w[0].to]).toEqual([9, 21]);
    const dom = w[0].w.toDOM();
    expect(dom.textContent).toBe("(Wang et al., 2026)");
    expect(dom.className).toContain("lw-cite--resolved");
    expect(dom.getAttribute("data-keys")).toBe("wang2026");
    expect(w[0].w.ignoreEvent()).toBe(false);
  });

  it("an unresolved citation shows its key in the missing style", () => {
    const w = widgets(make(DOC, [cite({ status: "unresolved", display: "wang2026" })]));
    const dom = w[0].w.toDOM();
    expect(dom.textContent).toBe("wang2026");
    expect(dom.className).toContain("lw-cite--unresolved");
  });

  it("reveals the raw text when the cursor touches it (edges included) and restores it after", () => {
    let s = make(DOC, [cite()], 0);
    expect(widgets(s)).toHaveLength(1);
    for (const at of [9, 15, 21]) {
      s = s.update({ selection: { anchor: at } }).state;
      expect(widgets(s)).toHaveLength(0);
      expect(citeMarks(s)).toEqual(["lw-cite lw-cite--resolved"]);
    }
    s = s.update({ selection: { anchor: 25 } }).state;
    expect(widgets(s)).toHaveLength(1);
    expect(citeMarks(s)).toEqual([]);
  });

  it("a selection range that overlaps the citation reveals it", () => {
    const s = make(DOC, [cite()], 0).update({ selection: { anchor: 3, head: 12 } }).state;
    expect(widgets(s)).toHaveLength(0);
  });

  it("eq is true for the same display, false when display, status or title change", () => {
    const a = new CiteWidget("(Wang et al., 2026)", "resolved", "T", "k");
    expect(a.eq(new CiteWidget("(Wang et al., 2026)", "resolved", "T", "k"))).toBe(true);
    expect(a.eq(new CiteWidget("(Wang et al., 2026)", "resolved", "T", "other"))).toBe(false);   // keys decide what data-keys says
    expect(a.eq(new CiteWidget("(Wang et al., 2026a)", "resolved", "T", "k"))).toBe(false);
    expect(a.eq(new CiteWidget("(Wang et al., 2026)", "unresolved", "T", "k"))).toBe(false);
    expect(a.eq(new CiteWidget("(Wang et al., 2026)", "resolved", "U", "k"))).toBe(false);
  });

  it("typing elsewhere keeps an equal widget and the raw text is untouched", () => {
    let s = make(DOC, [cite()], 0);
    const before = widgets(s)[0].w;
    s = s.update({ changes: { from: 0, insert: "xx" }, selection: { anchor: 2 } }).state;
    const after = widgets(s);
    expect(after[0].from).toBe(11);
    expect(after[0].w.eq(before)).toBe(true);
    expect(s.doc.toString()).toBe("xx" + DOC);
  });

  it("does not replace a citation across a line break or a soft-break position", () => {
    const doc = "A [[@wang\n2026]] b";
    expect(widgets(make(doc, [cite({ start: 2, end: 16 })], 0))).toHaveLength(0);
    expect(citeReplaced(cite(), [{ from: 0, to: 0 }], DOC, new Set([12]))).toBe(false);
    expect(citeReplaced(cite(), [{ from: 0, to: 0 }], DOC, new Set())).toBe(true);
    expect(citeReplaced(cite({ display: undefined }), [{ from: 0, to: 0 }], DOC, new Set())).toBe(false);
    // a span mapped through an edit that broke the citation (closing brackets deleted, key removed) never hides text
    expect(citeReplaced(cite(), [{ from: 0, to: 0 }], "As shown [[@wang2026 here, and more.", new Set())).toBe(false);
    expect(citeReplaced(cite(), [{ from: 0, to: 0 }], "As shown [[wang2026]] here.", new Set())).toBe(false);
  });

  it("a document with no citation spans has no citation widgets", () => {
    const s = make("Just [[Mara]] and text.", [{ kind: "link", start: 5, end: 13, innerStart: 7, innerEnd: 11, entity: "Mara", target: "Mara" }], 0);
    expect(widgets(s)).toHaveLength(0);
    expect(citeMarks(s)).toEqual([]);
  });
});
