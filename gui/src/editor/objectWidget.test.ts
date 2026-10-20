// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import { decoField, decorationCore, kindFacet, setSpans, spansField, editorExtensions } from "./cm";
import { invalidateObjects, objectDataField, ObjectBlockWidget, ObjectRefWidget, renderMath, setObjectData, setObjectImage, type ObjectInfo } from "./objects";
import { objrefReplaced, placementLine, specsFor, type Span } from "./spans";

const NAMES = { fig: "Figure", tbl: "Table", eq: "Equation" } as const;

/** Spans for every ![[x:y]] line and [[x:y]] reference of *doc*, as Python would send them. */
function spansOf(doc: string, unresolved: string[] = []): Span[] {
  const out: Span[] = [];
  for (const m of doc.matchAll(/(!?)\[\[(fig|tbl|eq):([a-z0-9-]+)\]\]/g)) {
    const start = m.index!;
    const key = `${m[2]}:${m[3]}`;
    const placement = m[1] === "!" && (start === 0 || doc[start - 1] === "\n");
    const bad = unresolved.includes(key);
    out.push({
      kind: placement ? "placement" : "objref", start, end: start + m[0].length,
      objectKind: m[2] as "fig" | "tbl" | "eq", label: m[3], key, status: bad ? "unresolved" : "resolved",
      display: bad ? key : `${NAMES[m[2] as keyof typeof NAMES]} ${m[2] === "eq" ? "(3)" : "2"}`,
    });
  }
  return out;
}

const DOC5 = ["Intro", "", "![[fig:a]]", "", "![[tbl:b]]", "", "![[eq:c]]", "", "![[fig:d]]", "", "![[fig:e]]", "", "See [[fig:a]] end.", ""].join("\n");

const FIG: ObjectInfo = { id: "fig:a", kind: "fig", caption: "Flow", imageUrl: "data:image/png;base64,AAAA", width: 4, alt: "a plot" };
const TBL: ObjectInfo = { id: "tbl:b", kind: "tbl", caption: "Results", cells: [["A", "B"], ["1", "2"]], align: ["left", "right"] };
const EQ: ObjectInfo = { id: "eq:c", kind: "eq", caption: "", latex: "x^2 + y^2" };

function make(doc: string, spans: Span[], anchor = 0, kind = "scene", infos: ObjectInfo[] = []) {
  let state = EditorState.create({
    doc, selection: { anchor },
    extensions: [kindFacet.of(kind), markdown(), ...decorationCore],
  });
  state = state.update({ effects: setSpans.of(spans) }).state;
  if (infos.length) state = state.update({ effects: setObjectData.of({ gen: 0, infos }) }).state;
  return state;
}

interface Found { from: number; to: number; w: ObjectBlockWidget | ObjectRefWidget; block: boolean; replace: boolean }
function widgets(state: EditorState): Found[] {
  const out: Found[] = [];
  const it = state.field(decoField).all.iter();
  while (it.value) {
    const spec = it.value.spec as { widget?: unknown; block?: boolean };
    const w = spec.widget;
    if (w instanceof ObjectBlockWidget || w instanceof ObjectRefWidget) {
      out.push({ from: it.from, to: it.to, w, block: !!spec.block, replace: it.from !== it.to });
    }
    it.next();
  }
  return out;
}
const blocks = (s: EditorState) => widgets(s).filter((x) => x.w instanceof ObjectBlockWidget);
const refs = (s: EditorState) => widgets(s).filter((x) => x.w instanceof ObjectRefWidget);

