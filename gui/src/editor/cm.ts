// CodeMirror 6 setup for a Chisel document: plain Markdown on disk, drawn
// with the design's prose styling. Live preview: [[link]] brackets and the
// <!--ai--> markers are hidden, mentions are coloured, pending drafts tinted.
import { Compartment, EditorSelection, EditorState, Prec, Facet, StateEffect, StateField, type Extension, type Range } from "@codemirror/state";
import { typingKeydown } from "../audio/typing";
import { Decoration, type DecorationSet, EditorView, WidgetType, drawSelection, hoverTooltip, keymap, tooltips } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { ensureSyntaxTree } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { autocompletion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { completionSpot, elementOfLine, upperNames, type ScriptNames } from "./script";
import { formatSpecs } from "./format";
import { citeCompletion } from "../data/research";
import { invalidateObjects, objectDataField, objectFetcher, ObjectBlockWidget, ObjectRefWidget, openObjectFacet, setObjectData, type ObjectInfo } from "./objects";
import { citeReplaced, objrefReplaced, placementLine, frontmatterRange, sourceMarkers, misspellingAt, sceneFrontmatter, misspellSpecs, scriptLineSpecs, softBreaks, specsFor, titleLine, type Misspelling, type Span } from "./spans";

export const setSpans = StateEffect.define<Span[]>();
export const setSpelling = StateEffect.define<Misspelling[]>();
/** The scene's comments with positions (see data/types CommentRow); resolved and detached ones are not drawn. */
export interface CommentMark { id: string; start: number; end: number }
export const setComments = StateEffect.define<CommentMark[]>();
/** The passage being read aloud (read-aloud mode), or null: drawn as a highlight, follows edits. */
export const setReading = StateEffect.define<{ from: number; to: number } | null>();
/** Holds metaFacet so the mentions line can change without rebuilding the editor. */
export const metaCompartment = new Compartment();
/** Show hard-wrapped source lines as flowing paragraphs (display only). */
export const reflowFacet = Facet.define<boolean, boolean>({ combine: (v) => (v.length ? v[v.length - 1] : true) });
export const reflowCompartment = new Compartment();

/** What the title block needs that only the host knows (mentions line). */
export const metaFacet = Facet.define<string, string>({ combine: (v) => v[v.length - 1] ?? "" });
/** "scene" | "entity" | "style": entity notes show their frontmatter as a mono block. */
export const kindFacet = Facet.define<string, string>({ combine: (v) => v[v.length - 1] ?? "scene" });
/** The entity's type ("character", "source", ...) for kind "entity": source notes hide their frontmatter. */
export const entityTypeFacet = Facet.define<string, string>({ combine: (v) => v[v.length - 1] ?? "" });
/** A scene of a script project: its lines are drawn as screenplay elements (Python classifies them). */
export const scriptFacet = Facet.define<boolean, boolean>({ combine: (v) => (v.length ? v[v.length - 1] : false) });

class MetaWidget extends WidgetType {
  readonly text: string;
  constructor(text: string) { super(); this.text = text; }
  eq(o: MetaWidget) { return o.text === this.text; }
  toDOM() {
    const el = document.createElement("div");
    el.className = "lw-page__meta";
    el.textContent = this.text;
    return el;
  }
  ignoreEvent() { return true; }
}

/** The one-line note above the Zotero part of a source note (display only, not in the file). */
export const SOURCE_BANNER = "From Zotero. This part is replaced when you sync. Write your own notes under My notes.";
class SourceBanner extends WidgetType {
  eq() { return true; }
  toDOM() {
    const el = document.createElement("div");
    el.className = "lw-source-banner";
    el.textContent = SOURCE_BANNER;
    return el;
  }
  ignoreEvent() { return true; }
}

/** Called by the inline Accept / Reject buttons: (index of the draft in document order, accept?). */
export const draftFacet = Facet.define<(index: number, accept: boolean) => void, (index: number, accept: boolean) => void>({
  combine: (v) => v[v.length - 1] ?? (() => {}),
});

class DraftBar extends WidgetType {
  readonly index: number;
  readonly run: (index: number, accept: boolean) => void;
  constructor(index: number, run: (index: number, accept: boolean) => void) { super(); this.index = index; this.run = run; }
  eq(o: DraftBar) { return o.index === this.index; }
  toDOM() {
    const bar = document.createElement("span");
    bar.className = "lw-draftbar";
    bar.contentEditable = "false";
    for (const [label, accept, key] of [["Accept", true, "F7"], ["Reject", false, "F8"]] as const) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = accept ? "lw-draftbar__btn is-accept" : "lw-draftbar__btn is-reject";
      b.textContent = label;
      b.title = `${label} this AI draft (${key})`;
      b.addEventListener("mousedown", (e) => e.preventDefault()); // keep the editor's selection
      b.addEventListener("click", () => this.run(this.index, accept));
      bar.append(b);
    }
    return bar;
  }
  ignoreEvent() { return true; }
}

