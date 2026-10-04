import type { Dispatch, SetStateAction } from "react";
import { api } from "../backend/api";
import type { SyncInfo } from "../data/types";
import type { Dialog } from "../data/dialog";
import type { SaveController } from "../editor/saveController";
import type { Notice } from "../components/Toast";

interface Deps {
  saver: SaveController;
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  setDialog: Dispatch<SetStateAction<Dialog>>;
  setSync: (s: SyncInfo | null) => void;
  refreshSync: (now?: boolean) => void;
}

/** Git sync actions: each runs only because the author confirmed it in a dialog. Push is never forced. */
export function useSyncActions({ saver, notify, setDialog, setSync, refreshSync }: Deps) {
  const syncDone = (r: { sync: SyncInfo | null }, text: string) => { setSync(r.sync); notify(text); };
  const syncCommit = async (message: string) => {
    setDialog(null);
    if (!(await saver.flush())) return notify("Could not save the current document first; nothing was committed.", "error");
    const r = await api.syncCommit(message);
    if (!r.ok) { notify(r.error, "error"); return refreshSync(true); }
    syncDone(r, `Committed: ${r.summary}`);
  };
  const syncPush = async () => {
    setDialog(null);
    notify("Pushing…");
    const r = await api.syncPush();
    if (!r.ok) { notify(r.error, "error"); return refreshSync(true); }
    syncDone(r, r.summary);
  };
  const syncInit = async () => {
    setDialog(null);
    const r = await api.syncInit();
    if (!r.ok) { notify(r.error, "error"); return refreshSync(true); }
    syncDone(r, "This folder is now a git repository. Nothing is committed yet.");
  };
  return { syncCommit, syncPush, syncInit };
}
