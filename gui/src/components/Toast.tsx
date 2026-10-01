import { X } from "lucide-react";
import { Icon } from "./primitives";

export interface Notice { id: number; text: string; tone: "info" | "error"; action?: { label: string; run: () => void } }

export function Toasts({ notices, onDismiss }: { notices: Notice[]; onDismiss: (id: number) => void }) {
  if (notices.length === 0) return null;
  return (
    <div className="lw-toasts" role="status" aria-live="polite">
      {notices.map((n) => (
        <div key={n.id} className={`lw-toast is-${n.tone}`}>
          <span>{n.text}</span>
          {n.action && <button className="lw-toast__action" onClick={() => { n.action!.run(); onDismiss(n.id); }}>{n.action.label}</button>}
          <button aria-label="Dismiss" onClick={() => onDismiss(n.id)}><Icon icon={X} size={12} stroke={1.8} /></button>
        </div>
      ))}
    </div>
  );
}
