import { useEffect, useRef, useState } from "react";
import { api } from "../../../backend/api";
import type { ObjectKind } from "../../../data/research";

/** The label field of an insert dialog: Python proposes a unique plain label from *source* (the caption or file name)
 *  until the author types one; after that their text stays. */
export function useSuggestedLabel(kind: ObjectKind, source: string) {
  const [label, setLabelState] = useState("");
  const edited = useRef(false);
  const seq = useRef(0);
  useEffect(() => {
    if (edited.current) return;
    const mine = ++seq.current;
    void api.objectSuggestLabel(kind, source.trim()).then((r) => {
      if (r.ok && mine === seq.current && !edited.current) setLabelState(r.label);
    });
  }, [kind, source]);
  const setLabel = (v: string) => { edited.current = true; setLabelState(v); };
  return { label, setLabel };
}

export function LabelField({ kind, label, onChange }: { kind: ObjectKind; label: string; onChange: (v: string) => void }) {
  const prefix = `${kind}:`;
  return (
    <label className="lw-dialog__label">Label
      <input className="lw-launch__input lw-mono" value={label} onChange={(e) => onChange(e.target.value)} aria-label="Label" spellCheck={false}
        placeholder="a short plain name" />
      <span className="lw-faint">References read <span className="lw-mono">[[{prefix}{label || "label"}]]</span>. Letters, digits, - . and _ only.</span>
    </label>
  );
}
