import { useEffect, useRef, useState } from "react";
import { api } from "../../../backend/api";
import type { FigureRunStatus, FigureTrustInfo } from "../../../data/research";

type Notify = (text: string, tone?: "info" | "error") => void;

/** The script of a generated figure: shown in full with its hash, path and interpreter. A click on "Trust this script
 *  version" confirms exactly the hash shown; Run is possible only when that version is trusted, and only from its click.
 *  A changed script is untrusted again. */
export function FigureScript({ id, notify, onRan, pollMs = 400 }: {
  id: string; notify: Notify;
  /** The run finished and the picture was rewritten. */
  onRan: () => void;
  pollMs?: number;
}) {
  const [info, setInfo] = useState<FigureTrustInfo | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const [run, setRun] = useState<FigureRunStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  const load = async () => {
    const r = await api.figureTrustInfo(id);
    if (!live.current) return;
    if (r.ok) setInfo(r); else notify(r.error, "error");
  };
  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [id]);

  // poll a running job until it finishes
  useEffect(() => {
    if (!job) return;
    let stop = false;
    const tick = async () => {
      const r = await api.figureRunStatus(job);
      if (stop || !live.current) return;
      if (!r.ok) { setJob(null); setRun({ job, figure: id, state: "failed", error: r.error }); return; }
      setRun(r);
      if (r.state === "running") { timer = setTimeout(() => void tick(), pollMs); return; }
      setJob(null);
      if (r.state === "done") { onRan(); void load(); }
    };
    let timer = setTimeout(() => void tick(), pollMs);
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job]);

  const trust = async () => {
    if (!info || busy) return;
    setBusy(true);
    const r = await api.trustFigure(id, info.sha);          // exactly the version on screen
    setBusy(false);
    if (!r.ok) { notify(r.error, "error"); void load(); return; }
    setInfo({ ...info, trust: r.trust });
  };
  const start = async () => {
    if (!info || info.trust !== "trusted" || job) return;
    const r = await api.figureRunStart(id);
    if (!r.ok) return notify(r.error, "error");
    setRun({ job: r.job, figure: id, state: "running" });
    setJob(r.job);
  };
  const stop = async () => { if (job) await api.figureRunCancel(job); };

  if (!info) return <p className="lw-faint">Reading the script…</p>;
  const running = run?.state === "running";
  return (
    <section className="lw-obj__script" aria-label="Figure script">
      <h3>Script</h3>
      <dl className="lw-obj__facts">
        <dt>Path</dt><dd className="lw-mono">{info.path}</dd>
        <dt>SHA-256</dt><dd className="lw-mono lw-obj__sha" data-testid="script-sha">{info.sha}</dd>
        <dt>Interpreter</dt><dd className="lw-mono">{info.interpreter ?? "No Python interpreter found"}</dd>
        {info.data.length > 0 && <><dt>Data files</dt><dd className="lw-mono">{info.data.join(", ")}</dd></>}
      </dl>
      <pre className="lw-obj__code lw-mono" aria-label="Script text" tabIndex={0}>{info.script}</pre>
      {info.trust === "trusted" ? (
        <p className="lw-faint">You trusted this version of the script. If it changes, Chisel asks again before it runs.</p>
      ) : (
        <>
          <p className="lw-dialog__message">
            {info.trust === "changed"
              ? "The script changed since you trusted it. Read it again; it will not run until you trust this version."
              : "This script has not been trusted. It runs on your computer with your files. Read it, then trust it if it is yours."}
          </p>
          <div className="lw-row"><button className="lw-btn" disabled={busy} onClick={() => void trust()}>Trust this script version</button></div>
        </>
      )}
      <div className="lw-row lw-gap-8">
        <button className="lw-btn lw-btn--primary" disabled={info.trust !== "trusted" || !!job || !info.interpreter} onClick={() => void start()}>
          {running ? "Running…" : "Run the script"}
        </button>
        {running && <><span className="lw-spinner" role="status" aria-label="Running" /><button className="lw-btn" onClick={() => void stop()}>Stop</button></>}
        {run?.state === "cancelled" && <span className="lw-faint">Stopped. The old picture is unchanged.</span>}
        {run?.state === "done" && <span className="lw-faint">Done. The picture was updated.</span>}
      </div>
      {run?.state === "failed" && (
        <div role="alert" className="lw-obj__fail">
          <p className="lw-eq__error">{run.error || "The script failed."}</p>
          {run.stderr && <pre className="lw-obj__code lw-mono" aria-label="Error output">{run.stderr}</pre>}
        </div>
      )}
    </section>
  );
}