/** An in-text citation drawn as its formatted text; the raw [[@key]] stays in the document. */
export class CiteWidget extends WidgetType {
  readonly display: string;
  readonly status: string;
  readonly title: string;
  readonly keys: string;
  constructor(display: string, status: string, title: string, keys: string) {
    super();
    this.display = display; this.status = status; this.title = title; this.keys = keys;
  }
  eq(o: CiteWidget) { return o.display === this.display && o.status === this.status && o.title === this.title && o.keys === this.keys; }
  toDOM() {
    const el = document.createElement("span");
    el.className = `lw-cite lw-cite--shown ${this.status === "resolved" ? "lw-cite--resolved" : "lw-cite--unresolved"}`;
    el.setAttribute("data-keys", this.keys);
    el.textContent = this.display;
    return el;
  }
  // false: a click on it must still move the cursor in (which reveals the raw text), and Ctrl-click / hover keep working
  ignoreEvent() { return false; }
}

class SpaceWidget extends WidgetType {
  eq() { return true; }
  toDOM() { const el = document.createElement("span"); el.textContent = " "; return el; }
}
const SPACE = Decoration.replace({ widget: new SpaceWidget() });

/** Spans follow the text through edits until fresh ones arrive from Python. */
const spansField = StateField.define<Span[]>({
  create: () => [],
  update(spans, tr) {
    for (const e of tr.effects) if (e.is(setSpans)) return e.value;
    if (!tr.docChanged || spans.length === 0) return spans;
    const map = (p: number | undefined, assoc: 1 | -1) => (p === undefined ? p : tr.changes.mapPos(p, assoc));
    return spans.map((s) => ({
      ...s,
      start: tr.changes.mapPos(s.start, 1), end: tr.changes.mapPos(s.end, -1),
      innerStart: map(s.innerStart, -1), innerEnd: map(s.innerEnd, 1),
      bodyStart: map(s.bodyStart, -1), bodyEnd: map(s.bodyEnd, 1),
    })).filter((s) => s.start <= s.end);
  },
});

/** Misspelled words follow the text through edits until a fresh check arrives from Python. */
const spellingField = StateField.define<Misspelling[]>({
  create: () => [],
  update(list, tr) {
    for (const e of tr.effects) if (e.is(setSpelling)) return e.value;
    if (!tr.docChanged || list.length === 0) return list;
    return list
      .map((m) => ({ ...m, start: tr.changes.mapPos(m.start, 1), end: tr.changes.mapPos(m.end, -1) }))
      .filter((m) => m.start < m.end);
  },
});

/** Comment passages follow the text through edits until Python re-anchors them. */
export const readingField = StateField.define<{ from: number; to: number } | null>({
  create: () => null,
  update(range, tr) {
    for (const e of tr.effects) if (e.is(setReading)) return e.value;
    if (!range || !tr.docChanged) return range;
    return { from: tr.changes.mapPos(range.from, 1), to: tr.changes.mapPos(range.to, -1) };
  },
});

export const commentsField = StateField.define<CommentMark[]>({
  create: () => [],
  update(list, tr) {
    for (const e of tr.effects) if (e.is(setComments)) return e.value;
    if (!tr.docChanged || list.length === 0) return list;
    return list
      .map((m) => ({ ...m, start: tr.changes.mapPos(m.start, 1), end: tr.changes.mapPos(m.end, -1) }))
      .filter((m) => m.start < m.end);
  },
});

export interface Built { all: DecorationSet; atomic: DecorationSet }

const HEADING = /^ATXHeading(\d)$/;

