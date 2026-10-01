// CodeMirror 6 setup for a LoreWriter document: plain Markdown on disk, drawn
// with the design's prose styling. Live preview: [[link]] brackets and the
// <!--ai--> markers are hidden, mentions are coloured, pending drafts tinted.
import { Compartment, EditorState, Facet, StateEffect, StateField, type Extension, type Range } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, WidgetType, drawSelection, hoverTooltip, keymap, tooltips } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { ensureSyntaxTree } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { frontmatterRange, misspellingAt, misspellSpecs, softBreaks, specsFor, titleLine, type Misspelling, type Span } from "./spans";

export const setSpans = StateEffect.define<Span[]>();
export const setSpelling = StateEffect.define<Misspelling[]>();
/** Holds metaFacet so the mentions line can change without rebuilding the editor. */
export const metaCompartment = new Compartment();
/** Show hard-wrapped source lines as flowing paragraphs (display only). */
export const reflowFacet = Facet.define<boolean, boolean>({ combine: (v) => (v.length ? v[v.length - 1] : true) });
export const reflowCompartment = new Compartment();

/** What the title block needs that only the host knows (mentions line). */
export const metaFacet = Facet.define<string, string>({ combine: (v) => v[v.length - 1] ?? "" });
/** "scene" | "entity" | "style": entity notes show their frontmatter as a mono block. */
export const kindFacet = Facet.define<string, string>({ combine: (v) => v[v.length - 1] ?? "scene" });

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

interface Built { all: DecorationSet; atomic: DecorationSet }

const HEADING = /^ATXHeading(\d)$/;

function build(state: EditorState): Built {
  const doc = state.doc;
  const text = doc.toString();
  const kind = state.facet(kindFacet);
  const ranges: Range<Decoration>[] = [];
  const atomic: Range<Decoration>[] = [];
  const hide = Decoration.replace({});
  const head = state.selection.main.head;

  // span decorations (mentions, links, drafts, expand markers)
  for (const sp of specsFor(state.field(spansField), head, doc.length)) {
    if (sp.from === sp.to) continue;
    if (sp.type === "hide") { ranges.push(hide.range(sp.from, sp.to)); atomic.push(hide.range(sp.from, sp.to)); }
    else ranges.push(Decoration.mark({ class: sp.cls, attributes: sp.attrs }).range(sp.from, sp.to));
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
  const title = kind !== "entity" && !plain ? titleLine(text) : null;
  if (title) {
    const line = doc.lineAt(title.from);
    ranges.push(Decoration.line({ class: "lw-title-line" }).range(line.from));
    ranges.push(hide.range(title.from, title.from + title.prefix));
    atomic.push(hide.range(title.from, title.from + title.prefix));
    // always present: it also carries the violet rule under the title
    ranges.push(Decoration.widget({ widget: new MetaWidget(state.facet(metaFacet)), block: true, side: 1 }).range(line.to));
  }

  // YAML frontmatter of entity notes: a muted mono block
  const fm = kind === "entity" ? frontmatterRange(text) : null;
  if (fm) {
    const last = doc.lineAt(Math.max(fm.to - 1, 0)).number;
    for (let n = 1; n <= last; n++) ranges.push(Decoration.line({ class: "lw-frontmatter" }).range(doc.line(n).from));
  }

  // hard-wrapped source lines flow as one paragraph (display only)
  for (const pos of state.facet(reflowFacet) && !plain ? softBreaks(text, fm) : []) {
    ranges.push(SPACE.range(pos, pos + 1));
    atomic.push(SPACE.range(pos, pos + 1));
  }

  // blank lines are paragraph gaps, not full lines
  for (let n = 1; n <= doc.lines; n++) {
    const line = doc.line(n);
    if (line.length === 0) ranges.push(Decoration.line({ class: "lw-blank" }).range(line.from));
  }

  // Markdown structure: headings, emphasis, quotes, inline code
  const tree = ensureSyntaxTree(state, doc.length, 40);
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
        } else if (node.name === "EmphasisMark" || node.name === "HeaderMark" || node.name === "QuoteMark" || node.name === "CodeMark") {
          if (!(title && node.from === title.from)) ranges.push(Decoration.mark({ class: "lw-syn" }).range(node.from, node.to));
        }
      },
    });
  }

  return { all: Decoration.set(ranges, true), atomic: Decoration.set(atomic, true) };
}

const decoField = StateField.define<Built>({
  create: (state) => build(state),
  update(value, tr) {
    const facetChanged = tr.startState.facet(metaFacet) !== tr.state.facet(metaFacet)
      || tr.startState.facet(reflowFacet) !== tr.state.facet(reflowFacet);
    if (tr.docChanged || tr.selection || facetChanged || tr.effects.some((e) => e.is(setSpans) || e.is(setSpelling))) return build(tr.state);
    return value;
  },
  provide: (f) => [
    EditorView.decorations.from(f, (v) => v.all),
    EditorView.atomicRanges.of((view) => view.state.field(f).atomic),
  ],
});

export interface CursorInfo {
  line: number; col: number; head: number; from: number; to: number;
  canUndo: boolean; canRedo: boolean;
}

/** A hover card for a mention or link: what the host knows about the target. */
export interface Card { title: string; kind: string; body: string; missing?: boolean }

const isTarget = (s: Span) => s.kind === "mention" || s.kind === "link" || s.kind === "unresolved";
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

export interface Hooks {
  /** Open the spelling popover (click on a misspelled word, right-click, Ctrl+.). */
  onSpell?(target: SpellTarget): void;
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
}

export function editorExtensions(kind: string, meta: string, reflow: boolean, hooks: Hooks, undoDepth: (s: EditorState) => number, redoDepth: (s: EditorState) => number): Extension[] {
  return [
    kindFacet.of(kind),
    draftFacet.of((i, a) => hooks.onResolveDraft(i, a)),
    metaCompartment.of(metaFacet.of(meta)),
    reflowCompartment.of(reflowFacet.of(reflow)),
    history(),
    drawSelection(),
    ...(kind === "dictionary" ? [] : [markdown()]),
    EditorView.lineWrapping,
    spansField,
    spellingField,
    decoField,
    keymap.of([
      { key: "Mod-s", run: () => { hooks.onSaveNow(); return true; }, preventDefault: true },
      { key: "Mod-.", run: (view) => {
        const t = spellTargetAt(view, null);
        if (t) hooks.onSpell?.(t);
        return !!t;
      } },
      ...(hooks.extraKeys ?? []).map((k) => ({ key: k.key, run: () => k.run() })),
      ...defaultKeymap, ...historyKeymap,
    ]),
    // LoreWriter checks spelling itself (core.spelling), so the browser must not
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
          return { dom };
        },
      };
    }, { hoverTime: 350 }),
    EditorView.domEventHandlers({
      blur: () => { hooks.onBlur(); return false; },
      contextmenu: (e, view) => {
        const pos = view.posAtCoords({ x: e.clientX, y: e.clientY });
        const t = pos === null ? null : spellTargetAt(view, pos);
        if (!t || !hooks.onSpell) return false;
        e.preventDefault();
        hooks.onSpell(t);
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
