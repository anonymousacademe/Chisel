// The client half of the AI job contract (docs/dev/plan-feedback-2026-10.md, Appendix):
// start a job, poll it every 100 ms, hand the streamed text to onText, resolve with the result.
import { api, type AiKind } from "./api";

export const POLL_MS = 100;

/** The job was stopped (by the author); nothing was applied. */
export class AiCancelled extends Error {
  constructor() { super("Stopped"); this.name = "AiCancelled"; }
}

export interface AiJob<R> {
  /** Resolves with the synchronous method's result; rejects with AiCancelled or an Error. */
  promise: Promise<R>;
  /** Idempotent. Resolves once the backend has been told. */
  cancel(): Promise<void>;
}

export interface AiJobOptions {
  /** Text deltas as they arrive (streaming kinds only), with the total so far. */
  onText?: (delta: string, total: string) => void;
  /** What the author sees while it runs; informational for the caller. */
  label?: string;
}

export function runAiJob<R = Record<string, unknown>>(kind: AiKind, args: Record<string, unknown>, opts: AiJobOptions = {}): AiJob<R> {
  let jobId: string | null = null;
  let started = false;
  let stopped = false;
  let wake: (() => void) | null = null;
  let cancelSent: Promise<void> | null = null;

  const cancel = (): Promise<void> => {
    stopped = true;
    wake?.();
    if (!cancelSent) {
      cancelSent = (async () => {
        // Started but not yet answered: wait for the id so the backend is told.
        while (jobId === null && !started) await new Promise((r) => setTimeout(r, 10));
        if (jobId) await api.aiCancel(jobId);
      })();
    }
    return cancelSent;
  };
  const promise = (async (): Promise<R> => {
    const s = await api.aiStart(kind, args);
    started = true;
    if (!s.ok) throw new Error(s.error);
    jobId = s.job;
    if (stopped) { await cancel(); throw new AiCancelled(); }
    let since = 0, total = "";
    for (;;) {
      const p = await api.aiPoll(jobId, since);
      if (!p.ok) throw new Error(p.error);
      if (p.text) { total += p.text; opts.onText?.(p.text, total); }
      since = p.length;
      if (stopped || p.state === "cancelled") throw new AiCancelled();
      if (p.state === "error") throw new Error(p.error || "The AI request failed.");
      if (p.state === "done") return { ok: true, ...(p.result ?? {}) } as R;
      await new Promise<void>((resolve) => { wake = resolve; setTimeout(resolve, POLL_MS); });
      wake = null;
    }
  })();
  return { promise, cancel };
}
