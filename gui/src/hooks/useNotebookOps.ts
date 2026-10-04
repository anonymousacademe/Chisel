import type { Dispatch, RefObject, SetStateAction } from "react";
import { api } from "../backend/api";
import type { DocumentPayload, Workspace } from "../data/types";
import type { Dialog } from "../data/dialog";
import type { NoteTemplate } from "../data/notebook";
import { firstScene } from "../data/appLogic";
import type { SaveController } from "../editor/saveController";
import type { EditorHandle } from "../components/EditorPane";
import type { Notice } from "../components/Toast";

interface Deps {
  saver: SaveController;
  docRef: RefObject<DocumentPayload | null>;
  editorRef: RefObject<EditorHandle | null>;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  refresh: () => Promise<Workspace | null>;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
  setDoc: Dispatch<SetStateAction<DocumentPayload | null>>;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  setExpanded: Dispatch<SetStateAction<Set<string>>>;
  focusNextOpen: () => void;
}

/** Notebook notes ("research" internally): create, save a link, send a selection, move to the Trash. */
export function useNotebookOps({ saver, docRef, editorRef, notify, refresh, openDoc, setDoc, setDialog, setExpanded, focusNextOpen }: Deps) {
  // -- notebook notes ("research" internally) ----------------------------------------------------------------------
  const createResearch = async (title: string, template: NoteTemplate = "blank") => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newResearchNote(title, template);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    focusNextOpen();
    await openDoc(r.id, { force: true });
  };
  /** A pasted or dropped link becomes a note holding the link and a title; the page is never fetched. */
  const researchFromUrl = async (url: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newResearchFromUrl(url);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    await openDoc(r.id, { force: true });
    notify(`Saved the link as a notebook note: ${r.title}`);
  };
  const deleteResearch = async () => {
    setDialog(null);
    const d = docRef.current;
    if (!d || d.kind !== "research") return;
    saver.detach(); // a pending autosave must not bring the file back
    setDoc(null);
    const r = await api.deleteResearchNote(d.id);
    if (!r.ok) { notify(r.error, "error"); await openDoc(d.id, { force: true }); return; }
    const w = await refresh();
    const next = firstScene(w?.scenes);
    if (next) await openDoc(next.id, { force: true });
    notify(`Moved the notebook note “${d.title}” to the Trash.`, "info", { label: "Open Trash", run: () => setDialog({ kind: "trash" }) });
  };

  /** Copy the selected passage into notebook/clippings.md; the scene is not changed. */
  const sendSelectionToNotebook = async () => {
    const sel = editorRef.current?.selection();
    if (!sel || !sel.text.trim()) return notify("Select the passage to send first.");
    const r = await api.sendToNotebook(sel.text, docRef.current?.id ?? "");
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add("group:research"));
    notify("Sent to the notebook (clippings).", "info", { label: "Open", run: () => { void openDoc(r.id); } });
  };
  return { createResearch, researchFromUrl, deleteResearch, sendSelectionToNotebook };
}
