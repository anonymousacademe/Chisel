import { useEffect, useState } from "react";
import { api } from "../../backend/api";
import { defaultJournal, journalsOf, type JournalProfile, type ResearchKind } from "../../data/research";

const KINDS: { id: ResearchKind; label: string }[] = [
  { id: "manuscript", label: "Manuscript" },
  { id: "proposal", label: "Proposal" },
];

/** Loads the journal profiles once; an empty list until they arrive (or when the bridge has none). */
export function useProfiles(): { profiles: JournalProfile[]; failed: boolean } {
  const [profiles, setProfiles] = useState<JournalProfile[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const r = await api.researchProfiles();
        if (!live) return;
        if (r.ok) { setProfiles(r.profiles); setFailed(false); } else setFailed(true);
      } catch { if (live) setFailed(true); }
    })();
    return () => { live = false; };
  }, []);
  return { profiles, failed };
}

/** "What are you writing?" (Manuscript / Proposal) and the target journal for it. Shared by the launch screen and Project settings. */
export function JournalPicker({ profiles, kind, journal, onChange, disabled, failed }: {
  profiles: JournalProfile[]; kind: ResearchKind; journal: string; disabled?: boolean; failed?: boolean;
  onChange: (kind: ResearchKind, journal: string) => void;
}) {
  const options = journalsOf(profiles, kind);
  return (
    <div className="lw-settings__section">
      <span className="lw-section-label">What are you writing?</span>
      <div className="lw-row lw-gap-8" role="radiogroup" aria-label="What are you writing?">
        {KINDS.map((k) => (
          <button key={k.id} role="radio" aria-checked={kind === k.id} disabled={disabled}
            className={`lw-btn${kind === k.id ? " lw-btn--primary" : ""}`}
            onClick={() => { if (k.id !== kind) onChange(k.id, defaultJournal(profiles, k.id)); }}>{k.label}</button>
        ))}
      </div>
      <span className="lw-section-label">{kind === "manuscript" ? "Target journal" : "Proposal guide"}</span>
      <select className="lw-launch__input" value={journal} disabled={disabled}
        aria-label={kind === "manuscript" ? "Target journal" : "Proposal guide"}
        onChange={(e) => onChange(kind, e.target.value)}>
        {options.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        <option value="">No target journal (standard structure)</option>
      </select>
      {failed && <span className="lw-faint" role="alert">Could not load the journal list. You can still create the project and choose a journal later in Project settings.</span>}
      <span className="lw-faint">Starts with the journal's section layout and checks your paper against its rules. You can change this later.</span>
    </div>
  );
}
