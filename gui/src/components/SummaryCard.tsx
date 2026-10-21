import { useEffect, useState } from "react";
import { api } from "../backend/api";
import { Modal } from "./Dialogs";
import { StopButton } from "./AiProgress";
import {
  estimateSentence, statusLabel, statusNote, thinkingNote, wordsLine, SCENE_WORDS_CAP,
  type Estimate, type Pending, type StoredSummary, type SummaryBody, type SummaryStatus,
} from "../data/summaries";
import "../styles/summaries.css";

/** The status chip: None / Fresh / Out of date / Locked. */
export function StatusChip({ status }: { status: SummaryStatus }) {
  return <span className={`lw-sumchip lw-sumchip--${status}`}>{statusLabel(status)}</span>;
}

/** The price and size of what is about to be sent, asked of Python (no network) before anything is. Cancel / Continue. */
export function EstimateDialog({ title, ids, unit, onContinue, onClose }: {
  title: string; ids: string[] | null; unit: string; onContinue: () => void; onClose: () => void;
}) {
  const [est, setEst] = useState<Estimate | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    void api.summariesEstimate(ids).then((r) => { if (!live) return; if (r.ok) setEst(r); else setError(r.error); });
    return () => { live = false; };
  }, [ids]);
  return (
    <Modal title={title} onClose={onClose}>
      {!est && !error && <p className="lw-dialog__message">Working out the size and the price…</p>}
      {error && <p className="lw-sumrev__error" role="alert">{error}</p>}
      {est && (
        <div className="lw-sumest">
          <p className="lw-dialog__message">{estimateSentence(est, unit)}</p>
          {thinkingNote(est) && <p className="lw-sumest__note">{thinkingNote(est)}</p>}
          {est.notes.filter((n) => !/thinks before|does not know whether|price of this model is unknown/.test(n)).map((n) => <p key={n} className="lw-faint lw-sumest__note">{n}</p>)}
          <p className="lw-faint lw-sumest__note">You review every summary before it is kept. Nothing is saved without your click, and what is sent is listed under each proposal.</p>
        </div>
      )}
      <div className="lw-dialog__buttons">
        <button className="lw-btn" autoFocus onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!est || est.calls === 0} onClick={onContinue}>Continue</button>
      </div>
    </Modal>
  );
}

/**
 * The Summary tab of the side panel: the open scene's summary, how fresh it is, and the actions. Writing one shows the
 * estimate first; the result opens in the review, and nothing is saved before the author accepts it.
 */
export function SummaryCard({ sceneId, title, unit, stored, proposal, busy, running, onWrite, onReview, onDiscard, onEdit, onLock, onRemove, onOpenPanel, onStop }: {
  sceneId: string | null; title: string; unit: string;
  stored: StoredSummary | null; proposal: Pending | undefined;
  /** Another AI request is running (one at a time). */
  busy: boolean;
  /** The summary of this scene is being written now. */
  running: boolean;
  onWrite: () => void; onReview: () => void; onDiscard: () => void; onEdit: () => void;
  onLock: (locked: boolean) => void; onRemove: () => void; onOpenPanel: () => void; onStop: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [removing, setRemoving] = useState(false);
  if (!sceneId) return <div className="lw-sumcard"><p className="lw-empty">Open a {unit} to see its summary.</p></div>;
  const status: SummaryStatus = stored?.status ?? "missing";
  const body = stored?.summary as SummaryBody | null | undefined;
  const facts = body && "facts" in body ? body.facts : [];
  const locked = status === "locked" || !!stored?.locked;
  const count = body ? wordsLine(body.summary, SCENE_WORDS_CAP).text : "";
  const note = statusNote(status, stored?.changedSince);

  return (
    <div className="lw-sumcard">
      <div className="lw-sumcard__head">
        <h3 className="lw-sumcard__title">Summary of “{title}”</h3>
        <StatusChip status={status} />
      </div>
      {note && <p className={`lw-sumcard__note${status === "stale" ? " is-warn" : ""}`}>{note}</p>}
      {stored?.authorEdited && <p className="lw-faint lw-sumcard__note">You edited this summary, so Chisel will not rewrite it.</p>}

      {proposal && (
        <div className="lw-sumcard__proposal" role="status">
          <span>A proposal is waiting for your review. Nothing is saved until you accept it.</span>
          <span className="lw-row lw-gap-6"><button className="lw-btn lw-btn--primary" onClick={onReview}>Review proposal</button>
            <button className="lw-btn" onClick={onDiscard}>Discard</button></span>
        </div>
      )}
      {running && <div className="lw-sumcard__proposal" role="status"><span className="lw-pulse">Writing the summary…</span><StopButton onStop={onStop} small /></div>}

      {body ? (
        <>
          <p className="lw-sumcard__text">{body.summary}</p>
          <p className="lw-faint lw-sumcard__count">{count}</p>
          {facts.length > 0 && (
            <details className="lw-sumcard__facts">
              <summary>{facts.length} fact{facts.length === 1 ? "" : "s"}</summary>
              <ul>{facts.map((f, i) => <li key={i} title={f.quote ? `From your text: “${f.quote}”` : ""}>{f.text}</li>)}</ul>
            </details>
          )}
          {body.characters.length > 0 && (
            <p className="lw-sumcard__chars"><span className="lw-faint">At the end: </span>{body.characters.map((c) => c.state ? `${c.name} (${c.state})` : c.name).join("; ")}</p>
          )}
          {body.threads.length > 0 && <p className="lw-sumcard__chars"><span className="lw-faint">Left open: </span>{body.threads.join("; ")}</p>}
        </>
      ) : !proposal && !running && (
        <p className="lw-sumcard__text lw-faint">Chisel can write a short summary of this {unit}. The AI reads it, you review the result, and nothing is kept without your click.</p>
      )}

      <div className="lw-sumcard__actions">
        {!locked && <button className="lw-btn lw-btn--primary" disabled={busy || running} onClick={() => setAsking(true)}>{body ? "Write again" : "Write summary"}</button>}
        {body && <button className="lw-btn" onClick={onEdit}>Edit</button>}
        {body && <button className="lw-btn" onClick={() => onLock(!locked)} title={locked ? "Let Chisel replace this summary again" : "Chisel will never rewrite a locked summary"}>{locked ? "Unlock" : "Lock"}</button>}
        {body && <button className="lw-btn lw-btn--danger" onClick={() => setRemoving(true)}>Remove</button>}
      </div>
      <p className="lw-sumcard__more"><button className="lw-link" onClick={onOpenPanel}>All summaries in the book…</button></p>

      {asking && (
        <EstimateDialog title={body ? "Write this summary again" : "Write a summary"} ids={[sceneId]} unit={unit}
          onClose={() => setAsking(false)} onContinue={() => { setAsking(false); onWrite(); }} />
      )}
      {removing && (
        <Modal title="Remove this summary" onClose={() => setRemoving(false)}>
          <p className="lw-dialog__message">Remove the summary of “{title}”?{stored?.authorEdited || locked ? " It holds your own edits or is locked, and they are lost." : ""} It is not kept anywhere else; writing a new one costs a request to the AI.</p>
          <div className="lw-dialog__buttons">
            <button className="lw-btn" autoFocus onClick={() => setRemoving(false)}>Cancel</button>
            <button className="lw-btn lw-btn--danger" onClick={() => { setRemoving(false); onRemove(); }}>Remove</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
