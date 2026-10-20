import { useState } from "react";
import { Modal } from "./Dialogs";
import { showNotice, type ScaleHint } from "../data/summaries";
import "../styles/summaries.css";

/**
 * A calm banner at the top of the editor area when a long project lacks summaries (Chisel sends the AI one scene, not the book). The
 * wording comes from Python, verbatim; `strong` is only another wording, not another colour. It can be closed (once per
 * project: the dismissal is kept in the project), never blocks typing and never appears while typing: the host fetches it
 * on project open and, debounced, after saves.
 */
export function GrowthNotice({ hint, onOpenSummaries, onDismiss }: { hint: ScaleHint | null; onOpenSummaries: () => void; onDismiss: () => void }) {
  const [explain, setExplain] = useState(false);
  if (!showNotice(hint)) return null;
  return (
    <div className="lw-growth" role="note" aria-label="This project is getting long">
      <p className="lw-growth__text">{hint.message}</p>
      <div className="lw-growth__actions">
        <button className="lw-btn lw-btn--primary" onClick={onOpenSummaries}>Open the summaries</button>
        <button className="lw-link" onClick={() => setExplain(true)}>What does “What was sent” show?</button>
        <button className="lw-btn" onClick={onDismiss} title="Close this for the project; it does not come back at this level">Close</button>
      </div>
      {explain && (
        <Modal title="What was sent" onClose={() => setExplain(false)}>
          <p className="lw-dialog__message">
            Under every answer from the AI, Chisel lists exactly what it sent with your request: the passage, the notes about the
            characters, the style guide and, once you have summaries, the story so far. It also says what was left out to fit the
            model’s limit, by name, and how big the request was. Nothing is cut without being listed there.
          </p>
          <div className="lw-dialog__buttons"><button className="lw-btn" autoFocus onClick={() => setExplain(false)}>Close</button></div>
        </Modal>
      )}
    </div>
  );
}
