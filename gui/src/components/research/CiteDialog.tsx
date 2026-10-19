import { useEffect, useRef, useState } from "react";
import { api } from "../../backend/api";
import { citeText, type SourceHit } from "../../data/research";
import { Modal } from "../Dialogs";

/** The shortcut that opens this dialog from the editor (CodeMirror spelling) and how it reads on screen. */
export const CITE_KEY = "Mod-Shift-l";
export const CITE_KEY_LABEL = "Ctrl+Shift+L";

type Notify = (text: string, tone?: "info" | "error") => void;

/**
 * Pick a source from the synced library and insert its citation at the cursor. Search runs in Python
 * (search_sources); this only shows the hits and builds the text with citeText.
 */
export function CiteDialog({ onInsert, onSync, onClose, notify }: {
  /** Insert this text at the cursor of the open document. */
  onInsert: (text: string) => void;
  /** Open the Zotero sync dialog (shown when there are no sources yet). */
  onSync: () => void;
  onClose: () => void;
  notify: Notify;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState("");
  const [hits, setHits] = useState<SourceHit[] | null>(null);
  const [index, setIndex] = useState(0);
  const [everSeen, setEverSeen] = useState(false);   // any source at all (an empty query found some)
  const seq = useRef(0);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mine = ++seq.current;
    const t = setTimeout(() => {
      void api.searchSources(query).then((r) => {
        if (mine !== seq.current) return;           // a newer search follows
        if (!r.ok) { notify(r.error, "error"); setHits([]); return; }
        setHits(r.sources);
        setIndex(0);
        if (!query.trim() && r.sources.length > 0) setEverSeen(true);
      });
    }, query ? 200 : 0);
    return () => clearTimeout(t);
  }, [query, notify]);

  useEffect(() => { list.current?.querySelector(".is-selected")?.scrollIntoView?.({ block: "nearest" }); }, [index]);

  const insert = (hit: SourceHit | undefined) => {
    if (!hit) return;
    onInsert(citeText(hit.key, page));
    onClose();
  };
  const onKey = (e: React.KeyboardEvent) => {
    const n = hits?.length ?? 0;
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, n - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); insert(hits?.[index]); }
  };

  const empty = hits !== null && hits.length === 0;
  const noSources = empty && !query.trim() && !everSeen;
  const chosen = hits?.[index];

  return (
    <Modal title="Cite a source" wide onClose={onClose}>
      {noSources ? (
        <>
          <p className="lw-dialog__message">
            There are no sources in this project yet. Sync from Zotero first: it brings your library in as sources you can cite.
          </p>
          <div className="lw-dialog__buttons">
            <button className="lw-btn" onClick={onClose}>Cancel</button>
            <button className="lw-btn lw-btn--primary" onClick={() => { onClose(); onSync(); }}>Sync sources from Zotero…</button>
          </div>
        </>
      ) : (
        <>
          <input autoFocus className="lw-launch__input" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey}
            placeholder="Search by author, year, title or key" aria-label="Search sources" />
          <div className="lw-cite__list" ref={list} role="listbox" aria-label="Sources">
            {hits === null && <p className="lw-empty">Searching…</p>}
            {empty && <p className="lw-empty">No source matches “{query}”.</p>}
            {(hits ?? []).map((h, i) => (
              <button key={h.key} role="option" aria-selected={i === index}
                className={`lw-switcher__row${i === index ? " is-selected" : ""}`}
                onMouseMove={() => setIndex(i)} onClick={() => insert(h)}>
                <span className="lw-switcher__title">{h.display}</span>
                <span className="lw-switcher__detail">{h.title}{h.venue ? ` · ${h.venue}` : ""}{h.year ? ` · ${h.year}` : ""}</span>
              </button>
            ))}
          </div>
          <label className="lw-dialog__label">Page (optional)
            <input className="lw-launch__input" value={page} onChange={(e) => setPage(e.target.value)} onKeyDown={onKey}
              placeholder="12, or ch. 3" aria-label="Page" />
          </label>
          <p className="lw-faint lw-cite__hint">
            Inserts {chosen ? <span className="lw-mono">{citeText(chosen.key, page)}</span> : "[[@key]]"} at the cursor.
            Up and Down choose, Enter inserts. Open this from the editor with {CITE_KEY_LABEL}.
          </p>
          <div className="lw-dialog__buttons">
            <button className="lw-btn" onClick={onClose}>Cancel</button>
            <button className="lw-btn lw-btn--primary" disabled={!chosen} onClick={() => insert(chosen)}>Insert</button>
          </div>
        </>
      )}
    </Modal>
  );
}
