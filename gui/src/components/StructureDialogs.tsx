import { useEffect, useState } from "react";
import { api } from "../backend/api";
import type { DetailsPatch, EntitySummary, PartSummary, SceneDetails, TrashItem } from "../data/types";
import { SUGGESTED_STATUS } from "../data/sceneFacts";
import { restoredText } from "../data/restoreText";
import { Modal } from "./Dialogs";

/** Pick a part (or the top level) for a scene to move into. */
export function PartPickerDialog({ title, message, parts, allowTop, onPick, onClose }: {
  title: string; message: string; parts: PartSummary[]; allowTop: boolean;
  onPick: (partId: string | null) => void; onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="lw-dialog__message">{message}</p>
      <div className="lw-picklist" role="listbox" aria-label="Parts">
        {parts.map((p) => (
          <button key={p.id} role="option" aria-selected={false} className="lw-picklist__row" onClick={() => onPick(p.id)}>
            <span>{p.title}</span><span className="lw-mono lw-faint">{p.sceneIds.length}</span>
          </button>
        ))}
        {allowTop && (
          <button role="option" aria-selected={false} className="lw-picklist__row" onClick={() => onPick(null)}>
            <span>No part (top level)</span>
          </button>
        )}
        {parts.length === 0 && !allowTop && <p className="lw-empty">There are no parts yet.</p>}
      </div>
      <div className="lw-dialog__buttons"><button className="lw-btn" onClick={onClose}>Cancel</button></div>
    </Modal>
  );
}

/**
 * The Trash: deleted scenes and research notes wait here. Restore puts a scene back
 * at the end of its original part (Unplaced if the part is gone) and a research
 * note at its original path (research/ if its folder is gone); nothing is removed
 * for good without the confirmation shown here.
 */
