import { useEffect, useState } from "react";
import { api } from "../backend/api";
import type { StatsSummary } from "../data/types";
import { chartBars, dayLabel, signedWords } from "../data/stats";
import { fmt } from "../data/tree";
import { Modal } from "./Dialogs";

/** Read-only writing stats: today, this session, the last 30 days, streak. Not a dashboard. */
export function StatsDialog({ onClose, notify }: { onClose: () => void; notify: (text: string, tone?: "info" | "error") => void }) {
  const [s, setS] = useState<StatsSummary | null>(null);
  useEffect(() => {
    void api.statsSummary().then((r) => { if (r.ok) setS(r.stats); else notify(r.error, "error"); });
  }, [notify]);
  const bars = s ? chartBars(s.chart, s.target) : [];
  return (
    <Modal title="Session stats" wide onClose={onClose}>
      {!s ? <p className="lw-empty">Loading…</p> : (
        <div className="lw-stats">
          <dl className="lw-stats__grid">
            <div><dt>Today</dt><dd>{signedWords(s.today.words)}{s.target ? <span className="lw-faint"> of {fmt(s.target)}</span> : null}</dd>
              <small>{s.today.minutes} min active · {s.today.sessions} session{s.today.sessions === 1 ? "" : "s"}{s.today.aiWords ? ` · ${fmt(s.today.aiWords)} AI words accepted` : ""}</small></div>
            <div><dt>This session</dt><dd>{signedWords(s.session.words)}</dd><small>{s.session.minutes} min active</small></div>
            <div><dt>Streak</dt><dd>{s.streak} day{s.streak === 1 ? "" : "s"}</dd>
              <small>{s.target ? `${fmt(s.target)}+ words a day` : "any day with a word"}{s.todayMet ? " · today is done" : ""}</small></div>
            <div><dt>Best day</dt><dd>{s.bestDay ? fmt(s.bestDay.words) : "—"}</dd><small>{s.bestDay ? dayLabel(s.bestDay.date) : "nothing yet"}</small></div>
            <div><dt>Per session</dt><dd>{fmt(s.averagePerSession)}</dd><small>words on average</small></div>
            <div><dt>Project</dt><dd>{fmt(s.projectWords)}</dd><small>words in the book · {fmt(s.totalWords)} written here</small></div>
          </dl>
          <h3 className="lw-stats__h">Last 30 days</h3>
          <div className="lw-stats__chart" role="img" aria-label="Words written per day over the last 30 days">
            {bars.map((b) => (
              <div key={b.date} className={`lw-stats__col${b.met ? " is-met" : ""}`} title={`${dayLabel(b.date)}: ${signedWords(b.words)}`}>
                <div className="lw-stats__bar" style={{ height: `${b.height}%` }} />
              </div>
            ))}
          </div>
          <div className="lw-stats__axis"><span>{dayLabel(s.chart[0].date)}</span><span>today</span></div>
          {s.sprints.length > 0 && (
            <>
              <h3 className="lw-stats__h">Sprints today</h3>
              <ul className="lw-stats__sprints">
                {s.sprints.map((p, i) => (
                  <li key={i}>{p.minutes} minutes: {signedWords(p.words)}{p.completed ? "" : " (stopped early)"}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      <div className="lw-dialog__buttons"><button className="lw-btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

const SPRINT_LENGTHS = [15, 25, 45];

/** Pick a sprint length (15 / 25 / 45 / custom) and whether to hide the chrome while it runs. */
export function SprintDialog({ initialFocus, onStart, onClose }: {
  initialFocus: boolean; onStart: (minutes: number, focusMode: boolean) => void; onClose: () => void;
}) {
  const [choice, setChoice] = useState<number | "custom">(25);
  const [custom, setCustom] = useState("30");
  const [focus, setFocus] = useState(initialFocus);
  const minutes = choice === "custom" ? Number(custom) : choice;
  const valid = Number.isInteger(minutes) && minutes >= 1 && minutes <= 240;
  const go = () => { if (valid) onStart(minutes, focus); };
  return (
    <Modal title="Focus sprint" onClose={onClose}>
      <p className="lw-dialog__message">Write against the clock. The countdown sits in the status bar; when it ends you get a quiet notice with the words you wrote. Nothing is sent anywhere.</p>
      <div className="lw-dialog__types" role="radiogroup" aria-label="Sprint length">
        {SPRINT_LENGTHS.map((m) => (
          <button key={m} role="radio" aria-checked={choice === m} className={`lw-chip lw-chip--pick${choice === m ? " is-on" : ""}`}
            onClick={() => setChoice(m)}>{m} min</button>
        ))}
        <button role="radio" aria-checked={choice === "custom"} className={`lw-chip lw-chip--pick${choice === "custom" ? " is-on" : ""}`}
          onClick={() => setChoice("custom")}>Custom</button>
        {choice === "custom" && (
          <input className="lw-launch__input lw-settings__narrow" autoFocus inputMode="numeric" aria-label="Sprint minutes" value={custom}
            onChange={(e) => setCustom(e.target.value.replace(/[^\d]/g, ""))} onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
        )}
      </div>
      <label className="lw-check">
        <input type="checkbox" checked={focus} onChange={(e) => setFocus(e.target.checked)} />
        Hide everything but the page while it runs <span className="lw-faint">(focus mode, F11)</span>
      </label>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!valid} onClick={go}>Start sprint</button>
      </div>
    </Modal>
  );
}