describe("object spans", () => {
  it("the Span type carries placement and objref, and specsFor marks a reference", () => {
    const sp = spansOf(DOC5);
    expect(sp.filter((s) => s.kind === "placement")).toHaveLength(5);
    const ref = sp.find((s) => s.kind === "objref")!;
    expect(specsFor([ref], 0, DOC5.length)[0]).toMatchObject({ cls: "lw-objref lw-objref--resolved", attrs: { "data-object": "fig:a" } });
    expect(specsFor(sp.filter((s) => s.kind === "placement"), 0, DOC5.length)).toEqual([]);
  });

  it("placementLine and objrefReplaced refuse text that no longer has the shape", () => {
    const [p] = spansOf("![[fig:a]]\n");
    expect(placementLine(p, "![[fig:a]]\n")).toEqual({ from: 0, to: 10 });
    expect(placementLine(p, "x ![[fig:a]]\n")).toBeNull();
    expect(placementLine(p, "![[fig:a]] and more\n")).toBeNull();
    const r = spansOf("See [[fig:a]] x")[0];
    expect(objrefReplaced(r, [{ from: 0, to: 0 }], "See [[fig:a]] x", new Set())).toBe(true);
    expect(objrefReplaced(r, [{ from: 0, to: 0 }], "See [[fig:a] x", new Set())).toBe(false);
    expect(objrefReplaced(r, [{ from: 0, to: 0 }], "See [[fig:a]] x", new Set([6]))).toBe(false);
  });
});

