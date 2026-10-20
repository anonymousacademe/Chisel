import { useCallback, useEffect, useState } from "react";
import { api } from "../../backend/api";
import { CHECK_CHOICES, CHECK_PARAMS, DEFAULT_GROUP, OBJECT_WORD, cleanRow, describeCheck, uniqueId, type ParamName } from "../../data/requirementsCustom";
import type { CustomCheck, CustomRequirement, CustomSeverity, ObjectKind } from "../../data/research";
import { ConfirmDialog } from "../Dialogs";

type Notify = (text: string, tone?: "info" | "error") => void;

const NUMBER_LABEL: Record<"min" | "max" | "item_chars_max", string> = { min: "At least", max: "At most", item_chars_max: "Characters per item, at most" };

/** The author's own requirements (requirements.toml): list, remove (after a confirm) and a small form to add one.
 *  Python validates every row; its message is shown as is when it refuses. */
export function ManageRequirements({ notify, onChanged }: { notify: Notify; onChanged: () => void }) {
  const [rows, setRows] = useState<CustomRequirement[]>([]);
  const [open, setOpen] = useState(false);
  const [removing, setRemoving] = useState<CustomRequirement | null>(null);
  const [title, setTitle] = useState("");
  const [choice, setChoice] = useState<CustomCheck | "advice">("section-words-max");
  const [section, setSection] = useState("");
  const [nums, setNums] = useState<Record<"min" | "max" | "item_chars_max", string>>({ min: "", max: "", item_chars_max: "" });
  const [object, setObject] = useState<ObjectKind>("fig");
  const [severity, setSeverity] = useState<CustomSeverity>("warn");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.requirementsCustom();
      if (r?.ok) setRows(r.rows);
    } catch { /* the list is optional: the checklist above still works */ }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const params: ParamName[] = choice === "advice" ? [] : CHECK_PARAMS[choice];

  const remove = async (row: CustomRequirement) => {
    setRemoving(null);
    const r = await api.requirementsRemove(row.id);
    if (!r.ok) return notify(r.error, "error");
    setRows(r.rows); notify(`Removed ${row.title}.`); onChanged();
  };

  const add = async () => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const row: CustomRequirement = {
        id: uniqueId(title, new Set(rows.map((x) => x.id))), group: DEFAULT_GROUP, title, severity,
        kind: choice === "advice" ? "advice" : "check",
      };
      if (choice !== "advice") {
        row.check = choice;
        if (params.includes("section")) row.section = section.split(",").map((s) => s.trim()).filter(Boolean);
        if (params.includes("object")) row.object = object;
        for (const key of ["min", "max", "item_chars_max"] as const) {
          if (params.includes(key) && nums[key].trim() !== "") row[key] = Number(nums[key]);
        }
      }
      const r = await api.requirementsSave([...rows, cleanRow(row)]);
      if (!r.ok) return setError(r.error);
      setRows(r.rows); setTitle(""); setSection(""); setNums({ min: "", max: "", item_chars_max: "" });
      notify(`Added ${row.title.trim()}.`); onChanged();
    } finally { setBusy(false); }
  };

  const ready = title.trim() !== "" && (!params.includes("section") || section.trim() !== "")
    && (choice !== "section-words-max" || nums.max.trim() !== "");

  return (
    <section className="lw-settings__section" aria-label="My requirements">
      <h3>Manage my requirements...</h3>
      {rows.length === 0 && <p className="lw-dialog__message lw-faint">You have not added any requirements.</p>}
      <ul className="lw-dialog__message" aria-label="My requirements list" style={{ listStyle: "none", padding: 0 }}>
        {rows.map((r) => (
          <li key={r.id} className="lw-row lw-gap-8">
            <span className="lw-btn--grow">
              <strong>{r.title}</strong> <span className="lw-faint">{describeCheck(r)}{r.source ? `, from ${r.source}` : ""}</span>
              {r.quote && <div className="lw-faint">“{r.quote}”</div>}
            </span>
            <button className="lw-btn" aria-label={`Remove ${r.title}`} onClick={() => setRemoving(r)}>Remove</button>
          </li>
        ))}
      </ul>
      {!open && <div className="lw-row lw-gap-8"><button className="lw-btn" onClick={() => setOpen(true)}>Add a requirement</button></div>}
      {open && (
        <div className="lw-settings__section" role="group" aria-label="Add a requirement">
          <label className="lw-dialog__label">Title
            <input className="lw-launch__input" value={title} aria-label="Requirement title" onChange={(e) => setTitle(e.target.value)} placeholder="Abstract length" />
          </label>
          <label className="lw-dialog__label">What to check
            <select className="lw-launch__input" value={choice} aria-label="What to check" onChange={(e) => setChoice(e.target.value as CustomCheck | "advice")}>
              {CHECK_CHOICES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </label>
          {params.includes("section") && (
            <label className="lw-dialog__label">Section title (words it contains; separate alternatives with commas)
              <input className="lw-launch__input" value={section} aria-label="Section title" onChange={(e) => setSection(e.target.value)} placeholder="abstract" />
            </label>
          )}
          {params.includes("object") && (
            <label className="lw-dialog__label">Which
              <select className="lw-launch__input" value={object} aria-label="Which kind" onChange={(e) => setObject(e.target.value as ObjectKind)}>
                {(Object.keys(OBJECT_WORD) as ObjectKind[]).map((k) => <option key={k} value={k}>{OBJECT_WORD[k]}s</option>)}
              </select>
            </label>
          )}
          {(["min", "max", "item_chars_max"] as const).filter((k) => params.includes(k)).map((k) => (
            <label key={k} className="lw-dialog__label">{NUMBER_LABEL[k]}
              <input type="number" min={0} className="lw-launch__input" value={nums[k]} aria-label={NUMBER_LABEL[k]}
                onChange={(e) => setNums((n) => ({ ...n, [k]: e.target.value }))} />
            </label>
          ))}
          {choice !== "advice" && (
            <label className="lw-dialog__label">When it is not met
              <select className="lw-launch__input" value={severity} aria-label="Severity" onChange={(e) => setSeverity(e.target.value as CustomSeverity)}>
                <option value="warn">Needs attention</option>
                <option value="info">Note</option>
              </select>
            </label>
          )}
          {error && <p className="lw-dialog__message" role="alert">{error}</p>}
          <div className="lw-row lw-gap-8">
            <button className="lw-btn lw-btn--primary" disabled={!ready || busy} onClick={() => void add()}>Add requirement</button>
            <button className="lw-btn" onClick={() => { setOpen(false); setError(""); }}>Cancel</button>
          </div>
        </div>
      )}
      {removing && (
        <ConfirmDialog title="Remove requirement" confirm="Remove"
          message={<>Remove “{removing.title}” from your requirements? Your paper is not changed.</>}
          onConfirm={() => void remove(removing)} onClose={() => setRemoving(null)} />
      )}
    </section>
  );
}
