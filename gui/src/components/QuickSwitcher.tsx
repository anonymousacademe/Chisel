import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import type { Workspace } from "../data/types";
import { filterSwitcher, switcherItems } from "../data/switcher";
import { Icon } from "./primitives";

export function QuickSwitcher({ ws, onPick, onClose }: { ws: Workspace; onPick: (id: string) => void; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const all = useMemo(() => switcherItems(ws), [ws]);
  const shown = useMemo(() => filterSwitcher(all, query).slice(0, 50), [all, query]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { listRef.current?.querySelector(".is-selected")?.scrollIntoView({ block: "nearest" }); }, [index]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, shown.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && shown[index]) { e.preventDefault(); onPick(shown[index].id); }
  };

  return (
    <div className="lw-overlay" onMouseDown={onClose}>
      <div className="lw-switcher" role="dialog" aria-label="Quick switcher" onMouseDown={(e) => e.stopPropagation()}>
        <div className="lw-switcher__input">
          <Icon icon={Search} size={14} stroke={1.7} color="var(--lw-text-muted)" />
          <input autoFocus value={query} onChange={(e) => { setQuery(e.target.value); setIndex(0); }} onKeyDown={onKey}
            placeholder="Jump to a scene or note…" aria-label="Quick switcher" />
        </div>
        <div className="lw-switcher__list" ref={listRef} role="listbox">
          {shown.map((it, i) => (
            <button key={it.id} role="option" aria-selected={i === index}
              className={`lw-switcher__row${i === index ? " is-selected" : ""}`}
              onMouseMove={() => setIndex(i)} onClick={() => onPick(it.id)}>
              <span className="lw-switcher__title">{it.title}</span>
              <span className="lw-switcher__detail">{it.category} · {it.detail}</span>
            </button>
          ))}
          {shown.length === 0 && <p className="lw-empty">Nothing matches “{query}”.</p>}
        </div>
      </div>
    </div>
  );
}