describe("placement blocks", () => {
  it("replaces each placement line with a block widget when the selection is elsewhere", () => {
    const b = blocks(make(DOC5, spansOf(DOC5)));
    expect(b).toHaveLength(5);
    expect(b.every((x) => x.block && x.replace)).toBe(true);
    expect(DOC5.slice(b[0].from, b[0].to)).toBe("![[fig:a]]");
  });

  it("draws a figure with its image and the caption under it", () => {
    const [b] = blocks(make(DOC5, spansOf(DOC5), 0, "scene", [FIG]));
    const dom = b.w.toDOM();
    expect(dom.querySelector("img")?.getAttribute("src")).toBe(FIG.imageUrl);
    expect(dom.querySelector("img")?.style.width).toBe("384px");
    expect(dom.querySelector("img")?.getAttribute("alt")).toBe("a plot");
    expect(dom.querySelector(".lw-object__caption")?.textContent).toBe("Figure 2. Flow");
    expect(dom.querySelector("figure")?.lastElementChild?.className).toContain("lw-object__caption");
  });

  it("draws a table as HTML with the caption above and the alignment kept", () => {
    const b = blocks(make(DOC5, spansOf(DOC5), 0, "scene", [TBL]))[1];
    const dom = b.w.toDOM();
    expect(dom.querySelector(".lw-object__tablewrap")?.firstElementChild?.textContent).toBe("Table 2. Results");
    expect([...dom.querySelectorAll("th")].map((x) => x.textContent)).toEqual(["A", "B"]);
    expect([...dom.querySelectorAll("td")].map((x) => x.textContent)).toEqual(["1", "2"]);
    expect((dom.querySelectorAll("td")[1] as HTMLElement).style.textAlign).toBe("right");
  });

  it("draws an equation with KaTeX and the number on the right", () => {
    const b = blocks(make(DOC5, spansOf(DOC5), 0, "scene", [EQ]))[2];
    const dom = b.w.toDOM();
    expect(dom.querySelector(".katex")).not.toBeNull();
    expect(dom.querySelector(".lw-object__eqno")?.textContent).toBe("(3)");
  });

  it("shows a sized placeholder until the data arrives", () => {
    const b = blocks(make(DOC5, spansOf(DOC5)));
    expect(b[0].w.toDOM().querySelector(".lw-object__placeholder--fig")).not.toBeNull();
    expect(b[1].w.toDOM().querySelector(".lw-object__placeholder--tbl")).not.toBeNull();
    expect(b[2].w.toDOM().querySelector(".lw-object__placeholder--eq")).not.toBeNull();
    expect(b[0].w.toDOM().className).toContain("lw-object--pending");
  });

  it("an unresolved placement is a muted notice, never fake content", () => {
    const [b] = blocks(make(DOC5, spansOf(DOC5, ["fig:a"]), 0, "scene", [FIG]));
    const dom = b.w.toDOM();
    expect(dom.textContent).toBe("Missing figure: fig:a");
    expect(dom.querySelector("img")).toBeNull();
    expect(dom.querySelector("button")).toBeNull();
  });

  it("an error entry from the bridge is a notice too", () => {
    const [b] = blocks(make(DOC5, spansOf(DOC5), 0, "scene", [{ id: "fig:a", error: "gone" }]));
    expect(b.w.toDOM().textContent).toContain("gone");
  });

  it("the cursor touching the line shows the raw line plus the rendered block above; away replaces", () => {
    let s = make(DOC5, spansOf(DOC5), 0, "scene", [FIG]);
    expect(blocks(s)).toHaveLength(5);
    for (const at of [7, 12, 17]) {   // start, inside and end of "![[fig:a]]" (offsets 7..17)
      s = s.update({ selection: { anchor: at } }).state;
      const b = blocks(s);
      expect(b).toHaveLength(5);
      const first = b[0];
      expect(first.replace).toBe(false);                  // a widget only: the raw line stays in the document
      expect(first.from).toBe(7);
      expect(first.w.toDOM().className).toContain("lw-object--above");
      expect(b.slice(1).every((x) => x.replace)).toBe(true);
    }
    s = s.update({ selection: { anchor: 2 } }).state;
    expect(blocks(s).every((x) => x.replace)).toBe(true);
    expect(s.doc.toString()).toBe(DOC5);
  });

  it("a range selection that crosses the line reveals it", () => {
    const s = make(DOC5, spansOf(DOC5), 0).update({ selection: { anchor: 2, head: 9 } }).state;
    expect(blocks(s)[0].replace).toBe(false);
  });

  it("eq is true for identical content and false when anything shown changes", () => {
    const a = new ObjectBlockWidget("fig:a", "fig", "Figure 2", true, FIG, false);
    expect(a.eq(new ObjectBlockWidget("fig:a", "fig", "Figure 2", true, FIG, false))).toBe(true);
    // a rebuilt entry is a new identity (the cache keeps the same object while nothing shown changes)
    expect(a.eq(new ObjectBlockWidget("fig:a", "fig", "Figure 2", true, { ...FIG }, false))).toBe(false);
    expect(a.eq(new ObjectBlockWidget("fig:a", "fig", "Figure 3", true, FIG, false))).toBe(false);
    expect(a.eq(new ObjectBlockWidget("fig:a", "fig", "Figure 2", true, { ...FIG, caption: "x" }, false))).toBe(false);
    expect(a.eq(new ObjectBlockWidget("fig:a", "fig", "Figure 2", true, undefined, false))).toBe(false);
    expect(a.eq(new ObjectBlockWidget("fig:a", "fig", "Figure 2", true, FIG, true))).toBe(false);
  });

  it("the Edit affordance and the click rules: only the button is the widget's own event", () => {
    const [b] = blocks(make(DOC5, spansOf(DOC5), 0, "scene", [FIG]));
    const dom = b.w.toDOM();
    const btn = dom.querySelector("button")!;
    expect(btn.textContent).toBe("Edit");
    expect(b.w.ignoreEvent({ target: btn } as unknown as Event)).toBe(true);
    expect(b.w.ignoreEvent({ target: dom.querySelector("img") } as unknown as Event)).toBe(false);
  });

  it("no widgets in a style or dictionary document, and none in code", () => {
    expect(widgets(make(DOC5, spansOf(DOC5), 0, "dictionary"))).toHaveLength(0);
    expect(widgets(make(DOC5, spansOf(DOC5), 0, "style"))).toHaveLength(0);
    const code = "Use `[[fig:a]]` here.\n\n```\n![[fig:a]]\n```\n";
    expect(widgets(make(code, spansOf(code)))).toHaveLength(0);
  });

  it("a document without object spans has no object widgets", () => {
    expect(widgets(make(DOC5, []))).toHaveLength(0);
  });

  it("a stale placement span (the line was edited) never hides text", () => {
    const s = make("![[fig:a]] more\n", spansOf("![[fig:a]]\n"));
    expect(blocks(s)).toHaveLength(0);
  });
});

