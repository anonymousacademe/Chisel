import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { redo, redoDepth, undo, undoDepth } from "@codemirror/commands";
import { api } from "../backend/api";
import { setComments, metaCompartment, metaFacet, reflowCompartment, reflowFacet, setSpans, setSpelling, spansField, spellingField, editorExtensions, type Card, type CursorInfo, type SpellTarget } from "../editor/cm";
import { replaceRange, toggleWrap } from "../editor/commands";
import { nextMisspelling, type Span } from "../editor/spans";
import type { CommentRow } from "../data/types";

export interface EditorHandle {
  undo(): void; redo(): void; bold(): void; italic(): void; focus(): void;
  /** Focus with the cursor at the end of the text (a fresh scene). */
  focusEnd(): void;
  getText(): string;
  selection(): { from: number; to: number; text: string };
  replace(from: number, to: number, insert: string): void;
  /** Move the cursor to the start of a 0-based line and scroll it into view. */
  gotoLine(row: number): void;
  spans(): Span[];
  /** Apply several edits (original coordinates, non-overlapping) as one undoable step. */
  applyEdits(edits: { from: number; to: number; insert: string }[]): void;
  /** Put generated text in place of [from, to) and leave the cursor after it. */
  insertDraft(from: number, to: number, insert: string): void;
  head(): number;
  /** Viewport point just under the cursor (for the drafting panel), or null. */
  cursorPoint(): { x: number; y: number } | null;
  /** Index (document order) of the pending draft containing the cursor, or -1. */
  pendingIndexAtCursor(): number;
  /** Span of a link/mention/unresolved link containing the cursor. */
  spanAtCursor(): Span | undefined;
  /** Move to the next misspelled word after the cursor (wrapping) and select it; false if there is none. */
  gotoNextMisspelling(): boolean;
  /** Select [from, to), scroll it into view and return the viewport point under its first line (for a popover). */
  selectRange(from: number, to: number): { x: number; y: number } | null;
  /** Refetch the comments now (after adding, resolving or deleting one). */
  reloadComments(): void;
}

interface Props {
  docId: string;
  kind: string;
  initialText: string;
  meta: string;
  reflow: boolean;
  /** Bump to refetch spans (entity notes or aliases changed). */
  spansVersion: number;
  onChange(text: string): void;
  onCursor(info: CursorInfo): void;
  onBlur(): void;
  onSaveNow(): void;
  getCard(span: Span): Promise<Card | null>;
  onOpenEntity(span: Span): void;
  onResolveDraft(index: number, accept: boolean): void;
  /** Bump to recheck spelling (dictionary, ignore or the setting changed). */
  spellVersion: number;
  /** Misspelling count of the document, or null when spell check does not apply. */
  onSpellCount(count: number | null): void;
  onSpell(target: SpellTarget): void;
  onSelectionMenu?(x: number, y: number): void;
  /** Comments with positions, refetched after edits (scenes only; null otherwise). */
  onComments(rows: CommentRow[] | null): void;
  extraKeys?: { key: string; run: () => boolean }[];
}

const SPAN_DEBOUNCE_MS = 150;
const SPELL_DEBOUNCE_MS = 600;

