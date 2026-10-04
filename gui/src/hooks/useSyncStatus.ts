import { useCallback, useRef, useState } from "react";
import { api } from "../backend/api";
import type { SyncInfo } from "../data/types";

/** Read-only git status. Trailing-throttled (2.5 s) so autosaves do not spawn git every time. */
export function useSyncStatus() {
  const [sync, setSync] = useState<SyncInfo | null>(null);
  const syncTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshSync = useCallback((now = false) => {
    const run = () => { syncTimer.current = null; void api.syncStatus().then((r) => { if (r.ok) setSync(r.sync); }); };
    if (now) { if (syncTimer.current) clearTimeout(syncTimer.current); run(); return; }
    if (!syncTimer.current) syncTimer.current = setTimeout(run, 2500);
  }, []);
  return { sync, setSync, refreshSync };
}