describe("reference widget", () => {
  const DOC = "See [[fig:a]] and [[eq:c]] here.";
  it("shows the display text and the key, and reveals the raw text when touched", () => {
    let s = make(DOC, spansOf(DOC), 0);
    const r = refs(s);
    expect(r).toHaveLength(2);
    const dom = (r[0].w as ObjectRefWidget).toDOM();
    expect(dom.textContent).toBe("Figure 2");
    expect(dom.getAttribute("data-object")).toBe("fig:a");
    expect(dom.className).toContain("lw-objref--resolved");
    expect((r[1].w as ObjectRefWidget).toDOM().textContent).toBe("Equation (3)");
    for (const at of [4, 8, 13]) {
      s = s.update({ selection: { anchor: at } }).state;
      expect(refs(s)).toHaveLength(1);
    }
    s = s.update({ selection: { anchor: 30 } }).state;
    expect(refs(s)).toHaveLength(2);
  });

  it("an unresolved reference shows its key in the missing style", () => {
    const r = refs(make(DOC, spansOf(DOC, ["fig:a"]), 0));
    const dom = (r[0].w as ObjectRefWidget).toDOM();
    expect(dom.textContent).toBe("fig:a");
    expect(dom.className).toContain("lw-objref--unresolved");
  });

  it("eq compares key, display and status", () => {
    const a = new ObjectRefWidget("fig:a", "Figure 2", "resolved");
    expect(a.eq(new ObjectRefWidget("fig:a", "Figure 2", "resolved"))).toBe(true);
    expect(a.eq(new ObjectRefWidget("fig:a", "Figure 3", "resolved"))).toBe(false);
    expect(a.eq(new ObjectRefWidget("fig:a", "Figure 2", "unresolved"))).toBe(false);
    expect(a.ignoreEvent()).toBe(false);
  });

  it("is not drawn across a line break", () => {
    const doc = "See [[fig:\na]] x";
    expect(refs(make(doc, [{ kind: "objref", start: 4, end: 14, key: "fig:a", objectKind: "fig", display: "Figure 2", status: "resolved" }], 0))).toHaveLength(0);
  });
});

describe("KaTeX", () => {
  it("renders LaTeX to KaTeX HTML", () => {
    const r = renderMath("a^2");
    expect("html" in r && r.html.includes("katex")).toBe(true);
  });
  it("shows an error as plain text, never as markup", () => {
    const bad = "\\frac{1}{<img src=x onerror=alert(1)>";
    const r = renderMath(bad);
    expect(r).toEqual({ error: bad });
    const doc = "x\n\n![[eq:c]]\n";
    const [b] = blocks(make(doc, spansOf(doc), 0, "scene", [{ id: "eq:c", latex: bad }]));
    const dom = b.w.toDOM();
    expect(dom.querySelector(".lw-object__eq--error")?.textContent).toBe(bad);
    expect(dom.querySelector("img")).toBeNull();
  });
  it("does not enable \\href, \\url or \\includegraphics (trust is off)", () => {
    for (const tex of ["\\href{https://example.com}{x}", "\\url{https://example.com}", "\\includegraphics{a.png}"]) {
      const r = renderMath(tex);
      expect("html" in r ? r.html.includes("<a ") || r.html.includes("<img") : true).toBe(false);
    }
  });
});

// -- a live view: DOM reuse and the cache ----------------------------------------------------------------

let mounted: EditorView | null = null;
afterEach(() => { mounted?.destroy(); mounted = null; vi.restoreAllMocks(); });

const tick = () => new Promise<void>((r) => setTimeout(r, 0));

function live(doc: string, render: (keys: string[]) => Promise<ObjectInfo[]>, spans = spansOf(doc), fetchObjectImage?: (label: string) => Promise<string | null>) {
  const hooks = {
    getCard: async () => null, onOpenEntity: () => {}, onChange: () => {}, onCursor: () => {}, onBlur: () => {},
    onSaveNow: () => {}, onResolveDraft: () => {}, renderObjects: render, fetchObjectImage,
  };
  const view = new EditorView({
    parent: document.body,
    state: EditorState.create({ doc, selection: { anchor: 0 }, extensions: editorExtensions("scene", "", true, hooks, () => 0, () => 0) }),
  });
  mounted = view;
  view.dispatch({ effects: setSpans.of(spans) });
  return view;
}

const INFOS: ObjectInfo[] = [
  ...["a", "d", "e"].map((l): ObjectInfo => ({ id: `fig:${l}`, kind: "fig", caption: l, imageUrl: "data:image/png;base64,AAAA" })),
  TBL, EQ,
];

