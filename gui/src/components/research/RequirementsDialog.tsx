import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Info } from "lucide-react";
import { api } from "../../backend/api";
import { REQUIREMENT_LABEL, requirementSummary, type RequirementStatus, type RequirementsReport } from "../../data/research";
import { Modal } from "../Dialogs";
import { Icon } from "../primitives";
import { SourceLine } from "./SourceLine";
import { ManageRequirements } from "./ManageRequirements";

type Notify = (text: string, tone?: "info" | "error") => void;

const ICON = { ok: Check, warn: AlertTriangle, info: Info, na: Info, advice: Info } as const;

/** Journal requirements: the paper checked against the target journal's rules (Python decides each status). */
export function RequirementsDialog({ onClose, notify }: { onClose: () => void; notify: Notify }) {
  const [report, setReport] = useState<RequirementsReport | null>(null);
  const [busy, setBusy] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    const r = await api.researchRequirements();
    setBusy(false); setLoaded(true);
    if (!r.ok) { setError(r.error); return notify(r.error, "error"); }
    setError(""); setReport(r);
  }, [notify]);
  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.researchRequirements();
      if (!live) return;
      setBusy(false); setLoaded(true);
      if (!r.ok) { setError(r.error); notify(r.error, "error"); } else setReport(r);
    })();
    return () => { live = false; };
  }, [notify]);

  return (
    <Modal title="Journal requirements" wide onClose={onClose}>
      <div className="lw-settings">
        {!report && busy && <p className="lw-dialog__message">Checking…</p>}
        {!report && loaded && !busy && <p className="lw-dialog__message" role="alert">Could not check the requirements{error ? ": " + error : "."}</p>}
        {report && !report.journal && <p className="lw-dialog__message">This project has no journal selected. Choose one in Project settings.</p>}
        {report && (
          <>
            <section className="lw-settings__section">
              <h3>{report.name || "Requirements"}</h3>
              {report.source && <SourceLine source={report.source} readOn={report.readOn} />}
              <p className="lw-dialog__message" aria-label="Summary"><strong>{requirementSummary(report.summary)}</strong></p>
            </section>
            {report.groups.map((g) => (
              <section key={g.title} className="lw-settings__section">
                <h3>{g.title}</h3>
                <ul className="lw-dialog__message" style={{ listStyle: "none", padding: 0 }}>
                  {g.items.map((it) => {
                    const st: RequirementStatus = it.status;
                    return (
                      <li key={it.id} data-status={st} className={st === "advice" ? "lw-faint" : undefined}>
                        <Icon icon={ICON[st]} size={14} stroke={1.8} />{" "}
                        <strong>{it.title}</strong>
                        <span className="lw-faint"> ({REQUIREMENT_LABEL[st]})</span>
                        {it.message && <>: {it.message}</>}
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </>
        )}
        <ManageRequirements notify={notify} onChanged={() => void load()} />
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" disabled={busy} onClick={() => void load()}>{busy ? "Checking…" : "Check again"}</button>
        <button className="lw-btn lw-btn--primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
