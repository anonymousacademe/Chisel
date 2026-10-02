import { useMemo, useState } from "react";
import type { ResearchSummary } from "../data/types";
import { NOTE_TEMPLATES, type NoteTemplate } from "../data/notebook";
import { Modal } from "./Dialogs";

/** New note: a title and a starting template (blank / idea / location / timeline). */
export function NewNoteDialog({ onSubmit, onClose }: { onSubmit: (title: string, template: NoteTemplate) => void; onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [template, setTemplate] = useState<NoteTemplate>("blank");
  const submit = () => { if (title.trim()) onSubmit(title.trim(), template); };
  return (
    <Modal title="New note" onClose={onClose}>
      <label className="lw-dialog__label">Title
        <input autoFocus className="lw-launch__input" value={title} onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
      </label>
      <div className="lw-picklist" role="radiogroup" aria-label="Template">
        {NOTE_TEMPLATES.map((t) => (
          <button key={t.id} role="radio" aria-checked={template === t.id} className={`lw-picklist__row${template === t.id ? " is-current" : ""}`}
            onClick={() => setTemplate(t.id)}>
            <span>{t.label}</span><span className="lw-faint">{t.detail}</span>
          </button>
        ))}
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!title.trim()} onClick={submit}>Create</button>
      </div>
    </Modal>
  );
}

/** The Notebook: every note in one list, with + New note and Ask my notebook. */
export function NotebookDialog({ notes, onOpen, onNew, onFromLink, onAsk, onClose }: {
  notes: ResearchSummary[]; onOpen: (id: string) => void; onNew: () => void; onFromLink: () => void; onAsk: () => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const shown = useMemo(() => notes.filter((n) => `${n.title} ${n.folder}`.toLowerCase().includes(q.trim().toLowerCase())), [notes, q]);
  return (
    <Modal title="Notebook" onClose={onClose} wide>
      <p className="lw-dialog__message">Notes about anything that is not the manuscript: ideas, places, timelines, research, links. They are plain Markdown files in the notebook folder.</p>
      <div className="lw-dialog__buttons lw-dialog__buttons--start">
        <button className="lw-btn lw-btn--primary" onClick={onNew}>+ New note</button>
        <button className="lw-btn" onClick={onFromLink}>New note from a link</button>
        <button className="lw-btn" onClick={onAsk}>Ask my notebook</button>
      </div>
      {notes.length > 6 && (
        <input className="lw-launch__input" aria-label="Filter notes" placeholder="Filter notes…" value={q} onChange={(e) => setQ(e.target.value)} />
      )}
      <div className="lw-picklist" role="list" aria-label="Notes">
        {notes.length === 0 && <p className="lw-empty">No notes yet. Use + New note, or paste a link anywhere.</p>}
        {shown.map((n) => (
          <button key={n.id} role="listitem" className="lw-picklist__row" onClick={() => onOpen(n.id)}>
            <span>{n.title}{n.folder ? <span className="lw-faint"> · {n.folder}</span> : null}</span>
            <span className="lw-mono lw-faint">{n.words.toLocaleString("en-US")}</span>
          </button>
        ))}
      </div>
      <div className="lw-dialog__buttons"><button className="lw-btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}
