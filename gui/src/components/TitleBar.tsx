import { BookOpen, CloudCheck, Search, PanelRight, Ellipsis } from "lucide-react";
import { Icon, IconButton, Tag } from "./primitives";
import { windowAction } from "../backend";

export function TitleBar(props: {
  projectTitle: string; documentLabel: string; draft: string; saved: boolean;
  assistantOpen: boolean; onToggleAssistant: () => void; onSearch: () => void;
}) {
  return (
    <header className="lw-titlebar pywebview-drag-region">
      <div className="lw-traffic">
        <button className="lw-traffic__dot is-close" aria-label="Close window" onClick={() => windowAction("close")} />
        <button className="lw-traffic__dot is-min" aria-label="Minimize window" onClick={() => windowAction("minimize")} />
        <button className="lw-traffic__dot is-max" aria-label="Maximize window" onClick={() => windowAction("toggle_maximize")} />
      </div>

      <div className="lw-titlebar__identity pywebview-drag-region">
        <Icon icon={BookOpen} size={15} stroke={1.7} color="var(--lw-accent-text)" />
        <span className="lw-titlebar__project">{props.projectTitle}</span>
        <span className="lw-titlebar__sep">/</span>
        <span className="lw-titlebar__doc">{props.documentLabel}</span>
        <Tag>{props.draft}</Tag>
      </div>

      <div className="lw-titlebar__actions">
        <span className="lw-sync">
          <Icon icon={CloudCheck} size={14} stroke={1.7} color="var(--lw-success)" />
          <span>{props.saved ? "Saved" : "Saving…"}</span>
        </span>
        <IconButton icon={Search} label="Search project" onClick={props.onSearch} />
        <IconButton icon={PanelRight} label="Toggle assistant panel" active={props.assistantOpen} onClick={props.onToggleAssistant} />
        <IconButton icon={Ellipsis} label="More" />
      </div>
    </header>
  );
}