export function TrashDialog({ onClose, onRestored, onChanged, notify }: {
  onClose: () => void; onRestored: (id: string) => void; onChanged: () => void;
  notify: (text: string, tone?: "info" | "error") => void;
}) {
  const [items, setItems] = useState<TrashItem[] | null>(null);
  const [ask, setAsk] = useState<{ kind: "one"; item: TrashItem } | { kind: "all" } | null>(null);
  const [rev, setRev] = useState(0);
  const reload = () => setRev((n) => n + 1);
  useEffect(() => {
    let live = true;
    void api.listTrash().then((r) => {
      if (!live) return;
      if (r.ok) setItems(r.items); else notify(r.error, "error");
    });
    return () => { live = false; };
  }, [rev, notify]);

  const restore = async (it: TrashItem) => {
    const r = await api.restoreTrash(it.name);
    if (!r.ok) return notify(r.error, "error");
    notify(restoredText(it.title, r));
    onChanged();
    if (r.kind !== "inspiration") onRestored(r.id);   // a picture is not a document to open
    reload();
  };
  const forever = async (it: TrashItem) => {
    setAsk(null);
    const r = await api.deleteForever(it.name);
    if (!r.ok) return notify(r.error, "error");
    onChanged();
    reload();
  };
  const empty = async () => {
    setAsk(null);
    const r = await api.emptyTrash();
    if (!r.ok) return notify(r.error, "error");
    notify(`Emptied the Trash (${r.deleted}).`);
    onChanged();
    reload();
  };

  if (ask) {
    const one = ask.kind === "one" ? ask.item : null;
    return (
      <Modal title={one ? "Delete forever" : "Empty the Trash"} onClose={() => setAsk(null)}>
        <p className="lw-dialog__message">
          {one ? <>Delete “{one.title}” forever? </> : <>Delete all {items?.length} {items?.length === 1 ? "item" : "items"} in the Trash forever? </>}
          This cannot be undone.
        </p>
        <div className="lw-dialog__buttons">
          <button className="lw-btn" autoFocus onClick={() => setAsk(null)}>Cancel</button>
          <button className="lw-btn lw-btn--danger" onClick={() => void (one ? forever(one) : empty())}>
            {one ? "Delete forever" : "Empty Trash"}
          </button>
        </div>
      </Modal>
    );
  }
  return (
    <Modal title="Trash" wide onClose={onClose}>
      <p className="lw-dialog__message">Deleted scenes, research notes and inspiration pictures are kept here until you delete them forever.</p>
      <div className="lw-picklist lw-picklist--tall">
        {items === null && <p className="lw-empty">Loading…</p>}
        {items?.length === 0 && <p className="lw-empty">The Trash is empty.</p>}
        {items?.map((it) => (
          <div key={it.name} className="lw-picklist__row lw-picklist__row--static">
            <span className="lw-picklist__main">
              <strong>{it.title}</strong>
              <span className="lw-faint">{it.kind === "inspiration" ? "inspiration picture" : <>{it.kind === "research" ? "research note · " : ""}from {it.original}</>} · deleted {it.deleted}</span>
            </span>
            <span className="lw-row lw-gap-6">
              <button className="lw-btn" onClick={() => void restore(it)}>Restore</button>
              <button className="lw-btn lw-btn--danger" onClick={() => setAsk({ kind: "one", item: it })}>Delete forever</button>
            </span>
          </div>
        ))}
      </div>
      <div className="lw-dialog__buttons lw-dialog__buttons--split">
        <button className="lw-btn lw-btn--danger" disabled={!items?.length} onClick={() => setAsk({ kind: "all" })}>Empty Trash</button>
        <button className="lw-btn" autoFocus onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}

/** Status, POV, place, purpose and word target of a scene. Saved into its frontmatter by the caller. */
export function DetailsDialog({ details, entities, onSave, onClose, unit }: {
  details: SceneDetails; entities: EntitySummary[]; unit: string;
  onSave: (patch: DetailsPatch) => void; onClose: () => void;
}) {
  const [status, setStatus] = useState(details.status);
  const [pov, setPov] = useState(details.pov);
  const [place, setPlace] = useState(details.place);
  const [purpose, setPurpose] = useState(details.purpose);
  const [target, setTarget] = useState(details.target ? String(details.target) : "");
  const bad = target.trim() !== "" && !/^\d[\d,]*$/.test(target.trim());
  const submit = () => {
    if (bad) return;
    onSave({ status, pov, place, purpose, target: target.trim() === "" ? null : target.trim() });
  };
  const names = (types: string[]) => entities.filter((e) => types.includes(e.type)).map((e) => e.name);
  return (
    <Modal title={`${unit[0].toUpperCase()}${unit.slice(1)} details`} onClose={onClose}>
      <label className="lw-dialog__label">Status
        <input autoFocus className="lw-launch__input" list="lw-status-options" value={status} placeholder="idea, draft, revising, done, or your own"
          onChange={(e) => setStatus(e.target.value)} />
        <datalist id="lw-status-options">{SUGGESTED_STATUS.map((s) => <option key={s} value={s} />)}</datalist>
      </label>
      <div className="lw-row lw-gap-8 lw-details__pair">
        <label className="lw-dialog__label lw-grow">POV
          <input className="lw-launch__input" list="lw-pov-options" value={pov} placeholder="a character, or any name"
            onChange={(e) => setPov(e.target.value)} />
          <datalist id="lw-pov-options">{names(["character"]).map((n) => <option key={n} value={n} />)}</datalist>
        </label>
        <label className="lw-dialog__label lw-grow">Place
          <input className="lw-launch__input" list="lw-place-options" value={place} placeholder="a place, or any name"
            onChange={(e) => setPlace(e.target.value)} />
          <datalist id="lw-place-options">{names(["place"]).map((n) => <option key={n} value={n} />)}</datalist>
        </label>
      </div>
      <label className="lw-dialog__label">{unit[0].toUpperCase()}{unit.slice(1)} purpose
        <textarea className="lw-launch__input lw-details__purpose" rows={3} value={purpose} onChange={(e) => setPurpose(e.target.value)}
          placeholder="What this is for in the story" />
      </label>
      <label className="lw-dialog__label">Target words
        <input className="lw-launch__input" inputMode="numeric" value={target} placeholder="blank for none"
          aria-invalid={bad} onChange={(e) => setTarget(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
        {bad && <span className="lw-details__error">A number of words, like 2400.</span>}
      </label>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={bad} onClick={submit}>Save</button>
      </div>
    </Modal>
  );
}
