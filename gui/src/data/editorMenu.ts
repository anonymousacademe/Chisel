// What the editor's right-click menu offers. Pure: the host maps each action to what it does (open a document,
// open the new-note dialog, the clipboard...). Whether a name is a known note is Python's call (span.entity),
// this only lists what to show.
import type { Span } from "../editor/spans";

export interface MenuEntity { id: string; name: string; type: string }

/** What was under the pointer when the menu was asked for. */
export interface ContextTarget {
  /** A mention or [[link]] under the pointer (resolved: `entity`; unresolved: `target`). */
  span?: Span;
  /** The word under the pointer, when there is no selection and no span. */
  word?: string;
  /** The selected text, when the pointer is inside the selection. */
  selection?: string;
  /** A research project: the menu offers Cite... */
  research?: boolean;
}

export type MenuAction =
  | { id: "open-note"; label: string; entityId: string }
  | { id: "create-note"; label: string; name: string }
  | { id: "cite"; label: string }
  | { id: "selection-to-notebook"; label: string }
  | { id: "selection-to-dictionary"; label: string }
  | { id: "cut" | "copy" | "paste" | "select-all"; label: string; disabled?: boolean }
  | { id: "separator" };

const short = (s: string, n = 28) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const oneLine = (s: string) => !s.includes("\n") && s.trim().length > 0;

/** The menu for *target*: note actions first, then selection actions, then the clipboard. */
export function contextActions(target: ContextTarget, entities: MenuEntity[]): MenuAction[] {
  const notes: MenuAction[] = [];
  const { span, word, selection } = target;
  const has = !!selection && selection.length > 0;
  if (span?.kind === "citation") {
    // a citation is not a note name: no "create note" for its key
  } else if (span?.entity) {
    const e = entities.find((x) => x.name === span.entity);
    if (e) notes.push({ id: "open-note", label: `Go to note: ${short(e.name)} (${e.type})`, entityId: e.id });
  } else if (span?.target) {
    notes.push({ id: "create-note", label: `Create note “${short(span.target)}”…`, name: span.target });
  } else if (has && oneLine(selection!)) {
    notes.push({ id: "create-note", label: `Create note from “${short(selection!.trim())}”…`, name: selection!.trim() });
  } else if (!has && word && word.length >= 2 && /\p{L}/u.test(word)) {
    notes.push({ id: "create-note", label: `Create note from “${short(word)}”…`, name: word });
  }
  if (target.research) notes.push({ id: "cite", label: "Cite…" });
  const selected: MenuAction[] = has
    ? [{ id: "selection-to-notebook", label: "Send selection to notebook" },
       { id: "selection-to-dictionary", label: "Add selection to dictionary" }]
    : [];
  const clipboard: MenuAction[] = [
    { id: "cut", label: "Cut", disabled: !has },
    { id: "copy", label: "Copy", disabled: !has },
    { id: "paste", label: "Paste" },
    { id: "select-all", label: "Select all" },
  ];
  const groups = [notes, selected, clipboard].filter((g) => g.length > 0);
  const out: MenuAction[] = [];
  groups.forEach((g, i) => { if (i > 0) out.push({ id: "separator" }); out.push(...g); });
  return out;
}
