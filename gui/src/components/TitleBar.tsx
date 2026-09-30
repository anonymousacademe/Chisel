import { BookOpen, CloudCheck, CloudUpload, CloudAlert, Search, PanelRight, Ellipsis } from "lucide-react";
import { Icon, IconButton, Tag } from "./primitives";
import { api } from "../backend/api";

import type { SaveState } from "../editor/saveController";

const SAVE_LABEL: Record<SaveState, string> = {
  saved: "Saved", dirty: "Unsaved", saving: "Saving…", conflict: "Changed on disk", error: "Save failed",
};

export function TitleBar(props: {
  projectTitle: string; documentLabel: string; saveState: SaveState;
  assistantOpen: boolean; onToggleAssistant: () => void; onSearch: () => void;
  onMore?: (anchor: HTMLElement) => void; onClose: () => void;
}) {
  const SaveIcon = props.saveState === "saved" ? CloudCheck : props.saveState === "conflict" || props.saveState === "error" ? CloudAlert : CloudUpload;
  const saveColor = props.saveState === "saved" ? "var(--lw-success)" : props.saveState === "dirty" || props.saveState === "saving" ? "var(--lw-text-muted)" : "var(--lw-warning)";
  return (
    <header className="lw-titlebar pywebview-drag-region">
      <div className="lw-traffic">
        <button className="lw-traffic__dot is-close" aria-label="Close window" onClick={props.onClose} />
        <button className="lw-traffic__dot is-min" aria-label="Minimize window" onClick={() => api.minimize()} />
        <button className="lw-traffic__dot is-max" aria-label="Maximize window" onClick={() => api.toggleMaximize()} />
      </div>

      <div className="lw-titlebar__identity pywebview-drag-region">
        <Icon icon={BookOpen} size={15} stroke={1.7} color="var(--lw-accent-text)" />
        <span className="lw-titlebar__project">{props.projectTitle}</span>
        {props.documentLabel && <>
          <span className="lw-titlebar__sep">/</span>
          <span className="lw-titlebar__doc">{props.documentLabel}</span>
        </>}
        <Tag placeholder>Draft</Tag>
      </div>

      <div className="lw-titlebar__actions">
        <span className="lw-sync" role="status">
          <Icon icon={SaveIcon} size={14} stroke={1.7} color={saveColor} />
          <span>{SAVE_LABEL[props.saveState]}</span>
        </span>
        <IconButton icon={Search} label="Quick switcher (Ctrl K)" onClick={props.onSearch} />
        <IconButton icon={PanelRight} label="Toggle assistant panel" active={props.assistantOpen} onClick={props.onToggleAssistant} />
        <IconButton icon={Ellipsis} label="More" onClick={(e) => props.onMore?.(e.currentTarget)} placeholder={!props.onMore} />
      </div>
    </header>
  );
}