export function build(state: EditorState): Built {
  const doc = state.doc;
  const text = doc.toString();
  const kind = state.facet(kindFacet);
  const ranges: Range<Decoration>[] = [];
  const atomic: Range<Decoration>[] = [];
  const hide = Decoration.replace({});
  const head = state.selection.main.head;

  // span decorations (mentions, links, drafts, expand markers)
  const citeMarks: Range<Decoration>[] = []; // citations: a widget or this mark, decided once the soft breaks are known
  const objMarks: Range<Decoration>[] = []; // object references: a widget or this mark
  for (const sp of specsFor(state.field(spansField), head, doc.length)) {
    if (sp.from === sp.to) continue;
    if (sp.cls?.startsWith("lw-cite")) citeMarks.push(Decoration.mark({ class: sp.cls, attributes: sp.attrs }).range(sp.from, sp.to));
    else if (sp.cls?.startsWith("lw-objref")) objMarks.push(Decoration.mark({ class: sp.cls, attributes: sp.attrs }).range(sp.from, sp.to));
    else if (sp.type === "hide") { ranges.push(hide.range(sp.from, sp.to)); atomic.push(hide.range(sp.from, sp.to)); }
    else ranges.push(Decoration.mark({ class: sp.cls, attributes: sp.attrs }).range(sp.from, sp.to));
  }

  // script scenes: one class per Fountain line (scene heading, cue, dialogue ...), positions from Python
  if (state.facet(scriptFacet)) {
    const seen = new Set<number>();
    for (const l of scriptLineSpecs(state.field(spansField), doc.length)) {
      const at = doc.lineAt(l.from).from;
      if (seen.has(at)) continue;
      seen.add(at);
      ranges.push(Decoration.line({ class: l.cls }).range(at));
    }
  }

  // misspelled words (scenes only: Python sends nothing for other documents)
  for (const sp of misspellSpecs(state.field(spellingField), doc.length)) {
    ranges.push(Decoration.mark({ class: sp.cls }).range(sp.from, sp.to));
  }

  // inline Accept / Reject after every pending AI draft
  const act = state.facet(draftFacet);
  let pendingIndex = 0;
  for (const sp of state.field(spansField)) {
    if (sp.kind !== "pending") continue;
    const index = pendingIndex++;
    if (sp.end <= doc.length && sp.start < sp.end) ranges.push(Decoration.widget({ widget: new DraftBar(index, act), side: 1 }).range(sp.end));
  }

  // title block: the first "# " line, styled big; its "# " prefix hidden; meta line under it
  const plain = kind === "dictionary"; // one term per line: no title block, no Markdown, no reflow
  // a scene's details (YAML frontmatter) are edited in the inspector, not here: hide the block
  const details = kind === "scene" ? sceneFrontmatter(text) : null;
  if (details) {
    ranges.push(hide.range(details.from, details.to));
    atomic.push(hide.range(details.from, details.to));
  }
  const title = kind !== "entity" && !plain ? titleLine(text, details?.to ?? 0) : null;
  if (title) {
    const line = doc.lineAt(title.from);
    // the hidden details block merges with the title into one visual line, which takes the
    // decorations of the line it starts on (line 1)
    ranges.push(Decoration.line({ class: "lw-title-line" }).range(details ? 0 : line.from));
    ranges.push(hide.range(title.from, title.from + title.prefix));
    atomic.push(hide.range(title.from, title.from + title.prefix));
    // always present: it also carries the violet rule under the title
    ranges.push(Decoration.widget({ widget: new MetaWidget(state.facet(metaFacet)), block: true, side: 1 }).range(line.to));
  }

  // YAML frontmatter of entity notes: a muted mono block
  const fm = kind === "entity" ? frontmatterRange(text) : details;
  // a source note: the CSL dump is data for the export, not for reading: hide it like a scene's details, and
  // quiet the sync markers; the file is untouched (every range here is display only)
  const source = kind === "entity" && state.facet(entityTypeFacet) === "source";
  const markerHides: { from: number; to: number }[] = [];
  if (source) {
    if (fm) {
      ranges.push(hide.range(fm.from, fm.to));
      atomic.push(hide.range(fm.from, fm.to));
    }
    const mk = sourceMarkers(text, fm?.to ?? 0);
    for (const h of mk.hide) {
      if (h.to === mk.begin) {
        // the head's begin marker: hidden and atomic, protected by sourceGuard
        ranges.push(hide.range(h.from, h.to));
        atomic.push(hide.range(h.from, h.to));
      } else {
        // interior markers stay visible, dimmed, editable: hiding text inside an editable document lets a
        // Backspace join a marker to the line above unseen. A hand-damaged marker blocks that note's sync
        // (damaged markers => row blocked), so the failure is visible and safe.
        ranges.push(Decoration.line({ class: "lw-source-marker" }).range(h.from));
        markerHides.push(h);
      }
    }
    if (mk.begin !== null) {
      ranges.push(Decoration.widget({ widget: new SourceBanner(), block: true, side: -1 }).range(mk.begin));
      // the hidden head is one empty visual row above the banner: collapse it
      ranges.push(Decoration.line({ class: "lw-source-head" }).range(0));
    }
    if (mk.title !== null) ranges.push(Decoration.line({ class: "lw-h lw-h3" }).range(mk.title));
  } else if (fm && kind === "entity") {
    const last = doc.lineAt(Math.max(fm.to - 1, 0)).number;
    for (let n = 1; n <= last; n++) ranges.push(Decoration.line({ class: "lw-frontmatter" }).range(doc.line(n).from));
  }

  // figures, tables and equations (research projects only: Python sends no object spans elsewhere). A placement
  // line is replaced by its block unless the selection touches it; then the raw line stays editable and the
  // rendered block sits just above it.
  const tree = ensureSyntaxTree(state, doc.length, 40);
  const objectsOn = kind !== "dictionary" && kind !== "style";
  const objectData = state.field(objectDataField, false);
  const inCode = (pos: number) => {
    if (!tree) return false;
    for (let n: ReturnType<typeof tree.resolveInner> | null = tree.resolveInner(pos, 1); n; n = n.parent) {
      if (n.name === "InlineCode" || n.name === "FencedCode" || n.name === "CodeBlock") return true;
    }
    return false;
  };
  const placeEdges = new Set<number>();    // a placement line never joins its neighbours as a soft break
  if (objectsOn) {
    const placed = new Set<number>();
    for (const x of state.field(spansField)) {
      if (x.kind !== "placement" || !x.key || !x.objectKind) continue;
      const line = placementLine(x, text);
      if (!line || placed.has(line.from) || inCode(line.from)) continue;
      placed.add(line.from);
      placeEdges.add(line.to); placeEdges.add(line.from - 1);
      const info = objectData?.map.get(x.key)?.info;
      const resolved = x.status === "resolved";
      const touched = state.selection.ranges.some((r) => r.from <= line.to && r.to >= line.from);
      if (touched) {
        ranges.push(Decoration.widget({ widget: new ObjectBlockWidget(x.key, x.objectKind, x.display ?? x.key, resolved, info, true), block: true, side: -1 }).range(line.from));
        ranges.push(Decoration.line({ class: "lw-placement-raw" }).range(line.from));
      } else {
        ranges.push(Decoration.replace({ widget: new ObjectBlockWidget(x.key, x.objectKind, x.display ?? x.key, resolved, info, false), block: true }).range(line.from, line.to));
      }
    }
  }

  // hard-wrapped source lines flow as one paragraph (display only)
  const softBreakSet = new Set<number>((state.facet(reflowFacet) && !plain ? softBreaks(text, fm) : [])
    .filter((p) => !markerHides.some((h) => p >= h.from - 1 && p < h.to) && !placeEdges.has(p)));
  for (const pos of softBreakSet) {
    ranges.push(SPACE.range(pos, pos + 1));
    atomic.push(SPACE.range(pos, pos + 1));
  }

  // citations (research projects only: Python sends no citation spans elsewhere): the formatted text as a widget
  // unless the cursor touches it or it crosses a line / soft break, then the raw text with the dotted mark
  const cites = state.field(spansField).filter((x) => x.kind === "citation");
  const replaced = new Set<number>();
  for (const x of cites) {
    if (citeReplaced(x, state.selection.ranges, text, softBreakSet)) {
      replaced.add(x.start);
      ranges.push(Decoration.replace({
        widget: new CiteWidget(x.display ?? "", x.status ?? "unresolved", x.title ?? "", (x.keys ?? []).join(" ")),
      }).range(x.start, x.end));
    }
  }
  for (const m of citeMarks) if (!replaced.has(m.from)) ranges.push(m);

  // references to figures, tables and equations: "Figure 2" as a link-like word, the raw [[fig:x]] when touched
  const objReplaced = new Set<number>();
  if (objectsOn) {
    for (const x of state.field(spansField)) {
      if (x.kind !== "objref" || !x.key || inCode(x.start)) continue;
      if (objrefReplaced(x, state.selection.ranges, text, softBreakSet)) {
        objReplaced.add(x.start);
        ranges.push(Decoration.replace({ widget: new ObjectRefWidget(x.key, x.display ?? x.key, x.status ?? "unresolved") }).range(x.start, x.end));
      }
    }
    for (const m of objMarks) if (!objReplaced.has(m.from) && !inCode(m.from)) ranges.push(m);
  }

  // read aloud: the passage being spoken
  const reading = state.field(readingField);
  if (reading && reading.from < reading.to && reading.to <= doc.length) {
    ranges.push(Decoration.mark({ class: "lw-reading" }).range(reading.from, reading.to));
  }

  // comments: a subtle highlight on the passage and a marker in the margin of its first line
  const marks = state.field(commentsField).filter((m) => m.start < m.end && m.end <= doc.length);
  const byLine = new Map<number, string[]>();
  for (const m of marks) {
    ranges.push(Decoration.mark({ class: "lw-comment", attributes: { "data-comment": m.id } }).range(m.start, m.end));
    // hard-wrapped lines are drawn as one: the line decoration belongs to the first of them
    let line = doc.lineAt(m.start);
    while (line.number > 1 && softBreakSet.has(line.from - 1)) line = doc.line(line.number - 1);
    byLine.set(line.from, [...(byLine.get(line.from) ?? []), m.id]);
  }
  for (const [from, ids] of byLine) {
    ranges.push(Decoration.line({ class: "lw-has-comment", attributes: { "data-comments": ids.join(",") } }).range(from));
  }


  // blank lines are paragraph gaps, not full lines
  for (let n = 1; n <= doc.lines; n++) {
    const line = doc.line(n);
    if (line.length === 0) ranges.push(Decoration.line({ class: "lw-blank" }).range(line.from));
  }

  // Markdown structure: headings, emphasis, quotes, inline code
  if (tree) {
    tree.iterate({
      enter(node) {
        const h = HEADING.exec(node.name);
        if (h && !(title && node.from === title.from)) {
          const line = doc.lineAt(node.from);
          ranges.push(Decoration.line({ class: `lw-h lw-h${h[1]}` }).range(line.from));
        } else if (node.name === "StrongEmphasis") {
          ranges.push(Decoration.mark({ class: "lw-strong" }).range(node.from, node.to));
        } else if (node.name === "Emphasis") {
          ranges.push(Decoration.mark({ class: "lw-em" }).range(node.from, node.to));
        } else if (node.name === "InlineCode") {
          ranges.push(Decoration.mark({ class: "lw-code" }).range(node.from, node.to));
        } else if (node.name === "Blockquote") {
          for (let n = doc.lineAt(node.from).number; n <= doc.lineAt(node.to).number; n++) {
            ranges.push(Decoration.line({ class: "lw-quote" }).range(doc.line(n).from));
          }
        }
      },
    });
    // syntax marks: hidden unless the cursor is in or touching their span (plain notes keep them dim)
    const blocks = kind === "style";
    for (const f of formatSpecs(tree, text, head, { titleFrom: title?.from ?? null, blocks })) {
      if (f.type === "hide") { ranges.push(hide.range(f.from, f.to)); atomic.push(hide.range(f.from, f.to)); }
      else if (f.type === "line") ranges.push(Decoration.line({ class: f.cls ?? "" }).range(f.from));
      else ranges.push(Decoration.mark({ class: f.cls ?? "" }).range(f.from, f.to));
    }
  }

  return { all: Decoration.set(ranges, true), atomic: Decoration.set(atomic, true) };
}

