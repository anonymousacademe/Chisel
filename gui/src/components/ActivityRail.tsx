import { Library, Search, Sparkles, BookMarked, History, Settings, type LucideIcon } from "lucide-react";
import { Icon } from "./primitives";
import { placeholderProps } from "./placeholder";

export type RailView = "binder" | "search" | "assistant" | "library";

const primary: { id: RailView; icon: LucideIcon; label: string }[] = [
  { id: "binder", icon: Library, label: "Binder" },
  { id: "search", icon: Search, label: "Search" },
  { id: "assistant", icon: Sparkles, label: "Assistant" },
  { id: "library", icon: BookMarked, label: "Library" },
];

export function ActivityRail({ view, assistantOpen, onView, onSettings, badge, initials, author }:
  { view: RailView; assistantOpen: boolean; onView: (v: RailView) => void; onSettings?: () => void; badge: number; initials: string; author: string }) {
  return (
    <nav className="lw-rail" aria-label="Primary">
      <div className="lw-rail__group lw-rail__group--top">
        {primary.map((item) => {
          const active = item.id === "assistant" ? assistantOpen : view === item.id;
          return (
          <button key={item.id} className={`lw-rail__item${active ? " is-active" : ""}`}
            aria-label={item.label} title={item.label} onClick={() => onView(item.id)}>
            {active && <span className="lw-rail__indicator" />}
            <Icon icon={item.icon} size={19} />
            {item.id === "assistant" && badge > 0 && <span className="lw-rail__badge">{badge}</span>}
          </button>
          );
        })}
        {/* The design reserves two further, empty slots here (no icon assigned). */}
        <span className="lw-rail__item lw-rail__item--empty" aria-hidden />
        <span className="lw-rail__item lw-rail__item--empty" aria-hidden />
      </div>
      <div className="lw-rail__group lw-rail__group--bottom">
        <button className="lw-rail__item" aria-label="Snapshots" {...placeholderProps}><Icon icon={History} size={19} /></button>
        <button className="lw-rail__item" aria-label="Settings" {...(onSettings ? { title: "Settings", onClick: onSettings } : placeholderProps)}><Icon icon={Settings} size={19} /></button>
        <button className="lw-rail__profile" aria-label="Author profile" title={author || "Author (set `author` in project.toml)"}>
          <span className="lw-rail__avatar">{initials}</span>
          <span className="lw-rail__online" />
        </button>
      </div>
    </nav>
  );
}
