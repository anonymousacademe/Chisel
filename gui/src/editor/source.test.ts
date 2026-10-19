import { describe, expect, it } from "vitest";
import { EditorState } from "@codemirror/state";
import { markdown } from "@codemirror/lang-markdown";
import { decorationCore, decoField, entityTypeFacet, kindFacet, reflowFacet, SOURCE_BANNER } from "./cm";
import { sourceMarkers } from "./spans";

const FM = "---\nname: Smith 2024\ntype: source\ncsl: {\"title\": \"X\"}\n---\n";
const BODY =
  "<!-- zotero:begin -->\n## From Zotero\n\n**A Paper**\n\nSmith, A.\n\n### Highlights\n\n" +
  "- > a quote\n  <!--zotero-ann:AB12-->\n<!-- zotero:end -->\n\n## My notes\n\nmine\n";
const SOURCE = FM + BODY;

function stateFor(doc: string, kind: string, entityType = "") {
  return EditorState.create({ doc, extensions: [kindFacet.of(kind), entityTypeFacet.of(entityType), reflowFacet.of(true), markdown(), ...decorationCore] });
}

interface Found { from: number; to: number; cls?: string; block?: boolean; hasWidget: boolean; replace: boolean }
function decos(state: EditorState, atomic = false): Found[] {
  const set = atomic ? state.field(decoField).atomic : state.field(decoField).all;
  const out: Found[] = [];
  const it = set.iter();
  while (it.value) {
    const spec = it.value.spec as { class?: string; block?: boolean; widget?: unknown };
    out.push({ from: it.from, to: it.to, cls: spec.class, block: spec.block, hasWidget: !!spec.widget, replace: it.from < it.to && !spec.class });
    it.next();
  }
  return out;
}
const hidden = (state: EditorState) => decos(state).filter((d) => d.replace && !d.hasWidget);

describe("sourceMarkers", () => {
  it("finds the begin, end and highlight marker lines, each with its newline", () => {
    const m = sourceMarkers(BODY);
    expect(m.hide.map((h) => BODY.slice(h.from, h.to))).toEqual([
      "<!-- zotero:begin -->\n", "  <!--zotero-ann:AB12-->\n", "<!-- zotero:end -->\n",
    ]);
    expect(m.begin).toBe("<!-- zotero:begin -->\n".length);
    expect(BODY.slice(m.title!, m.title! + 9)).toBe("**A Paper");
  });
  it("finds nothing in a note without markers", () => {
    expect(sourceMarkers("## My notes\n\nx")).toEqual({ hide: [], begin: null, title: null });
  });
});

describe("source note decorations", () => {
  it("hides the frontmatter and the head begin marker atomically; interior markers are dimmed, not hidden", () => {
    const s = stateFor(SOURCE, "entity", "source");
    const hid = hidden(s);
    expect(hid).toContainEqual(expect.objectContaining({ from: 0, to: FM.length }));
    const beginAt = SOURCE.indexOf("<!-- zotero:begin -->");
    expect(hid.some((d) => d.from <= beginAt && d.to >= beginAt + 21)).toBe(true);
    for (const t of ["<!--zotero-ann:AB12-->", "<!-- zotero:end -->"]) {
      const at = SOURCE.indexOf(t);
      expect(hid.some((d) => d.from <= at && d.to > at), t).toBe(false);
      expect(decos(s).some((d) => d.cls === "lw-source-marker" && d.from <= at && SOURCE.lastIndexOf("\n", at) + 1 === d.from), t).toBe(true);
      expect(decos(s, true).some((d) => d.from <= at && d.to > at), t).toBe(false);
    }
    expect(decos(s, true)).toContainEqual(expect.objectContaining({ from: 0, to: FM.length }));
    expect(decos(s).some((d) => d.cls === "lw-frontmatter")).toBe(false);
  });

  it("shows the banner only for source notes, as a block widget at the Zotero part", () => {
    const s = stateFor(SOURCE, "entity", "source");
    const w = decos(s).filter((d) => d.block && d.hasWidget && d.from === FM.length + "<!-- zotero:begin -->\n".length);
    expect(w).toHaveLength(1);
    expect(SOURCE_BANNER).toContain("My notes");
    for (const [kind, type] of [["entity", "character"], ["entity", ""], ["scene", ""]] as const) {
      const o = stateFor(SOURCE, kind, type);
      expect(decos(o).some((d) => d.block && d.hasWidget), `${kind}/${type}`).toBe(false);
    }
  });

  it("styles the paper title line like a sub-heading", () => {
    const s = stateFor(SOURCE, "entity", "source");
    const at = SOURCE.indexOf("**A Paper**");
    expect(decos(s)).toContainEqual(expect.objectContaining({ from: at, cls: "lw-h lw-h3" }));
  });

  it("leaves other entity notes and scenes as they were", () => {
    const person = stateFor(FM.replace("source", "character") + "text\n", "entity", "character");
    const fmLines = decos(person).filter((d) => d.cls === "lw-frontmatter");
    expect(fmLines.length).toBe(FM.split("\n").length - 1);
    expect(hidden(person).some((d) => d.from === 0 && d.to === FM.length)).toBe(false);
    // a source note's markers are only quieted for sources
    const asCharacter = stateFor(SOURCE, "entity", "character");
    expect(hidden(asCharacter).some((d) => SOURCE.slice(d.from, d.to).includes("zotero:begin"))).toBe(false);
    const scene = stateFor(BODY, "scene");
    expect(hidden(scene).some((d) => BODY.slice(d.from, d.to).includes("zotero"))).toBe(false);
  });

  it("never changes the text the editor holds", () => {
    const s = stateFor(SOURCE, "entity", "source");
    expect(s.doc.toString()).toBe(SOURCE);
    // an edit under My notes keeps everything else byte for byte
    const at = SOURCE.length - 1;
    const next = s.update({ changes: { from: at, insert: " more" } }).state;
    expect(next.doc.toString()).toBe(SOURCE.slice(0, at) + " more" + SOURCE.slice(at));
  });
});

