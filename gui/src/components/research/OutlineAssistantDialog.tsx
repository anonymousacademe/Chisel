import { useEffect, useRef, useState } from "react";
import { api } from "../../backend/api";
import { runAiJob, AiCancelled, type AiJob } from "../../backend/aijobs";
import {
  ACTION_LABEL, changeCount, defaultTicked, describeItem, isActionable, previewOutline, tickedItems, visibleItems, type PreviewGroup,
} from "../../data/outline";
import type { GuidelineFile, OutlineApplied, OutlineCurrent, OutlineIgnored, OutlineItem, OutlineProposal } from "../../data/research";
import type { SentReport as Report } from "../../data/types";
import { useElapsed, secs } from "../aiRun";
import { ConfirmDialog, Modal } from "../Dialogs";
import { SentReport } from "../SentReport";

type Notify = (text: string, tone?: "info" | "error") => void;

interface Props {
  notify: Notify;
  onClose: () => void;
  /** False (and the host opens Settings) when no AI key is set. */
  requireAi: () => boolean;
  /** Save the open document before files are renamed or moved. */
  flushSave: () => Promise<boolean>;
  /** After apply: refresh the workspace and reopen the open document through the remap. */
  onApplied: (remap: Record<string, string>) => Promise<void>;
  /** The AI spend in the status bar. */
  refresh: () => Promise<unknown>;
}

