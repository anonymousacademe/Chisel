import { GitBranch, Clock3, CloudCheck, Target, ChevronsUpDown } from "lucide-react";
import { Icon } from "./primitives";

const fmt = (n: number) => n.toLocaleString("en-US");

export function StatusBar(props: {
  draft: string; snapshot: string; synced: boolean; streak: number;
  sessionWords: number; sessionTarget: number; projectWords: number;
  line: number; col: number; zoom: number; onZoom: () => void;
}) {
  return (
    <footer className="lw-status">
      <div className="lw-row">
        <span className="lw-status__item"><Icon icon={GitBranch} size={12} stroke={1.5} color="var(--lw-text-faint)" />{props.draft}</span>
        <span className="lw-status__div" />
        <span className="lw-status__item"><Icon icon={Clock3} size={12} stroke={1.5} color="var(--lw-text-faint)" />Snapshot {props.snapshot}</span>
        <span className="lw-status__div" />
        <span className="lw-status__item"><Icon icon={CloudCheck} size={12} stroke={1.5} color="var(--lw-text-faint)" />{props.synced ? "Project synced" : "Not synced"}</span>
      </div>
      <div className="lw-row">
        <span className="lw-status__item"><span className="lw-dot is-good" />{props.streak} day streak</span>
        <span className="lw-status__div" />
        <span className="lw-status__item is-accent"><Icon icon={Target} size={12} stroke={1.5} />{fmt(props.sessionWords)} / {fmt(props.sessionTarget)} session words</span>
        <span className="lw-status__div" />
        <span className="lw-status__item">{fmt(props.projectWords)} project words</span>
        <span className="lw-status__div" />
        <span className="lw-status__item">Ln {props.line}, Col {props.col}</span>
        <button className="lw-status__item" onClick={props.onZoom} aria-label="Change zoom">
          <Icon icon={ChevronsUpDown} size={12} stroke={1.5} color="var(--lw-text-faint)" />{props.zoom}%
        </button>
      </div>
    </footer>
  );
}
