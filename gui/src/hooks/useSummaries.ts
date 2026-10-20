import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AiKind } from "../backend/api";
import type { Notice } from "../components/Toast";
import { cleanProposal, progressLine, type PartBody, type PartProposal, type Pending, type ScaleHint, type SceneProposal, type StoredSummary, type SummaryBody } from "../data/summaries";

type Notify = (text: string, tone?: Notice["tone"], action?: Notice["action"]) => void;
type AiCall = <X>(label: string, verb: string, kind: AiKind, args: Record<string, unknown>) => Promise<(X & { ok: true }) | null>;

interface Deps {
  notify: Notify;
  /** Reload the workspace (status bar spend). */
  refresh: () => Promise<unknown>;
  aiCall: AiCall;
  stopAi: () => void;
  /** The open scene's id (null: no scene open). */
  sceneId: string | null;
  /** Bumped by App after each save of the open scene: summaries go out of date and the growth hint can change. */
  saveTick: number;
  /** The open project (the hint is fetched when it changes). */
  projectPath: string;
  /** Hide everything (research projects have no story to summarise). */
  enabled: boolean;
}

/** What the review dialog edits and sends back; `proposed` is the untouched proposal (null: the author's own words). */
export type Edited = SummaryBody | PartBody;
export interface Batch { running: boolean; done: number; total: number; title: string; failed: boolean }

/**
 * Everything the summaries screens need that outlives one dialog: the open scene's stored summary, the proposals waiting
 * for the author, the batch that writes the missing ones, and the growth hint. Nothing is saved except by `accept`
 * (the author's click); a proposal lives only here, in memory, until then.
 */
