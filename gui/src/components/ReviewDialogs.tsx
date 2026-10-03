import { useState, type ReactNode } from "react";
import type { AliasSuggestion, CanonProposal, SentReport as Report } from "../data/types";
import { Modal } from "./Dialogs";
import { SentReport } from "./SentReport";

function Footer(props: { confirm: string; disabled?: boolean; onConfirm: () => void; onClose: () => void; left?: ReactNode }) {
  return (
    <div className="lw-dialog__buttons lw-dialog__buttons--split">
      <div className="lw-row lw-gap-8">{props.left}</div>
      <div className="lw-row lw-gap-8">
        <button className="lw-btn" onClick={props.onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={props.disabled} onClick={props.onConfirm}>{props.confirm}</button>
      </div>
    </div>
  );
}

/** Alias finder results: each one is an opt-in; accepting only adds an alias to a note. */
export function AliasReviewDialog({ suggestions, sent, onApply, onClose }: {
  suggestions: AliasSuggestion[]; sent?: Report | null; onApply: (picked: AliasSuggestion[]) => void; onClose: () => void;
}) {
  const [on, setOn] = useState<Set<number>>(new Set());
  const toggle = (i: number) => setOn((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  return (
    <Modal title="Possible aliases" wide onClose={onClose}>
      <p className="lw-dialog__message">
        The assistant found other ways the prose refers to your notes. Tick the ones to teach as aliases.
        Your text is never changed; the alias is added to the note.
      </p>
      <div className="lw-review">
        {suggestions.map((s, i) => (
          <label key={`${s.entity}:${s.surface}:${i}`} className="lw-review__row">
            <input type="checkbox" checked={on.has(i)} onChange={() => toggle(i)} />
            <span className="lw-review__text">
              <span className="lw-review__context">…{s.before} <mark>{s.surface}</mark> {s.after}…</span>
              <span className="lw-review__target">→ {s.entity} <span className="lw-faint">(alias “{s.alias}”)</span></span>
            </span>
          </label>
        ))}
      </div>
      <SentReport report={sent} />
      <Footer confirm={on.size ? `Add ${on.size} alias${on.size === 1 ? "" : "es"}` : "Add aliases"} disabled={on.size === 0}
        onConfirm={() => onApply(suggestions.filter((_, i) => on.has(i)))} onClose={onClose}
        left={<button className="lw-link" onClick={() => setOn(new Set(suggestions.map((_, i) => i)))}>Select all</button>} />
    </Modal>
  );
}

/** Story-bible updates: per-fact review. Facts are only ever appended to a note's canon section. */
export function CanonReviewDialog({ proposals, sent, onApply, onClose }: {
  proposals: CanonProposal[]; sent?: Report | null; onApply: (picked: { entity: string; facts: string[] }[]) => void; onClose: () => void;
}) {
  const [on, setOn] = useState<Set<string>>(new Set());
  const key = (e: string, f: string) => `${e}\u0000${f}`;
  const toggle = (k: string) => setOn((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const picked = proposals
    .map((p) => ({ entity: p.entity, facts: p.facts.filter((f) => on.has(key(p.entity, f))) }))
    .filter((p) => p.facts.length);
  const total = picked.reduce((n, p) => n + p.facts.length, 0);
  return (
    <Modal title="Update the story bible" wide onClose={onClose}>
      <p className="lw-dialog__message">
        New facts this scene establishes. Ticked facts are added to the note’s “Canon (auto)” section; nothing already there is changed.
      </p>
      <div className="lw-review">
        {proposals.map((p) => (
          <div key={p.entity} className="lw-review__group">
            <strong>{p.entity}</strong>
            {p.evidence && <span className="lw-review__context">{p.evidence}</span>}
            {p.facts.map((f) => (
              <label key={f} className="lw-review__row">
                <input type="checkbox" checked={on.has(key(p.entity, f))} onChange={() => toggle(key(p.entity, f))} />
                <span className="lw-review__text">{f}</span>
              </label>
            ))}
            {p.existing && <details><summary className="lw-faint">Existing canon</summary><p className="lw-review__existing">{p.existing}</p></details>}
          </div>
        ))}
      </div>
      <SentReport report={sent} />
      <Footer confirm={total ? `Add ${total} fact${total === 1 ? "" : "s"}` : "Add facts"} disabled={total === 0}
        onConfirm={() => onApply(picked)} onClose={onClose}
        left={<button className="lw-link" onClick={() => setOn(new Set(proposals.flatMap((p) => p.facts.map((f) => key(p.entity, f)))))}>Select all</button>} />
    </Modal>
  );
}

/** A proposed style guide, editable before it is saved to style.md. */
export function StyleReviewDialog({ markdown, replacing, onSave, onClose }: {
  markdown: string; replacing: boolean; onSave: (text: string) => void; onClose: () => void;
}) {
  const [text, setText] = useState(markdown);
  return (
    <Modal title="Style guide learned from your prose" wide onClose={onClose}>
      <p className="lw-dialog__message">
        Read it, edit anything you disagree with, then save.
        {replacing ? " This replaces your current style.md (a copy is kept as style.md.bak)." : " It is saved as style.md in your project."}
      </p>
      <textarea className="lw-review__editor" value={text} onChange={(e) => setText(e.target.value)} aria-label="Style guide" spellCheck={false} />
      <Footer confirm="Save style guide" onConfirm={() => onSave(text)} onClose={onClose} />
    </Modal>
  );
}
