import { useRef, useState } from "react";
import { api } from "../../../backend/api";
import { blankGrid, figureFileProblem, fileStem, gridIsBlank, type Grid } from "../../../data/objects";
import { Modal } from "../../Dialogs";
import { KatexView } from "./KatexView";
import { LabelField, useSuggestedLabel } from "./useLabel";
import { TableGridEditor } from "./TableGridEditor";

type Notify = (text: string, tone?: "info" | "error") => void;

interface InsertProps {
  notify: Notify;
  onClose: () => void;
  /** The object exists: put its placement in the open section (App) and close. */
  onCreated: (id: string) => void;
}

const readAsDataUrl = (f: File) => new Promise<string>((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result));
  r.onerror = () => reject(new Error("The file could not be read."));
  r.readAsDataURL(f);
});

/** Insert a figure from a PNG or JPG: choose it or drop it here. Python checks the bytes and writes figures/. */
export function InsertFigureDialog({ notify, onClose, onCreated }: InsertProps) {
  const [file, setFile] = useState<{ name: string; dataUrl: string } | null>(null);
  const [problem, setProblem] = useState("");
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { label, setLabel } = useSuggestedLabel("fig", caption.trim() || (file ? fileStem(file.name) : ""));

  const take = async (f: File | undefined) => {
    if (!f) return;
    const p = figureFileProblem(f);
    setProblem(p);
    if (p) { setFile(null); return; }
    try { setFile({ name: f.name, dataUrl: await readAsDataUrl(f) }); } catch (e) { setProblem(String((e as Error).message)); }
  };
  const create = async () => {
    if (!file || !label.trim() || busy) return;
    setBusy(true);
    const r = await api.insertFigure(file.dataUrl, label.trim(), caption.trim());
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    onCreated(r.id);
  };
  return (
    <Modal title="Insert a figure" wide onClose={onClose}>
      <div className={`lw-drop${over ? " is-over" : ""}`} role="group" aria-label="Choose a picture"
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); void take(e.dataTransfer.files?.[0]); }}>
        {file ? <img className="lw-drop__preview" src={file.dataUrl} alt={`Preview of ${file.name}`} /> : <p className="lw-faint">Drop a PNG or JPG here, or choose one.</p>}
        <div className="lw-row lw-gap-8">
          <button type="button" className="lw-btn" onClick={() => input.current?.click()}>{file ? "Choose another…" : "Choose a picture…"}</button>
          {file && <span className="lw-mono lw-faint">{file.name}</span>}
        </div>
        <input ref={input} type="file" hidden accept="image/png,image/jpeg,.png,.jpg,.jpeg" aria-label="Picture file" onChange={(e) => void take(e.target.files?.[0])} />
        <p className="lw-faint lw-grid__hint">PNG or JPG, up to 10 MB.</p>
      </div>
      {problem && <p className="lw-eq__error" role="alert">{problem}</p>}
      <label className="lw-dialog__label">Caption
        <textarea className="lw-launch__input lw-obj__area" rows={2} value={caption} onChange={(e) => setCaption(e.target.value)} aria-label="Caption" />
      </label>
      <LabelField kind="fig" label={label} onChange={setLabel} />
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!file || !label.trim() || busy} onClick={() => void create()}>Insert figure</button>
      </div>
    </Modal>
  );
}

/** Insert a table: type it, or paste cells copied from a spreadsheet. */
export function InsertTableDialog({ notify, onClose, onCreated }: InsertProps) {
  const [grid, setGrid] = useState<Grid>(() => blankGrid(3, 3));
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const { label, setLabel } = useSuggestedLabel("tbl", caption.trim());
  const create = async () => {
    if (gridIsBlank(grid) || !label.trim() || busy) return;
    setBusy(true);
    const r = await api.createTable(label.trim(), caption.trim(), grid.cells, grid.align);
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    onCreated(r.id);
  };
  return (
    <Modal title="Insert a table" wide onClose={onClose}>
      <label className="lw-dialog__label">Caption
        <textarea className="lw-launch__input lw-obj__area" rows={2} value={caption} onChange={(e) => setCaption(e.target.value)} aria-label="Caption" autoFocus />
      </label>
      <TableGridEditor grid={grid} onChange={setGrid} />
      <LabelField kind="tbl" label={label} onChange={setLabel} />
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={gridIsBlank(grid) || !label.trim() || busy} onClick={() => void create()}>Insert table</button>
      </div>
    </Modal>
  );
}

/** Insert an equation: LaTeX with a live preview. "Suggest LaTeX with AI" sends only the description typed in its box
 *  and shows the answer apart; it enters the equation only when the author clicks "Use this". */
export function InsertEquationDialog({ notify, onClose, onCreated, requireAi }: InsertProps & { requireAi?: () => boolean }) {
  const [latex, setLatex] = useState("");
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [desc, setDesc] = useState("");
  const [asking, setAsking] = useState(false);
  const [proposal, setProposal] = useState<string | null>(null);
  const { label, setLabel } = useSuggestedLabel("eq", caption.trim());
  const create = async () => {
    if (!latex.trim() || !label.trim() || busy) return;
    setBusy(true);
    const r = await api.createEquation(label.trim(), latex.trim(), caption.trim());
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    onCreated(r.id);
  };
  const ask = async () => {
    if (!desc.trim() || asking) return;
    if (requireAi && !requireAi()) return;
    setAsking(true);
    const r = await api.suggestLatex(desc.trim());
    setAsking(false);
    if (!r.ok) return notify(r.error, "error");
    setProposal(r.text);
  };
  return (
    <Modal title="Insert an equation" wide onClose={onClose}>
      <label className="lw-dialog__label">LaTeX
        <textarea className="lw-launch__input lw-mono lw-obj__area" rows={3} value={latex} onChange={(e) => setLatex(e.target.value)} aria-label="LaTeX"
          spellCheck={false} autoFocus placeholder="E = mc^2" />
      </label>
      <KatexView latex={latex} />
      <label className="lw-dialog__label">Caption (optional)
        <input className="lw-launch__input" value={caption} onChange={(e) => setCaption(e.target.value)} aria-label="Caption" />
      </label>
      <LabelField kind="eq" label={label} onChange={setLabel} />
      <section className="lw-obj__ai" aria-label="Suggest LaTeX with AI">
        <label className="lw-dialog__label">Describe the equation in words
          <textarea className="lw-launch__input lw-obj__area" rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} aria-label="Describe the equation"
            placeholder="Monod growth rate with a substrate inhibition term" />
        </label>
        <div className="lw-row lw-gap-8">
          <button className="lw-btn" disabled={!desc.trim() || asking} onClick={() => void ask()}>{asking ? "Asking…" : "Suggest LaTeX with AI"}</button>
          <span className="lw-faint lw-grid__hint">Only this description is sent. Nothing changes until you click Use this.</span>
        </div>
        {proposal !== null && (
          <div className="lw-obj__proposal" aria-label="Suggested LaTeX">
            <pre className="lw-mono">{proposal}</pre>
            <KatexView latex={proposal} label="Suggestion preview" />
            <div className="lw-row lw-gap-8">
              <button className="lw-btn lw-btn--primary" onClick={() => { setLatex(proposal); setProposal(null); }}>Use this</button>
              <button className="lw-btn" onClick={() => setProposal(null)}>Discard</button>
            </div>
          </div>
        )}
      </section>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!latex.trim() || !label.trim() || busy} onClick={() => void create()}>Insert equation</button>
      </div>
    </Modal>
  );
}
