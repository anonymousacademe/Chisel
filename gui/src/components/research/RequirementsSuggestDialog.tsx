import { useEffect, useRef, useState } from "react";
import { api } from "../../backend/api";
import { runAiJob, AiCancelled, type AiJob } from "../../backend/aijobs";
import { CHECK_PARAMS, addCount, defaultTickedRequirements, describeCheck, rowsToSave } from "../../data/requirementsCustom";
import type { GuidelineFile, RequirementDropped, RequirementsProposal, SuggestedRequirement } from "../../data/research";
import type { SentReport as Report } from "../../data/types";
import { useElapsed, secs } from "../aiRun";
import { Modal } from "../Dialogs";
import { SentReport } from "../SentReport";

type Notify = (text: string, tone?: "info" | "error") => void;

interface Props {
  notify: Notify;
  onClose: () => void;
  /** False (and the host opens Settings) when no AI key is set. */
  requireAi: () => boolean;
  /** The AI spend in the status bar. */
  refresh: () => Promise<unknown>;
  /** After rows were saved. */
  onSaved?: () => void;
}

const NUMBERS = [
  ["min", "At least"], ["max", "At most"], ["item_chars_max", "Characters per item, at most"],
] as const;

/** Suggest requirements from guideline documents (research projects). The AI only proposes: nothing is saved until the
 *  author ticks rows and presses Add, and rows whose quote Python could not find in the guideline start unticked. */
