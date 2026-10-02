import { useState } from "react";
import type { RenameDone, RenamePreview, RenameScope, RenameUndone } from "../data/types";
import { aliasRenames, countTicked, defaultTicks, KIND_LABEL } from "../data/rename";
import { Modal } from "./Dialogs";

const SCOPES: { id: RenameScope; label: string; on: boolean }[] = [
  { id: "scenes", label: "Scenes (text, [[links]], POV and place)", on: true },
  { id: "entities", label: "Other notes", on: true },
  { id: "research", label: "Notebook notes", on: false },
  { id: "comments", label: "Comments", on: false },
];

/**
 * Rename a note everywhere, in three steps: the new name (and aliases), a preview of
 * every occurrence with checkboxes, then the result with Undo. The host flushes the open
 * scene before each call; nothing is written until Apply.
 */
export function RenameDialog({ name, aliases, onPreview, onApply, onUndo, onClose }: {
  name: string; aliases: string[];
  onPreview: (newName: string, keepOld: boolean, renameAliases: Record<string, string>, scope: RenameScope[]) => Promise<RenamePreview | null>;
  onApply: (plan: string, accepted: string[]) => Promise<RenameDone | null>;
  onUndo: (undoId: string) => Promise<RenameUndone | null>;
  onClose: () => void;
}) {
  const [newName, setNewName] = useState(name);
  const [keepOld, setKeepOld] = useState(true);
  const [aliasEdit, setAliasEdit] = useState<Record<string, string>>(() => Object.fromEntries(aliases.map((a) => [a, a])));
  const [scope, setScope] = useState<Set<RenameScope>>(() => new Set(SCOPES.filter((s) => s.on).map((s) => s.id)));
  const [preview, setPreview] = useState<RenamePreview | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [done, setDone] = useState<RenameDone | null>(null);
  const [undone, setUndone] = useState<RenameUndone | null>(null);
  const [busy, setBusy] = useState(false);

  const renames = aliasRenames(aliasEdit);
  const canPreview = newName.trim() !== "" && (newName.trim() !== name || Object.keys(renames).length > 0) && scope.size > 0;
  const toggle = (id: string) => setTicked((t) => { const n = new Set(t); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const toggleFile = (ids: string[], on: boolean) => setTicked((t) => { const n = new Set(t); ids.forEach((i) => on ? n.add(i) : n.delete(i)); return n; });

  const runPreview = async () => {
    setBusy(true);
    const p = await onPreview(newName.trim(), keepOld, renames, [...scope]);
    setBusy(false);
    if (p) { setPreview(p); setTicked(defaultTicks(p)); }
  };
  const runApply = async () => {
    if (!preview) return;
    setBusy(true);
    const d = await onApply(preview.plan, [...ticked]);
    setBusy(false);
    if (d) setDone(d);
  };
  const runUndo = async () => {
    if (!done) return;
    setBusy(true);
    const u = await onUndo(done.undoId);
    setBusy(false);
    if (u) setUndone(u);
  };

  if (done) {
    return (
      <Modal title="Rename everywhere" onClose={onClose}>
        {undone ? (
          <p className="lw-dialog__message">
            Undone: the scenes and the note are back as they were.
            {undone.skipped.length > 0 && <> Left alone because they changed since: {undone.skipped.join(", ")}.</>}
          </p>
        ) : (
          <p className="lw-dialog__message">
            Renamed to “{done.name}”: {done.replacements} change{done.replacements === 1 ? "" : "s"}, {done.scenes} scene{done.scenes === 1 ? "" : "s"} rewritten.
            Each scene was snapshotted first (“before-rename”), so Undo puts everything back.
          </p>
        )}
        <div className="lw-dialog__buttons">
          {!undone && <button className="lw-btn" disabled={busy} onClick={() => void runUndo()}>Undo</button>}
          <button className="lw-btn lw-btn--primary" autoFocus onClick={onClose}>Close</button>
        </div>
      </Modal>
    );
  }

  if (preview) {
    const { occurrences, files } = countTicked(preview.files, ticked);
    return (
      <Modal title={`Rename “${preview.name}” to “${preview.newName}”`} wide onClose={onClose}>
        <p className="lw-dialog__message">
          {preview.files.length === 0
            ? "Nothing in the text uses this name. Only the note itself will be renamed."
            : "Untick anything that should stay (a word that is also an ordinary one, say). Text inside an unaccepted AI draft is shown unticked. Nothing changes until Apply."}
        </p>
        <div className="lw-rename__list">
          {preview.files.map((f) => {
            const ids = f.occurrences.map((o) => o.id);
            const n = ids.filter((i) => ticked.has(i)).length;
            return (
              <section key={f.file} className="lw-rename__file">
                <label className="lw-check lw-rename__head">
                  <input type="checkbox" checked={n === ids.length} ref={(el) => { if (el) el.indeterminate = n > 0 && n < ids.length; }}
                    onChange={(e) => toggleFile(ids, e.target.checked)} />
                  <span className="lw-rename__title">{f.title}</span>
                  <span className="lw-faint">{KIND_LABEL[f.kind] ?? f.kind} · {n}/{ids.length}</span>
                </label>
                {f.occurrences.map((o) => (
                  <label key={o.id} className="lw-check lw-rename__row">
                    <input type="checkbox" checked={ticked.has(o.id)} onChange={() => toggle(o.id)} />
                    <span className="lw-mono lw-faint lw-rename__line">{o.line}</span>
                    <span className="lw-rename__ctx">
                      {o.pre}<del className="lw-rename__old">{o.before}</del><ins className="lw-rename__new">{o.after}</ins>{o.post}
                      {o.inDraft && <em className="lw-faint"> · in an AI draft</em>}
                    </span>
                  </label>
                ))}
              </section>
            );
          })}
        </div>
        <div className="lw-dialog__buttons">
          <button className="lw-btn" onClick={() => setPreview(null)}>Back</button>
          <button className="lw-btn lw-btn--primary" disabled={busy} onClick={() => void runApply()}>
            Apply {occurrences} change{occurrences === 1 ? "" : "s"} in {files} file{files === 1 ? "" : "s"}
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title={`Rename “${name}” everywhere`} onClose={onClose}>
      <label className="lw-dialog__label">New name
        <input autoFocus className="lw-launch__input" value={newName} onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && canPreview && !busy) void runPreview(); }} />
      </label>
      <label className="lw-check"><input type="checkbox" checked={keepOld} onChange={(e) => setKeepOld(e.target.checked)} />
        Keep “{name}” as an alias</label>
      {aliases.length > 0 && (
        <div className="lw-rename__aliases">
          <p className="lw-dialog__label">Aliases (change a spelling to rename it too)</p>
          {aliases.map((a) => (
            <input key={a} className="lw-launch__input" aria-label={`Alias ${a}`} value={aliasEdit[a] ?? a}
              onChange={(e) => setAliasEdit((m) => ({ ...m, [a]: e.target.value }))} />
          ))}
        </div>
      )}
      <p className="lw-dialog__label">Look in</p>
      {SCOPES.map((s) => (
        <label key={s.id} className="lw-check">
          <input type="checkbox" checked={scope.has(s.id)}
            onChange={(e) => setScope((cur) => { const n = new Set(cur); if (e.target.checked) n.add(s.id); else n.delete(s.id); return n; })} />
          {s.label}
        </label>
      ))}
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!canPreview || busy} onClick={() => void runPreview()}>Preview changes</button>
      </div>
    </Modal>
  );
}