function Preview({ title, groups }: { title: string; groups: PreviewGroup[] }) {
  return (
    <section aria-label={title} className="lw-btn--grow">
      <h3>{title}</h3>
      {groups.length === 0 && <p className="lw-faint">No sections.</p>}
      {groups.map((g) => (
        <div key={g.part || "top"}>
          {g.part && <strong>{g.part}</strong>}
          <ol style={{ margin: "2px 0 8px", paddingLeft: 20 }}>
            {g.rows.map((r) => (
              <li key={r.key} data-state={r.state}>
                {r.title}
                {r.state !== "same" && <span className="lw-faint"> ({r.state === "new" ? "new" : r.state})</span>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}

/** Outline assistant (research projects): scope, optional guidelines, a proposal to review, and apply for the ticked items only.
 *  The AI only proposes; Python validates and applies, and nothing is ever deleted. */
export function OutlineAssistantDialog({ notify, onClose, requireAi, flushSave, onApplied, refresh }: Props) {
  const [scope, setScope] = useState("");
  const [savedScope, setSavedScope] = useState("");
  const [instruction, setInstruction] = useState("");
  const [files, setFiles] = useState<GuidelineFile[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [phase, setPhase] = useState<"form" | "review" | "done">("form");
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [elapsedSeen, setElapsedSeen] = useState<number | undefined>(undefined);
  const [outline, setOutline] = useState<OutlineCurrent | null>(null);
  const [items, setItems] = useState<OutlineItem[]>([]);
  const [ignored, setIgnored] = useState<OutlineIgnored[]>([]);
  const [sent, setSent] = useState<Report | null>(null);
  const [heading, setHeading] = useState("");
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [appliedEdit, setAppliedEdit] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [result, setResult] = useState<OutlineApplied | null>(null);
  const jobRef = useRef<AiJob<OutlineProposal & { ok: true }> | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const [s, g] = await Promise.all([api.outlineGetScope(), api.guidelinesList()]);
      if (!live) return;
      if (s.ok) { setScope(s.text); setSavedScope(s.text); } else notify(s.error, "error");
      if (g.ok) setFiles(g.files); else notify(g.error, "error");
    })();
    return () => { live = false; void jobRef.current?.cancel(); };   // closing the dialog stops a running request
  }, [notify]);

  const saveScope = async (): Promise<boolean> => {
    if (scope === savedScope) return true;
    const r = await api.outlineSetScope(scope);
    if (!r.ok) { notify(r.error, "error"); return false; }
    setSavedScope(scope);
    return true;
  };
  const toReview = (next: OutlineItem[], current: OutlineCurrent, name: string) => {
    setOutline(current); setItems(next); setTicked(defaultTicked(next)); setHeading(name); setPhase("review");
  };

  const suggest = async () => {
    if (running || !requireAi()) return;
    if (!(await saveScope())) return;
    setRunning(true); setStartedAt(Date.now()); setElapsedSeen(undefined);
    const job = runAiJob<OutlineProposal & { ok: true }>("outline", { instruction: instruction.trim(), guidelines: [...picked] },
      { label: "Suggesting an outline…", onElapsed: setElapsedSeen });
    jobRef.current = job;
    try {
      const r = await job.promise;
      const cur = await api.outlineCurrent();
      if (!cur.ok) return notify(cur.error, "error");
      setIgnored(r.dropped ?? []); setSent(r.sent ?? null);
      toReview(r.items ?? [], cur, "Suggested outline");
    } catch (e) {
      if (e instanceof AiCancelled) notify("Stopped. Nothing was changed.");
      else notify(e instanceof Error ? e.message : String(e), "error");
    } finally { jobRef.current = null; setRunning(false); void refresh(); }
  };
  const unsaved = scope !== savedScope;
  /** Closing never throws scope edits away silently. */
  const requestClose = () => { if (unsaved) setConfirmClose(true); else onClose(); };
  const stop = () => { void jobRef.current?.cancel(); };

  const standard = async () => {
    const [s, cur] = await Promise.all([api.outlineStandard(), api.outlineCurrent()]);
    if (!s.ok) return notify(s.error, "error");
    if (!cur.ok) return notify(cur.error, "error");
    setIgnored([]); setSent(null);
    if (s.items.length === 0) notify("The outline already has every section of the standard structure.");
    toReview(s.items, cur, s.name ? `Standard structure: ${s.name}` : "Standard structure");
  };

  const apply = async () => {
    const chosen = tickedItems(items, ticked);
    if (chosen.length === 0 || applying) return;
    setApplying(true);
    try {
      if (!(await flushSave())) return notify("Could not save the current document first.", "error");
      const r = await api.outlineApply(chosen);
      if (!r.ok) return notify(r.error, "error");
      setAppliedEdit(chosen.some((i) => i.action === "rename" || i.action === "move") && r.changed.length > 0);
      setResult(r); setPhase("done");
      await onApplied(r.remap ?? {});
    } finally { setApplying(false); }
  };

  const toggle = (id: string) => setTicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const togglePick = (name: string) => setPicked((s) => { const n = new Set(s); if (n.has(name)) n.delete(name); else n.add(name); return n; });

  const chosen = tickedItems(items, ticked);
  const view = outline ? previewOutline(outline.sections, chosen) : null;
  const shown = visibleItems(items);
  const titleOf = (id: string) => items.find((i) => i.id === id)?.title ?? id;

  return (
    <Modal title="Outline assistant" wide onClose={requestClose}>
      <div className="lw-settings">
        {phase === "form" && (
          <>
            <section className="lw-settings__section">
              <label className="lw-dialog__label">What is this paper about?
                <textarea className="lw-launch__input" rows={6} value={scope} onChange={(e) => setScope(e.target.value)} aria-label="What is this paper about?"
                  placeholder="A paragraph on the question, the method, the data and the expected contribution." />
              </label>
              <p className="lw-dialog__message lw-faint">Saved with the project when you press Suggest or Save. Sent to the AI only when you press Suggest; the standard structure never sends it.</p>
              <div className="lw-row lw-gap-8">
                <button className="lw-btn" disabled={scope === savedScope} onClick={() => void saveScope().then((ok) => { if (ok) notify("Saved."); })}>Save</button>
              </div>
            </section>
            <section className="lw-settings__section">
              <label className="lw-dialog__label">Instruction (optional)
                <input className="lw-launch__input" value={instruction} onChange={(e) => setInstruction(e.target.value)} aria-label="Instruction"
                  placeholder="Make the methods section more detailed" />
              </label>
            </section>
            <section className="lw-settings__section">
              <h3>Guidelines to include</h3>
              {files.length === 0 && <p className="lw-dialog__message lw-faint">No guideline files in this project.</p>}
              <ul aria-label="Guidelines to include" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {files.map((f) => (
                  <li key={f.name}>
                    <label className="lw-row lw-gap-8">
                      <input type="checkbox" checked={picked.has(f.name)} disabled={!f.extracted} onChange={() => togglePick(f.name)} />
                      <span>{f.name}{!f.extracted && <span className="lw-faint"> (no text could be read)</span>}</span>
                    </label>
                  </li>
                ))}
              </ul>
              <p className="lw-dialog__message lw-faint">Ticked guidelines are sent to the AI. Nothing else from them is shared.</p>
            </section>
            {running && (
              <p className="lw-dialog__message" role="status"><Working startedAt={startedAt} reported={elapsedSeen} /></p>
            )}
            <div className="lw-row lw-gap-8">
              {running
                ? <button className="lw-btn" onClick={stop}>Stop</button>
                : <button className="lw-btn lw-btn--primary" onClick={() => void suggest()}>Suggest an outline</button>}
              <button className="lw-btn" disabled={running} onClick={() => void standard()}>Use the standard structure</button>
            </div>
          </>
        )}

        {phase === "review" && view && (
          <>
            <h3>{heading}</h3>
            {shown.length === 0 && <p className="lw-dialog__message">Nothing to change.</p>}
            <div className="lw-review">
              {shown.map((i) => isActionable(i) ? (
                <label key={i.id} className="lw-review__row">
                  <input type="checkbox" checked={ticked.has(i.id)} onChange={() => toggle(i.id)} aria-label={describeItem(i, outline?.sections)} />
                  <span className="lw-review__text">
                    <span className="lw-review__target"><strong>{ACTION_LABEL[i.action]}</strong> {describeItem(i, outline?.sections)}</span>
                    {i.purpose && i.action === "add" && <span className="lw-review__context">Purpose: {i.purpose}</span>}
                    {i.why && <span className="lw-review__context">{i.why}</span>}
                  </span>
                </label>
              ) : (
                <div key={i.id} className="lw-review__row" role="note">
                  <span className="lw-review__text">
                    <span className="lw-review__target"><strong>{ACTION_LABEL[i.action]}</strong> {i.title}</span>
                    {i.why && <span className="lw-review__context">{i.why}</span>}
                  </span>
                </div>
              ))}
            </div>
            {ignored.length > 0 && (
              <details open>
                <summary>Ignored from the reply</summary>
                <ul>{ignored.map((g, n) => <li key={n}>{g.title ? `${g.title}: ` : ""}{g.reason}</li>)}</ul>
              </details>
            )}
            <div className="lw-row lw-gap-8" style={{ alignItems: "flex-start" }}>
              <Preview title="Now" groups={view.before} />
              <Preview title="After the ticked changes" groups={view.after} />
            </div>
            <SentReport report={sent} />
          </>
        )}

        {phase === "done" && result && (
          <section role="status" aria-label="Summary">
            <p className="lw-dialog__message">
              {result.changed.length} changed, {result.created.length} created, {result.skipped.length} skipped.{appliedEdit ? ' Each renamed or moved section was saved as a snapshot first.' : ''}
            </p>
            {result.skipped.length > 0 && (
              <ul>{result.skipped.map((s) => <li key={s.id}>{titleOf(s.id)}: {s.reason}</li>)}</ul>
            )}
          </section>
        )}
      </div>
      <div className="lw-dialog__buttons">
        {phase === "review" && <button className="lw-btn" onClick={() => setPhase("form")}>Back</button>}
        {phase === "review" && (
          <button className="lw-btn lw-btn--primary" disabled={chosen.length === 0 || applying} onClick={() => void apply()}>{changeCount(chosen.length)}</button>
        )}
        <button className={phase === "done" ? "lw-btn lw-btn--primary" : "lw-btn"} onClick={requestClose}>{phase === "done" ? "Close" : "Cancel"}</button>
      </div>
      {confirmClose && (
        <ConfirmDialog title="Discard unsaved changes" confirm="Discard" message="The description of the paper has changes that are not saved. Close without saving them?"
          onConfirm={onClose} onClose={() => setConfirmClose(false)} />
      )}
    </Modal>
  );
}

function Working({ startedAt, reported }: { startedAt: number; reported?: number }) {
  const s = useElapsed(startedAt, reported);
  return <span><span className="lw-spinner" aria-hidden="true" /> Suggesting an outline… {secs(s)}</span>;
}
