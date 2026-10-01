import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../backend/api";
import type { DiffSegment, SnapshotRow } from "../data/types";
import { agoText, deltaText, identical, labelText, sides, whenText } from "../data/snapshots";
import { Modal } from "./Dialogs";

type Ask = { kind: "restore" | "delete"; row: SnapshotRow };
type Compare = { row: SnapshotRow; segments: DiffSegment[]; added: number; removed: number };

/**
 * History of the open scene: take snapshots (this scene, or every scene),
 * compare one with the text as it is now, restore it (the current text is
 * snapshotted first, so a restore can be undone) or delete it.
 */
export function SnapshotsDialog({ docId, title, unit, getText, onClose, onRestore, onChanged, notify }: {
  docId: string; title: string; unit: string; getText: () => string;
  onClose: () => void;
  /** Restore snapshot *id*; resolves true when the scene was rewritten (the caller reopens it). */
  onRestore: (id: string) => Promise<boolean>;
  /** Latest snapshot time changed (status bar). */
  onChanged: (snapshotAt: string | null) => void;
  notify: (text: string, tone?: "info" | "error") => void;
}) {
  const [items, setItems] = useState<SnapshotRow[] | null>(null);
  const [label, setLabel] = useState("");
  const [ask, setAsk] = useState<Ask | null>(null);
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [busy, setBusy] = useState(false);
  const [rev, setRev] = useState(0);
  const reload = useCallback(() => setRev((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    void api.listSnapshots(docId, getText()).then((r) => {
      if (!live) return;
      if (r.ok) { setItems(r.items); onChanged(r.snapshotAt); } else notify(r.error, "error");
    });
    return () => { live = false; };
    // getText/onChanged/notify are stable enough per open; reload on rev
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, rev]);

  const snapScene = async () => {
    setBusy(true);
    const r = await api.createSnapshot(docId, label.trim(), getText());
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    notify(label.trim() ? `Snapshot “${label.trim()}” taken.` : "Snapshot taken.");
    setLabel(""); reload();
  };
  const snapAll = async () => {
    setBusy(true);
    const r = await api.snapshotAll(label.trim());
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    notify(`Snapshot taken of ${r.count} ${unit}${r.count === 1 ? "" : "s"}.`);
    setLabel(""); reload();
  };
  const compare = async (row: SnapshotRow) => {
    const r = await api.compareSnapshot(docId, row.id, getText());
    if (!r.ok) return notify(r.error, "error");
    setCmp({ row, segments: r.segments, added: r.added, removed: r.removed });
  };
  const remove = async (row: SnapshotRow) => {
    setAsk(null);
    const r = await api.deleteSnapshot(docId, row.id);
    if (!r.ok) return notify(r.error, "error");
    onChanged(r.snapshotAt); reload();
  };
  const restore = async (row: SnapshotRow) => {
    setAsk(null);
    setBusy(true);
    const ok = await onRestore(row.id);
    setBusy(false);
    if (ok) onClose();
  };

  if (ask) {
    const restoring = ask.kind === "restore";
    return (
      <Modal title={restoring ? "Restore this snapshot" : "Delete this snapshot"} onClose={() => setAsk(null)}>
        <p className="lw-dialog__message">
          {restoring
            ? <>Replace “{title}” with the snapshot from {whenText(ask.row.when)}? The text as it is now is snapshotted first (“Before a restore”), so you can come back to it.</>
            : <>Delete the snapshot from {whenText(ask.row.when)}? This cannot be undone.</>}
        </p>
        <div className="lw-dialog__buttons">
          <button className="lw-btn" autoFocus onClick={() => setAsk(null)}>Cancel</button>
          <button className={`lw-btn lw-btn--${restoring ? "primary" : "danger"}`}
            onClick={() => void (restoring ? restore(ask.row) : remove(ask.row))}>{restoring ? "Restore" : "Delete"}</button>
        </div>
      </Modal>
    );
  }
  if (cmp) return <CompareView cmp={cmp} onBack={() => setCmp(null)} onClose={onClose}
    onRestore={() => setAsk({ kind: "restore", row: cmp.row })} />;

  return (
    <Modal title={`History: ${title}`} wide onClose={onClose}>
      <div className="lw-row lw-gap-8">
        <input className="lw-launch__input lw-grow" value={label} placeholder="Label (optional), e.g. before the rewrite"
          onChange={(e) => setLabel(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void snapScene(); }} />
        <button className="lw-btn lw-btn--primary" disabled={busy} onClick={() => void snapScene()}>Snapshot this {unit}</button>
        <button className="lw-btn" disabled={busy} title={`One snapshot of every ${unit}, all with this label`} onClick={() => void snapAll()}>Snapshot all</button>
      </div>
      <div className="lw-picklist lw-picklist--tall" aria-label="Snapshots">
        {items === null && <p className="lw-empty">Loading…</p>}
        {items?.length === 0 && <p className="lw-empty">No snapshots of this {unit} yet.</p>}
        {items?.map((it) => (
          <div key={it.id} className="lw-picklist__row lw-picklist__row--static">
            <span className="lw-picklist__main">
              <strong>{labelText(it.label)}</strong>
              <span className="lw-faint">{whenText(it.when)} · {agoText(it.when)} · {it.words} words ({deltaText(it.delta)} now)</span>
            </span>
            <span className="lw-row lw-gap-6">
              <button className="lw-btn" onClick={() => void compare(it)}>Compare</button>
              <button className="lw-btn" onClick={() => setAsk({ kind: "restore", row: it })}>Restore</button>
              <button className="lw-btn lw-btn--danger" onClick={() => setAsk({ kind: "delete", row: it })}>Delete</button>
            </span>
          </div>
        ))}
      </div>
      <div className="lw-dialog__buttons"><button className="lw-btn" autoFocus onClick={onClose}>Close</button></div>
    </Modal>
  );
}

/** Snapshot on the left (removed words marked), the text now on the right (added words marked). */
function CompareView({ cmp, onBack, onClose, onRestore }: {
  cmp: Compare; onBack: () => void; onClose: () => void; onRestore: () => void;
}) {
  const { left, right } = sides(cmp.segments);
  const a = useRef<HTMLDivElement>(null), b = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);
  // open on the first change, not on the top of a long scene
  useEffect(() => {
    for (const box of [a.current, b.current]) {
      const mark = box?.querySelector("del, ins") as HTMLElement | null;
      if (box && mark) box.scrollTop = Math.max(0, mark.offsetTop - box.offsetTop - box.clientHeight / 3);
    }
  }, []);
  const sync = (from: HTMLDivElement | null, to: HTMLDivElement | null) => {
    if (!from || !to || syncing.current) return;
    syncing.current = true;
    const max = from.scrollHeight - from.clientHeight;
    to.scrollTop = max > 0 ? (from.scrollTop / max) * (to.scrollHeight - to.clientHeight) : 0;
    requestAnimationFrame(() => { syncing.current = false; });
  };
  return (
    <Modal title={`Compare: ${labelText(cmp.row.label)}`} wide onClose={onClose}>
      <p className="lw-dialog__message">
        {identical(cmp.segments)
          ? "The text is the same as this snapshot."
          : <>{cmp.added} word{cmp.added === 1 ? "" : "s"} added, {cmp.removed} removed since {whenText(cmp.row.when)}.</>}
      </p>
      <div className="lw-diff">
        <div className="lw-diff__col">
          <span className="lw-diff__head">Snapshot · {agoText(cmp.row.when)}</span>
          <div ref={a} className="lw-diff__text" onScroll={() => sync(a.current, b.current)}>
            {left.map((p, i) => p.mark ? <del key={i}>{p.text}</del> : <span key={i}>{p.text}</span>)}
          </div>
        </div>
        <div className="lw-diff__col">
          <span className="lw-diff__head">Now</span>
          <div ref={b} className="lw-diff__text" onScroll={() => sync(b.current, a.current)}>
            {right.map((p, i) => p.mark ? <ins key={i}>{p.text}</ins> : <span key={i}>{p.text}</span>)}
          </div>
        </div>
      </div>
      <div className="lw-dialog__buttons lw-dialog__buttons--split">
        <button className="lw-btn" onClick={onBack}>Back to the list</button>
        <span className="lw-row lw-gap-8">
          <button className="lw-btn lw-btn--primary" onClick={onRestore}>Restore this snapshot</button>
          <button className="lw-btn" autoFocus onClick={onClose}>Close</button>
        </span>
      </div>
    </Modal>
  );
}
