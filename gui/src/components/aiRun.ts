import { useEffect, useState } from "react";
import type React from "react";

/** What the UI knows about the AI job that is running (one at a time). */
export interface AiRunView {
  label: string;          // "Drafting…"
  verb: string;           // "drafting" (status bar)
  mode: "chat" | "draft" | "strip";
  text: string;           // streamed so far
  startedAt: number;      // Date.now()
  anchor: { x: number; y: number } | null; // viewport point under the cursor (draft mode)
}

/** Whole seconds since `startedAt`, ticking while mounted. */
export function useElapsed(startedAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(t); }, []);
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}

export const secs = (n: number) => `${n} s`;

/** Esc on a focused panel stops its job. */
export const stopOnEsc = (stop: () => void) => (e: React.KeyboardEvent) => {
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); stop(); }
};
