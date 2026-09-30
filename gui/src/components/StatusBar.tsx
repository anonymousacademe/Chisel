import { GitBranch, Clock3, CloudCheck, Target, ChevronsUpDown, Coins } from "lucide-react";
import { Icon } from "./primitives";
import { placeholderProps } from "./placeholder";
import { fmt } from "../data/tree";

export function StatusBar(props: {
  sessionWords: number; projectWords: number; aiCost: number;
  line: number; col: number; zoom: number; onZoom: () => void;
}) {
  const signed = props.sessionWords >= 0 ? `+${fmt(props.sessionWords)}` : `−${fmt(-props.sessionWords)}`;
  return (
    <footer className="lw-status">
      <div className="lw-row">
        <span className="lw-status__item" {...placeholderProps}><Icon icon={GitBranch} size={12} stroke={1.5} color="var(--lw-text-faint)" />Draft</span>
        <span className="lw-status__div" />
        <span className="lw-status__item" {...placeholderProps}><Icon icon={Clock3} size={12} stroke={1.5} color="var(--lw-text-faint)" />Snapshots</span>
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
        <span className="lw-status__item">Ln {props.line}, Col {props.col}</span>
        <button className="lw-status__item" onClick={props.onZoom} aria-label="Change zoom">
          <Icon icon={ChevronsUpDown} size={12} stroke={1.5} color="var(--lw-text-faint)" />{props.zoom}%
        </button>
      </div>
    </footer>
  );
}
