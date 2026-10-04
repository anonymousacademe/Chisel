import { useCallback, useRef, useState } from "react";
import type { Notice } from "../components/Toast";

/** Toast notices: notify() shows one and removes it after a few seconds. */
export function useNotices() {
  const [notices, setNotices] = useState<Notice[]>([]);
  const noticeId = useRef(0);
  const notify = useCallback((text: string, tone: Notice["tone"] = "info", action?: Notice["action"]) => {
    const id = ++noticeId.current;
    setNotices((n) => [...n, { id, text, tone, action }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), tone === "error" || action ? 9000 : 3500);
  }, []);
  const dismiss = useCallback((id: number) => setNotices((n) => n.filter((x) => x.id !== id)), []);
  return { notices, notify, dismiss };
}
