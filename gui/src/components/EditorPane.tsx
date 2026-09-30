import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { redo, redoDepth, undo, undoDepth } from "@codemirror/commands";
import { api } from "../backend/api";
import { metaCompartment, metaFacet, setSpans, spansField, editorExtensions, type Card, type CursorInfo } from "../editor/cm";
import { replaceRange, toggleWrap } from "../editor/commands";
import type { Span } from "../editor/spans";

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
  /** Index (document order) of the pending draft containing the cursor, or -1. */
  pendingIndexAtCursor(): number;
  /** Span of a link/mention/unresolved link containing the cursor. */
  spanAtCursor(): Span | undefined;
}

interface Props {
  docId: string;
  kind: string;
  initialText: string;
  meta: string;
  /** Bump to refetch spans (entity notes or aliases changed). */
  spansVersion: number;
  onChange(text: string): void;
  onCursor(info: CursorInfo): void;
  onBlur(): void;
  onSaveNow(): void;
  getCard(span: Span): Promise<Card | null>;
  onOpenEntity(span: Span): void;
  onResolveDraft(index: number, accept: boolean): void;
  extraKeys?: { key: string; run: () => boolean }[];
}

const SPAN_DEBOUNCE_MS = 150;

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
  }), []);

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
        extensions: editorExtensions(hooks.current.kind, hooks.current.meta, {
          onChange: (t) => { hooks.current.onChange(t); schedule(); },
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
    return () => { disposed = true; clearTimeout(timer); v.destroy(); view.current = null; };
  }, []);

  // The mentions line under the title can change without rebuilding the editor.
  useEffect(() => {
    view.current?.dispatch({ effects: metaCompartment.reconfigure(metaFacet.of(props.meta)) });
  }, [props.meta]);

  // Entities changed: spans depend on them.
  useEffect(() => {
    const v = view.current;
    if (!v || props.spansVersion === 0) return;
    const text = v.state.doc.toString();
    api.linkSpans(hooks.current.docId, text).then((r) => {
      if (r.ok && view.current && view.current.state.doc.toString() === text) view.current.dispatch({ effects: setSpans.of(r.spans) });
    });
  }, [props.spansVersion]);

  return <div className="lw-cm" ref={host} />;
});