describe("object cache", () => {
  it("asks for five keys in ONE call, then nothing while typing", async () => {
    const render = vi.fn(async (keys: string[]) => INFOS.filter((i) => keys.includes(i.id)));
    const view = live(DOC5, render);
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(1);
    expect([...render.mock.calls[0][0]].sort()).toEqual(["eq:c", "fig:a", "fig:d", "fig:e", "tbl:b"]);
    expect(view.state.field(objectDataField).map.size).toBe(5);
    view.dispatch({ changes: { from: 0, insert: "xx" }, selection: { anchor: 2 } });
    view.dispatch({ changes: { from: 2, insert: "yy" }, selection: { anchor: 4 } });
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(1);
  });

  it("typing elsewhere rebuilds no widget DOM (five placements)", async () => {
    const render = vi.fn(async (keys: string[]) => INFOS.filter((i) => keys.includes(i.id)));
    const view = live(DOC5, render);
    await tick(); await tick();
    const spy = vi.spyOn(ObjectBlockWidget.prototype, "toDOM");
    for (let i = 0; i < 4; i++) view.dispatch({ changes: { from: 0, insert: "x" }, selection: { anchor: i + 1 } });
    await tick();
    expect(spy).not.toHaveBeenCalled();
    expect(view.dom.querySelectorAll(".lw-object").length).toBe(5);
  });

  it("invalidation refetches only what is on the page and keeps the old content meanwhile", async () => {
    let n = 0;
    const render = vi.fn(async (keys: string[]) => { n++; return INFOS.filter((i) => keys.includes(i.id)).map((i) => ({ ...i, caption: `v${n}` })); });
    const view = live(DOC5, render);
    await tick(); await tick();
    view.dispatch({ effects: invalidateObjects.of(null) });
    expect(view.state.field(objectDataField).map.get("fig:a")?.stale).toBe(true);
    expect(view.state.field(objectDataField).map.get("fig:a")?.info.caption).toBe("v1");
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(2);
    expect(view.state.field(objectDataField).map.get("fig:a")).toMatchObject({ stale: false, info: { caption: "v2" } });
  });

  it("ignores a response for a key that left the document and one from before an invalidation", async () => {
    let release: (v: ObjectInfo[]) => void = () => {};
    const first = new Promise<ObjectInfo[]>((r) => { release = r; });
    const render = vi.fn((keys: string[]) => (render.mock.calls.length === 1 ? first : Promise.resolve(INFOS.filter((i) => keys.includes(i.id)))));
    const doc = "![[fig:a]]\n\n![[fig:d]]\n";
    const view = live(doc, render);
    await tick();
    expect(render).toHaveBeenCalledTimes(1);
    // fig:d is deleted from the text and the spans are refreshed, then the old answer arrives
    view.dispatch({ changes: { from: 12, to: doc.length, insert: "" } });
    view.dispatch({ effects: setSpans.of(spansOf("![[fig:a]]\n\n")) });
    release(INFOS.filter((i) => i.id === "fig:a" || i.id === "fig:d"));
    await tick(); await tick();
    const map = view.state.field(objectDataField).map;
    expect(map.has("fig:d")).toBe(false);
    expect(map.has("fig:a")).toBe(true);
  });

  it("drops an answer to a question asked before an invalidation", () => {
    let s = make(DOC5, spansOf(DOC5));
    s = s.update({ effects: invalidateObjects.of(null) }).state;
    s = s.update({ effects: setObjectData.of({ gen: 0, infos: [FIG] }) }).state;
    expect(s.field(objectDataField).map.has("fig:a")).toBe(false);
    s = s.update({ effects: setObjectData.of({ gen: 1, infos: [FIG] }) }).state;
    expect(s.field(objectDataField).map.has("fig:a")).toBe(true);
  });

  it("a view without renderObjects asks for nothing and shows placeholders", async () => {
    const hooks = { getCard: async () => null, onOpenEntity: () => {}, onChange: () => {}, onCursor: () => {}, onBlur: () => {}, onSaveNow: () => {}, onResolveDraft: () => {} };
    const view = new EditorView({
      parent: document.body,
      state: EditorState.create({ doc: DOC5, selection: { anchor: 0 }, extensions: editorExtensions("scene", "", true, hooks, () => 0, () => 0) }),
    });
    mounted = view;
    view.dispatch({ effects: setSpans.of(spansOf(DOC5)) });
    await tick();
    expect(view.dom.querySelectorAll(".lw-object--pending").length).toBe(5);
    expect(spansField).toBeDefined();
  });
});