export const decoField = StateField.define<Built>({
  create: (state) => build(state),
  update(value, tr) {
    const facetChanged = tr.startState.facet(metaFacet) !== tr.state.facet(metaFacet)
      || tr.startState.facet(reflowFacet) !== tr.state.facet(reflowFacet);
    if (tr.docChanged || tr.selection || facetChanged || tr.effects.some((e) => e.is(setSpans) || e.is(setSpelling) || e.is(setComments) || e.is(setReading) || e.is(setObjectData) || e.is(invalidateObjects))) return build(tr.state);
    return value;
  },
  provide: (f) => [
    EditorView.decorations.from(f, (v) => v.all),
    EditorView.atomicRanges.of((view) => view.state.field(f).atomic),
  ],
});

/** Hidden ranges of a source note (frontmatter, head begin marker) and the first visible offset. */
function sourceHidden(text: string): { ranges: { from: number; to: number }[]; start: number } {
  const fm = frontmatterRange(text);
  const ranges = fm ? [{ from: fm.from, to: fm.to }] : [];
  const mk = sourceMarkers(text, fm?.to ?? 0);
  ranges.push(...mk.hide.filter((h) => h.to === mk.begin)); // only the head's begin marker; interior markers are plain text
  ranges.sort((a, b) => a.from - b.from);
  let start = 0;
  for (const r of ranges) if (r.from <= start && r.to > start) start = r.to;
  return { ranges, start };
}

