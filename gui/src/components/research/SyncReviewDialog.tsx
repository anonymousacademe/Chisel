import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../backend/api";
import {
  SYNC_ACTION_LABEL, blockedReason, collectionDepth, collectionName, filterCollections, filterSyncRows,
  type SyncApplied, type SyncPlan, type ZoteroCollection,
} from "../../data/research";
import { Modal } from "../Dialogs";

type Notify = (text: string, tone?: "info" | "error") => void;

/** Review what a Zotero sync would change. Preview never writes; only the Apply button does, with only the ticked rows. */
export function SyncReviewDialog({ onClose, notify, onApplied }: { onClose: () => void; notify: Notify; onApplied: () => void }) {
  const [collections, setCollections] = useState<ZoteroCollection[] | null>(null);
  const [filter, setFilter] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());   // ticked collections; none = whole library
  const [saved, setSaved] = useState<string[]>([]);               // the selection of the last successful sync
  const [subs, setSubs] = useState(true);
  const [plan, setPlan] = useState<SyncPlan | null>(null);
  const [on, setOn] = useState<Set<string>>(new Set());
  const [rowFilter, setRowFilter] = useState("");
  const [phase, setPhase] = useState<"idle" | "previewing" | "applying">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [cancelled, setCancelled] = useState(false);
  const [done, setDone] = useState<SyncApplied | null>(null);
  const run = useRef(0);       // a preview whose number is no longer current was cancelled: its answer is dropped
  const busy = phase !== "idle";

  useEffect(() => {
    let live = true;
    void (async () => {
      const [r, sv] = await Promise.all([api.zoteroCollections(), api.zoteroSavedCollections()]);
      if (!live) return;
      if (!r.ok) { notify(r.error, "error"); setCollections([]); return; }
      setCollections(r.collections);
      if (sv.ok) {
        const known = new Set(r.collections.map((c) => c.key));
        const keys = sv.keys.filter((k) => known.has(k));
        setSaved(keys);
        setPicked(new Set(keys));
      }
    })();
    return () => { live = false; };
  }, [notify]);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const shown = useMemo(() => filterCollections(collections ?? [], filter), [collections, filter]);
  const rows = useMemo(() => (plan ? filterSyncRows(plan.rows, rowFilter) : []), [plan, rowFilter]);
  const again = saved.length > 0 && saved.length === picked.size && saved.every((k) => picked.has(k));

  const togglePick = (key: string) => setPicked((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  const pickShown = () => setPicked((s) => new Set([...s, ...shown.map((c) => c.key)]));

  const preview = async () => {
    const id = ++run.current;
    setPhase("previewing"); setElapsed(0); setDone(null); setCancelled(false);
    const keys = [...picked];
    const r = await api.zoteroSyncPlan(keys.length ? { collections: keys, includeSubcollections: subs } : {});
    if (id !== run.current) return;      // cancelled meanwhile: the late answer is discarded
    setPhase("idle");
    if (!r.ok) return notify(r.error, "error");
    setPlan(r); setRowFilter("");
    setOn(new Set(r.rows.filter((x) => !blockedReason(x)).map((x) => x.id)));
  };
  const cancelPreview = () => { run.current++; setPhase("idle"); setCancelled(true); };
  const toggle = (id: string) => setOn((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const setShownRows = (ticked: boolean) => setOn((s) => {
    const n = new Set(s);
    for (const r of rows) { if (blockedReason(r)) continue; if (ticked) n.add(r.id); else n.delete(r.id); }
    return n;
  });

  const apply = async () => {
    if (!plan) return;
    const ticked = plan.rows.filter((x) => on.has(x.id) && !blockedReason(x)).map((x) => x.id);
    if (!ticked.length) return;
    setPhase("applying"); setElapsed(0);
    const r = await api.zoteroSyncApply(ticked);
    setPhase("idle");
    if (!r.ok) return notify(r.error, "error");
    setDone(r); setPlan(null); setOn(new Set());
    if (picked.size) setSaved([...picked]);
    notify(`${r.changed.length} source${r.changed.length === 1 ? "" : "s"} updated.`);
    onApplied();
  };

  const count = plan ? plan.rows.filter((x) => on.has(x.id) && !blockedReason(x)).length : 0;
  const total = plan ? plan.rows.length : 0;
  const n = picked.size;

  return (
    <Modal title="Sync sources from Zotero" wide onClose={onClose}>
      <p className="lw-dialog__message">
        Tick the collections to read (none ticked reads the whole library), then preview. Nothing is changed until you press Apply,
        and only the ticked rows are applied. Papers added to a ticked collection later arrive the next time you sync it.
      </p>
      <div className="lw-row lw-gap-8">
        <input className="lw-launch__input" value={filter} onChange={(e) => setFilter(e.target.value)} disabled={collections === null || busy}
          placeholder="Type to filter collections" aria-label="Filter collections" spellCheck={false} />
        <button className="lw-btn" disabled={busy || shown.length === 0} onClick={pickShown}>Select all shown</button>
        <button className="lw-btn" disabled={busy || n === 0} onClick={() => setPicked(new Set())}>Clear</button>
      </div>
      <div className="lw-review" role="group" aria-label="Collections">
        {shown.map((c) => (
          <label key={c.key} className="lw-review__row" style={{ paddingLeft: 10 + (filter.trim() ? 0 : collectionDepth(c, collections ?? []) * 18) }}>
            <input type="checkbox" checked={picked.has(c.key)} disabled={busy} onChange={() => togglePick(c.key)} />
            <span className="lw-review__text">{filter.trim() ? c.path : collectionName(c)}{c.items != null && <span className="lw-faint"> ({c.items})</span>}</span>
          </label>
        ))}
        {collections !== null && filter.trim() && shown.length === 0 && <p className="lw-faint">No collection matches.</p>}
      </div>
      <div className="lw-row lw-gap-8">
        <label className="lw-review__text">
          <input type="checkbox" checked={subs} disabled={busy} onChange={(e) => setSubs(e.target.checked)} /> Include subcollections
        </label>
        <span className="lw-faint">{n === 0 ? "Whole library" : `${n} collection${n === 1 ? "" : "s"} selected`}</span>
      </div>
      <div className="lw-row lw-gap-8">
        <button className="lw-btn" disabled={busy} onClick={() => void preview()}>{again ? "Sync again" : "Preview changes"}</button>
        {phase === "previewing" && <button className="lw-btn" onClick={cancelPreview}>Cancel preview</button>}
      </div>

      {busy && (
        <p className="lw-dialog__message" role="status">
          <span className="lw-spinner" aria-hidden="true" />
          {phase === "previewing" ? "Reading Zotero... the first read can take a minute" : "Applying the ticked changes..."}
          {elapsed >= 5 && <span className="lw-faint"> ({elapsed} s)</span>}
        </p>
      )}
      {cancelled && !busy && <p className="lw-dialog__message">Preview cancelled. Nothing was written.</p>}

      {plan && (
        <>
          {plan.report.map((line, i) => <p key={i} className="lw-dialog__message">{line}</p>)}
          {plan.rows.length === 0 ? <p className="lw-dialog__message">Nothing to change.</p> : (
            <>
              <div className="lw-row lw-gap-8">
                <input className="lw-launch__input" value={rowFilter} onChange={(e) => setRowFilter(e.target.value)} disabled={busy}
                  placeholder="Search these papers" aria-label="Search papers" spellCheck={false} />
                <button className="lw-btn" disabled={busy} onClick={() => setShownRows(true)}>Select all</button>
                <button className="lw-btn" disabled={busy} onClick={() => setShownRows(false)}>Select none</button>
                <span className="lw-faint" role="status">{count} of {total} selected</span>
              </div>
              <div className="lw-review">
                {rows.map((r) => {
                  const why = blockedReason(r);
                  return (
                    <label key={r.id} className="lw-review__row">
                      <input type="checkbox" checked={on.has(r.id)} disabled={!!why || busy} onChange={() => toggle(r.id)} />
                      <span className="lw-review__text">
                        <span className="lw-review__target">{SYNC_ACTION_LABEL[r.action] ?? r.action}: {r.summary}</span>
                        {why && <span className="lw-faint">Not applied: {why}</span>}
                      </span>
                    </label>
                  );
                })}
                {rows.length === 0 && <p className="lw-faint">No paper matches.</p>}
              </div>
            </>
          )}
        </>
      )}

      {done && (
        <div className="lw-dialog__message">
          <p>{done.changed.length} changed{done.skipped.length ? `, ${done.skipped.length} skipped` : ""}.</p>
          {done.skipped.length > 0 && <ul>{done.skipped.map((s) => <li key={s.id}>{s.id}: {s.reason}</li>)}</ul>}
          {!done.recorded && <p>The sync could not be recorded, so the next preview may list these again.</p>}
        </div>
      )}

      <div className="lw-dialog__buttons">
        <button className="lw-btn" disabled={phase === "applying"} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
        {plan && plan.rows.length > 0 && (
          <button className="lw-btn lw-btn--primary" disabled={busy || count === 0} onClick={() => void apply()}>
            {count === 1 ? "Apply 1 change" : `Apply ${count} changes`}
          </button>
        )}
      </div>
    </Modal>
  );
}
