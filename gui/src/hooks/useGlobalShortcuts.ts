import { useEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../backend/api";
import type { SaveController } from "../editor/saveController";
import type { Dialog } from "../data/dialog";

interface Deps {
  saver: SaveController;
  openDoc: (id: string, opts?: { force?: boolean; keepMode?: boolean }) => Promise<void>;
  notify: (text: string, tone?: "info" | "error") => void;
  setSwitcher: Dispatch<SetStateAction<boolean>>;
  setFocus: Dispatch<SetStateAction<boolean>>;
  setDialog: Dispatch<SetStateAction<Dialog>>;
}

/** Global keys (ctrl+k, F11, ctrl+n), link paste, and flushing saves when the window loses focus or goes away. */
export function useGlobalShortcuts({ saver, openDoc, notify, setSwitcher, setFocus, setDialog }: Deps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSwitcher((s) => !s); }
      else if (e.key === "F11") { e.preventDefault(); setFocus((f) => !f); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n" && !e.shiftKey) { e.preventDefault(); setDialog({ kind: "new-scene" }); }
    };
    const onHide = () => { void saver.flush(); };
    // a link pasted anywhere outside a text field offers to become a notebook note
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.closest("input, textarea, [contenteditable=true], .cm-editor"))) return;
      const text = e.clipboardData?.getData("text/plain")?.trim() ?? "";
      if (/^https?:\/\/\S+$/.test(text)) { e.preventDefault(); setDialog({ kind: "research-url", url: text }); }
    };
    // the terminal app may have edited the file while we were in the background
    const onFocus = async () => {
      const id = saver.documentId;
      if (!id) return;
      const r = await api.documentMtime(id);
      if (!r.ok || r.mtime === saver.baseMtime) return;
      if (saver.isDirty) saver.markConflict();
      else { await openDoc(id, { force: true }); notify("Reloaded: the file changed on disk."); }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("paste", onPaste);
    window.addEventListener("pagehide", onHide);
    window.addEventListener("blur", onHide);
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("paste", onPaste);
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("blur", onHide);
      window.removeEventListener("focus", onFocus);
    };
  }, [saver, openDoc, notify, setSwitcher, setFocus, setDialog]);
}