/** First visible offset of a source note (where its cursor starts); 0 for any other note. */
export function sourceStart(text: string, entityType: string): number {
  return entityType === "source" ? sourceHidden(text).start : 0;
}

const isSource = (s: EditorState) => s.facet(kindFacet) === "entity" && s.facet(entityTypeFacet) === "source";

/** Source notes: the hidden ranges can never be touched by a keystroke (a Backspace that would reach into one
 *  deletes nothing); a cursor never rests in the hidden head; whole-document replacements pass. */
export const sourceGuard: Extension[] = [
  EditorState.changeFilter.of((tr) => {
    if (!isSource(tr.startState)) return true;
    const doc = tr.startState.doc;
    const { ranges, start } = sourceHidden(doc.toString());
    let ok = true;
    tr.changes.iterChanges((from, to) => {
      if (!ok || (from === 0 && to === doc.length && doc.length > 0)) return;
      if (from === to && from < start) { ok = false; return; }
      for (const r of ranges) {
        if (from < to ? from < r.to && to > r.from : from >= r.from && from < r.to) { ok = false; return; }
      }
    });
    return ok;
  }),
  EditorState.transactionFilter.of((tr) => {
    if (!isSource(tr.startState) || (!tr.docChanged && !tr.selection)) return tr;
    const { start } = sourceHidden(tr.newDoc.toString());
    const sel = tr.newSelection;
    if (!sel.ranges.some((r) => r.from < start)) return tr;
    const fixed = EditorSelection.create(sel.ranges.map((r) => EditorSelection.range(Math.max(r.anchor, start), Math.max(r.head, start))), sel.mainIndex);
    return [tr, { selection: fixed, sequential: true }];
  }),
];

