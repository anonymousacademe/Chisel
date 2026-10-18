import { useEffect, useMemo, useState } from "react";
import { api } from "../../backend/api";
import { SYNC_ACTION_LABEL, blockedReason, filterCollections, type SyncApplied, type SyncPlan, type ZoteroCollection } from "../../data/research";
import { Modal } from "../Dialogs";

type Notify = (text: string, tone?: "info" | "error") => void;

/** Review what a Zotero sync would change. Preview never writes; only the Apply button does, with only the ticked rows. */
export function SyncReviewDialog({ onClose, notify, onApplied }: { onClose: () => void; notify: Notify; onApplied: () => void }) {
  const [collections, setCollections] = useState<ZoteroCollection[] | null>(null);
  const [filter, setFilter] = useState("");
  const [scope, setScope] = useState("");   // "" = whole library, else a collection key
  const [plan, setPlan] = useState<SyncPlan | null>(null);
  const [on, setOn] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<SyncApplied | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.zoteroCollections();
      if (!live) return;
      if (!r.ok) { notify(r.error, "error"); setCollections([]); } else setCollections(r.collections);
    })();
    return () => { live = false; };
  }, [notify]);

  const shown = useMemo(() => filterCollections(collections ?? [], filter), [collections, filter]);

  const preview = async () => {
    setBusy(true); setDone(null);
    const r = await api.zoteroSyncPlan(scope ? { collection: scope } : {});
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    setPlan(r);
    setOn(new Set(r.rows.filter((x) => !blockedReason(x)).map((x) => x.id)));
  };
  const toggle = (id: string) => setOn((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const apply = async () => {
    if (!plan) return;
    const ticked = plan.rows.filter((x) => on.has(x.id) && !blockedReason(x)).map((x) => x.id);
    if (!ticked.length) return;
    setBusy(true);
    const r = await api.zoteroSyncApply(ticked);
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    setDone(r); setPlan(null); setOn(new Set());
    notify(`${r.changed.length} source${r.changed.length === 1 ? "" : "s"} updated.`);
    onApplied();
  };

  const count = plan ? plan.rows.filter((x) => on.has(x.id) && !blockedReason(x)).length : 0;

  return (
    <Modal title="Sync sources from Zotero" wide onClose={onClose}>
      <p className="lw-dialog__message">
        Choose what to read, then preview. Nothing is changed until you press Apply, and only the ticked rows are applied.
      </p>
      <div className="lw-row lw-gap-8">
        <input className="lw-launch__input" value={filter} onChange={(e) => setFilter(e.target.value)} disabled={collections === null}
          placeholder="Type to filter collections" aria-label="Filter collections" spellCheck={false} />
      </div>
      <div className="lw-review" role="radiogroup" aria-label="Collection">
        <label className="lw-review__row">
          <input type="radio" name="zotero-scope" checked={scope === ""} onChange={() => setScope("")} />
          <span className="lw-review__text">Whole library</span>
        </label>
        {shown.map((c) => (
          <label key={c.key} className="lw-review__row">
            <input type="radio" name="zotero-scope" checked={scope === c.key} onChange={() => setScope(c.key)} />
            <span className="lw-review__text">{c.path}{c.items != null && <span className="lw-faint"> ({c.items})</span>}</span>
          </label>
        ))}
        {collections !== null && filter.trim() && shown.length === 0 && <p className="lw-faint">No collection matches.</p>}
      </div>
      <div className="lw-row lw-gap-8">
        <button className="lw-btn" disabled={busy} onClick={() => void preview()}>Preview changes</button>
      </div>

      {plan && (
        <>
          {plan.report.map((line, i) => <p key={i} className="lw-dialog__message">{line}</p>)}
          {plan.rows.length === 0 ? <p className="lw-dialog__message">Nothing to change.</p> : (
            <div className="lw-review">
              {plan.rows.map((r) => {
                const why = blockedReason(r);
                return (
                  <label key={r.id} className="lw-review__row">
                    <input type="checkbox" checked={on.has(r.id)} disabled={!!why} onChange={() => toggle(r.id)} />
                    <span className="lw-review__text">
                      <span className="lw-review__target">{SYNC_ACTION_LABEL[r.action] ?? r.action}: {r.summary}</span>
                      {why && <span className="lw-faint">Not applied: {why}</span>}
                    </span>
                  </label>
                );
              })}
            </div>
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
        <button className="lw-btn" onClick={onClose}>{done ? "Close" : "Cancel"}</button>
        {plan && plan.rows.length > 0 && (
          <button className="lw-btn lw-btn--primary" disabled={busy || count === 0} onClick={() => void apply()}>
            {count === 1 ? "Apply 1 change" : `Apply ${count} changes`}
          </button>
        )}
      </div>
    </Modal>
  );
}
