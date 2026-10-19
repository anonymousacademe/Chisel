import { useCallback, useEffect, useState } from "react";
import { api } from "../backend/api";
import { Modal } from "./Dialogs";
import { StopButton } from "./AiProgress";
import { EstimateDialog, StatusChip } from "./SummaryCard";
import {
  acceptAllSentence, batchLabel, cleanProposal, coverageLine, reviewLabel, rowNote,
  type Pending, type PartStatusRow, type SceneProposal, type StatusInfo, type StatusRow,
} from "../data/summaries";
import type { Batch } from "../hooks/useSummaries";
import "../styles/summaries.css";

/**
 * The book's summaries: how many scenes have one, a row per part and per scene, the button that writes the missing ones
 * (the estimate first, then one scene at a time with Stop), and the list of proposals waiting for review. Nothing is
 * ever saved without the author's click on Accept (or on "Accept all that had nothing left out", which says what it does).
 */
export function SummariesDialog({ unit, after, pending, batch, progress, rev, onStartBatch, onStop, onReview, onDiscard, onAcceptClean, onOpenScene, onWritePart, onClose, notify }: {
  unit: string; after?: string | null; pending: Pending[]; batch: Batch | null; progress: string; rev: number;
  onStartBatch: (scenes: { id: string; title: string }[]) => void; onStop: () => void;
  onReview: (id: string) => void; onDiscard: (id: string) => void; onAcceptClean: () => Promise<void>;
  onOpenScene: (id: string) => void; onWritePart: (id: string, title: string) => void;
  onClose: () => void; notify: (text: string, tone?: "info" | "error") => void;
}) {
  const [info, setInfo] = useState<StatusInfo | null>(null);
  const [view, setView] = useState<"list" | "review">("list");
  const [estimating, setEstimating] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    let live = true;
    void api.summariesStatus().then((r) => { if (!live) return; if (r.ok) setInfo(r); else notify(r.error, "error"); });
    return () => { live = false; };
  }, [notify]);
  useEffect(() => load(), [load, rev, batch?.running]);

  const todo = (info?.scenes ?? []).filter((s) => s.status === "missing" || s.status === "stale");
  const batchTitle = batchLabel(todo.filter((s) => s.status === "missing").length, todo.filter((s) => s.status === "stale").length);
  const running = !!batch?.running;
  const clean = pending.filter(cleanProposal).length;
  const plural = (n: number) => (n === 1 ? unit : `${unit}s`);

  if (estimating) {
    return <EstimateDialog title={batchTitle} ids={null} unit={unit} onClose={() => setEstimating(false)}
      onContinue={() => { setEstimating(false); onStartBatch(todo.map((s) => ({ id: s.id, title: s.title }))); }} />;
  }

  if (view === "review") {
    return (
      <Modal title={reviewLabel(pending.length)} wide onClose={onClose}>
        <p className="lw-dialog__message">Each proposal is waiting for you. Open one to read and change it; nothing is saved until you accept it.</p>
        <div className="lw-picklist lw-picklist--tall" aria-label="Proposals">
          {pending.length === 0 && <p className="lw-empty">No proposals waiting.</p>}
          {pending.map((p) => {
            const r = p.result as SceneProposal;
            const left = p.kind === "scene" ? r.dropped.length : 0;
            return (
              <div key={p.id} className="lw-picklist__row lw-picklist__row--static">
                <span className="lw-picklist__main">
                  <strong>{p.title}</strong>
                  <span className="lw-faint">
                    {p.kind === "part" ? "Part summary" : left ? `${left} left out${r.trimmed ? ", shortened" : ""}` : r.trimmed ? "Shortened to fit" : "Nothing left out"}
                  </span>
                </span>
                <span className="lw-row lw-gap-6">
                  <button className="lw-btn lw-btn--primary" onClick={() => onReview(p.id)}>Open</button>
                  <button className="lw-btn" onClick={() => onDiscard(p.id)}>Discard</button>
                </span>
              </div>
            );
          })}
        </div>
        {confirmAll && (
          <div className="lw-sumpanel__confirm" role="alert">
            <p>{acceptAllSentence(pending)}</p>
            <span className="lw-row lw-gap-6">
              <button className="lw-btn" onClick={() => setConfirmAll(false)}>Cancel</button>
              <button className="lw-btn lw-btn--primary" disabled={clean === 0 || busy}
                onClick={() => { setBusy(true); void onAcceptClean().finally(() => { setBusy(false); setConfirmAll(false); }); }}>
                Save {clean} {clean === 1 ? "summary" : "summaries"}</button>
            </span>
          </div>
        )}
        <div className="lw-dialog__buttons lw-dialog__buttons--split">
          <button className="lw-btn" onClick={() => { setConfirmAll(false); setView("list"); }}>Back to the summaries</button>
          <span className="lw-row lw-gap-8">
            <button className="lw-btn" disabled={pending.length === 0} onClick={() => setConfirmAll(true)}
              title="Saves the proposals that had no fact left out and were not shortened; asks you first">Accept all that had nothing left out</button>
            <button className="lw-btn" autoFocus onClick={onClose}>Close</button>
          </span>
        </div>
      </Modal>
    );
  }

  const partRows = new Map<string, PartStatusRow>((info?.parts ?? []).map((p) => [p.id, p]));
  const groups: { part: PartStatusRow | null; rows: StatusRow[] }[] = [];
  for (const s of info?.scenes ?? []) {
    const last = groups[groups.length - 1];
    const part = s.part ? partRows.get(s.part) ?? null : null;
    if (last && (last.part?.id ?? null) === (part?.id ?? null)) last.rows.push(s); else groups.push({ part, rows: [s] });
  }
  const waiting = new Set(pending.map((p) => p.id));

  return (
    <Modal title="Summaries" wide onClose={onClose}>
      <div className="lw-sumpanel">
        {after && <p className="lw-faint lw-sumpanel__after">{after}</p>}
        <p className="lw-sumpanel__coverage" aria-live="polite">{info ? coverageLine(info.totals, unit) : "Reading the summaries…"}</p>
        <p className="lw-faint lw-sumpanel__lead">
          A summary is a short record of what happens in a {unit}. Chisel gives the AI the summaries of the earlier {unit}s as “the story so far”,
          so checks and questions can see the whole book. Every summary is reviewed by you before it is kept.
        </p>
        {running && (
          <div className="lw-sumpanel__progress" role="status">
            <span className="lw-pulse">{progress}</span>
            <StopButton onStop={onStop} small />
          </div>
        )}
        <div className="lw-row lw-gap-8 lw-sumpanel__buttons">
          <button className="lw-btn lw-btn--primary" disabled={running || todo.length === 0} onClick={() => setEstimating(true)}>
            {batchTitle}{todo.length ? ` (${todo.length})` : ""}</button>
          {pending.length > 0 && <button className="lw-btn" onClick={() => setView("review")}>{reviewLabel(pending.length)}</button>}
        </div>
        <div className="lw-sumpanel__list" aria-label="Summaries by part and scene">
          {info === null && <p className="lw-empty">Loading…</p>}
          {info && info.scenes.length === 0 && <p className="lw-empty">There are no {unit}s to summarise yet.</p>}
          {groups.map((g, gi) => (
            <section key={g.part?.id ?? `top-${gi}`} className="lw-sumpanel__group">
              {g.part && (
                <div className="lw-sumpanel__part">
                  <strong>{g.part.title}</strong>
                  <span className="lw-faint">{g.part.summarised} of {g.part.scenes} {plural(g.part.scenes)} summarised</span>
                  <StatusChip status={g.part.status} />
                  {g.part.summarised > 0 && g.part.status !== "locked" && (
                    <button className="lw-btn lw-sumpanel__btn" disabled={running || waiting.has(g.part.id)}
                      title="One request to the AI, made from the summaries of this part's scenes"
                      onClick={() => onWritePart(g.part!.id, g.part!.title)}>{g.part.status === "missing" ? "Write part summary" : "Write again"}</button>
                  )}
                </div>
              )}
              <ul className="lw-sumpanel__rows">
                {g.rows.map((s) => (
                  <li key={s.id} className="lw-sumpanel__row">
                    <button className="lw-link lw-sumpanel__title" onClick={() => onOpenScene(s.id)} title={`Open this ${unit}`}>{s.title}</button>
                    <span className="lw-faint lw-sumpanel__meta">
                      {[s.status === "missing" ? "" : `${s.words} words`, rowNote(s, waiting.has(s.id))].filter(Boolean).join(" · ")}
                    </span>
                    <StatusChip status={s.status} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
      <div className="lw-dialog__buttons"><button className="lw-btn" autoFocus onClick={onClose}>Close</button></div>
    </Modal>
  );
}
