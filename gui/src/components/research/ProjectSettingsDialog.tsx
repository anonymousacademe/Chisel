import { useEffect, useState } from "react";
import { api } from "../../backend/api";
import type { ResearchKind, ResearchSettings } from "../../data/research";
import { Modal } from "../Dialogs";
import { JournalPicker, useProfiles } from "./JournalPicker";
import { SourceLine } from "./SourceLine";

type Notify = (text: string, tone?: "info" | "error") => void;

/** Project settings of a research project: what is being written and the target journal. */
export function ProjectSettingsDialog({ onClose, notify, onSaved }: { onClose: () => void; notify: Notify; onSaved?: () => void }) {
  const { profiles, failed } = useProfiles();
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [saved, setSaved] = useState<ResearchSettings | null>(null);
  const [kind, setKind] = useState<ResearchKind>("manuscript");
  const [journal, setJournal] = useState("");

  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.researchGetSettings();
      if (!live) return;
      if (!r.ok) { setLoadError(r.error); notify(r.error, "error"); }
      else { setSaved(r); setKind(r.kind); setJournal(r.journal); setLoaded(true); }
    })();
    return () => { live = false; };
  }, [notify]);

  const save = async () => {
    const r = await api.researchSetSettings(kind, journal);
    if (!r.ok) return notify(r.error, "error");
    setSaved(r); notify("Project settings saved."); onSaved?.(); onClose();
  };

  return (
    <Modal title="Project settings" wide onClose={onClose}>
      <div className="lw-settings">
        {loadError && <p className="lw-dialog__message" role="alert">Could not read this project's settings: {loadError}</p>}
        <JournalPicker profiles={profiles} failed={failed} kind={kind} journal={journal} disabled={!loaded}
          onChange={(k, j) => { setKind(k); setJournal(j); }} />
        {saved && saved.source && (
          <section className="lw-settings__section">
            <h3>{saved.journalName}</h3>
            <SourceLine source={saved.source} readOn={saved.readOn} />
          </section>
        )}
        <p className="lw-dialog__message">Changing the journal never moves or deletes your sections.</p>
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!loaded} onClick={() => void save()}>Save</button>
      </div>
    </Modal>
  );
}
