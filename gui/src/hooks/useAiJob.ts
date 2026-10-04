import { useRef, useState } from "react";
import type { RefObject } from "react";
import { STREAMING_KINDS, type AiKind } from "../backend/api";
import { runAiJob, AiCancelled, type AiJob } from "../backend/aijobs";
import type { AiRunView } from "../components/aiRun";
import type { EditorHandle } from "../components/EditorPane";
import type { Notice } from "../components/Toast";
import type { ChatMessage } from "../data/types";
import { aiRunMode, failedMessage } from "../data/appLogic";

interface Deps {
  notify: (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
  refresh: () => Promise<unknown>;
  editorRef: RefObject<EditorHandle | null>;
  openSettings: () => Promise<void>;
  aiReady: boolean;
}

const uid = () => crypto.randomUUID();

/**
 * The AI job plumbing. Everything the model returns is a suggestion: nothing here edits prose.
 * One job at a time; Stop abandons it (a stopped call must never insert or save anything).
 */
export function useAiJob({ notify, refresh, editorRef, openSettings, aiReady }: Deps) {
  const [aiRun, setAiRun] = useState<AiRunView | null>(null);
  const aiJobRef = useRef<AiJob<unknown> | null>(null);
  const stoppedRef = useRef(false); // the last AI job ended because the author pressed Stop
  const aiBusy = aiRun?.label ?? null;

  const requireAi = () => {
    if (!aiReady) {
      notify("Add your OpenRouter API key first. AI features are off until then.", "error");
      void openSettings();
      return false;
    }
    return true;
  };
  /** One AI job at a time: start, poll, show the working state, resolve with the result (null: failed or stopped). */
  async function aiCall<X>(label: string, verb: string, kind: AiKind, args: Record<string, unknown>): Promise<(X & { ok: true }) | null> {
    if (!requireAi()) return null;
    if (aiJobRef.current) { notify("Wait for the current AI request to finish."); return null; }
    const mode = aiRunMode(kind, STREAMING_KINDS);
    stoppedRef.current = false;
    const job = runAiJob<X & { ok: true }>(kind, args, { label, onText: (_d, total) => setAiRun((r) => (r ? { ...r, text: total } : r)),
      onElapsed: (elapsed) => setAiRun((r) => (r ? { ...r, elapsed } : r)) });
    aiJobRef.current = job as AiJob<unknown>;
    setAiRun({ label, verb, mode, text: "", startedAt: Date.now(), anchor: mode === "draft" ? editorRef.current?.cursorPoint() ?? null : null });
    try {
      return await job.promise;
    } catch (e) {
      if (e instanceof AiCancelled) { stoppedRef.current = true; notify("Stopped. Nothing was changed."); }
      else notify(e instanceof Error ? e.message : String(e), "error");
      return null;
    } finally { aiJobRef.current = null; setAiRun(null); void refresh(); } // refresh: the status bar's AI spend
  }
  const stopAi = () => { void aiJobRef.current?.cancel(); };
  const failedReply = (): ChatMessage => failedMessage(uid(), stoppedRef.current);

  return { aiReady, aiRun, aiBusy, requireAi, aiCall, stopAi, failedReply };
}
