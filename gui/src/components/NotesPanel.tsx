import { useState } from "react";
import { FilePenLine, Pencil, Plus, User } from "lucide-react";
import type { EntityInfo } from "../data/types";
import { Icon, SectionLabel, Tag } from "./primitives";
import { noteBlocks } from "../data/noteBlocks";

/** The Notes tab: the note under the cursor / picked in the binder, with aliases and backlinks. */
export function NotesPanel(props: {
  note: EntityInfo | null;
  /** A [[link]] under the cursor that has no note yet. */
  missingTarget: string | null;
  onOpenNote: (id: string) => void;
  onAddAlias: (name: string, alias: string) => void;
  /** Save the character's `born:` story time (blank clears it). */
  onSetBorn: (name: string, born: string) => void;
  onRename: (name: string, aliases: string[]) => void;
  onCreateNote: (target: string) => void;
  onOpenBacklink: (sourceId: string, row: number) => void;
}) {
  const [alias, setAlias] = useState("");
  const { note } = props;

  if (props.missingTarget) {
    return (
      <section className="lw-note">
        <p className="lw-note__title">{props.missingTarget}</p>
        <p className="lw-empty">No note for this name yet. Make one and every mention of it is recognized.</p>
        <button className="lw-btn" onClick={() => props.onCreateNote(props.missingTarget!)}>
          <Icon icon={Plus} size={14} stroke={1.8} /> Create note
        </button>
      </section>
    );
  }
  if (!note) {
    return <p className="lw-empty">Put the cursor on a name, or pick a note in the binder or library, to read it here. Ctrl-click a name in the text to open it.</p>;
  }
  if (!note.found) {
    return (
      <section className="lw-note">
        <p className="lw-note__title">{note.name}</p>
        <p className="lw-empty">This note no longer exists.</p>
      </section>
    );
  }
  const addAlias = () => { if (alias.trim()) { props.onAddAlias(note.name, alias.trim()); setAlias(""); } };
  return (
    <section className="lw-note">
      <div className="lw-row lw-gap-8">
        <span className="lw-source__icon"><Icon icon={User} size={14} stroke={1.5} /></span>
        <div className="lw-note__head">
          <p className="lw-note__title">{note.name}</p>
          <Tag>{note.type}</Tag>
        </div>
      </div>
      <div className="lw-note__aliases">
        {note.aliases.map((a) => <span key={a} className="lw-chip">{a}</span>)}
        <input className="lw-note__alias-input" value={alias} placeholder="Add alias" aria-label="Add alias"
          onChange={(e) => setAlias(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addAlias(); }} />
      </div>
      {note.type === "character" && (
        <BornField key={`${note.id}:${note.born}`} name={note.name} saved={note.born} invalid={note.bornInvalid}
          ageNow={note.ageNow} onSave={props.onSetBorn} />
      )}
      {note.body.trim()
        ? (
          <div className="lw-note__body">
            {noteBlocks(note.body).map((b, i) => b.kind === "heading" ? <h3 key={i}>{b.text}</h3>
              : b.kind === "list" ? <ul key={i}>{b.items.map((t, j) => <li key={j}>{t}</li>)}</ul>
              : <p key={i}>{b.text}</p>)}
          </div>
        )
        : <p className="lw-empty">This note has no text yet.</p>}
      <button className="lw-btn" onClick={() => props.onOpenNote(note.id)}>
        <Icon icon={FilePenLine} size={14} stroke={1.8} /> Open in editor
      </button>
      <button className="lw-btn" onClick={() => props.onRename(note.name, note.aliases)}>
        <Icon icon={Pencil} size={14} stroke={1.8} /> Rename everywhere…
      </button>
      <SectionLabel>Backlinks · {note.backlinks.length}</SectionLabel>
      <div className="lw-note__backlinks">
        {note.backlinks.length === 0 && <p className="lw-empty">Nothing mentions this note yet.</p>}
        {note.backlinks.map((b, i) => (
          <button key={`${b.sourceId}:${b.row}:${i}`} className="lw-backlink" onClick={() => props.onOpenBacklink(b.sourceId, b.row)}>
            <span className="lw-backlink__title">{b.sourceTitle}<span className="lw-mono lw-faint"> · line {b.row + 1}</span></span>
            <span className="lw-backlink__line">{b.line}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

/** The character's `born:` story time. Python says whether it is valid and what age it gives at the open scene. */
function BornField({ name, saved, invalid, ageNow, onSave }: {
  name: string; saved: string; invalid: boolean; ageNow: string; onSave: (name: string, born: string) => void;
}) {
  const [born, setBorn] = useState(saved);   // remounted (key) when the note or its saved value changes
  const unchanged = born.trim() === saved.trim();
  const save = () => { if (!unchanged) onSave(name, born.trim()); };
  return (
    <label className="lw-note__born">
      <span className="lw-faint">Born</span>
      <input className="lw-note__alias-input" value={born} placeholder="2187 or 2187-03-14" aria-label="Born"
        aria-invalid={invalid && unchanged} onChange={(e) => setBorn(e.target.value)} onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter") save(); }} />
      {invalid && unchanged && <span className="lw-details__error">Not a story time. Kept as text.</span>}
      {ageNow && <span className="lw-faint lw-note__age">{ageNow} (this scene)</span>}
    </label>
  );
}
