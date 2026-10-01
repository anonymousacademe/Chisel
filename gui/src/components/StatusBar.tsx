import { useEffect, useState } from "react";
import { GitBranch, Clock3, CloudCheck, CloudUpload, CloudOff, Target, ChevronsUpDown, Coins, SpellCheck } from "lucide-react";
import { Icon } from "./primitives";
import type { StatsBrief, SyncInfo } from "../data/types";
import { syncTip } from "../data/syncText";
import { fmt } from "../data/tree";
import { agoText } from "../data/snapshots";

export function StatusBar(props: {
  projectWords: number; aiCost: number;
  line: number; col: number; zoom: number; onZoom: () => void;
  /** Misspellings in the open scene (null: spell check does not apply here). */
  spelling: number | null; onSpelling: () => void;
  /** Latest snapshot of the open scene (ISO local time); undefined = no scene is open. */
  snapshotAt: string | null | undefined; onSnapshots: () => void;
  draft: number; onDraft: (anchor: HTMLElement) => void;
  /** Git state of the project folder; null = git is not installed (item hidden). */
  sync: SyncInfo | null; onSync: (anchor: HTMLElement) => void;
  /** Writing stats (null: no project); the buttons open the Session stats page. */
  stats: StatsBrief | null; onStats: () => void;
}) {
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 30_000); return () => clearInterval(t); }, []);
  const stats = props.stats;
  const today = stats ? (stats.todayWords >= 0 ? `+${fmt(stats.todayWords)}` : `−${fmt(-stats.todayWords)}`) : "";
  const goal = stats && stats.target > 0 ? ` / ${fmt(stats.target)}` : "";
  return (
    <footer className="lw-status">
      <div className="lw-row">
        <button className="lw-status__item" title="Which draft of the book this is: click to start the next one" onClick={(e) => props.onDraft(e.currentTarget)}>
          <Icon icon={GitBranch} size={12} stroke={1.5} color="var(--lw-text-faint)" />Draft {props.draft}
        </button>
        <span className="lw-status__div" />
        {props.snapshotAt === undefined
          ? <span className="lw-status__item" title="Open a scene to see its snapshots"><Icon icon={Clock3} size={12} stroke={1.5} color="var(--lw-text-faint)" />Snapshots</span>
          : <button className="lw-status__item" title="Snapshots of this scene" onClick={props.onSnapshots}>
            <Icon icon={Clock3} size={12} stroke={1.5} color="var(--lw-text-faint)" />
            {props.snapshotAt ? `Snapshot ${agoText(props.snapshotAt)}` : "No snapshot"}
          </button>}
        {props.sync && (
          <>
            <span className="lw-status__div" />
            <button className={`lw-status__item${props.sync.repo && props.sync.state !== "synced" ? " is-warn" : ""}`}
              title={syncTip(props.sync)} onClick={(e) => props.onSync(e.currentTarget)}>
              <Icon icon={!props.sync.repo ? CloudOff : props.sync.state === "synced" ? CloudCheck : CloudUpload} size={12} stroke={1.5} color="currentColor" />
              {props.sync.label}
            </button>
          </>
        )}
      </div>
      <div className="lw-row">
        {stats && (
          <>
            <button className="lw-status__item" onClick={props.onStats}
              title={stats.streak ? `${stats.streak} day${stats.streak === 1 ? "" : "s"} in a row${stats.target ? ` at ${fmt(stats.target)}+ words` : ""}` : "No streak yet: write to the daily target to start one"}>
              <span className="lw-dot" />Streak {stats.streak}
            </button>
            <span className="lw-status__div" />
            <button className={`lw-status__item${stats.todayMet ? " is-accent" : ""}`} onClick={props.onStats}
              title="Words you wrote today across sessions (accepted AI drafts are not counted). Click for session stats.">
              <Icon icon={Target} size={12} stroke={1.5} />{today}{goal} words today
            </button>
            <span className="lw-status__div" />
          </>
        )}
        <span className="lw-status__item">{fmt(props.projectWords)} project words</span>
        <span className="lw-status__div" />
        <span className="lw-status__item" title="AI spend this session"><Icon icon={Coins} size={12} stroke={1.5} color="var(--lw-text-faint)" />AI ${props.aiCost.toFixed(4)}</span>
        <span className="lw-status__div" />
        {props.spelling !== null && (
          <>
            <button className={`lw-status__item${props.spelling ? " is-warn" : ""}`} disabled={props.spelling === 0}
              title={props.spelling ? "Jump to the next misspelled word" : "No misspelled words"} onClick={props.onSpelling}>
              <Icon icon={SpellCheck} size={12} stroke={1.5} color="currentColor" />{props.spelling} spelling
            </button>
            <span className="lw-status__div" />
          </>
        )}
        <span className="lw-status__item">Ln {props.line}, Col {props.col}</span>
        <button className="lw-status__item" onClick={props.onZoom} aria-label="Change zoom">
          <Icon icon={ChevronsUpDown} size={12} stroke={1.5} color="var(--lw-text-faint)" />{props.zoom}%
        </button>
      </div>
    </footer>
  );
}