describe("images, failures and layout", () => {
  const META: ObjectInfo[] = [
    ...["a", "d", "e"].map((l): ObjectInfo => ({ id: `fig:${l}`, kind: "fig", caption: l, mtime: "100", pixels: [800, 400] })),
    TBL, EQ,
  ];
  const meta = (keys: string[]) => META.filter((i) => keys.includes(i.id));

  it("eq compares identity: 50 builds with 3 MB data URLs cost nothing per keystroke", () => {
    const big = "data:image/png;base64," + "A".repeat(3 * 1024 * 1024);
    const infos = ["a", "d", "e"].map((l): ObjectInfo => ({ id: `fig:${l}`, kind: "fig", imageUrl: big + l, mtime: "1" }));
    const stringify = vi.spyOn(JSON, "stringify");
    const t0 = performance.now();
    let prev = infos.map((i) => new ObjectBlockWidget(i.id, "fig", "Fig. 1", true, i, false));
    for (let n = 0; n < 50; n++) {
      const next = infos.map((i) => new ObjectBlockWidget(i.id, "fig", "Fig. 1", true, i, false));
      next.forEach((w, i) => expect(w.eq(prev[i])).toBe(true));
      prev = next;
    }
    expect(performance.now() - t0).toBeLessThan(200);
    expect(stringify).not.toHaveBeenCalled();     // nothing serialised the images
  });

  it("a key that never gets an answer is not asked again while typing", async () => {
    const render = vi.fn(async (): Promise<ObjectInfo[]> => { throw new Error("bridge down"); });
    const view = live(DOC5, render);
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 5; i++) view.dispatch({ changes: { from: 0, insert: "x" }, selection: { anchor: i + 1 } });
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(1);
    view.dispatch({ effects: invalidateObjects.of(null) });     // a new generation retries
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(2);
  });

  it("a batch over 200 keys is split, and an unanswered key is not re-requested", async () => {
    const doc = Array.from({ length: 250 }, (_, i) => `![[eq:k${i}]]`).join("\n\n") + "\n";
    const render = vi.fn(async (keys: string[]) => keys.filter((k) => k !== "eq:k7").map((k): ObjectInfo => ({ id: k, kind: "eq", latex: "x" })));
    const view = live(doc, render);
    await tick(); await tick();
    expect(render.mock.calls.map((c) => c[0].length).sort((a, b) => a - b)).toEqual([50, 200]);
    view.dispatch({ changes: { from: 0, insert: "y" }, selection: { anchor: 1 } });
    await tick(); await tick();
    expect(render).toHaveBeenCalledTimes(2);
  });

  it("fetches each placed figure's image once per (key, mtime), at most 4 at a time", async () => {
    const doc = Array.from({ length: 7 }, (_, i) => `![[fig:f${i}]]`).join("\n\n") + "\n";
    const infos = Array.from({ length: 7 }, (_, i): ObjectInfo => ({ id: `fig:f${i}`, kind: "fig", mtime: "5", pixels: [10, 10] }));
    const render = vi.fn(async (keys: string[]) => infos.filter((i) => keys.includes(i.id)).map((i) => ({ ...i })));
    let active = 0, peak = 0;
    const waiting: (() => void)[] = [];
    const fetchImage = vi.fn((label: string) => new Promise<string | null>((res) => {
      active++; peak = Math.max(peak, active);
      waiting.push(() => { active--; res(`data:image/png;base64,${label}`); });
    }));
    const view = live(doc, render, spansOf(doc), fetchImage);
    await tick(); await tick();
    expect(fetchImage).toHaveBeenCalledTimes(4);
    while (waiting.length) { waiting.shift()!(); await tick(); await tick(); }
    expect(fetchImage).toHaveBeenCalledTimes(7);
    expect(peak).toBe(4);
    expect(view.state.field(objectDataField).map.get("fig:f3")?.info.imageUrl).toBe("data:image/png;base64,f3");
    // an invalidation with the same mtime refetches metadata but never the images
    view.dispatch({ effects: invalidateObjects.of(null) });
    await tick(); await tick(); await tick();
    expect(render.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(fetchImage).toHaveBeenCalledTimes(7);
    expect(view.state.field(objectDataField).map.get("fig:f3")?.info.imageUrl).toBe("data:image/png;base64,f3");
  });

  it("a figure that is only referenced (not placed) never fetches its image", async () => {
    const doc = "See [[fig:a]] here.\n";
    const fetchImage = vi.fn(async () => "data:image/png;base64,Z");
    live(doc, async (k) => meta(k), spansOf(doc), fetchImage);
    await tick(); await tick();
    expect(fetchImage).not.toHaveBeenCalled();
  });

  it("a changed mtime fetches the new image; an unreadable image becomes a settled notice", async () => {
    const doc = "![[fig:a]]\n";
    let m = "1";
    const render = vi.fn(async (k: string[]) => meta(k).map((i) => ({ ...i, mtime: m })));
    const fetchImage = vi.fn(async () => (m === "1" ? "data:image/png;base64,ONE" : null));
    const view = live(doc, render, spansOf(doc), fetchImage);
    await tick(); await tick(); await tick();
    expect(fetchImage).toHaveBeenCalledTimes(1);
    m = "2";
    view.dispatch({ effects: invalidateObjects.of(null) });
    await tick(); await tick(); await tick(); await tick();
    expect(fetchImage).toHaveBeenCalledTimes(2);
    expect(view.state.field(objectDataField).map.get("fig:a")?.info.imageUrl).toBeNull();
  });

  it("pixels give the placeholder and the image the same aspect ratio before the image loads", () => {
    const pending: ObjectInfo = { id: "fig:a", kind: "fig", mtime: "1", pixels: [800, 400] };
    const ph = new ObjectBlockWidget("fig:a", "fig", "Fig. 1", true, pending, false).toDOM().querySelector<HTMLElement>(".lw-object__placeholder")!;
    expect(ph.style.aspectRatio.replace(/\s/g, "")).toBe("800/400");
    const img = new ObjectBlockWidget("fig:a", "fig", "Fig. 1", true, { ...pending, imageUrl: "data:image/png;base64,AAAA" }, false).toDOM().querySelector("img")!;
    expect(img.getAttribute("width")).toBe("800");
    expect(img.getAttribute("height")).toBe("400");
    expect(img.style.aspectRatio.replace(/\s/g, "")).toBe("800/400");
    const noPx = new ObjectBlockWidget("fig:a", "fig", "Fig. 1", true, { id: "fig:a", kind: "fig", imageUrl: "data:image/png;base64,AAAA", pixels: null }, false).toDOM().querySelector("img")!;
    expect(noPx.hasAttribute("width")).toBe(false);
  });

  it("a placement line with leading spaces is still a placement", () => {
    const sp: Span = { kind: "placement", start: 2, end: 12, key: "fig:a", objectKind: "fig", display: "Fig. 1", status: "resolved" };
    expect(placementLine(sp, "  ![[fig:a]]\n")).toEqual({ from: 0, to: 12 });
    expect(placementLine(sp, "x ![[fig:a]]\n")).toBeNull();
  });
});

describe("an image arriving", () => {
  it("redraws the decorations by itself: no keystroke or cursor move is needed to show it", () => {
    const noImage: ObjectInfo = { ...FIG, imageUrl: undefined, mtime: "1" };
    let s = make(DOC5, spansOf(DOC5), 0, "scene", [noImage]);      // the cursor is far from every placement
    const before = s.field(decoField);
    const first = blocks(s).find((b) => (b.w as ObjectBlockWidget).key === "fig:a")!.w as ObjectBlockWidget;
    expect(first.info?.imageUrl).toBeUndefined();
    s = s.update({ effects: setObjectImage.of({ key: "fig:a", mtime: "1", url: "data:image/png;base64,AAAA" }) }).state;
    expect(s.field(decoField)).not.toBe(before);
    const after = blocks(s).find((b) => (b.w as ObjectBlockWidget).key === "fig:a")!.w as ObjectBlockWidget;
    expect(after.info?.imageUrl).toBe("data:image/png;base64,AAAA");
  });
});
