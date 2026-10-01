import { useState } from "react";
import { Trash2 } from "lucide-react";
import type { CollectionColor, CollectionSummary } from "../data/types";
import { COLLECTION_COLORS, swatchVar } from "../data/collections";
import { Icon } from "./primitives";
import { ConfirmDialog, Modal } from "./Dialogs";

function Swatches({ value, onPick, label }: { value: CollectionColor; onPick: (c: CollectionColor) => void; label: string }) {
  return (
    <span className="lw-swatches" role="radiogroup" aria-label={label}>
      {COLLECTION_COLORS.map((c) => (
        <button key={c} role="radio" aria-checked={value === c} aria-label={c} title={c}
          className={`lw-swatch${value === c ? " is-on" : ""}`} style={{ background: swatchVar(c) }} onClick={() => onPick(c)} />
      ))}
    </span>
  );
}

/**
 * Add, rename, recolour and delete collections. Every call goes to the host, which
 * flushes the open scene first (rename and delete rewrite the member scenes' files)
 * and refreshes `collections`; each returns whether it worked.
 */
export function CollectionsManager({ collections, unit, onCreate, onRecolor, onRename, onDelete, onClose }: {
  collections: CollectionSummary[]; unit: string;
  onCreate: (name: string, color: CollectionColor) => Promise<boolean>;
  onRecolor: (name: string, color: CollectionColor) => Promise<boolean>;
  onRename: (name: string, to: string) => Promise<boolean>;
  onDelete: (name: string) => Promise<boolean>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [color, setColor] = useState<CollectionColor>("violet");
  const [editing, setEditing] = useState<{ name: string; value: string } | null>(null);
  const [ask, setAsk] = useState<CollectionSummary | null>(null);

  const add = async () => {
    if (!name.trim()) return;
    if (await onCreate(name.trim(), color)) setName("");
  };
  const rename = async () => {
    if (!editing) return;
    const to = editing.value.trim();
    if (!to || to === editing.name || await onRename(editing.name, to)) setEditing(null);
  };

  if (ask) {
    return (
      <ConfirmDialog title="Delete collection" confirm="Delete collection"
        message={<>Delete the collection “{ask.name}”? It is taken off its {ask.count} {unit}{ask.count === 1 ? "" : "s"}; no {unit} is deleted.</>}
        onConfirm={() => { const c = ask; setAsk(null); void onDelete(c.name); }} onClose={() => setAsk(null)} />
    );
  }
  return (
    <Modal title="Collections" wide onClose={onClose}>
      <p className="lw-dialog__message">Group {unit}s however you like (“Needs continuity pass”, “Mara’s arc”). A {unit} can be in several; click one in the binder to see only its members.</p>
      <div className="lw-picklist">
        {collections.length === 0 && <p className="lw-empty">No collections yet. Add one below.</p>}
        {collections.map((c) => (
          <div key={c.name} className="lw-picklist__row lw-picklist__row--static">
            <span className="lw-picklist__main">
              {editing?.name === c.name ? (
                <input autoFocus className="lw-launch__input" aria-label={`New name for ${c.name}`} value={editing.value}
                  onChange={(e) => setEditing({ name: c.name, value: e.target.value })}
                  onKeyDown={(e) => { if (e.key === "Enter") void rename(); else if (e.key === "Escape") { e.stopPropagation(); setEditing(null); } }}
                  onBlur={() => void rename()} />
              ) : (
                <button className="lw-link lw-collections__name" title="Rename" onClick={() => setEditing({ name: c.name, value: c.name })}>{c.name}</button>
              )}
              <span className="lw-faint">
                {c.count} {unit}{c.count === 1 ? "" : "s"}{c.declared ? "" : " · used by scenes, not yet defined: pick a colour to keep it"}
              </span>
            </span>
            <span className="lw-row lw-gap-8">
              <Swatches value={c.color} label={`Colour of ${c.name}`} onPick={(col) => void onRecolor(c.name, col)} />
              <button className="lw-iconbtn" aria-label={`Delete ${c.name}`} title="Delete collection" onClick={() => setAsk(c)}>
                <Icon icon={Trash2} size={14} stroke={1.6} />
              </button>
            </span>
          </div>
        ))}
      </div>
      <div className="lw-row lw-gap-8 lw-collections__add">
        <input className="lw-launch__input lw-grow" aria-label="New collection name" placeholder="New collection" value={name}
          onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void add(); }} />
        <Swatches value={color} label="Colour of the new collection" onPick={setColor} />
        <button className="lw-btn lw-btn--primary" disabled={!name.trim()} onClick={() => void add()}>Add</button>
      </div>
      <div className="lw-dialog__buttons"><button className="lw-btn" autoFocus onClick={onClose}>Close</button></div>
    </Modal>
  );
}

/** Tick the collections the open scene belongs to. */
export function SceneCollectionsDialog({ collections, current, title, onSave, onManage, onClose }: {
  collections: CollectionSummary[]; current: string[]; title: string;
  onSave: (names: string[]) => void; onManage: () => void; onClose: () => void;
}) {
  const [picked, setPicked] = useState(new Set(current));
  const flip = (n: string) => setPicked((s) => { const x = new Set(s); if (x.has(n)) x.delete(n); else x.add(n); return x; });
  // keep names the scene has that the project no longer lists
  const rows = [...collections, ...current.filter((n) => !collections.some((c) => c.name === n)).map((n): CollectionSummary =>
    ({ name: n, color: "gray", declared: false, count: 0, sceneIds: [] }))];
  return (
    <Modal title={`Collections · ${title}`} onClose={onClose}>
      <div className="lw-picklist" role="group" aria-label="Collections">
        {rows.length === 0 && <p className="lw-empty">No collections yet.</p>}
        {rows.map((c) => (
          <label key={c.name} className="lw-picklist__row lw-collections__check">
            <input type="checkbox" checked={picked.has(c.name)} onChange={() => flip(c.name)} />
            <span className="lw-collections__swatch" style={{ background: swatchVar(c.color) }} />
            <span className="lw-picklist__main">{c.name}</span>
          </label>
        ))}
      </div>
      <div className="lw-dialog__buttons lw-dialog__buttons--split">
        <button className="lw-btn" onClick={onManage}>Edit collections…</button>
        <span className="lw-row lw-gap-8">
          <button className="lw-btn" onClick={onClose}>Cancel</button>
          <button className="lw-btn lw-btn--primary" onClick={() => onSave(rows.map((c) => c.name).filter((n) => picked.has(n)))}>Save</button>
        </span>
      </div>
    </Modal>
  );
}