/** CodeMirror host. Remounted (via `key`) whenever a different text is loaded. */
export const EditorPane = forwardRef<EditorHandle, Props>(function EditorPane(props, ref) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const hooks = useRef(props);
  useEffect(() => { hooks.current = props; });

  useImperativeHandle(ref, () => ({
    undo: () => { if (view.current) { undo(view.current); view.current.focus(); } },
    redo: () => { if (view.current) { redo(view.current); view.current.focus(); } },
    bold: () => view.current && toggleWrap(view.current, "**"),
    italic: () => view.current && toggleWrap(view.current, "*"),
    focus: () => view.current?.focus(),
    focusEnd: () => {
      const v = view.current;
      if (!v) return;
      v.dispatch({ selection: { anchor: v.state.doc.length }, scrollIntoView: true });
      v.focus();
    },
    getText: () => view.current?.state.doc.toString() ?? "",
    selection: () => {
      const s = view.current!.state;
      const { from, to } = s.selection.main;
      return { from, to, text: s.sliceDoc(from, to) };
    },
    replace: (from, to, insert) => view.current && replaceRange(view.current, from, to, insert),
    gotoLine: (row) => {
      const v = view.current;
      if (!v) return;
      const line = v.state.doc.line(Math.min(Math.max(row + 1, 1), v.state.doc.lines));
      v.dispatch({ selection: { anchor: line.from }, effects: EditorView.scrollIntoView(line.from, { y: "center" }) });
      v.focus();
    },
    spans: () => view.current?.state.field(spansField) ?? [],
    applyEdits: (edits) => {
      const v = view.current;
      if (v && edits.length) { v.dispatch({ changes: edits, scrollIntoView: true }); v.focus(); }
    },
    insertDraft: (from, to, insert) => view.current && replaceRange(view.current, from, to, insert),
    head: () => view.current?.state.selection.main.head ?? 0,
    cursorPoint: () => {
      const v = view.current;
      const c = v?.coordsAtPos(v.state.selection.main.head);
      return c ? { x: c.left, y: c.bottom } : null;
    },
    pendingIndexAtCursor: () => {
      const v = view.current;
      if (!v) return -1;
      const head = v.state.selection.main.head;
      return v.state.field(spansField).filter((s) => s.kind === "pending").findIndex((s) => head >= s.start && head <= s.end);
    },
    spanAtCursor: () => {
      const v = view.current;
      if (!v) return undefined;
      const head = v.state.selection.main.head;
      return v.state.field(spansField).find((s) => (s.kind === "mention" || s.kind === "link" || s.kind === "unresolved") && head >= s.start && head <= s.end);
    },
    gotoNextMisspelling: () => {
      const v = view.current;
      if (!v) return false;
      const m = nextMisspelling(v.state.field(spellingField), v.state.selection.main.head);
      if (!m) return false;
      v.dispatch({ selection: { anchor: m.start, head: m.end }, effects: EditorView.scrollIntoView(m.start, { y: "center" }) });
      v.focus();
      return true;
    },
    selectRange: (from, to) => {
      const v = view.current;
      if (!v) return null;
      v.dispatch({ selection: { anchor: from, head: to }, effects: EditorView.scrollIntoView(from, { y: "center" }) });
      v.focus();
      const c = v.coordsAtPos(from);
      return c ? { x: c.left, y: c.bottom } : null;
    },
    reloadComments: () => fetchComments(),
  }), []);

  // Spelling is checked in Python, off the typing path (debounced, stale answers dropped).
  const spellTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const spellSeq = useRef(0);
  const fetchSpelling = () => {
    const v = view.current;
    if (!v) return;
    const text = v.state.doc.toString();
    const seq = ++spellSeq.current;
    api.spelling(hooks.current.docId, text).then((r) => {
      if (seq !== spellSeq.current || !view.current) return;
      if (!r.ok || !r.enabled) {
        view.current.dispatch({ effects: setSpelling.of([]) });
        hooks.current.onSpellCount(null);
        return;
      }
      if (view.current.state.doc.toString() !== text) return; // a newer request follows
      view.current.dispatch({ effects: setSpelling.of(r.spans) });
      hooks.current.onSpellCount(r.spans.length);
    });
  };
  // Comments are positioned in Python against the editor's text (debounced, stale answers dropped).
  const commentTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const commentSeq = useRef(0);
  const fetchComments = () => {
    const v = view.current;
    if (!v || hooks.current.kind !== "scene") return;
    const text = v.state.doc.toString();
    const seq = ++commentSeq.current;
    api.listComments(hooks.current.docId, text).then((r) => {
      if (seq !== commentSeq.current || !view.current || !r.ok) return;
      if (view.current.state.doc.toString() !== text) return; // a newer request follows
      view.current.dispatch({ effects: setComments.of(r.comments.filter((c) => !c.resolved && c.start !== null && c.end !== null)
        .map((c) => ({ id: c.id, start: c.start!, end: c.end! }))) });
      hooks.current.onComments(r.comments);
    });
  };
  const cancelComments = () => { clearTimeout(commentTimer.current); commentSeq.current++; };
  const scheduleComments = () => { clearTimeout(commentTimer.current); commentTimer.current = setTimeout(fetchComments, 500); };
  const cancelSpelling = () => { clearTimeout(spellTimer.current); spellSeq.current++; };
  const scheduleSpelling = () => { clearTimeout(spellTimer.current); spellTimer.current = setTimeout(fetchSpelling, SPELL_DEBOUNCE_MS); };

  // Create the editor once per mounted document.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    const fetchSpans = () => {
      const v = view.current;
      if (!v) return;
      const text = v.state.doc.toString();
      api.linkSpans(hooks.current.docId, text).then((r) => {
        // drop answers for text that has since changed: a newer request follows
        if (disposed || !r.ok || !view.current || view.current.state.doc.toString() !== text) return;
        view.current.dispatch({ effects: setSpans.of(r.spans) });
      });
    };
    const schedule = () => { clearTimeout(timer); timer = setTimeout(fetchSpans, SPAN_DEBOUNCE_MS); };
    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: hooks.current.initialText,
        extensions: editorExtensions(hooks.current.kind, hooks.current.meta, hooks.current.reflow, {
          onChange: (t) => { hooks.current.onChange(t); schedule(); scheduleSpelling(); scheduleComments(); },
          onSpell: (t) => hooks.current.onSpell(t),
          onSelectionMenu: (x, y) => hooks.current.onSelectionMenu?.(x, y),
          onCursor: (c) => hooks.current.onCursor(c),
          onBlur: () => hooks.current.onBlur(),
          onSaveNow: () => hooks.current.onSaveNow(),
          getCard: (sp) => hooks.current.getCard(sp),
          onOpenEntity: (sp) => hooks.current.onOpenEntity(sp),
          onResolveDraft: (i, a) => hooks.current.onResolveDraft(i, a),
          // keys are fixed at mount; their handlers always come from the latest render
          extraKeys: hooks.current.extraKeys?.map((k) => ({
            key: k.key, run: () => hooks.current.extraKeys?.find((x) => x.key === k.key)?.run() ?? false,
          })),
        }, undoDepth, redoDepth),
      }),
    });
    view.current = v;
    fetchSpans();
    fetchSpelling();
    fetchComments();
    return () => {
      disposed = true; clearTimeout(timer); cancelSpelling(); cancelComments();
      hooks.current.onSpellCount(null);
      hooks.current.onComments(null);
      v.destroy(); view.current = null;
    };
  }, []);

  // The mentions line under the title can change without rebuilding the editor.
  useEffect(() => {
    view.current?.dispatch({ effects: metaCompartment.reconfigure(metaFacet.of(props.meta)) });
  }, [props.meta]);

  useEffect(() => {
    view.current?.dispatch({ effects: reflowCompartment.reconfigure(reflowFacet.of(props.reflow)) });
  }, [props.reflow]);

  // Dictionary / ignore / setting changed.
  useEffect(() => {
    if (props.spellVersion !== 0) fetchSpelling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.spellVersion]);

  // Entities changed: spans depend on them.
  useEffect(() => {
    const v = view.current;
    if (!v || props.spansVersion === 0) return;
    scheduleSpelling(); // entity names and aliases are accepted words
    const text = v.state.doc.toString();
    api.linkSpans(hooks.current.docId, text).then((r) => {
      if (r.ok && view.current && view.current.state.doc.toString() === text) view.current.dispatch({ effects: setSpans.of(r.spans) });
    });
  }, [props.spansVersion]);

  return <div className="lw-cm" ref={host} />;
});
