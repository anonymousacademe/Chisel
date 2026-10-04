import { useState } from "react";
import type { RefObject } from "react";
import { api } from "../backend/api";
import type { CollectionColor, DocumentPayload } from "../data/types";
import type { SaveController } from "../editor/saveController";
import type { Notice } from "../components/Toast";

interface Deps {
  saver: SaveController;
  docRef: RefObject<DocumentPayload | null>;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  refresh: () => Promise<unknown>;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
}

/** Collections: the board filter and the create / recolor / rename / delete calls. */
export function useCollectionOps({ saver, docRef, notify, refresh, openDoc }: Deps) {
  const [collection, setCollection] = useState<string | null>(null);

  /** Rename and delete rewrite the member scenes on disk: flush the open one first, reopen it after. */
  const collectionsCall = async (run: () => Promise<{ ok: true; changed?: string[] } | { ok: false; error: string }>): Promise<boolean> => {
    if (!(await saver.flush())) { notify("Could not save the current document first.", "error"); return false; }
    const r = await run();
    if (!r.ok) { notify(r.error, "error"); return false; }
    await refresh();
    const d = docRef.current;
    if (d && r.changed?.includes(d.id)) await openDoc(d.id, { force: true, keepMode: true });
    return true;
  };
  const createCollection = (name: string, color: CollectionColor) => collectionsCall(() => api.createCollection(name, color));
  const recolorCollection = (name: string, color: CollectionColor) => collectionsCall(() => api.recolorCollection(name, color));
  const renameCollection = async (name: string, to: string) => {
    const ok = await collectionsCall(() => api.renameCollection(name, to));
    if (ok && collection === name) setCollection(to);
    return ok;
  };
  const deleteCollection = async (name: string) => {
    const ok = await collectionsCall(() => api.deleteCollection(name));
    if (ok && collection === name) setCollection(null);
    return ok;
  };

  return { collection, setCollection, createCollection, recolorCollection, renameCollection, deleteCollection };
}
