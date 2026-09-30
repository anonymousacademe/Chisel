import { Library, Search, Sparkles, BookMarked, History, Settings, type LucideIcon } from "lucide-react";
import { Icon } from "./primitives";

export type RailView = "binder" | "search" | "assistant" | "research";

const primary: { id: RailView; icon: LucideIcon; label: string }[] = [
  { id: "binder", icon: Library, label: "Binder" },
  { id: "search", icon: Search, label: "Search" },
  { id: "assistant", icon: Sparkles, label: "Assistant" },
  { id: "research", icon: BookMarked, label: "Research" },
];

export function ActivityRail({ view, onView, badge, initials }:
  { view: RailView; onView: (v: RailView) => void; badge: number; initials: string }) {
  return (
    <nav className="lw-rail" aria-label="Primary">
      <div className="lw-rail__group lw-rail__group--top">
        {primary.map((item) => (
          <button key={item.id} className={`lw-rail__item${view === item.id ? " is-active" : ""}`}
            aria-label={item.label} title={item.label} onClick={() => onView(item.id)}>
            {view === item.id && <span className="lw-rail__indicator" />}
            <Icon icon={item.icon} size={19} />
            {item.id === "assistant" && badge > 0 && <span className="lw-rail__badge">{badge}</span>}
          </button>
        ))}
        {/* The design reserves two further, empty slots here (no icon assigned). */}
        <span className="lw-rail__item lw-rail__item--empty" aria-hidden />
        <span className="lw-rail__item lw-rail__item--empty" aria-hidden />
      </div>
      <div className="lw-rail__group lw-rail__group--bottom">
        <button className="lw-rail__item" aria-label="Snapshots" title="Snapshots"><Icon icon={History} size={19} /></button>
        <button className="lw-rail__item" aria-label="Settings" title="Settings"><Icon icon={Settings} size={19} /></button>
        <button className="lw-rail__profile" aria-label="Author profile" title="Author profile">
          <span className="lw-rail__avatar">{initials}</span>
          <span className="lw-rail__online" />
        </button>
      </div>
    </nav>
  );
}