export function useSummaries({ notify, refresh, aiCall, stopAi, sceneId, saveTick, projectPath, enabled }: Deps) {
  const [stored, setStored] = useState<StoredSummary | null>(null);
  const [rev, setRev] = useState(0);                     // bumped when a summary was saved, locked or removed
  const [pending, setPending] = useState<Pending[]>([]);
  const [review, setReview] = useState<{ id: string; mode: "proposal" | "edit" } | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [hint, setHint] = useState<ScaleHint | null>(null);
  const [writing, setWriting] = useState<string | null>(null);   // the id whose summary is being written now
  const stopRef = useRef(false);
  const bump = useCallback(() => setRev((n) => n + 1), []);

  // the open scene's stored summary (and again, a moment after a save: the scene may have gone out of date)
  useEffect(() => {
    if (!enabled || !sceneId) return;
    let live = true;
    const t = setTimeout(() => {
      void api.summaryGet(sceneId).then((r) => { if (live) setStored(r.ok ? r : null); });
    }, saveTick ? 700 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [enabled, sceneId, rev, saveTick]);

  // the growth hint: when the project opens, after saves (debounced) and after summaries change. Never per keystroke.
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    const t = setTimeout(() => {
      void api.scaleHint().then((r) => { if (live && r.ok) setHint(r); });
    }, saveTick ? 4000 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [enabled, projectPath, rev, saveTick]);

  const dismissHint = useCallback(async () => {
    if (!hint || hint.level === "none") return;
    const r = await api.scaleHintDismiss(hint.level);
    if (!r.ok) return notify(r.error, "error");
    setHint({ ...hint, dismissed: true, dismissedLevel: hint.level });
  }, [hint, notify]);

  const addPending = (p: Pending) => setPending((l) => [...l.filter((x) => x.id !== p.id), p]);
  const dropPending = (id: string) => setPending((l) => l.filter((x) => x.id !== id));

  /** Write one scene's summary as a PROPOSAL (nothing is saved). Resolves the proposal, or null when it failed or was stopped. */
  const proposeScene = useCallback(async (id: string, title: string, from: Pending["from"]): Promise<SceneProposal | null> => {
    setWriting(id);
    const r = await aiCall<SceneProposal>(`Writing a summary of “${title}”…`, "summarising", "summarize", { scene_id: id }).finally(() => setWriting(null));
    if (!r) return null;
    addPending({ kind: "scene", id, title, result: r, from });
    if (from === "card") setReview({ id, mode: "proposal" });
    return r;
  }, [aiCall]);

  const proposePart = useCallback(async (id: string, title: string, from: Pending["from"]): Promise<PartProposal | null> => {
    setWriting(id);
    const r = await aiCall<PartProposal>(`Writing a summary of “${title}”…`, "summarising", "part_summarize", { part_id: id }).finally(() => setWriting(null));
    if (!r) return null;
    addPending({ kind: "part", id, title, result: r, from });
    if (from === "card") setReview({ id, mode: "proposal" });
    return r;
  }, [aiCall]);

  /** The missing / out of date scenes one at a time; a proposal each, nothing saved. Stop ends it after the current call is abandoned. */
  const startBatch = useCallback(async (scenes: { id: string; title: string }[]) => {
    if (batch?.running || scenes.length === 0) return;
    stopRef.current = false;
    let made = 0, failed = false;
    for (let i = 0; i < scenes.length; i++) {
      if (stopRef.current) break;
      setBatch({ running: true, done: i, total: scenes.length, title: scenes[i].title, failed: false });
      const r = await proposeScene(scenes[i].id, scenes[i].title, "panel");
      if (r) made++;
      else { failed = !stopRef.current; break; }
    }
    setBatch(null);
    void refresh();
    if (made) notify(`${made} ${made === 1 ? "proposal is" : "proposals are"} waiting for your review. Nothing is saved until you accept.`, "info");
    else if (failed) notify("No summary was written.", "error");
  }, [batch, proposeScene, refresh, notify]);

  const stopBatch = useCallback(() => { stopRef.current = true; stopAi(); }, [stopAi]);

  /** The author accepted (possibly after editing): saves through the bridge, which checks every quote against the scene again. */
  const accept = useCallback(async (p: Pending, edited: Edited, proposed: boolean): Promise<{ ok: true } | { ok: false; error: string }> => {
    const base = p.kind === "scene" ? p.result as SceneProposal : p.result as PartProposal;
    const payload = {
      ...edited,
      ...(proposed ? { proposed: base.proposal, model: base.model, cost: base.cost, ...(p.kind === "scene" ? { sourceHash: (base as SceneProposal).sourceHash } : {}) } : {}),
    };
    const r = p.kind === "scene" ? await api.summarySave(p.id, payload) : await api.partSummarySave(p.id, payload);
    if (!r.ok) return { ok: false, error: r.error };
    dropPending(p.id);
    bump(); void refresh();
    notify(p.kind === "scene" ? "Summary saved." : "Part summary saved.");
    return { ok: true };
  }, [bump, refresh, notify]);

  /** Save the author's own edit of a stored summary (no proposal behind it). */
  const saveEdit = useCallback(async (id: string, part: boolean, edited: Edited): Promise<{ ok: true } | { ok: false; error: string }> => {
    const r = part ? await api.partSummarySave(id, { ...edited }) : await api.summarySave(id, { ...edited });
    if (!r.ok) return { ok: false, error: r.error };
    bump(); void refresh();
    notify("Summary saved.");
    return { ok: true };
  }, [bump, refresh, notify]);

  const discard = useCallback((id: string) => { dropPending(id); }, []);

  /** Save every proposal that had nothing left out and nothing cut, as proposed. The bridge re-checks each one. */
  const acceptClean = useCallback(async () => {
    let saved = 0, refused = 0;
    for (const p of pending.filter(cleanProposal)) {
      const r = await accept(p, (p.result as SceneProposal).proposal, true);
      if (r.ok) saved++; else refused++;
    }
    if (refused) notify(`${saved} saved; ${refused} could not be saved (the scene changed, or a summary is locked). They stay in the list.`, "error");
  }, [pending, accept, notify]);

  const lock = useCallback(async (id: string, locked: boolean) => {
    const r = await api.summaryLock(id, locked);
    if (!r.ok) return notify(r.error, "error");
    bump(); notify(locked ? "Locked: Chisel will not rewrite this summary." : "Unlocked.");
  }, [bump, notify]);

  const remove = useCallback(async (id: string) => {
    const r = await api.summaryDelete(id);
    if (!r.ok) return notify(r.error, "error");
    bump(); void refresh(); notify("Summary removed.");
  }, [bump, refresh, notify]);

  const progress = batch ? progressLine(batch.done, batch.total, batch.title) : "";
  return {
    stored, pending, review, setReview, batch, progress, hint, rev, bump, writing,
    proposeScene, proposePart, startBatch, stopBatch, accept, saveEdit, discard, acceptClean, lock, remove, dismissHint,
  };
}
