import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../backend/api";
import {
  fitOptions, layoutOf, PAGE_SIZE_LABEL, summaryLine, usableFormat,
  type ExportInfo, type ExportOptions, type ExportResult, type ExportSummary,
} from "../data/export";
import { Modal } from "./Dialogs";
import "../styles/export.css";

type Run = { stage: string; fraction: number } | null;

/**
 * Export the book: pick a format and layout, see what will be in it, export in
 * the background, then open the file or its folder (only on a click).
 */
export function ExportDialog({ unit, onClose, notify }: {
  unit: string; onClose: () => void; notify: (text: string, tone?: "info" | "error") => void;
}) {
  const [info, setInfo] = useState<ExportInfo | null>(null);
  const [opts, setOpts] = useState<ExportOptions | null>(null);
  const [summary, setSummary] = useState<ExportSummary | null>(null);
  const [run, setRun] = useState<Run>(null);
  const [result, setResult] = useState<ExportResult | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  useEffect(() => {
    void api.exportInfo().then((r) => {
      if (!r.ok) { notify(r.error, "error"); return onClose(); }
      const o = r.options;
      setInfo(r);
      setOpts(fitOptions(r, { ...o, format: usableFormat(r, o.format) }));
    });
    // once, on open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // the live summary follows the options that change what is in the book
  const key = opts && JSON.stringify([opts.include_drafts, opts.include_front_matter, opts.numbering, opts.continuous]);
  useEffect(() => {
    if (!opts) return;
    let live = true;
    void api.exportSummary(opts).then((r) => { if (live && r.ok) setSummary(r.summary); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = useCallback((patch: Partial<ExportOptions>) => {
    setOpts((o) => (o && info ? fitOptions(info, { ...o, ...patch }) : o));
  }, [info]);

  const start = async () => {
    if (!opts) return;
    setResult(null);
    setRun({ stage: "Starting", fraction: 0 });
    const r = await api.exportStart(opts);
    if (!r.ok) { setRun(null); return notify(r.error, "error"); }
    for (;;) {
      await new Promise((res) => setTimeout(res, 250));
      if (!alive.current) return;
      const s = await api.exportStatus(r.job);
      if (!s.ok) { setRun(null); return notify(s.error, "error"); }
      if (s.state === "running") { setRun({ stage: s.stage, fraction: s.fraction }); continue; }
      setRun(null);
      if (s.state === "error") return notify(s.error, "error");
      setResult(s.result);
      return;
    }
  };
  const open = async (folder: boolean) => {
    const r = await api.exportOpen(result?.name ?? "", folder);
    if (!r.ok) notify(r.error, "error");
  };

  if (!info || !opts) return <Modal title="Export" onClose={onClose}><p className="lw-empty">Loading…</p></Modal>;

  if (result) {
    return (
      <Modal title="Export finished" onClose={onClose}>
        <p className="lw-dialog__message">
          Saved to <code>{result.rel}</code>
          <span className="lw-faint"> · {result.pages ? `${result.pages} pages, ` : ""}{result.words.toLocaleString("en-US")} words</span>
        </p>
        {result.warnings.length > 0 && (
          <ul className="lw-export__warnings" aria-label="Warnings">
            {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        )}
        <div className="lw-dialog__buttons lw-dialog__buttons--split">
          <button className="lw-btn" onClick={() => setResult(null)}>Back</button>
          <span className="lw-row lw-gap-8">
            <button className="lw-btn" onClick={() => void open(true)}>Show folder</button>
            <button className="lw-btn lw-btn--primary" autoFocus onClick={() => void open(false)}>Open file</button>
            <button className="lw-btn" onClick={onClose}>Close</button>
          </span>
        </div>
      </Modal>
    );
  }

  const layout = layoutOf(info, opts);
  const busy = run !== null;
  const current = info.formats.find((f) => f.key === opts.format);
  const check = (label: string, name: "toc" | "include_front_matter" | "include_drafts" | "continuous") => (
    <label className="lw-collections__check">
      <input type="checkbox" checked={opts[name]} disabled={busy} onChange={(e) => set({ [name]: e.target.checked })} /> {label}
    </label>
  );
  const chips = (label: string, items: { value: string; text: string; disabled?: boolean; title?: string }[], value: string, pick: (v: string) => void) => (
    <div className="lw-export__field">
      <span className="lw-export__label">{label}</span>
      <div className="lw-row lw-gap-8 lw-export__chips" role="radiogroup" aria-label={label}>
        {items.map((it) => (
          <button key={it.value} role="radio" aria-checked={value === it.value} disabled={busy || it.disabled} title={it.title}
            className={`lw-chip lw-chip--pick${value === it.value ? " is-on" : ""}`} onClick={() => pick(it.value)}>{it.text}</button>
        ))}
      </div>
    </div>
  );

  return (
    <Modal title="Export the book" wide onClose={onClose}>
      <p className="lw-export__summary" role="status">
        {summary ? summaryLine(summary, unit) : "Counting…"}
      </p>
      <div className="lw-export__body">
      {chips("Format", info.formats.map((f) => ({ value: f.key, text: f.label, disabled: !f.available, title: f.reason || undefined })),
        opts.format, (v) => set({ format: v as ExportOptions["format"] }))}
      {current && !current.available && <p className="lw-faint">{current.reason}</p>}
      {layout && chips("Layout", info.layouts.map((l) => ({ value: l.name, text: l.label, title: l.description })), layout.name, (v) => set({ layout: v }))}
      {layout && <p className="lw-faint lw-export__hint">{layout.description}</p>}
      {layout && layout.page_sizes.length > 1 && chips("Page size", layout.page_sizes.map((p) => ({ value: p, text: PAGE_SIZE_LABEL[p] ?? p })), opts.page_size, (v) => set({ page_size: v }))}
      {layout && layout.fonts.length > 1 && chips("Font", layout.fonts.map((f) => ({ value: f.key, text: f.label, disabled: !f.available, title: f.available ? undefined : "not installed" })), opts.font, (v) => set({ font: v }))}
      {chips(`${unit[0].toUpperCase()}${unit.slice(1)} headings`, [
        { value: "words", text: `“${unit === "scene" ? "Scene" : "Chapter"} 3”` }, { value: "numbers", text: "Numbers" }, { value: "titles-only", text: "Titles only" },
      ], opts.numbering, (v) => set({ numbering: v as ExportOptions["numbering"] }))}
      <div className="lw-export__checks">
        {(!layout || layout.toc) && check("Table of contents", "toc")}
        {check("Include front matter", "include_front_matter")}
        {(!layout || layout.continuous) && check(`Run ${unit}s on with a break ornament (no ${unit} pages)`, "continuous")}
        {check("Include pending AI drafts", "include_drafts")}
      </div>
      {summary?.draft_scenes ? (
        <p className="lw-export__warn">
          {summary.draft_scenes} {unit}{summary.draft_scenes === 1 ? " has" : "s have"} unaccepted AI drafts.
          {opts.include_drafts ? " Their text will be in the export." : " The export uses the text from before the draft."}
        </p>
      ) : null}
      {summary && summary.messages.filter((m) => !m.includes("unaccepted AI drafts")).map((m, i) => <p key={i} className="lw-export__warn">{m}</p>)}
      <label className="lw-dialog__label">Copyright line (optional override)
        <input className="lw-launch__input" value={opts.copyright} disabled={busy}
          placeholder={info?.project_copyright || "From Settings: Project & author, or e.g. First edition, 2026"}
          onChange={(e) => set({ copyright: e.target.value })} />
      </label>
      <p className="lw-faint lw-export__hint">Files are saved in the project’s <code>exports</code> folder; nothing is overwritten.</p>
      </div>
      {busy && (
        <div className="lw-export__progress" role="progressbar" aria-valuenow={Math.round((run?.fraction ?? 0) * 100)} aria-label="Export progress">
          <div className="lw-export__bar" style={{ width: `${Math.max(6, Math.round((run?.fraction ?? 0) * 100))}%` }} />
          <span>{run?.stage}…</span>
        </div>
      )}
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={busy || !current?.available || !summary?.scenes} onClick={() => void start()}>
          {busy ? "Exporting…" : "Export"}
        </button>
      </div>
    </Modal>
  );
}
