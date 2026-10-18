import { useEffect, useState } from "react";
import { api } from "../../backend/api";
import { COLLECTIONS_FALLBACK, type SourceCardInfo } from "../../data/research";
import { SectionLabel } from "../primitives";

type Notify = (text: string, tone?: "info" | "error") => void;
type Collections = { state: "loading" } | { state: "ok"; paths: string[] } | { state: "failed"; why: string };

/**
 * The top of the Notes panel for an open source note: how it reads, how to cite it, where it lives in Zotero.
 * Everything comes from Python (source_card, zotero_item_collections); the collections are read live and lazily.
 */
export function SourceCard({ id, notify }: { id: string; notify: Notify }) {
  const [card, setCard] = useState<SourceCardInfo | null>(null);
  const [failed, setFailed] = useState("");
  const [cols, setCols] = useState<Collections>({ state: "loading" });

  useEffect(() => {
    let live = true;
    void api.sourceCard(id).then((r) => {
      if (!live) return;
      if (r.ok) { setCard(r); setFailed(""); } else { setCard(null); setFailed(r.error); }
    });
    void api.zoteroItemCollections(id).then((r) => {
      if (!live) return;
      setCols(r.ok ? { state: "ok", paths: r.collections } : { state: "failed", why: r.error || COLLECTIONS_FALLBACK });
    });
    return () => { live = false; };
  }, [id]);

  if (failed) return <section className="lw-note lw-source-card"><p className="lw-empty">{failed}</p></section>;
  if (!card) return <section className="lw-note lw-source-card"><p className="lw-empty">Loading the source…</p></section>;

  const copy = async () => {
    try { await navigator.clipboard.writeText(card.citeAs); notify("Copied " + card.citeAs); }
    catch { notify("The clipboard is not available here: select the text and press Ctrl C.", "error"); }
  };
  const openZotero = async () => {
    const r = await api.openInZotero(id);
    if (!r.ok) notify(r.error, "error");
  };
  const link = (label: string, url: string) => (
    <button className="lw-btn lw-source-card__link" onClick={() => void api.openExternal(url)} title={url}>{label}</button>
  );
  const meta = [card.authors, card.year ? String(card.year) : "", card.venue].filter(Boolean).join(" · ");

  return (
    <section className="lw-note lw-source-card" aria-label="Source">
      <SectionLabel>Source</SectionLabel>
      <p className="lw-note__title">{card.display}</p>
      {card.title && <p className="lw-source-card__title">{card.title}</p>}
      {meta && <p className="lw-faint lw-source-card__meta">{meta}</p>}
      {(card.doi || card.url) && (
        <div className="lw-row lw-gap-6">
          {card.doi && link("DOI", `https://doi.org/${card.doi}`)}
          {card.url && link("Link", card.url)}
        </div>
      )}
      <div className="lw-row lw-gap-6">
        <span className="lw-faint">Cite as</span>
        <span className="lw-mono lw-source-card__cite">{card.citeAs}</span>
        <button className="lw-btn" onClick={() => void copy()}>Copy</button>
      </div>
      <div>
        <button className="lw-btn" disabled={!card.zoteroKey} onClick={() => void openZotero()}
          title={card.zoteroKey ? "Show this paper in the Zotero app" : "This note has no Zotero item key"}>Open in Zotero</button>
      </div>
      <div>
        <SectionLabel>In your Zotero library</SectionLabel>
        {cols.state === "loading" && <p className="lw-faint">Looking in Zotero…</p>}
        {cols.state === "failed" && <p className="lw-faint">{cols.why}</p>}
        {cols.state === "ok" && (cols.paths.length === 0
          ? <p className="lw-faint">Not in any collection (it is in the library root).</p>
          : <ul className="lw-source-card__cols">{cols.paths.map((p) => <li key={p}>{p}</li>)}</ul>)}
      </div>
      <p className="lw-faint">{card.noteCount} note{card.noteCount === 1 ? "" : "s"} · {card.highlightCount} highlight{card.highlightCount === 1 ? "" : "s"} in Zotero</p>
    </section>
  );
}
