import type { Dispatch, RefObject, SetStateAction } from "react";
import { api } from "../backend/api";
import type { DetailsPatch, DocumentPayload, Remap, SceneMention, Workspace } from "../data/types";
import type { Dialog } from "../data/dialog";
import { follow, type MovePlan } from "../data/reorder";
import { firstScene } from "../data/appLogic";
import type { SaveController } from "../editor/saveController";
import type { EditorHandle } from "../components/EditorPane";
import type { Notice } from "../components/Toast";

interface Deps {
  saver: SaveController;
  ws: Workspace | null | undefined;
  doc: DocumentPayload | null;
  docRef: RefObject<DocumentPayload | null>;
  editorRef: RefObject<EditorHandle | null>;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  refresh: () => Promise<Workspace | null>;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
  setDoc: Dispatch<SetStateAction<DocumentPayload | null>>;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  setExpanded: Dispatch<SetStateAction<Set<string>>>;
  setPartFocus: (id: string | null) => void;
  setMentions: (m: SceneMention[]) => void;
  focusNextOpen: () => void;
}

/** Scene, part and trash management. Every move flushes the open buffer first; deleting detaches the saver first. */
export function useSceneOps(d: Deps) {
  const { saver, ws, doc, docRef, editorRef, notify, refresh, openDoc, setDoc, setDialog, setExpanded, setPartFocus, setMentions, focusNextOpen } = d;
  // -- scene, part and trash management -------------------------------------------
  /** Open the document the user was in, at its (possibly renamed) id. */
  const reopen = async (id: string, remap?: Remap) => { await openDoc(follow(id, remap), { force: true, keepMode: true }); };
  const createScene = async (title: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.newScene(title, null, doc && doc.kind === "scene" ? doc.id : null);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    focusNextOpen();
    await openDoc(r.id, { force: true });
  };
  const renameScene = async (title: string) => {
    setDialog(null);
    if (!doc || !(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.renameScene(doc.id, title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    await openDoc(doc.id, { force: true });
  };
  const moveScene = async (delta: number) => {
    if (!doc || !(await saver.flush())) return;
    const r = await api.moveScene(doc.id, delta);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    await openDoc(r.id, { force: true });
  };
  /** Move a scene to a part / the top level / Unplaced; keeps the open document open. */
  const placeScene = async (id: string, partId: string | null, index: number | null, unplaced: boolean) => {
    if (!(await saver.flush())) { notify("Could not save the current document first.", "error"); return null; }
    const r = await api.placeScene(id, partId, index, unplaced);
    if (!r.ok) { notify(r.error, "error"); return null; }
    await refresh();
    setExpanded((s) => (partId ? new Set(s).add(partId) : s));
    if (docRef.current) await reopen(docRef.current.id, r.remap);
    return r;
  };
  /** The confirmed drag-and-drop: move, then offer to move it back. */
  const performMove = async (plan: MovePlan) => {
    setDialog(null);
    const title = ws?.scenes.find((s) => s.id === plan.sceneId)?.title ?? "scene";
    const r = await placeScene(plan.sceneId, plan.partId, plan.index, plan.unplaced);
    if (!r) return;
    notify(`Moved “${title}”.`, "info", {
      label: "Undo",
      run: () => { void placeScene(r.id, plan.from.partId, plan.from.index, plan.from.unplaced).then((u) => u && notify("Moved back.")); },
    });
  };
  const deleteScene = async () => {
    setDialog(null);
    if (!doc) return;
    const id = doc.id, title = doc.title;
    saver.detach(); // before anything else: a pending autosave must not resurrect the file
    setDoc(null);
    const r = await api.deleteScene(id);
    if (!r.ok) { notify(r.error, "error"); await openDoc(id, { force: true }); return; }
    const w = await refresh();
    const next = firstScene(w?.scenes);
    if (next) await openDoc(next.id, { force: true });
    notify(`Moved “${title}” to the Trash.`);
  };
  const createPart = async (title: string) => {
    setDialog(null);
    const r = await api.newPart(title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setExpanded((s) => new Set(s).add(r.id));
    setPartFocus(r.id);
  };
  const renamePart = async (id: string, title: string) => {
    setDialog(null);
    const r = await api.renamePart(id, title);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
  };
  const movePart = async (id: string, delta: number) => {
    if (!(await saver.flush())) return notify("Could not save the current document first.", "error");
    const r = await api.movePart(id, delta);
    if (!r.ok) return notify(r.error, "error");
    await refresh();
    setPartFocus(r.id);
    setExpanded((s) => new Set(s).add(r.id));
    if (docRef.current) await reopen(docRef.current.id, r.remap);
  };
  const deletePart = async (id: string) => {
    setDialog(null);
    const r = await api.deletePart(id);
    if (!r.ok) return notify(r.error, "error");
    setPartFocus(null);
    await refresh();
  };
  const saveDetails = async (patch: DetailsPatch) => {
    setDialog(null);
    const d = docRef.current, ed = editorRef.current;
    if (!d || d.kind !== "scene" || !ed) return;
    const text = ed.getText();
    const r = await api.setSceneDetails(d.id, text, patch);
    if (!r.ok) return notify(r.error, "error");
    if (ed.getText() !== text) return notify("The text changed while saving the details; try again.", "error");
    ed.applyEdits([r.edit]);  // an ordinary edit: undoable, and autosave writes it
    setDoc((cur) => (cur && cur.id === d.id
      ? { ...cur, details: r.details, bodyStart: r.bodyStart, text: r.edit.insert + text.slice(r.edit.to) } : cur));
    void refresh();
    const c = await api.sceneContext(d.id, ed.getText());
    if (c.ok && docRef.current?.id === d.id) setMentions(c.mentions);
  };
  return { createScene, renameScene, moveScene, placeScene, performMove, deleteScene, createPart, renamePart, movePart, deletePart, saveDetails };
}