/** The fields the decorations read, without the DOM-bound parts of editorExtensions (for tests). */
export const decorationCore: Extension[] = [spansField, spellingField, commentsField, readingField, objectDataField, decoField, sourceGuard];

export interface CursorInfo {
  line: number; col: number; head: number; from: number; to: number;
  canUndo: boolean; canRedo: boolean;
}

/** A hover card for a mention or link: what the host knows about the target. */
export interface Card { title: string; kind: string; body: string; missing?: boolean }

const isTarget = (s: Span) => s.kind === "mention" || s.kind === "link" || s.kind === "unresolved" || s.kind === "citation";
const spanAt = (state: EditorState, pos: number) => state.field(spansField).find((s) => isTarget(s) && pos >= s.start && pos <= s.end);

/** What the spelling popover is about: a misspelled word, or a selected phrase. x/y = viewport point below it. */
export type SpellTarget =
  | { kind: "word"; from: number; to: number; word: string; x: number; y: number }
  | { kind: "phrase"; from: number; to: number; text: string; x: number; y: number };

/** The popover target for a click / right-click at *pos*, or at the cursor for Ctrl+. (pos = null). */
function spellTargetAt(view: EditorView, pos: number | null): SpellTarget | null {
  const sel = view.state.selection.main;
  const at = pos ?? sel.head;
  const place = (from: number, to: number) => {
    const c = view.coordsAtPos(from) ?? view.coordsAtPos(to);
    return c ? { x: c.left, y: c.bottom } : { x: 0, y: 0 };
  };
  const text = view.state.sliceDoc(sel.from, sel.to);
  const hit = misspellingAt(view.state.field(spellingField), at);
  // a multi-word selection is a phrase for the dictionary (unless it is exactly one flagged word)
  const exact = hit && hit.start === sel.from && hit.end === sel.to;
  if (!sel.empty && !exact && /\s/.test(text.trim()) && at >= sel.from && at <= sel.to) {
    return { kind: "phrase", from: sel.from, to: sel.to, text, ...place(sel.from, sel.to) };
  }
  if (!hit) return null;
  return { kind: "word", from: hit.start, to: hit.end, word: view.state.sliceDoc(hit.start, hit.end), ...place(hit.start, hit.end) };
}

/** What a right-click landed on (see data/editorMenu.ts for the menu built from it). */
export interface ContextInfo { x: number; y: number; span?: Span; word?: string; selection?: string }

export interface Hooks {
  /** Open the spelling popover (click on a misspelled word, right-click, Ctrl+.). */
  onSpell?(target: SpellTarget): void;
  /** Right-click with text selected: the selection menu (Send selection to notebook, ...), at the pointer. */
  /** Any other right-click: the pointer position and what is under it (a mention or link, a word, the selection). */
  onContextMenu?(info: ContextInfo): void;
  /** Hover card for a span (null = none). */
  getCard(span: Span): Promise<Card | null>;
  /** ctrl/cmd+click on a mention or link. */
  onOpenEntity(span: Span): void;
  onChange(text: string): void;
  onCursor(info: CursorInfo): void;
  onBlur(): void;
  onSaveNow(): void;
  /** Accept/Reject buttons of a pending draft (index in document order). */
  onResolveDraft(index: number, accept: boolean): void;
  /** Extra key bindings (e.g. f7/f8) supplied by the host. */
  extraKeys?: { key: string; run: () => boolean }[];
  /** Script scenes: Tab rewrites a line as the next element (Python decides how); null = leave it. */
  onCycleElement?(line: string, element: string, reverse: boolean): Promise<string | null>;
  /** Script scenes: the project's character and place names, for the completion list. */
  getNames?(): ScriptNames;
  /** Research projects: sources for the [[@ completion list (absent = not a research project). */
  searchSources?(query: string): Promise<{ key: string; display: string; title: string }[]>;
  /** Research projects: object_render for these keys ("fig:label"); absent = the widgets stay sized placeholders. */
  renderObjects?(keys: string[]): Promise<ObjectInfo[]>;
  /** A figure's image as a data URL (object_image), fetched lazily one at a time; null = unreadable. */
  fetchObjectImage?(label: string): Promise<string | null>;
  /** The Edit affordance of a block, or Ctrl-click on a reference: open the object's dialog (key "fig:label"). */
  onOpenObject?(key: string): void;
}

