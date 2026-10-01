import { useEffect, useRef, useState, type ReactNode } from "react";

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  // Escape closes the dialog wherever focus is (it may still be on the button that opened it).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); onClose(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="lw-overlay lw-overlay--center" onMouseDown={onClose}>
      <div className={`lw-dialog${wide ? " lw-dialog--wide" : ""}`} role="dialog" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <h2 className="lw-dialog__title">{title}</h2>
        {children}
      </div>
    </div>
  );
}

/** One text field + OK/Cancel (new scene, rename, new note). */
export function PromptDialog({ title, label, initial = "", confirm = "OK", onSubmit, onClose, children }: {
  title: string; label: string; initial?: string; confirm?: string;
  onSubmit: (value: string) => void; onClose: () => void; children?: ReactNode;
}) {
  const [value, setValue] = useState(initial);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.select(); }, []);
  const submit = () => { if (value.trim()) onSubmit(value.trim()); };
  return (
    <Modal title={title} onClose={onClose}>
      <label className="lw-dialog__label">{label}
        <input ref={input} autoFocus className="lw-launch__input" value={value} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
      </label>
      {children}
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!value.trim()} onClick={submit}>{confirm}</button>
      </div>
    </Modal>
  );
}

export function ConfirmDialog({ title, message, confirm = "Delete", tone = "danger", onConfirm, onClose }: {
  title: string; message: ReactNode; confirm?: string; tone?: "danger" | "primary"; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="lw-dialog__message">{message}</p>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" autoFocus onClick={onClose}>Cancel</button>
        <button className={`lw-btn lw-btn--${tone}`} onClick={onConfirm}>{confirm}</button>
      </div>
    </Modal>
  );
}

export interface MenuItem { label: string; onSelect: () => void; disabled?: boolean; danger?: boolean; separator?: boolean }

/** A small popover menu anchored under a button. */
export function Menu({ anchor, items, onClose }: { anchor: HTMLElement; items: MenuItem[]; onClose: () => void }) {
  const rect = anchor.getBoundingClientRect();
  // anchored near the bottom (status bar): open upward instead of off-screen
  const height = items.length * 30 + 12;
  const up = rect.bottom + 4 + height > window.innerHeight && rect.top - 4 - height > 0;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="lw-overlay lw-overlay--clear" onMouseDown={onClose}>
      <div className="lw-menu" role="menu" style={{ ...(up ? { bottom: window.innerHeight - rect.top + 4 } : { top: rect.bottom + 4 }), left: Math.min(rect.left, window.innerWidth - 220) }}
        onMouseDown={(e) => e.stopPropagation()}>
        {items.map((it) => it.separator ? <hr key={it.label} className="lw-menu__sep" /> : (
          <button key={it.label} role="menuitem" disabled={it.disabled} className={`lw-menu__item${it.danger ? " is-danger" : ""}`}
            onClick={() => { onClose(); it.onSelect(); }}>{it.label}</button>
        ))}
      </div>
    </div>
  );
}
