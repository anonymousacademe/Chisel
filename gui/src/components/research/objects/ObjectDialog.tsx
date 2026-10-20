import { useCallback, useEffect, useState } from "react";
import { api } from "../../../backend/api";
import { usedIn, type Grid } from "../../../data/objects";
import { OBJECT_NAMES, type BuiltTable, type ObjectRefs, type ObjectRender, type TableAlign } from "../../../data/research";
import { ConfirmDialog, Modal } from "../../Dialogs";
import { FigureScript } from "./FigureScript";
import { KatexView } from "./KatexView";
import { TableGridEditor } from "./TableGridEditor";

type Notify = (text: string, tone?: "info" | "error") => void;

const STATUS_WORDS: Record<string, string> = {
  current: "Up to date", stale: "Out of date: rebuild or run it again", failed: "The last build failed", missing: "A file is missing",
};

/** The card of one figure, table or equation: preview, caption and the rest of its details, where it is used, and for
 *  generated figures and tables the script or data flow. Python validates and writes every change. */
export function ObjectDialog({ id, notify, onClose, onChanged, pollMs }: {
  id: string; notify: Notify; onClose: () => void;
  /** The object changed or went to the Trash: refresh the binder and the open section's widgets. */
  onChanged: () => void;
  pollMs?: number;
}) {
  const [obj, setObj] = useState<ObjectRender | null>(null);
  const [refs, setRefs] = useState<ObjectRefs | null>(null);
  const [caption, setCaption] = useState("");
  const [alt, setAlt] = useState("");
  const [width, setWidth] = useState("");
  const [latex, setLatex] = useState("");
  const [grid, setGrid] = useState<Grid | null>(null);
  const [mtime, setMtime] = useState("");
  const [conflict, setConflict] = useState(false);
  const [dirtyGrid, setDirtyGrid] = useState(false);
  const [built, setBuilt] = useState<BuiltTable | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tableError, setTableError] = useState("");
  const [refsFailed, setRefsFailed] = useState(false);
  const [runJob, setRunJob] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);

  const load = useCallback(async () => {
    const r = await api.objectRender([id]);
    const o = r.ok ? r.objects[0] : undefined;
    if (!r.ok || !o || o.error) { setError(r.ok ? o?.error ?? "No such object." : r.error); return; }
    setError(""); setObj(o);
    setCaption(o.caption); setAlt(o.alt ?? ""); setWidth(o.width ? String(o.width) : ""); setLatex(o.latex ?? "");
    if (o.kind === "tbl") {
      const t = await api.readTable(id);
      if (t.ok) { setGrid({ cells: t.cells, align: t.align as TableAlign[] }); setMtime(t.mtime); setConflict(false); setDirtyGrid(false); setTableError(""); }
      else setTableError(t.error);
    }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void api.objectReferences(id).then((r) => { if (r.ok) setRefs(r); else setRefsFailed(true); }); }, [id]);

  /** Closing while a script runs asks first: yes stops it (the script card cancels on unmount), no keeps the card open. */
  const requestClose = () => { if (runJob) setConfirmClose(true); else onClose(); };

  if (error) {
    return (
      <Modal title="Object" onClose={requestClose}>
        <p className="lw-eq__error" role="alert">{error}</p>
        <div className="lw-dialog__buttons"><button className="lw-btn" onClick={onClose}>Close</button></div>
      </Modal>
    );
  }
  if (!obj) return <Modal title="Object" onClose={requestClose}><p className="lw-faint">Loading…</p></Modal>;

  const name = obj.number ?? `${OBJECT_NAMES[obj.kind]} (not placed yet)`;
  const widthNum = width.trim() === "" ? null : Number(width);
  const widthBad = widthNum !== null && !(widthNum >= 1 && widthNum <= 20);
  const detailsChanged = caption !== obj.caption
    || (obj.kind === "fig" && (alt !== (obj.alt ?? "") || (widthNum !== null && widthNum !== (obj.width ?? null))))
    || (obj.kind === "eq" && latex.trim() !== (obj.latex ?? "").trim());
  const generatedTable = obj.kind === "tbl" && !!obj.generated;
  const count = refs?.placements.length ?? 0;

  const saveDetails = async () => {
    if (busy || widthBad) return;
    setBusy(true);
    const patch = obj.kind === "fig"
      ? { caption, alt, ...(widthNum !== null ? { width: widthNum } : {}) }
      : obj.kind === "eq" ? { caption, latex: latex.trim() } : { caption };
    const r = await api.updateObject(id, patch);
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    notify("Saved.");
    onChanged();
    await refreshDetails();
  };
  /** After a details save: update the details fields and the base mtime only. A grid with unsaved edits is kept as it is,
   *  and the new mtime keeps the next Save table from reporting a conflict the caption write itself caused. */
  const refreshDetails = async () => {
    const r = await api.objectRender([id], false);
    const o = r.ok ? r.objects[0] : undefined;
    if (!r.ok || !o || o.error) return;
    setObj((prev) => ({ ...o, imageUrl: prev?.imageUrl }));
    setCaption(o.caption); setAlt(o.alt ?? ""); setWidth(o.width ? String(o.width) : ""); setLatex(o.latex ?? "");
    if (o.kind === "tbl" && o.mtime) setMtime(o.mtime);
  };
  const saveGrid = async () => {
    if (!grid || busy) return;
    setBusy(true);
    const r = await api.saveTable(id, grid.cells, grid.align, mtime);
    setBusy(false);
    if (!r.ok) {
      if ((r as { conflict?: boolean }).conflict) { setConflict(true); return; }
      return notify(r.error, "error");
    }
    setMtime(r.mtime); setDirtyGrid(false); setConflict(false);
    notify("Table saved.");
    onChanged();
  };
  const preview = async () => {
    const r = await api.buildTable(id);
    if (!r.ok) return notify(r.error, "error");
    setBuilt(r);
  };
  const applyBuilt = async () => {
    const r = await api.applyTable(id);
    if (!r.ok) return notify(r.error, "error");
    setBuilt(null);
    notify("The table was rebuilt from the data.");
    onChanged();
    void load();
  };
  const del = async () => {
    setConfirmDelete(false);
    const r = await api.trashObject(id);
    if (!r.ok) return notify(r.error, "error");
    notify(`${name} went to the Trash.`);
    onChanged();
    onClose();
  };

  return (
    <>
      <Modal title={name} wide onClose={requestClose}>
        <p className="lw-faint lw-obj__meta">
          <span className="lw-mono">{id}</span> · {STATUS_WORDS[obj.status] ?? obj.status}
          {obj.source !== "static" && <> · {obj.kind === "fig" ? "Made by a script" : "Built from data"}</>}
        </p>

        {obj.kind === "fig" && (
          obj.imageUrl
            ? <img className="lw-obj__image" src={obj.imageUrl} alt={obj.alt || obj.caption || obj.label} />
            : <p className="lw-faint">{obj.source === "script" ? "No picture yet: run the script below." : "The picture file is missing."}</p>
        )}
        {obj.kind === "eq" && <KatexView latex={latex} />}
        {obj.kind === "tbl" && !grid && tableError && <p className="lw-eq__error" role="alert">{tableError}</p>}
        {obj.kind === "tbl" && grid && (
          <>
            <TableGridEditor grid={grid} readOnly={generatedTable} onChange={(g) => { setGrid(g); setDirtyGrid(true); }} />
            {tableError && <p className="lw-eq__error" role="alert">{tableError}</p>}
            {conflict && (
              <p role="alert" className="lw-eq__error">
                This table changed on disk since you opened it. <button className="lw-link" onClick={() => void load()}>Reload it</button> before saving (your edits here will be lost).
              </p>
            )}
            {!generatedTable && <div className="lw-row"><button className="lw-btn" disabled={!dirtyGrid || busy} onClick={() => void saveGrid()}>Save table</button></div>}
          </>
        )}

        <label className="lw-dialog__label">Caption
          <textarea className="lw-launch__input lw-obj__area" rows={2} value={caption} onChange={(e) => setCaption(e.target.value)} aria-label="Caption" />
        </label>
        {obj.kind === "fig" && (
          <div className="lw-row lw-gap-8">
            <label className="lw-dialog__label lw-btn--grow">Alt text (for readers who cannot see the picture)
              <input className="lw-launch__input" value={alt} onChange={(e) => setAlt(e.target.value)} aria-label="Alt text" />
            </label>
            <label className="lw-dialog__label">Width (inches)
              <input className="lw-launch__input lw-obj__num" inputMode="decimal" value={width} onChange={(e) => setWidth(e.target.value)} aria-label="Width in inches" placeholder="auto" />
            </label>
          </div>
        )}
        {widthBad && <p className="lw-eq__error" role="alert">Width is 1 to 20 inches.</p>}
        {obj.kind === "eq" && (
          <label className="lw-dialog__label">LaTeX
            <textarea className="lw-launch__input lw-mono lw-obj__area" rows={3} value={latex} onChange={(e) => setLatex(e.target.value)} aria-label="LaTeX" spellCheck={false} />
          </label>
        )}
        <div className="lw-row"><button className="lw-btn" disabled={!detailsChanged || busy || widthBad || (obj.kind === "eq" && !latex.trim())} onClick={() => void saveDetails()}>Save details</button></div>

        {obj.kind === "fig" && obj.source === "script" && <FigureScript id={id} notify={notify} pollMs={pollMs} onRunning={setRunJob} onRan={() => { onChanged(); void load(); }} />}

        {generatedTable && (
          <section aria-label="Rebuild from the data">
            <h3>Data</h3>
            <p className="lw-faint">This table is built from a data file and its format. Edit those, then rebuild.</p>
            <div className="lw-row"><button className="lw-btn" onClick={() => void preview()}>Rebuild from the data</button></div>
            {built && (
              <div className="lw-obj__proposal" aria-label="Rebuilt table preview">
                <TableGridEditor grid={{ cells: built.grid, align: (built.grid[0] ?? []).map(() => "default" as TableAlign) }} readOnly onChange={() => {}} />
                {built.warnings.map((w) => <p key={w} className="lw-faint">{w}</p>)}
                <div className="lw-row lw-gap-8">
                  <button className="lw-btn lw-btn--primary" onClick={() => void applyBuilt()}>Use the rebuilt table</button>
                  <button className="lw-btn" onClick={() => setBuilt(null)}>Discard</button>
                </div>
              </div>
            )}
          </section>
        )}

        <section aria-label="Where it is used">
          <h3>Where it is used</h3>
          {!refs && !refsFailed && <p className="lw-faint">Looking…</p>}
          {refsFailed && <p className="lw-eq__error" role="alert">Chisel could not check where it is used.</p>}
          {refs && (
            <>
              <p className="lw-faint">{usedIn(refs.placements.length)}</p>
              <ul className="lw-obj__uses">
                {refs.placements.map((u) => <li key={`p${u.doc}:${u.row}`}>{u.title} <span className="lw-faint">(placed, line {u.row + 1})</span></li>)}
                {refs.refs.map((u) => <li key={`r${u.doc}:${u.row}`}>{u.title} <span className="lw-faint">(mentioned, line {u.row + 1})</span></li>)}
              </ul>
            </>
          )}
        </section>

        <div className="lw-dialog__buttons lw-dialog__buttons--split">
          <button className="lw-btn lw-btn--danger" disabled={!refs && !refsFailed} onClick={() => setConfirmDelete(true)}>Delete…</button>
          <button className="lw-btn" onClick={requestClose}>Close</button>
        </div>
      </Modal>
      {confirmClose && (
        <ConfirmDialog title="Stop the run?" confirm="Stop the run"
          message="The script is still running. Closing this card stops it, and the old picture stays as it is."
          onConfirm={() => { setConfirmClose(false); onClose(); }} onClose={() => setConfirmClose(false)} />
      )}
      {confirmDelete && (
        <ConfirmDialog title={`Delete ${name}`} confirm="Move to Trash"
          message={<>{name} goes to the Trash; you can restore it from there. {refsFailed ? "Chisel could not check which sections place it." : count === 0 ? "No section places it." : `${count} section${count === 1 ? " places" : "s place"} it: those lines will show as unresolved until it is restored.`}</>}
          onConfirm={() => void del()} onClose={() => setConfirmDelete(false)} />
      )}
    </>
  );
}
