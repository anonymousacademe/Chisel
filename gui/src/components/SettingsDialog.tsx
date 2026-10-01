import { useEffect, useMemo, useState } from "react";
import { KeyRound, Search } from "lucide-react";
import { api } from "../backend/api";
import type { EditorPrefs, ModelKind, ModelOption, SettingsInfo } from "../data/types";
import { IMAGE_COST_NOTE } from "../data/inspiration";
import { Modal } from "./Dialogs";
import { Icon } from "./primitives";

const KINDS: { kind: ModelKind; label: string; hint: string; structured: boolean; modality?: "image" }[] = [
  { kind: "fast", label: "Fast model", hint: "Alias finder. Needs structured outputs.", structured: true },
  { kind: "strong", label: "Strong model", hint: "Continuity and story bible. Needs structured outputs.", structured: true },
  { kind: "writing", label: "Writing model", hint: "Drafting, rewrites, style guide and chat. Any model.", structured: false },
  { kind: "image", label: "Image model", hint: `Inspiration pictures; ${IMAGE_COST_NOTE}. Only models that draw.`, structured: false, modality: "image" },
];
const ZOOMS = [90, 100, 110, 125];

const price = (m: ModelOption) => {
  const tokens = m.promptPerM != null && m.completionPerM != null ? `$${m.promptPerM.toFixed(2)} / $${m.completionPerM.toFixed(2)} per M tokens` : "price unknown";
  return m.imagePrice != null ? `${tokens} · $${m.imagePrice.toFixed(3)} per image` : tokens;
};

/** API key, model choices (with a searchable catalog), and editor preferences. */
export function SettingsDialog({ initial, onClose, onSaved, notify }: {
  initial: SettingsInfo; onClose: () => void;
  onSaved: (editor: EditorPrefs, spellcheck: boolean) => void; notify: (text: string, tone?: "info" | "error") => void;
}) {
  const [info, setInfo] = useState(initial);
  const [key, setKey] = useState("");
  const [models, setModels] = useState<Record<ModelKind, string>>({
    fast: initial.models.fast.value, strong: initial.models.strong.value, writing: initial.models.writing.value, image: initial.models.image.value,
  });
  const [editor, setEditor] = useState(initial.editor);
  const [spellcheck, setSpellcheck] = useState(initial.spellcheck);
  const [autoSnapshot, setAutoSnapshot] = useState(initial.autoSnapshot);
  const [dailyTarget, setDailyTarget] = useState(String(initial.dailyTarget));
  const [imageStyle, setImageStyle] = useState(initial.imageStyle);
  const [picking, setPicking] = useState<ModelKind | null>(null);

  const reload = async () => { const r = await api.getSettings(); if (r.ok) setInfo(r); };
  const saveKey = async () => {
    const r = await api.setApiKey(key);
    if (!r.ok) return notify(r.error, "error");
    setKey(""); notify("API key stored in the system keyring."); await reload();
  };
  const clearKey = async () => {
    const r = await api.clearApiKey();
    if (!r.ok) return notify(r.error, "error");
    notify(r.note || "API key removed."); await reload();
  };
  const save = async () => {
    const target = Number(dailyTarget.trim() || 0);
    if (!Number.isInteger(target) || target < 0 || target > 100000) return notify("The daily target must be a whole number from 0 to 100,000.", "error");
    const r = await api.setSettings(models, editor, spellcheck, autoSnapshot, target, imageStyle);
    if (!r.ok) return notify(r.error, "error");
    onSaved(editor, spellcheck); onClose();
  };

  return (
    <Modal title="Settings" wide onClose={onClose}>
      <div className="lw-settings">
        <section className="lw-settings__section">
          <h3>AI (OpenRouter)</h3>
          <p className="lw-dialog__message">
            {info.hasKey
              ? `An API key is set (${info.keySource === "environment" ? "from the OPENROUTER_API_KEY environment variable" : "stored in the system keyring"}).`
              : "No API key yet. AI features stay off until you add one."}
          </p>
          <div className="lw-row lw-gap-8">
            <input className="lw-launch__input" type="password" value={key} onChange={(e) => setKey(e.target.value)}
              placeholder="Paste an OpenRouter API key" aria-label="OpenRouter API key" autoComplete="off" spellCheck={false}
              onKeyDown={(e) => { if (e.key === "Enter" && key.trim()) void saveKey(); }} />
            <button className="lw-btn" disabled={!key.trim()} onClick={() => void saveKey()}><Icon icon={KeyRound} size={14} stroke={1.8} /> Save key</button>
            <button className="lw-btn" disabled={!info.hasKey} onClick={() => void clearKey()}>Clear</button>
          </div>
        </section>

        <section className="lw-settings__section">
          <h3>Models</h3>
          {KINDS.map((k) => (
            <div key={k.kind} className="lw-settings__model">
              <label className="lw-dialog__label">{k.label} <span className="lw-faint">{k.hint}</span>
                <div className="lw-row lw-gap-8">
                  <input className="lw-launch__input" value={models[k.kind]} spellCheck={false}
                    placeholder={info.models[k.kind].default}
                    onChange={(e) => setModels({ ...models, [k.kind]: e.target.value })} />
                  <button className="lw-btn" onClick={() => setPicking(picking === k.kind ? null : k.kind)}>Choose…</button>
                </div>
              </label>
              {info.models[k.kind].projectOverride && (
                <p className="lw-empty">This project overrides it in project.toml: {info.models[k.kind].projectOverride}</p>
              )}
              {picking === k.kind && (
                <ModelPicker structured={k.structured} modality={k.modality} onPick={(id) => { setModels({ ...models, [k.kind]: id }); setPicking(null); }} />
              )}
            </div>
          ))}
          <label className="lw-dialog__label">Image style <span className="lw-faint">added to every picture description; empty turns it off</span>
            <input className="lw-launch__input" value={imageStyle} spellCheck={false} maxLength={300}
              placeholder={info.imageStyleDefault} aria-label="Image style" onChange={(e) => setImageStyle(e.target.value)} />
          </label>
        </section>

        <section className="lw-settings__section">
          <h3>Editor</h3>
          <div className="lw-row lw-gap-8" role="radiogroup" aria-label="Text size">
            <span className="lw-dialog__label">Text size</span>
            {ZOOMS.map((z) => (
              <button key={z} role="radio" aria-checked={editor.zoom === z} className={`lw-chip lw-chip--pick${editor.zoom === z ? " is-on" : ""}`}
                onClick={() => setEditor({ ...editor, zoom: z })}>{z}%</button>
            ))}
          </div>
          <label className="lw-check">
            <input type="checkbox" checked={editor.reflow} onChange={(e) => setEditor({ ...editor, reflow: e.target.checked })} />
            Show hard-wrapped lines as flowing paragraphs <span className="lw-faint">(display only; files are never changed)</span>
          </label>
          <label className="lw-check">
            <input type="checkbox" checked={spellcheck} onChange={(e) => setSpellcheck(e.target.checked)} />
            Underline misspellings <span className="lw-faint">(scenes only; names in your notes and your dictionaries are never flagged)</span>
          </label>
        </section>
        <section className="lw-settings__section">
          <h3>Writing goals</h3>
          <label className="lw-check">
            Daily word target
            <input className="lw-launch__input lw-settings__narrow" inputMode="numeric" value={dailyTarget} aria-label="Daily word target"
              onChange={(e) => setDailyTarget(e.target.value.replace(/[^\d]/g, ""))} />
            <span className="lw-faint">words; 0 turns the target off. Your streak counts the days you met it.</span>
          </label>
        </section>
        <section className="lw-settings__section">
          <h3>History</h3>
          <label className="lw-check">
            <input type="checkbox" checked={autoSnapshot} onChange={(e) => setAutoSnapshot(e.target.checked)} />
            Snapshot a scene the first time it is edited each day <span className="lw-faint">(a safety net; you can always take your own from the History button)</span>
          </label>
        </section>
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" onClick={() => void save()}>Save</button>
      </div>
    </Modal>
  );
}

