import { useCallback, useEffect, useState } from "react";
import { FilePlus, ClipboardPaste } from "lucide-react";
import { api } from "../../backend/api";
import { fileSize, type GuidelineFile, type GuidelineText } from "../../data/research";
import { ConfirmDialog, Modal } from "../Dialogs";
import { Icon } from "../primitives";

type Notify = (text: string, tone?: "info" | "error") => void;

/** Guideline files of a research project (journal guide, call for proposals): add, paste, view, remove. */
export function GuidelinesDialog({ onClose, notify }: { onClose: () => void; notify: Notify }) {
  const [files, setFiles] = useState<GuidelineFile[]>([]);
  const [pasting, setPasting] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [viewing, setViewing] = useState<GuidelineText | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await api.guidelinesList();
    if (!r.ok) return notify(r.error, "error");
    setFiles(r.files);
  }, [notify]);
  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.guidelinesList();
      if (!live) return;
      if (!r.ok) notify(r.error, "error"); else setFiles(r.files);
    })();
    return () => { live = false; };
  }, [notify]);

  const add = async () => {
    const r = await api.guidelinesAdd();
    if (!r.ok) return notify(r.error, "error");
    for (const s of r.skipped) notify(`${s.name} was not added: ${s.reason}`, "error");
    if (r.added.length) notify(r.added.length === 1 ? `Added ${r.added[0]}.` : `Added ${r.added.length} files.`);
    await load();
  };
  const addText = async () => {
    const r = await api.guidelinesAddText(title.trim(), text);
    if (!r.ok) return notify(r.error, "error");
    notify(`Added ${r.name}.`); setPasting(false); setTitle(""); setText("");
    await load();
  };
  const view = async (name: string) => {
    const r = await api.guidelinesRead(name);
    if (!r.ok) return notify(r.error, "error");
    setViewing(r);
  };
  const remove = async (name: string) => {
    setRemoving(null);
    const r = await api.guidelinesRemove(name);
    if (!r.ok) return notify(r.error, "error");
    notify(`Removed ${name}.`);
    await load();
  };

  return (
    <>
    <Modal title="Guidelines" wide onClose={onClose}>
      <div className="lw-settings">
        <p className="lw-dialog__message">Guidelines stay on this computer. They are sent to an AI only when you use an assistant feature that says so.</p>
        <section className="lw-settings__section">
          {files.length === 0 && <p className="lw-dialog__message lw-faint">No guideline files yet.</p>}
          <ul className="lw-dialog__message" aria-label="Guideline files" style={{ listStyle: "none", padding: 0 }}>
            {files.map((f) => (
              <li key={f.name} className="lw-row lw-gap-8">
                <span className="lw-btn--grow">
                  <strong>{f.name}</strong> <span className="lw-faint">{f.type}, {fileSize(f.size)}, {f.extracted ? "text read" : "no text read"}</span>
                  {!f.extracted && f.message && <div role="note">{f.message}</div>}
                </span>
                <button className="lw-btn" disabled={!f.extracted} onClick={() => void view(f.name)}>View text</button>
                <button className="lw-btn" onClick={() => setRemoving(f.name)}>Remove</button>
              </li>
            ))}
          </ul>
          <div className="lw-row lw-gap-8">
            <button className="lw-btn" onClick={() => void add()}><Icon icon={FilePlus} size={14} stroke={1.8} /> Add files</button>
            <button className="lw-btn" onClick={() => setPasting((p) => !p)}><Icon icon={ClipboardPaste} size={14} stroke={1.8} /> Paste text</button>
          </div>
        </section>
        {pasting && (
          <section className="lw-settings__section">
            <input className="lw-launch__input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" aria-label="Guideline title" />
            <textarea className="lw-launch__input" rows={8} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="Paste the guidelines here" aria-label="Guideline text" />
            <div className="lw-row lw-gap-8">
              <button className="lw-btn lw-btn--primary" disabled={!title.trim() || !text.trim()} onClick={() => void addText()}>Add text</button>
              <button className="lw-btn" onClick={() => setPasting(false)}>Cancel</button>
            </div>
          </section>
        )}
        {viewing && (
          <section className="lw-settings__section">
            <h3>{viewing.name}</h3>
            <textarea className="lw-launch__input" readOnly rows={12} value={viewing.text} aria-label="Guideline text view" />
            {viewing.truncated && <p className="lw-dialog__message">Showing the first part only ({viewing.text.length} of {viewing.chars} characters).</p>}
            <div className="lw-row lw-gap-8"><button className="lw-btn" onClick={() => setViewing(null)}>Hide text</button></div>
          </section>
        )}
      </div>
      <div className="lw-dialog__buttons"><button className="lw-btn lw-btn--primary" onClick={onClose}>Close</button></div>
    </Modal>
    {removing && (
      <ConfirmDialog title="Remove guideline file" confirm="Remove"
        message={<>Remove {removing} from this project? Your paper is not changed.</>}
        onConfirm={() => void remove(removing)} onClose={() => setRemoving(null)} />
    )}
    </>
  );
}
