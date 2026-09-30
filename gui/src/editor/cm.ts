// CodeMirror 6 setup for a LoreWriter document: plain Markdown on disk, drawn
// with the design's prose styling. Live preview: [[link]] brackets and the
// <!--ai--> markers are hidden, mentions are coloured, pending drafts tinted.
import { Compartment, EditorState, Facet, StateEffect, StateField, type Extension, type Range } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, WidgetType, drawSelection, hoverTooltip, keymap, tooltips } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { ensureSyntaxTree } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { frontmatterRange, softBreaks, specsFor, titleLine, type Span } from "./spans";

export const setSpans = StateEffect.define<Span[]>();
/** Holds metaFacet so the mentions line can change without rebuilding the editor. */
export const metaCompartment = new Compartment();

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

  // title block: the first "# " line, styled big; its "# " prefix hidden; meta line under it
  const title = kind !== "entity" ? titleLine(text) : null;
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
  for (const pos of softBreaks(text, fm)) {
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
    const facetChanged = tr.startState.facet(metaFacet) !== tr.state.facet(metaFacet);
    if (tr.docChanged || tr.selection || facetChanged || tr.effects.some((e) => e.is(setSpans))) return build(tr.state);
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

export interface Hooks {
  /** Hover card for a span (null = none). */
  getCard(span: Span): Promise<Card | null>;
  /** ctrl/cmd+click on a mention or link. */
  onOpenEntity(span: Span): void;
  onChange(text: string): void;
  onCursor(info: CursorInfo): void;
  onBlur(): void;
  onSaveNow(): void;
  /** Extra key bindings (e.g. f7/f8) supplied by the host. */
  extraKeys?: { key: string; run: () => boolean }[];
}

export function editorExtensions(kind: string, meta: string, hooks: Hooks, undoDepth: (s: EditorState) => number, redoDepth: (s: EditorState) => number): Extension[] {
  return [
    kindFacet.of(kind),
    metaCompartment.of(metaFacet.of(meta)),
    history(),
    drawSelection(),
    markdown(),
    EditorView.lineWrapping,
    spansField,
    decoField,
    keymap.of([
      { key: "Mod-s", run: () => { hooks.onSaveNow(); return true; }, preventDefault: true },
      ...(hooks.extraKeys ?? []).map((k) => ({ key: k.key, run: () => k.run() })),
      ...defaultKeymap, ...historyKeymap,
    ]),
    EditorView.contentAttributes.of({ spellcheck: "true", autocorrect: "off" }),
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

export { spansField };