/** Searchable OpenRouter catalog. Fetched on demand (it needs the network). */
function ModelPicker({ structured, modality, onPick }: { structured: boolean; modality?: "image"; onPick: (id: string) => void }) {
  const [models, setModels] = useState<ModelOption[] | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    let live = true;
    void api.listModels(structured, modality).then((r) => {
      if (!live) return;
      if (r.ok) setModels(r.models); else setError(r.error);
    });
    return () => { live = false; };
  }, [structured, modality]);
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return (models ?? []).filter((m) => words.every((w) => `${m.name} ${m.id}`.toLowerCase().includes(w))).slice(0, 80);
  }, [models, q]);
  return (
    <div className="lw-picker">
      <div className="lw-switcher__input">
        <Icon icon={Search} size={14} stroke={1.7} color="var(--lw-text-muted)" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search models…" aria-label="Search models" />
      </div>
      <div className="lw-picker__list" role="listbox">
        {error && <p className="lw-empty">Could not load the model list ({error}). You can still type a model id above.</p>}
        {!models && !error && <p className="lw-empty lw-pulse">Loading models…</p>}
        {shown.map((m) => (
          <button key={m.id} role="option" aria-selected={false} className="lw-switcher__row" onClick={() => onPick(m.id)}>
            <span className="lw-switcher__title">{m.name}<span className="lw-faint"> · {m.id}</span></span>
            <span className="lw-switcher__detail">{price(m)}</span>
          </button>
        ))}
        {models && shown.length === 0 && <p className="lw-empty">Nothing matches “{q}”.</p>}
      </div>
    </div>
  );
}
