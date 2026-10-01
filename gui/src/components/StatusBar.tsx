import { useEffect, useState } from "react";
import { GitBranch, Clock3, CloudCheck, Target, ChevronsUpDown, Coins, SpellCheck } from "lucide-react";
import { Icon } from "./primitives";
import { placeholderProps } from "./placeholder";
import { fmt } from "../data/tree";
import { agoText } from "../data/snapshots";

export function StatusBar(props: {
  sessionWords: number; projectWords: number; aiCost: number;
  line: number; col: number; zoom: number; onZoom: () => void;
  /** Misspellings in the open scene (null: spell check does not apply here). */
  spelling: number | null; onSpelling: () => void;
  /** Latest snapshot of the open scene (ISO local time); undefined = no scene is open. */
  snapshotAt: string | null | undefined; onSnapshots: () => void;
  draft: number; onDraft: (anchor: HTMLElement) => void;
}) {
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 30_000); return () => clearInterval(t); }, []);
  const signed = props.sessionWords >= 0 ? `+${fmt(props.sessionWords)}` : `−${fmt(-props.sessionWords)}`;
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
        <span className="lw-status__div" />
        <span className="lw-status__item" {...placeholderProps}><Icon icon={CloudCheck} size={12} stroke={1.5} color="var(--lw-text-faint)" />Sync</span>
      </div>
      <div className="lw-row">
        <span className="lw-status__item" {...placeholderProps}><span className="lw-dot" />Streak</span>
        <span className="lw-status__div" />
        <span className="lw-status__item is-accent" title="Net words since the project was opened">
          <Icon icon={Target} size={12} stroke={1.5} />{signed}
          <span {...placeholderProps}>/ —</span> session words
        </span>
        <span className="lw-status__div" />
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
