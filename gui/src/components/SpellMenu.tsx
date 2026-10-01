import { useEffect, useState } from "react";
import { api } from "../backend/api";
import type { SpellTarget } from "../editor/cm";

/** The spelling popover: suggestions (a normal undoable edit), dictionaries, ignore.
 *  For a selected phrase it only offers the dictionaries. */
export function SpellMenu({ target, onReplace, onAdd, onIgnore, onClose }: {
  target: SpellTarget;
  onReplace: (text: string) => void;
  onAdd: (scope: "project" | "personal") => void;
  onIgnore: () => void;
  onClose: () => void;
}) {
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const word = target.kind === "word" ? target.word : null;

  useEffect(() => {
    if (word === null) return;
    let live = true;
    void api.spellingSuggestions(word).then((r) => { if (live) setSuggestions(r.ok ? r.suggestions : []); });
    return () => { live = false; };
  }, [word]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const term = target.kind === "word" ? target.word : target.text.trim().replace(/\s+/g, " ");
  const shown = term.length > 28 ? `${term.slice(0, 27)}…` : term;
  const phrase = target.kind === "phrase";
  const top = Math.min(target.y + 4, window.innerHeight - 280);
  const left = Math.min(target.x, window.innerWidth - 240);
  const act = (fn: () => void) => () => { onClose(); fn(); };

  return (
    <div className="lw-overlay lw-overlay--clear" onMouseDown={onClose} onContextMenu={(e) => { e.preventDefault(); onClose(); }}>
      <div className="lw-menu lw-spellmenu" role="menu" aria-label={phrase ? "Phrase" : `Spelling: ${term}`} style={{ top, left }}
        onMouseDown={(e) => e.stopPropagation()}>
        {word !== null && (
          <>
            {suggestions === null && <span className="lw-spellmenu__note lw-pulse">Looking…</span>}
            {suggestions?.length === 0 && <span className="lw-spellmenu__note">No suggestions</span>}
            {suggestions?.map((s) => (
              <button key={s} role="menuitem" className="lw-menu__item lw-spellmenu__suggestion" onClick={act(() => onReplace(s))}>{s}</button>
            ))}
            <span className="lw-spellmenu__sep" role="separator" />
          </>
        )}
        <button role="menuitem" className="lw-menu__item" onClick={act(() => onAdd("project"))}>
          {phrase ? `Add phrase “${shown}” to dictionary` : "Add to dictionary"}
        </button>
        <button role="menuitem" className="lw-menu__item" onClick={act(() => onAdd("personal"))}>Add to my dictionary (all projects)</button>
        {!phrase && <button role="menuitem" className="lw-menu__item" onClick={act(onIgnore)}>Ignore</button>}
      </div>
    </div>
  );
}
