import { useState } from "react";
import { X } from "lucide-react";
import { Icon } from "./primitives";
import { Modal } from "./Dialogs";
import { SentReport } from "./SentReport";
import {
  PART_WORDS_CAP, SCENE_WORDS_CAP, TRIMMED_NOTE, costLine, leftOutLine, tolerantNote, wordsLine,
  type PartBody, type PartProposal, type Pending, type SceneProposal, type SummaryBody,
} from "../data/summaries";
import type { Edited } from "../hooks/useSummaries";
import "../styles/summaries.css";

/** What the review shows: a proposal waiting for the author, or a stored summary being edited by hand. */
export type ReviewTarget =
  | { mode: "proposal"; pending: Pending }
  | { mode: "edit"; id: string; title: string; part: boolean; stored: SummaryBody | PartBody };

const isScene = (b: SummaryBody | PartBody): b is SummaryBody => "facts" in b;

/**
 * Review of a summary before anything is saved. The text is an editable box with a live word count against the
 * limit; every fact is a row (the quote it rests on opens under it) and can be removed; what verification left out is
 * listed in plain words. Accept saves (the bridge checks every quote and name against the scene again and may refuse,
 * with a message shown here); Discard throws the proposal away. Nothing is saved before Accept.
 */
export function SummaryReview({ target, onAccept, onDiscard, onClose }: {
  target: ReviewTarget;
  onAccept: (edited: Edited) => Promise<{ ok: true } | { ok: false; error: string }>;
  onDiscard: () => void;
  onClose: () => void;
}) {
  const editing = target.mode === "edit";
  const result = target.mode === "proposal" ? target.pending.result : null;
  const start = target.mode === "proposal" ? (result as SceneProposal | PartProposal).proposal : target.stored;
  const part = target.mode === "proposal" ? target.pending.kind === "part" : target.part;
  const title = target.mode === "proposal" ? target.pending.title : target.title;
  const cap = part ? PART_WORDS_CAP : SCENE_WORDS_CAP;

  const [text, setText] = useState(start.summary);
  const [facts, setFacts] = useState(isScene(start) ? start.facts : []);
  const [characters, setCharacters] = useState(start.characters);
  const [threads, setThreads] = useState(start.threads);
  const [openQuote, setOpenQuote] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const count = wordsLine(text, cap);
  const scene = result as SceneProposal | null;
  const dropped = scene && "dropped" in scene ? scene.dropped : [];

  const accept = async () => {
    setBusy(true); setError("");
    const body: Edited = part ? { summary: text.trim(), characters, threads } : { summary: text.trim(), characters, facts, threads };
    const r = await onAccept(body);
    setBusy(false);
    if (!r.ok) setError(r.error);
  };

  return (
    <Modal title={`${editing ? "Edit" : "Review"} ${part ? "part " : ""}summary: ${title}`} wide onClose={onClose}>
      <div className="lw-sumrev">
        {!editing && <p className="lw-dialog__message lw-sumrev__lead">
          Chisel proposes this summary. Read it, change anything, and accept it, or discard it. Nothing is saved until you accept.
          {scene?.replacing ? " It will replace the summary you have now." : ""}
        </p>}
        <label className="lw-sumrev__label" htmlFor="lw-sumrev-text">Summary</label>
        <textarea id="lw-sumrev-text" className="lw-sumrev__text" value={text} rows={part ? 8 : 6} onChange={(e) => setText(e.target.value)} />
        <div className={`lw-sumrev__count${count.over ? " is-over" : ""}`} aria-live="polite">{count.text}</div>

        {!part && (
          <section aria-label="Facts">
            <h3 className="lw-sumrev__h">Facts <span className="lw-faint">({facts.length})</span></h3>
            {facts.length === 0 && <p className="lw-faint lw-sumrev__none">No facts kept.</p>}
            <ul className="lw-sumrev__rows">
              {facts.map((f, i) => (
                <li key={`${i}:${f.text}`} className="lw-sumrev__row" title={f.quote ? `From your scene: “${f.quote}”` : ""}>
                  <div className="lw-sumrev__rowmain">
                    <span>{f.text}</span>
                    {f.quote && <button className="lw-link lw-sumrev__show" aria-expanded={openQuote === i} onClick={() => setOpenQuote(openQuote === i ? null : i)}>
                      {openQuote === i ? "Hide the quote" : "Show the quote"}</button>}
                    {openQuote === i && <blockquote className="lw-sumrev__quote">{f.quote}</blockquote>}
                  </div>
                  <button className="lw-sumrev__x" aria-label={`Remove this fact: ${f.text}`} title="Remove this fact" onClick={() => setFacts(facts.filter((_, j) => j !== i))}>
                    <Icon icon={X} size={12} stroke={2} /></button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section aria-label="Characters">
          <h3 className="lw-sumrev__h">Characters at the end <span className="lw-faint">({characters.length})</span></h3>
          {characters.length === 0 && <p className="lw-faint lw-sumrev__none">None.</p>}
          <ul className="lw-sumrev__rows">
            {characters.map((c, i) => (
              <li key={`${i}:${c.name}`} className="lw-sumrev__row">
                <div className="lw-sumrev__rowmain"><strong>{c.name}</strong>{c.state && <span className="lw-faint"> · {c.state}</span>}</div>
                <button className="lw-sumrev__x" aria-label={`Remove ${c.name}`} title="Remove" onClick={() => setCharacters(characters.filter((_, j) => j !== i))}>
                  <Icon icon={X} size={12} stroke={2} /></button>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Open questions">
          <h3 className="lw-sumrev__h">Questions left open <span className="lw-faint">({threads.length})</span></h3>
          {threads.length === 0 && <p className="lw-faint lw-sumrev__none">None.</p>}
          <ul className="lw-sumrev__rows">
            {threads.map((t, i) => (
              <li key={`${i}:${t}`} className="lw-sumrev__row">
                <div className="lw-sumrev__rowmain">{t}</div>
                <button className="lw-sumrev__x" aria-label={`Remove: ${t}`} title="Remove" onClick={() => setThreads(threads.filter((_, j) => j !== i))}>
                  <Icon icon={X} size={12} stroke={2} /></button>
              </li>
            ))}
          </ul>
        </section>

        {dropped.length > 0 && (
          <details className="lw-sumrev__left">
            <summary>Left out ({dropped.length}): Chisel checked these against your scene and did not keep them</summary>
            <ul>{dropped.map((d, i) => <li key={i}>{leftOutLine(d)}</li>)}</ul>
          </details>
        )}
        {scene && tolerantNote(scene.tolerant) && <p className="lw-sumrev__note">{tolerantNote(scene.tolerant)}</p>}
        {result && (result as SceneProposal | PartProposal).trimmed && <p className="lw-sumrev__note is-warn">{TRIMMED_NOTE}</p>}
        {part && result && (result as PartProposal).missing.length > 0 && (
          <p className="lw-sumrev__note is-warn">{(result as PartProposal).missing.length} scene{(result as PartProposal).missing.length === 1 ? " has" : "s have"} no summary yet, so this part summary leaves {(result as PartProposal).missing.length === 1 ? "it" : "them"} out: {(result as PartProposal).missing.join(", ")}.</p>
        )}
        {result && <p className="lw-faint lw-sumrev__meta">{[(result as SceneProposal).model, costLine((result as SceneProposal).cost)].filter(Boolean).join(" · ")}</p>}
        {result && <SentReport report={(result as SceneProposal).sent} />}
        {error && <p className="lw-sumrev__error" role="alert">{error}</p>}
      </div>
      <div className="lw-dialog__buttons lw-dialog__buttons--split">
        {editing ? <span /> : <button className="lw-btn" disabled={busy} onClick={onDiscard}>Discard</button>}
        <span className="lw-row lw-gap-8">
          {editing && <button className="lw-btn" disabled={busy} onClick={onClose}>Cancel</button>}
          <button className="lw-btn lw-btn--primary" disabled={busy || count.over || !text.trim()} onClick={() => void accept()}
            title={count.over ? `Shorten it to ${cap} words first` : undefined}>{editing ? "Save" : "Accept"}</button>
        </span>
      </div>
    </Modal>
  );
}
