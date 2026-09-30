import type { EditorView } from "@codemirror/view";

/**
 * Toggle a Markdown wrapper (`**` bold, `*` italic) around the selection.
 * Already wrapped -> unwrap; empty selection -> insert the pair, cursor between.
 */
export function toggleWrap(view: EditorView, mark: string) {
  const { state } = view;
  const sel = state.selection.main;
  const n = mark.length;
  const before = state.sliceDoc(Math.max(0, sel.from - n), sel.from);
  const after = state.sliceDoc(sel.to, Math.min(state.doc.length, sel.to + n));
  if (sel.empty) {
    view.dispatch({ changes: { from: sel.from, insert: mark + mark }, selection: { anchor: sel.from + n } });
  } else if (before === mark && after === mark && !(mark === "*" && isBoldWrap(state.sliceDoc(sel.from - 2, sel.to + 2)))) {
    view.dispatch({
      changes: [{ from: sel.from - n, to: sel.from }, { from: sel.to, to: sel.to + n }],
      selection: { anchor: sel.from - n, head: sel.to - n },
    });
  } else {
    view.dispatch({
      changes: [{ from: sel.from, insert: mark }, { from: sel.to, insert: mark }],
      selection: { anchor: sel.from + n, head: sel.to + n },
    });
  }
  view.focus();
}

// `**x**` around the selection must not be mistaken for italic `*x*` wrappers.
const isBoldWrap = (s: string) => s.startsWith("**") && s.endsWith("**");

/** Replace [from,to) with *insert* as one undoable step, cursor at the end of the new text. */
export function replaceRange(view: EditorView, from: number, to: number, insert: string) {
  view.dispatch({ changes: { from, to, insert }, selection: { anchor: from + insert.length }, scrollIntoView: true });
  view.focus(); // dialogs steal focus; F7/F8 and typing must land in the editor afterwards
}
