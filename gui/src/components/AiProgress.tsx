import { useEffect, useRef } from "react";
import { secs, stopOnEsc, useElapsed, type AiRunView } from "./aiRun";
import { Square } from "lucide-react";
import { Icon } from "./primitives";

export function StopButton({ onStop, small = false }: { onStop: () => void; small?: boolean }) {
  return (
    <button className={`lw-stop${small ? " lw-stop--small" : ""}`} onClick={onStop} title="Stop (Esc): nothing is inserted or changed">
      <Icon icon={Square} size={10} stroke={2} /> Stop
    </button>
  );
}

/** Under the cursor: the draft as it is written. Nothing reaches the scene until the job is done. */
export function DraftPanel({ run, onStop }: { run: AiRunView; onStop: () => void }) {
  const elapsed = useElapsed(run.startedAt, run.elapsed);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight }); }, [run.text]);
  const a = run.anchor;
  const W = 380, H = 230;
  const style: React.CSSProperties = a
    ? { left: Math.max(8, Math.min(a.x, window.innerWidth - W - 12)), top: Math.max(8, Math.min(a.y + 8, window.innerHeight - H - 40)) }
    : { left: "50%", bottom: 48, transform: "translateX(-50%)" };
  return (
    <div className="lw-draftpanel" style={style} tabIndex={0} role="region" aria-label="AI drafting" onKeyDown={stopOnEsc(onStop)}>
      <div className="lw-draftpanel__head">
        <span className="lw-pulse">{run.label}</span>
        <span className="lw-faint lw-mono">{secs(elapsed)}</span>
        <StopButton onStop={onStop} small />
      </div>
      <div className="lw-draftpanel__body" ref={body}>
        {run.text || <span className="lw-faint">Waiting for the first words…</span>}
      </div>
      <div className="lw-draftpanel__foot">Nothing is inserted until it is finished. Stop discards it.</div>
    </div>
  );
}

/** For actions that answer all at once: a moving bar, the elapsed seconds and Stop. */
export function ProgressStrip({ run, onStop }: { run: AiRunView; onStop: () => void }) {
  const elapsed = useElapsed(run.startedAt, run.elapsed);
  return (
    <div className="lw-progress" tabIndex={0} role="status" onKeyDown={stopOnEsc(onStop)}>
      <span className="lw-progress__bar" aria-hidden />
      <span className="lw-progress__label">{run.label}</span>
      <span className="lw-faint lw-mono">{secs(elapsed)}</span>
      <StopButton onStop={onStop} small />
    </div>
  );
}

/** Status-bar item: "AI: drafting… 12 s · Stop". */
export function AiStatus({ run, onStop }: { run: AiRunView; onStop: () => void }) {
  const elapsed = useElapsed(run.startedAt, run.elapsed);
  return (
    <>
      <span className="lw-status__item is-accent" aria-live="off">AI: {run.verb}… {secs(elapsed)}</span>
      <button className="lw-status__item lw-status__stop" onClick={onStop} title="Stop the AI request">· Stop</button>
      <span className="lw-status__div" />
    </>
  );
}
