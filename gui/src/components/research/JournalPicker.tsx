import { useEffect, useState } from "react";
import { api } from "../../backend/api";
import { defaultJournal, profilesOf, type JournalProfile, type ResearchKind } from "../../data/research";

const KINDS: { id: ResearchKind; label: string }[] = [
  { id: "manuscript", label: "Manuscript" },
  { id: "proposal", label: "Proposal" },
];

/** Loads the journal profiles once; an empty list until they arrive (or when the bridge has none). */
export function useProfiles(): JournalProfile[] {
  const [profiles, setProfiles] = useState<JournalProfile[]>([]);
  useEffect(() => {
    let live = true;
    void api.researchProfiles().then((r) => { if (live && r.ok) setProfiles(r.profiles); });
    return () => { live = false; };
  }, []);
  return profiles;
}

/** "What are you writing?" (Manuscript / Proposal) and the target journal for it. Shared by the launch screen and Project settings. */
export function JournalPicker({ profiles, kind, journal, onChange, disabled }: {
  profiles: JournalProfile[]; kind: ResearchKind; journal: string; disabled?: boolean;
  onChange: (kind: ResearchKind, journal: string) => void;
}) {
  const options = profilesOf(profiles, kind);
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
      <span className="lw-faint">Starts with the journal's section layout and checks your paper against its rules. You can change this later.</span>
    </div>
  );
}
