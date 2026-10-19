import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Info } from "lucide-react";
import { api } from "../../backend/api";
import { REQUIREMENT_LABEL, requirementSummary, type RequirementStatus, type RequirementsReport } from "../../data/research";
import { Modal } from "../Dialogs";
import { Icon } from "../primitives";
import { SourceLine } from "./SourceLine";

type Notify = (text: string, tone?: "info" | "error") => void;

const ICON = { ok: Check, warn: AlertTriangle, info: Info, na: Info, advice: Info } as const;

/** Journal requirements: the paper checked against the target journal's rules (Python decides each status). */
export function RequirementsDialog({ onClose, notify }: { onClose: () => void; notify: Notify }) {
  const [report, setReport] = useState<RequirementsReport | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const r = await api.researchRequirements();
    setBusy(false);
    if (!r.ok) return notify(r.error, "error");
    setReport(r);
  }, [notify]);
  useEffect(() => {
    let live = true;
    void (async () => {
      const r = await api.researchRequirements();
      if (!live) return;
      if (!r.ok) notify(r.error, "error"); else setReport(r);
    })();
    return () => { live = false; };
  }, [notify]);

  return (
    <Modal title="Journal requirements" wide onClose={onClose}>
      <div className="lw-settings">
        {!report && <p className="lw-dialog__message">{busy ? "Checking…" : "No requirements to show."}</p>}
        {report && (
          <>
            <section className="lw-settings__section">
              <h3>{report.name}</h3>
              <SourceLine source={report.source} readOn={report.readOn} />
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
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" disabled={busy} onClick={() => void load()}>{busy ? "Checking…" : "Check again"}</button>
        <button className="lw-btn lw-btn--primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
