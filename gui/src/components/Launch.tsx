import { useEffect, useState } from "react";
import { FolderOpen, Plus } from "lucide-react";
import type { ProjectMode, RecentProject } from "../data/types";
import { api } from "../backend/api";
import { defaultJournal, type ResearchKind } from "../data/research";
import { Icon } from "./primitives";
import { JournalPicker, useProfiles } from "./research/JournalPicker";
import { Logo } from "./Logo";

const MODES: { id: ProjectMode; label: string; hint: string }[] = [
  { id: "story", label: "Story", hint: "A novel or stories: scenes, characters and places." },
  { id: "research", label: "Research", hint: "A paper, proposal or thesis: sections, sources and citations." },
  { id: "script", label: "Script", hint: "A screenplay, TV, stage or audio script: Fountain scenes, characters and places." },
];

/** Shown when no project is open: pick a recent one, open a folder, or start a new project. */
export function Launch({ onOpened }: { onOpened: () => void }) {
  const [recents, setRecents] = useState<RecentProject[]>([]);
  const [path, setPath] = useState("");
  const [title, setTitle] = useState("");
  const [newPath, setNewPath] = useState("");
  // The folder follows the title (~/novels/<slug>) until the author edits it.
  const [newPathEdited, setNewPathEdited] = useState(false);
  const [mode, setMode] = useState<ProjectMode>("story");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const profiles = useProfiles();
  const [kind, setKind] = useState<ResearchKind>("manuscript");
  const [journal, setJournal] = useState<string | null>(null);   // null: not chosen yet, use the kind's first profile
  const chosenJournal = journal ?? defaultJournal(profiles, kind);

  useEffect(() => { api.recentProjects().then((r) => r.ok && setRecents(r.recents)); }, []);

  const run = async (fn: () => Promise<{ ok: boolean; error?: string }>) => {
    setBusy(true); setError("");
    const r = await fn();
    setBusy(false);
    if (r.ok) onOpened(); else setError(r.error ?? "Something went wrong.");
  };
  const browse = async () => {
    const r = await api.chooseFolder();
    if (r.ok && r.path) setPath(r.path);
  };
  const onTitle = async (value: string) => {
    setTitle(value);
    if (newPathEdited) return;
    const r = await api.suggestProjectPath(value);
    if (r.ok) setNewPath(r.path);
  };
  const create = () => run(() => mode === "research"
    ? api.newProject(title.trim(), newPath.trim(), mode, kind, chosenJournal)
    : api.newProject(title.trim(), newPath.trim(), mode));

  return (
    <div className="lw-launch">
      <div className="lw-launch__card">
        <div className="lw-row lw-gap-8">
          <Logo size={32} />
          <h1 className="lw-launch__title">Chisel</h1>
        </div>
        {recents.length > 0 && (
          <section className="lw-launch__section">
            <span className="lw-section-label">Recent projects</span>
            {recents.map((r) => (
              <button key={r.path} className="lw-launch__recent" disabled={!r.exists || busy}
                onClick={() => run(() => api.openProject(r.path))}>
                <span className="lw-launch__recent-title">{r.title}</span>
                <span className="lw-mono lw-faint">{r.exists ? r.path : `${r.path} (missing)`}</span>
              </button>
            ))}
          </section>
        )}
        <section className="lw-launch__section">
          <span className="lw-section-label">New project</span>
          <div className="lw-row lw-gap-8">
            <input className="lw-launch__input" value={title} autoFocus
              onChange={(e) => onTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && title.trim() && !busy) create(); }}
              placeholder="Title of your book" aria-label="New project title" />
            <button className="lw-btn" disabled={!title.trim() || busy} onClick={create}>
              <Icon icon={Plus} size={14} stroke={1.8} /> Create
            </button>
          </div>
          <div className="lw-row lw-gap-8" role="radiogroup" aria-label="Project type">
            {MODES.map((m) => (
              <button key={m.id} role="radio" aria-checked={mode === m.id} title={m.hint}
                className={`lw-btn${mode === m.id ? " lw-btn--primary" : ""}`}
                onClick={() => setMode(m.id)}>{m.label}</button>
            ))}
          </div>
          <span className="lw-faint">{MODES.find((m) => m.id === mode)?.hint}</span>
          {mode === "research" && (
            <JournalPicker profiles={profiles} kind={kind} journal={chosenJournal}
              onChange={(k, j) => { setKind(k); setJournal(j); }} />
          )}
          <div className="lw-row lw-gap-8">
            <input className="lw-launch__input lw-mono" value={newPath}
              onChange={(e) => { setNewPath(e.target.value); setNewPathEdited(true); }}
              placeholder="Folder (chosen from the title)" aria-label="New project folder" />
          </div>
        </section>
        <section className="lw-launch__section">
          <span className="lw-section-label">Open an existing project</span>
          <div className="lw-row lw-gap-8">
            <input className="lw-launch__input" value={path} onChange={(e) => setPath(e.target.value)}
              placeholder="/path/to/project" aria-label="Project folder" />
            <button className="lw-btn" onClick={browse}><Icon icon={FolderOpen} size={14} stroke={1.8} /> Browse</button>
          </div>
          <div className="lw-row lw-gap-8">
            <button className="lw-btn lw-btn--grow" disabled={!path.trim() || busy} onClick={() => run(() => api.openProject(path.trim()))}>
              Open project
            </button>
          </div>
        </section>
        {error && <p className="lw-launch__error" role="alert">{error}</p>}
      </div>
    </div>
  );
}
