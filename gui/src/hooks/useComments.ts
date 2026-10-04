import { useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { api } from "../backend/api";
import type { BridgeResult } from "../backend/transport";
import type { CommentRow, DocumentPayload } from "../data/types";
import type { Dialog } from "../data/dialog";
import type { EditorHandle } from "../components/EditorPane";
import type { AssistantTab } from "../components/Assistant";
import type { Notice } from "../components/Toast";

interface Deps {
  editorRef: RefObject<EditorHandle | null>;
  docRef: RefObject<DocumentPayload | null>;
  dialog: Dialog;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  setTab: (t: AssistantTab) => void;
  setAssistantOpen: (open: boolean) => void;
}

/** Notes beside the scene (.comments/): the prose is never touched. */
export function useComments({ editorRef, docRef, dialog, setDialog, notify, setTab, setAssistantOpen }: Deps) {
  const [comments, setComments] = useState<CommentRow[] | null>(null);
  const [commentPop, setCommentPop] = useState<{ id: string; x: number; y: number } | null>(null);

  const startAddComment = () => {
    const ed = editorRef.current;
    if (!ed || docRef.current?.kind !== "scene") return notify("Open a scene first.");
    const sel = ed.selection();
    if (!sel.text.trim()) return notify("Select the passage to comment on first.");
    setDialog({ kind: "add-comment", from: sel.from, to: sel.to, quote: sel.text });
  };
  const addComment = async (body: string) => {
    const d = docRef.current, ed = editorRef.current, dlg = dialog;
    setDialog(null);
    if (!d || !ed || dlg?.kind !== "add-comment") return;
    const r = await api.addComment(d.id, ed.getText(), dlg.from, dlg.to, body);
    if (!r.ok) return notify(r.error, "error");
    setComments(r.comments);
    ed.reloadComments();
    setTab("notes"); setAssistantOpen(true);
    notify("Comment added. It is kept beside the scene, not in the text.");
  };
  const commentCall = async (run: (id: string, text: string) => Promise<BridgeResult<{ comments: CommentRow[] }>>) => {
    const d = docRef.current, ed = editorRef.current;
    if (!d || !ed) return;
    const r = await run(d.id, ed.getText());
    if (!r.ok) return notify(r.error, "error");
    setComments(r.comments);
    ed.reloadComments();
  };
  const openComment = (c: CommentRow) => {
    if (c.start === null || c.end === null) { setCommentPop({ id: c.id, x: Math.max(40, window.innerWidth - 700), y: 140 }); return; }
    const at = editorRef.current?.selectRange(c.start, c.end);
    setCommentPop({ id: c.id, x: at?.x ?? 400, y: at?.y ?? 200 });
  };
  const popComment = comments?.find((c) => c.id === commentPop?.id) ?? null;

  return { comments, setComments, commentPop, setCommentPop, startAddComment, addComment, commentCall, openComment, popComment };
}