export function RequirementsSuggestDialog({ notify, onClose, requireAi, refresh, onSaved }: Props) {
  const [files, setFiles] = useState<GuidelineFile[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [instruction, setInstruction] = useState("");
  const [phase, setPhase] = useState<"form" | "review" | "done">("form");
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [elapsedSeen, setElapsedSeen] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<SuggestedRequirement[]>([]);
  const [ignored, setIgnored] = useState<RequirementDropped[]>([]);
  const [sent, setSent] = useState<Report | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [added, setAdded] = useState(0);
  const jobRef = useRef<AiJob<RequirementsProposal & { ok: true }> | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const g = await api.guidelinesList();
      if (!live) return;
      if (g.ok) setFiles(g.files); else notify(g.error, "error");
    })();
    return () => { live = false; void jobRef.current?.cancel(); };   // closing the dialog stops a running request
  }, [notify]);

  const suggest = async () => {
    if (running || picked.size === 0 || !requireAi()) return;
    setRunning(true); setStartedAt(Date.now()); setElapsedSeen(undefined); setError("");
    const job = runAiJob<RequirementsProposal & { ok: true }>("requirements", { instruction: instruction.trim(), guidelines: [...picked] },
      { label: "Suggesting requirements…", onElapsed: setElapsedSeen });
    jobRef.current = job;
    try {
      const r = await job.promise;
      const next = r.items ?? [];
      setItems(next); setTicked(defaultTickedRequirements(next)); setIgnored(r.dropped ?? []); setSent(r.sent ?? null); setPhase("review");
    } catch (e) {
      if (e instanceof AiCancelled) notify("Stopped. Nothing was changed.");
      else notify(e instanceof Error ? e.message : String(e), "error");
    } finally { jobRef.current = null; setRunning(false); void refresh(); }
  };
  const stop = () => { void jobRef.current?.cancel(); };

  const edit = (id: string, patch: Partial<SuggestedRequirement>) =>
    setItems((all) => all.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  const setNumber = (id: string, key: "min" | "max" | "item_chars_max", text: string) => {
    const n = text.trim() === "" ? undefined : Number(text);
    edit(id, { [key]: n === undefined || !Number.isFinite(n) ? undefined : n });
  };
  const toggle = (id: string) => setTicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const togglePick = (name: string) => setPicked((s) => { const n = new Set(s); if (n.has(name)) n.delete(name); else n.add(name); return n; });

  const chosen = items.filter((i) => ticked.has(i.id));
  const add = async () => {
    if (chosen.length === 0 || saving) return;
    setSaving(true); setError("");
    try {
      const cur = await api.requirementsCustom();
      if (!cur.ok) { setError(cur.error); return notify(cur.error, "error"); }
      const r = await api.requirementsSave(rowsToSave(cur.rows, items, ticked));
      if (!r.ok) { setError(r.error); return notify(r.error, "error"); }
      setAdded(chosen.length); setPhase("done");
      notify(`Added ${chosen.length} requirement${chosen.length === 1 ? "" : "s"}.`);
      onSaved?.();
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Suggest requirements" wide onClose={onClose}>
      <div className="lw-settings">
        {phase === "form" && (
          <>
            <section className="lw-settings__section">
              <h3>Guidelines to read</h3>
              {files.length === 0 && <p className="lw-dialog__message lw-faint">No guideline files in this project.</p>}
              <ul aria-label="Guidelines to read" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {files.map((f) => (
                  <li key={f.name}>
                    <label className="lw-row lw-gap-8">
                      <input type="checkbox" checked={picked.has(f.name)} disabled={!f.extracted || running} onChange={() => togglePick(f.name)} />
                      <span>{f.name}{!f.extracted && <span className="lw-faint"> (no text could be read)</span>}</span>
                    </label>
                  </li>
                ))}
              </ul>
              <p className="lw-dialog__message lw-faint">Ticked guidelines are sent to the AI. Nothing else is shared.</p>
            </section>
            <section className="lw-settings__section">
              <label className="lw-dialog__label">Instruction (optional)
                <input className="lw-launch__input" value={instruction} onChange={(e) => setInstruction(e.target.value)} aria-label="Instruction"
                  placeholder="Only the rules about the abstract and the keywords" />
              </label>
            </section>
            {running && <p className="lw-dialog__message" role="status"><Working startedAt={startedAt} reported={elapsedSeen} /></p>}
            <div className="lw-row lw-gap-8">
              {running
                ? <button className="lw-btn" onClick={stop}>Stop</button>
                : <button className="lw-btn lw-btn--primary" disabled={picked.size === 0} onClick={() => void suggest()}>Suggest requirements</button>}
            </div>
          </>
        )}

        {phase === "review" && (
          <>
            <h3>Suggested requirements</h3>
            {items.length === 0 && <p className="lw-dialog__message">The AI found no rule the app can check in the ticked guidelines.</p>}
            <div className="lw-review">
              {items.map((i) => {
                const params = i.kind === "check" && i.check ? CHECK_PARAMS[i.check] : [];
                return (
                  <div key={i.id} className="lw-review__row" data-verified={i.verified ? "yes" : "no"}>
                    <input type="checkbox" checked={ticked.has(i.id)} onChange={() => toggle(i.id)} aria-label={`Add ${i.title}`} />
                    <span className="lw-review__text">
                      <input className="lw-launch__input" value={i.title} aria-label={`Title of ${i.id}`} onChange={(e) => edit(i.id, { title: e.target.value })} />
                      <span className="lw-review__target"><strong>{describeCheck(i)}</strong></span>
                      {NUMBERS.some(([key]) => params.includes(key)) && (
                        <span className="lw-row lw-gap-8">
                          {NUMBERS.filter(([key]) => params.includes(key)).map(([key, label]) => (
                            <label key={key} className="lw-faint">{label}{" "}
                              <input type="number" min={0} style={{ width: 80 }} aria-label={`${label} for ${i.id}`}
                                value={i[key] ?? ""} onChange={(e) => setNumber(i.id, key, e.target.value)} />
                            </label>
                          ))}
                        </span>
                      )}
                      {i.quote && <span className="lw-review__context">“{i.quote}” <span className="lw-faint">({i.source})</span></span>}
                      {i.why && <span className="lw-review__context">{i.why}</span>}
                      {!i.verified && <span className="lw-review__context" role="alert">Could not find this quote in the guideline: check it before adding.</span>}
                    </span>
                  </div>
                );
              })}
            </div>
            {ignored.length > 0 && (
              <details open>
                <summary>Ignored from the reply</summary>
                <ul>{ignored.map((g, n) => <li key={n}>{g.title ? `${g.title}: ` : ""}{g.reason}</li>)}</ul>
              </details>
            )}
            {error && <p className="lw-dialog__message" role="alert">{error}</p>}
            <SentReport report={sent} />
          </>
        )}

        {phase === "done" && (
          <section role="status" aria-label="Summary">
            <p className="lw-dialog__message">Added {added} requirement{added === 1 ? "" : "s"}. They are checked with the journal requirements, under “Your requirements”.</p>
          </section>
        )}
      </div>
      <div className="lw-dialog__buttons">
        {phase === "review" && <button className="lw-btn" onClick={() => setPhase("form")}>Back</button>}
        {phase === "review" && (
          <button className="lw-btn lw-btn--primary" disabled={chosen.length === 0 || saving} onClick={() => void add()}>{addCount(chosen.length)}</button>
        )}
        <button className={phase === "done" ? "lw-btn lw-btn--primary" : "lw-btn"} onClick={onClose}>{phase === "done" ? "Close" : "Cancel"}</button>
      </div>
    </Modal>
  );
}

function Working({ startedAt, reported }: { startedAt: number; reported?: number }) {
  const s = useElapsed(startedAt, reported);
  return <span><span className="lw-spinner" aria-hidden="true" /> Suggesting requirements… {secs(s)}</span>;
}