describe("source note protection", () => {
  const start = SOURCE.indexOf("## From Zotero");
  const press = (s: EditorState, from: number, to: number, insert = "") => s.update({ changes: { from, to, insert }, userEvent: "delete.backward" }).state;
  it("Backspace at the first visible position changes nothing", () => {
    const s = stateFor(SOURCE, "entity", "source");
    expect(press(s, 0, start).doc.toString()).toBe(SOURCE);
    expect(press(s, start - 1, start).doc.toString()).toBe(SOURCE);
  });
  it("allows edits at interior markers (they are visible, dimmed text)", () => {
    const s = stateFor(SOURCE, "entity", "source");
    const endMk = SOURCE.indexOf("<!-- zotero:end -->");
    expect(press(s, endMk - 1, endMk).doc.toString()).toBe(SOURCE.slice(0, endMk - 1) + SOURCE.slice(endMk));
    expect(press(s, endMk, endMk + 1).doc.toString()).toBe(SOURCE.slice(0, endMk) + SOURCE.slice(endMk + 1));
  });
  it("rejects insertion in the hidden head and keeps the frontmatter", () => {
    const s = stateFor(SOURCE, "entity", "source");
    for (const at of [0, 5, FM.length]) expect(s.update({ changes: { from: at, insert: "x" } }).state.doc.toString()).toBe(SOURCE);
  });
  it("lets whole-document replacement and visible typing through", () => {
    const s = stateFor(SOURCE, "entity", "source");
    expect(s.update({ changes: { from: 0, to: SOURCE.length, insert: "new" } }).state.doc.toString()).toBe("new");
    expect(s.update({ changes: { from: start, insert: "x" } }).state.doc.toString()).toBe(SOURCE.slice(0, start) + "x" + SOURCE.slice(start));
    const mine = SOURCE.indexOf("mine");
    expect(s.update({ changes: { from: mine, to: mine + 4 } }).state.doc.toString()).toBe(SOURCE.replace("mine", ""));
  });
  it("moves a cursor out of the hidden head", () => {
    const s = stateFor(SOURCE, "entity", "source");
    expect(s.update({ selection: { anchor: 0 } }).state.selection.main.head).toBe(start);
    expect(s.update({ selection: { anchor: 3 } }).state.selection.main.head).toBe(start);
  });
  it("does not touch other notes", () => {
    const s = stateFor(SOURCE, "entity", "character");
    expect(s.update({ changes: { from: 0, insert: "x" } }).state.doc.toString()).toBe("x" + SOURCE);
    expect(s.update({ selection: { anchor: 0 } }).state.selection.main.head).toBe(0);
  });
});