/** Tab / Shift-Tab in a script scene: the current line becomes the next (previous) element. */
function cycleLine(view: EditorView, hooks: Hooks, reverse: boolean): boolean {
  if (!hooks.onCycleElement) return false;
  const line = view.state.doc.lineAt(view.state.selection.main.head);
  const { from, text } = line;
  const element = elementOfLine(view.state.field(spansField), line.from, line.to);
  void hooks.onCycleElement(text, element, reverse).then((next) => {
    if (next === null) return;
    const doc = view.state.doc;
    if (from > doc.length) return;
    const now = doc.lineAt(from);
    if (now.from !== from || now.text !== text) return;     // the author kept typing: drop the answer
    view.dispatch({ changes: { from: now.from, to: now.to, insert: next }, selection: { anchor: now.from + next.length } });
  });
  return true;
}

/** Completion for script scenes: places after INT./EXT., characters for capitals at the start of a block. */
function scriptCompletions(hooks: Hooks) {
  return (ctx: CompletionContext): CompletionResult | null => {
    const doc = ctx.state.doc;
    const line = doc.lineAt(ctx.pos);
    const before = line.text.slice(0, ctx.pos - line.from);
    const prevBlank = line.number === 1 || doc.line(line.number - 1).text.trim() === "";
    const spot = completionSpot(before, prevBlank);
    const names = hooks.getNames?.();
    if (!spot || !names) return null;
    const list = upperNames(spot.kind === "place" ? names.places : names.characters);
    if (!list.length) return null;
    return { from: line.from + spot.from, options: list.map((label) => ({ label, type: "text" })), validFor: /^[A-Za-z .'-]*$/ };
  };
}

/** Completion after "[[@" or "[[+@": sources from Zotero (search_sources). Inserts the key and the closing brackets; never on its own. */
function citeCompletions(hooks: Hooks) {
  return async (ctx: CompletionContext): Promise<CompletionResult | null> => {
    const m = ctx.matchBefore(/\[\[\+?@[^\][;,\s]*/);
    if (!m || !hooks.searchSources) return null;
    const from = m.from + m.text.indexOf("@") + 1;
    const found = await hooks.searchSources(ctx.state.sliceDoc(from, ctx.pos));
    if (ctx.aborted || !found.length) return null;
    return {
      from, filter: false,
      options: found.map((s) => ({
        label: s.key, detail: s.display, info: s.title || undefined, type: "text",
        apply: (view: EditorView, _c: unknown, a: number, b: number) => {
          const { insert, cursor } = citeCompletion(view.state.sliceDoc(b, b + 2), s.key);
          view.dispatch({ changes: { from: a, to: b, insert }, selection: { anchor: a + cursor }, userEvent: "input.complete" });
        },
      })),
    };
  };
}

export function editorExtensions(kind: string, meta: string, reflow: boolean, hooks: Hooks, undoDepth: (s: EditorState) => number, redoDepth: (s: EditorState) => number, script = false, entityType = ""): Extension[] {
  const screenplay = script && kind === "scene";
  return [
    kindFacet.of(kind),
    entityTypeFacet.of(entityType),
    scriptFacet.of(screenplay),
    ...(screenplay ? [EditorView.editorAttributes.of({ class: "lw-script" })] : []),
    draftFacet.of((i, a) => hooks.onResolveDraft(i, a)),
    metaCompartment.of(metaFacet.of(meta)),
    reflowCompartment.of(reflowFacet.of(reflow)),
    history(),
    drawSelection(),
    ...(kind === "dictionary" ? [] : [markdown()]),
    ...(screenplay ? [autocompletion({ override: [scriptCompletions(hooks)], icons: false })] : []),
    ...(!screenplay && hooks.searchSources && kind !== "dictionary" ? [autocompletion({ override: [citeCompletions(hooks)], icons: false })] : []),
    EditorView.lineWrapping,
    spansField,
    spellingField,
    commentsField,
    readingField,
    objectDataField,
    decoField,
    sourceGuard,
    openObjectFacet.of((key) => hooks.onOpenObject?.(key)),
    ...(hooks.renderObjects ? [objectFetcher(hooks.renderObjects, (s) => s.field(spansField), hooks.fetchObjectImage)] : []),
    keymap.of([
      ...(screenplay ? [
        { key: "Tab", run: (view: EditorView) => cycleLine(view, hooks, false), preventDefault: true },
        { key: "Shift-Tab", run: (view: EditorView) => cycleLine(view, hooks, true), preventDefault: true },
      ] : []),
      { key: "Mod-s", run: () => { hooks.onSaveNow(); return true; }, preventDefault: true },
      { key: "Mod-.", run: (view) => {
        const t = spellTargetAt(view, null);
        if (t) hooks.onSpell?.(t);
        return !!t;
      } },
      ...(hooks.extraKeys ?? []).map((k) => ({ key: k.key, run: () => k.run() })),
      ...defaultKeymap, ...historyKeymap,
    ]),
    // Chisel checks spelling itself (core.spelling), so the browser must not
    EditorView.contentAttributes.of({ spellcheck: "false", autocorrect: "off" }),
    EditorView.updateListener.of((u) => {
      if (u.docChanged) hooks.onChange(u.state.doc.toString());
      if (u.docChanged || u.selectionSet || u.transactions.length) {
        const sel = u.state.selection.main;
        const line = u.state.doc.lineAt(sel.head);
        hooks.onCursor({
          line: line.number, col: sel.head - line.from + 1, head: sel.head, from: sel.from, to: sel.to,
          canUndo: undoDepth(u.state) > 0, canRedo: redoDepth(u.state) > 0,
        });
      }
    }),
    tooltips({ parent: document.body }),
    hoverTooltip(async (view, pos) => {
      const span = spanAt(view.state, pos);
      if (!span) return null;
      const card = await hooks.getCard(span);
      if (!card) return null;
      return {
        pos: span.start, end: span.end, above: true,
        create() {
          const dom = document.createElement("div");
          dom.className = "lw-hovercard";
          const head = document.createElement("div");
          head.className = "lw-hovercard__head";
          const title = document.createElement("strong");
          title.textContent = card.title;
          const kind = document.createElement("span");
          kind.textContent = card.kind;
          head.append(title, kind);
          const body = document.createElement("p");
          body.textContent = card.body;
          dom.append(head, body);
          if (span.kind === "citation") {
            const hint = document.createElement("p");
            hint.className = "lw-hovercard__hint";
            hint.textContent = "Shown in an approximate APA form; click it to see and edit the raw [[@key]].";
            dom.append(hint);
          }
          return { dom };
        },
      };
    }, { hoverTime: 350 }),
    // typing sounds: editor keydown only, ahead of the keymaps (Enter and Backspace are handled
    // there); it never handles the event, so it can never swallow a key
    Prec.highest(EditorView.domEventHandlers({ keydown: (e) => { typingKeydown(e); return false; } })),
    EditorView.domEventHandlers({
      blur: () => { hooks.onBlur(); return false; },
      contextmenu: (e, view) => {
        const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
        const sel = view.state.selection.main;
        const inSelection = !sel.empty && pos !== null && pos >= sel.from && pos <= sel.to;
        // a misspelled word (also when it is the selection): the spelling suggestions
        const t = pos === null ? null : spellTargetAt(view, pos);
        if (t && t.kind === "word" && hooks.onSpell) {
          e.preventDefault();
          hooks.onSpell(t);
          return true;
        }
        if (!hooks.onContextMenu) return false;
        e.preventDefault();
        // as in most editors, the caret goes where you right-click (unless that is inside the selection)
        if (!inSelection && pos !== null) view.dispatch({ selection: { anchor: pos } });
        const range = pos === null || inSelection ? null : view.state.wordAt(pos);
        hooks.onContextMenu({
          x: e.clientX, y: e.clientY,
          span: pos === null ? undefined : spanAt(view.state, pos),
          word: range ? view.state.sliceDoc(range.from, range.to) : undefined,
          selection: inSelection ? view.state.sliceDoc(sel.from, sel.to) : undefined,
        });
        return true;
      },
      click: (e, view) => {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.detail > 1 || !view.state.selection.main.empty) return false;
        const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
        const hit = pos === null ? undefined : misspellingAt(view.state.field(spellingField), pos);
        // a click inside the word, not on the blank space after the line's last word
        if (!hit || pos === null || pos === hit.end) return false;
        const t = spellTargetAt(view, pos);
        if (t && hooks.onSpell) hooks.onSpell(t);
        return false; // the cursor still moves into the word
      },
      mousedown: (e, view) => {
        if (!(e.ctrlKey || e.metaKey)) return false;
        const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
        const ref = pos === null ? undefined : view.state.field(spansField).find((s) => s.kind === "objref" && s.key && pos >= s.start && pos <= s.end);
        if (ref?.key && hooks.onOpenObject) {
          e.preventDefault();
          hooks.onOpenObject(ref.key);
          return true;
        }
        const span = pos === null ? undefined : spanAt(view.state, pos);
        if (!span) return false;
        e.preventDefault();
        hooks.onOpenEntity(span);
        return true;
      },
    }),
  ];
}

export { spansField, spellingField };
