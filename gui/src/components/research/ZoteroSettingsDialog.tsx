import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { api } from "../../backend/api";
import type { ZoteroSettings, ZoteroStatus } from "../../data/research";
import { Modal } from "../Dialogs";
import { Icon } from "../primitives";

type Notify = (text: string, tone?: "info" | "error") => void;

/** Zotero connection settings. The web API key is write-only: it is never shown, only "saved" or "not saved". */
export function ZoteroSettingsDialog({ onClose, notify }: { onClose: () => void; notify: Notify }) {
  const [loaded, setLoaded] = useState(false);
  const [userId, setUserId] = useState("");
  const [webBase, setWebBase] = useState("");
  const [local, setLocal] = useState(true);
  const [localBase, setLocalBase] = useState("");
  const [file, setFile] = useState("");
  const [keySet, setKeySet] = useState(false);
  const [key, setKey] = useState("");
  const [status, setStatus] = useState<ZoteroStatus | null>(null);
  const [checking, setChecking] = useState(false);

  const adopt = (s: ZoteroSettings) => {
    setUserId(s.userId); setWebBase(s.webBase); setLocal(s.local); setLocalBase(s.localBase); setFile(s.file); setKeySet(s.keySet);
  };

  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.zoteroGetSettings();
      if (!live) return;
      if (!r.ok) notify(r.error, "error"); else adopt(r);
      setLoaded(true);
    })();
    return () => { live = false; };
  }, [notify]);

  const save = async () => {
    const r = await api.zoteroSetSettings(userId.trim(), webBase.trim(), local, localBase.trim(), file.trim());
    if (!r.ok) return notify(r.error, "error");
    adopt(r); notify("Zotero settings saved."); onClose();
  };
  const saveKey = async () => {
    const r = await api.zoteroSetKey(key.trim());
    setKey("");   // never keep the key in the page
    if (!r.ok) return notify(r.error, "error");
    setKeySet(r.keySet); notify("Zotero key stored in the system keyring.");
  };
  const removeKey = async () => {
    const r = await api.zoteroClearKey();
    if (!r.ok) return notify(r.error, "error");
    setKeySet(r.keySet); notify("Zotero key removed.");
  };
  const check = async () => {
    setChecking(true);
    // The check uses what is saved, so save the form first.
    const s = await api.zoteroSetSettings(userId.trim(), webBase.trim(), local, localBase.trim(), file.trim());
    if (!s.ok) { setChecking(false); return notify(s.error, "error"); }
    const r = await api.zoteroStatus();
    setChecking(false);
    if (!r.ok) return notify(r.error, "error");
    setStatus(r);
  };

  return (
    <Modal title="Zotero settings" wide onClose={onClose}>
      <div className="lw-settings">
        <section className="lw-settings__section">
          <h3>Zotero on this computer</h3>
          <label className="lw-check">
            <input type="checkbox" checked={local} disabled={!loaded} onChange={(e) => setLocal(e.target.checked)} />
            Read my library from Zotero on this computer <span className="lw-faint">(needs Zotero open)</span>
          </label>
          <p className="lw-dialog__message">
            In Zotero 10, open Settings, then Advanced, and turn on “Allow other applications on this computer to communicate with Zotero”.
          </p>
          <input className="lw-launch__input" value={localBase} onChange={(e) => setLocalBase(e.target.value)} disabled={!loaded || !local}
            placeholder="Address of Zotero on this computer" aria-label="Local Zotero address" spellCheck={false} />
        </section>

        <section className="lw-settings__section">
          <h3>Zotero on the web</h3>
          <p className="lw-dialog__message">
            Used when Zotero on this computer is not available. The key identifies your account, so the user id can stay blank.
            {" "}{keySet ? "A key is saved." : "No key saved."}
          </p>
          <div className="lw-row lw-gap-8">
            <input className="lw-launch__input" type="password" value={key} onChange={(e) => setKey(e.target.value)}
              placeholder="Paste a Zotero web API key" aria-label="Zotero web API key" autoComplete="off" spellCheck={false}
              onKeyDown={(e) => { if (e.key === "Enter" && key.trim()) void saveKey(); }} />
            <button className="lw-btn" disabled={!key.trim()} onClick={() => void saveKey()}><Icon icon={KeyRound} size={14} stroke={1.8} /> Save key</button>
            <button className="lw-btn" disabled={!keySet} onClick={() => void removeKey()}>Remove key</button>
          </div>
          <input className="lw-launch__input" value={userId} onChange={(e) => setUserId(e.target.value)} disabled={!loaded}
            placeholder="Web user id (optional)" aria-label="Zotero web user id" spellCheck={false} />
          <input className="lw-launch__input" value={webBase} onChange={(e) => setWebBase(e.target.value)} disabled={!loaded}
            placeholder="Web address" aria-label="Zotero web address" spellCheck={false} />
        </section>

        <section className="lw-settings__section">
          <h3>Better BibTeX file</h3>
          <p className="lw-dialog__message">Optional. An exported .bib or .json file Chisel can read when Zotero is not running.</p>
          <input className="lw-launch__input" value={file} onChange={(e) => setFile(e.target.value)} disabled={!loaded}
            placeholder="Path to the export file (optional)" aria-label="Better BibTeX export file" spellCheck={false} />
        </section>

        <section className="lw-settings__section">
          <h3>Connection</h3>
          <div className="lw-row lw-gap-8">
            <button className="lw-btn" disabled={checking || !loaded} onClick={() => void check()}>{checking ? "Checking…" : "Check connection"}</button>
          </div>
          {status && (
            <ul className="lw-dialog__message" aria-label="Connection status">
              {status.backends.map((b) => (
                <li key={b.backend}><strong>{b.backend}</strong>: {b.ok ? "working" : "not working"}. {b.message}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!loaded} onClick={() => void save()}>Save</button>
      </div>
    </Modal>
  );
}
