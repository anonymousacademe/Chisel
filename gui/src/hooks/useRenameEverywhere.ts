import { useRef } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { api } from "../backend/api";
import type { DocumentPayload, RenameDone, RenamePreview, RenameScope, RenameUndone } from "../data/types";
import type { Dialog } from "../data/dialog";
import type { SaveController } from "../editor/saveController";
import type { Notice } from "../components/Toast";

interface Deps {
  saver: SaveController;
  docRef: RefObject<DocumentPayload | null>;
  dialog: Dialog;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  refresh: () => Promise<unknown>;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
  setSpansVersion: Dispatch<SetStateAction<number>>;
  setNoteVersion: Dispatch<SetStateAction<number>>;
  setNoteName: (name: string | null) => void;
}

/**
 * Rename a note everywhere. Scenes and notes are rewritten on disk: flush the open document first,
 * reopen it (or follow the note's new file name) after.
 */
export function useRenameEverywhere({ saver, docRef, dialog, notify, refresh, openDoc, setSpansVersion, setNoteVersion, setNoteName }: Deps) {
  const renameMoved = useRef<Record<string, string>>({});   // new note id -> old, to follow it on Undo

  const renameFlush = async (): Promise<boolean> => {
    if (await saver.flush()) return true;
    notify("Could not save the current document first.", "error");
    return false;
  };
  const renamePreview = async (to: string, keepOld: boolean, aliases: Record<string, string>, scope: RenameScope[]): Promise<RenamePreview | null> => {
    if (dialog?.kind !== "rename-note" || !(await renameFlush())) return null;
    const r = await api.renamePreview(dialog.name, to, keepOld, aliases, scope);
    if (!r.ok) { notify(r.error, "error"); return null; }
    return r;
  };
  const afterRename = async (changed: string[], remap: Record<string, string>, name: string | null) => {
    await refresh();
    setSpansVersion((v) => v + 1);
    setNoteName(name); setNoteVersion((v) => v + 1);
    const d = docRef.current;
    if (d && (remap[d.id] || changed.includes(d.id))) {
      saver.detach(); // the file was rewritten: a stale buffer must not be saved over it
      await openDoc(remap[d.id] ?? d.id, { force: true, keepMode: true });
    }
  };
  const renameApply = async (plan: string, accepted: string[]): Promise<RenameDone | null> => {
    if (!(await renameFlush())) return null;
    const r = await api.renameApply(plan, accepted);
    if (!r.ok) { notify(r.error, "error"); return null; }
    renameMoved.current = Object.fromEntries(Object.entries(r.remap).map(([from, to]) => [to, from]));
    await afterRename(r.changed, r.remap, r.name);
    return r;
  };
  const renameUndo = async (undoId: string): Promise<RenameUndone | null> => {
    const r = await api.renameUndo(undoId);
    if (!r.ok) { notify(r.error, "error"); return null; }
    const entity = await api.listEntities();
    const restored = entity.ok ? entity.entities.find((e) => e.id === r.id) : undefined;
    await afterRename(r.restored, renameMoved.current, restored?.name ?? null);
    return r;
  };

  return { renamePreview, renameApply, renameUndo };
}
