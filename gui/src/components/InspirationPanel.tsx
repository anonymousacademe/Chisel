import { useCallback, useEffect, useRef, useState } from "react";
import { Copy, Ellipsis, FolderOpen, ImagePlus, Pin, PinOff, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import { api } from "../backend/api";
import { IMAGE_COST_NOTE, costText, pinAction, replaceImage, splitImages, whenText } from "../data/inspiration";
import type { InspirationImage } from "../data/types";
import { ConfirmDialog, Menu, Modal, type MenuItem } from "./Dialogs";
import { Icon, IconButton, SectionLabel } from "./primitives";
import "../styles/inspiration.css";

/** Data URLs by image id for the session (a picture never changes under its id). */
const urls = new Map<string, string>();

function Picture({ img, className, onClick }: { img: InspirationImage; className?: string; onClick?: () => void }) {
  const [fetched, setFetched] = useState<{ id: string; url: string } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    if (urls.has(img.id)) return;
    let live = true;
    void api.inspirationImage(img.id).then((r) => {
      if (!live) return;
      if (r.ok) { urls.set(img.id, r.dataUrl); setFetched({ id: img.id, url: r.dataUrl }); } else setFailed(img.id);
    });
    return () => { live = false; };
  }, [img.id]);
  const src = urls.get(img.id) ?? (fetched?.id === img.id ? fetched.url : null);
  const alt = img.label;
  if (failed === img.id) return <div className={`lw-insp__img lw-insp__img--missing ${className ?? ""}`}>Picture file missing</div>;
  if (!src) return <div className={`lw-insp__img lw-pulse ${className ?? ""}`} aria-label="Loading picture" />;
  return onClick
    ? <button type="button" className={`lw-insp__imgbtn ${className ?? ""}`} onClick={onClick} aria-label={`Open “${alt}” large`}><img className="lw-insp__img" src={src} alt={alt} draggable={false} /></button>
    : <img className={`lw-insp__img ${className ?? ""}`} src={src} alt={alt} draggable={false} />;
}

type Busy = "describe" | "generate" | null;

/**
 * The Inspiration tab: describe a setting, get a picture, keep it beside the writing. Reference only -
 * nothing here touches the prose. The open scene's pinned pictures are shown large at the top and
 * follow the scene; everything else is a grid.
 */
export function InspirationPanel(props: {
  /** The open scene (null on a note or when nothing is open). */
  sceneId: string | null; sceneTitle: string;
  /** Bumped by the app when something outside changed the pictures (Trash restore). */
  rev: number;
  getEditor: () => { text: string; cursor: number } | null;
  requireAi: () => boolean; notify: (text: string, tone?: "info" | "error") => void;
  /** Refresh the status bar's AI spend. */
  onSpent: () => void;
}) {
  const { sceneId, notify } = props;
  const [images, setImages] = useState<InspirationImage[] | null>(null);
  const [prompt, setPrompt] = useState("");
  const [pin, setPin] = useState(true);
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; img: InspirationImage } | null>(null);
  const [editing, setEditing] = useState<InspirationImage | null>(null);
  const [trashing, setTrashing] = useState<InspirationImage | null>(null);
  const [model, setModel] = useState("");
  const busyRef = useRef<Busy>(null);

  const show = useCallback((r: Awaited<ReturnType<typeof api.listInspiration>>) => {
    if (r.ok) { setImages(r.images); setModel(r.model); } else { setImages([]); notify(r.error, "error"); }
  }, [notify]);
  const load = useCallback(async () => { show(await api.listInspiration()); }, [show]);
  // reload when the app says so, and when the open scene changes (renames and moves rewrite the links)
  useEffect(() => {
    let live = true;
    void api.listInspiration().then((r) => { if (live) show(r); });
    return () => { live = false; };
  }, [show, props.rev, sceneId]);

  const run = async <T,>(kind: Exclude<Busy, null>, fn: () => Promise<T | null>): Promise<T | null> => {
    if (busyRef.current) { notify("Wait for the current request to finish."); return null; }
    busyRef.current = kind; setBusy(kind);
    try { return await fn(); } finally { busyRef.current = null; setBusy(null); props.onSpent(); }
  };

  const describe = async () => {
    const ed = props.getEditor();
    if (!sceneId || !ed) return notify("Open a scene to describe it.");
    if (!props.requireAi()) return;
    const r = await run("describe", async () => {
      const x = await api.describeScene(sceneId, ed.text, ed.cursor);
      if (!x.ok) { notify(x.error, "error"); return null; }
      return x;
    });
    if (r) { setPrompt(r.prompt); notify("Edit the description if you like, then press Generate."); }
  };
  const generate = async () => {
    const text = prompt.trim();
    if (!text) return notify("Describe the picture first.");
    if (!props.requireAi()) return;
    const r = await run("generate", async () => {
      const x = await api.generateInspiration(text, sceneId, pin && !!sceneId);
      if (!x.ok) { notify(x.error, "error"); return null; }
      return x;
    });
    if (!r) return;
    await load();
    notify(`${r.images.length === 1 ? "Picture" : `${r.images.length} pictures`} saved to inspiration/${r.cost != null ? ` (AI ${costText(r.cost)})` : ""}.`);
  };
  const regenerate = async (img: InspirationImage) => {
    if (!props.requireAi()) return;
    const r = await run("generate", async () => {
      const x = await api.regenerateInspiration(img.id);
      if (!x.ok) { notify(x.error, "error"); return null; }
      return x;
    });
    if (!r) return;
    await load();
    notify(`Another picture saved${r.cost != null ? ` (AI ${costText(r.cost)})` : ""}. The first is still there.`);
  };
  const setPinned = async (img: InspirationImage, on: boolean) => {
    const r = await api.updateInspiration(img.id, on ? { pinned: true, scene: sceneId ?? img.scene } : { pinned: false });
    if (!r.ok) return notify(r.error, "error");
    setImages((l) => (l ? replaceImage(l, r.image) : l));
  };
  const saveDetails = async (img: InspirationImage, title: string, notes: string) => {
    const r = await api.updateInspiration(img.id, { title, notes });
    if (!r.ok) return notify(r.error, "error");
    setImages((l) => (l ? replaceImage(l, r.image) : l));
    setEditing(null);
  };
  const trash = async (img: InspirationImage) => {
    setTrashing(null); setOpen(null);
    const r = await api.deleteInspiration(img.id);
    if (!r.ok) return notify(r.error, "error");
    notify("Moved the picture to the Trash.");
    await load();
  };
  const copyPrompt = async (img: InspirationImage) => {
    try { await navigator.clipboard.writeText(img.prompt); notify("Prompt copied."); } catch { notify("Could not copy; select the prompt in the large view.", "error"); }
  };
  const reveal = async (img: InspirationImage) => {
    const r = await api.revealInspiration(img.id);
    if (!r.ok) return notify(r.error, "error");
    notify(r.opened ? "Opened the folder." : `File: ${r.path}`);
  };

  const menuItems = (img: InspirationImage): MenuItem[] => {
    const pa = pinAction(img, sceneId);
    return [
      { label: "Open large", onSelect: () => setOpen(img.id) },
      { label: pa.label, disabled: pa.disabled, onSelect: () => void setPinned(img, pa.pin) },
      { label: "Regenerate (about $0.03)", onSelect: () => void regenerate(img) },
      { label: "Rename / notes…", onSelect: () => setEditing(img) },
      { label: "Copy prompt", onSelect: () => void copyPrompt(img) },
      { label: "Reveal file", onSelect: () => void reveal(img) },
      { separator: true, label: "", onSelect: () => {} },
      { label: "Move to Trash", danger: true, onSelect: () => setTrashing(img) },
    ];
  };

  const shown = splitImages(images ?? [], sceneId, all);
  const opened = images?.find((i) => i.id === open) ?? null;
  const card = (img: InspirationImage, large: boolean) => (
    <figure key={img.id} className={`lw-insp__card${large ? " lw-insp__card--large" : ""}`}>
      <Picture img={img} onClick={() => setOpen(img.id)} />
      <figcaption className="lw-insp__cap">
        <span className="lw-insp__label" title={img.prompt}>{img.pinned && <Icon icon={Pin} size={11} stroke={1.8} />} {img.label}</span>
        <IconButton small icon={Ellipsis} label={`Actions for ${img.label}`} onClick={(e) => setMenu({ anchor: e.currentTarget, img })} />
      </figcaption>
    </figure>
  );

  return (
    <section className="lw-insp" aria-label="Inspiration pictures">
      <p className="lw-insp__lead">Pictures to keep beside you while you write. They are reference only and never go into your prose.</p>
      <div className="lw-insp__compose">
        <textarea className="lw-insp__prompt" rows={4} value={prompt} placeholder="A dark subway platform at night, flickering fluorescent lights…"
          aria-label="Picture description" onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void generate(); } }} />
        <div className="lw-insp__actions">
          <button className="lw-btn" disabled={!sceneId || busy !== null} onClick={() => void describe()}
            title={sceneId ? "Write the description from the passage around your cursor" : "Open a scene first"}>
            <Icon icon={Sparkles} size={14} stroke={1.8} /> {busy === "describe" ? "Describing…" : "Describe this scene"}
          </button>
          <button className="lw-btn lw-btn--primary" disabled={!prompt.trim() || busy !== null} onClick={() => void generate()}>
            <Icon icon={ImagePlus} size={14} stroke={1.8} /> {busy === "generate" ? "Generating…" : "Generate"}
          </button>
        </div>
        <div className="lw-insp__meta">
          <label className="lw-check lw-insp__pin">
            <input type="checkbox" checked={pin && !!sceneId} disabled={!sceneId} onChange={(e) => setPin(e.target.checked)} />
            Pin to this scene
          </label>
          <span className="lw-faint" title={model}>{IMAGE_COST_NOTE}</span>
        </div>
        {busy === "generate" && <p className="lw-empty lw-pulse">Making the picture; this takes a few seconds…</p>}
      </div>

      {images === null && <p className="lw-empty lw-pulse">Loading pictures…</p>}

      {shown.pinned.length > 0 && (
        <>
          <SectionLabel accent>Pinned to {props.sceneTitle || "this scene"}</SectionLabel>
          <div className="lw-insp__pinned">{shown.pinned.map((i) => card(i, true))}</div>
        </>
      )}

      {images !== null && (
        <>
          <div className="lw-insp__bar">
            <SectionLabel>{all || !sceneId ? "All pictures" : "This scene"} · {shown.rest.length}</SectionLabel>
            {sceneId && (
              <div className="lw-row lw-gap-4" role="radiogroup" aria-label="Which pictures">
                <button role="radio" aria-checked={!all} className={`lw-chip lw-chip--pick${!all ? " is-on" : ""}`} onClick={() => setAll(false)}>This scene</button>
                <button role="radio" aria-checked={all} className={`lw-chip lw-chip--pick${all ? " is-on" : ""}`} onClick={() => setAll(true)}>All</button>
              </div>
            )}
          </div>
          {shown.rest.length === 0 && shown.pinned.length === 0 && (
            <p className="lw-empty">{images.length === 0
              ? "No pictures yet. Describe a place above and press Generate; the first one is saved in your project's inspiration folder."
              : sceneId ? "No pictures for this scene yet. Switch to All to see the others." : "Nothing to show."}</p>
          )}
          <div className="lw-insp__grid">{shown.rest.map((i) => card(i, false))}</div>
        </>
      )}

      {menu && <Menu anchor={menu.anchor} items={menuItems(menu.img)} onClose={() => setMenu(null)} />}
      {opened && (
        <Lightbox img={opened} sceneId={sceneId} onClose={() => setOpen(null)}
          onPin={(on) => void setPinned(opened, on)} onRegenerate={() => void regenerate(opened)} onCopy={() => void copyPrompt(opened)}
          onEdit={() => setEditing(opened)} onReveal={() => void reveal(opened)} onTrash={() => setTrashing(opened)} />
      )}
      {editing && <DetailsDialog img={editing} onClose={() => setEditing(null)} onSave={(t, n) => void saveDetails(editing, t, n)} />}
      {trashing && (
        <ConfirmDialog title="Move picture to the Trash" confirm="Move to Trash"
          message={<>Move “{trashing.label}” to the Trash? You can restore it from the Trash later.</>}
          onConfirm={() => void trash(trashing)} onClose={() => setTrashing(null)} />
      )}
    </section>
  );
}

function Lightbox({ img, sceneId, onClose, onPin, onRegenerate, onCopy, onEdit, onReveal, onTrash }: {
  img: InspirationImage; sceneId: string | null; onClose: () => void; onPin: (on: boolean) => void;
  onRegenerate: () => void; onCopy: () => void; onEdit: () => void; onReveal: () => void; onTrash: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); onClose(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const pa = pinAction(img, sceneId);
  return (
    <div className="lw-overlay lw-overlay--center lw-insp__lightbox" onMouseDown={onClose}>
      <div className="lw-insp__lbbox" role="dialog" aria-label={img.label} onMouseDown={(e) => e.stopPropagation()}>
        <div className="lw-insp__lbtop">
          <strong className="lw-insp__lbtitle">{img.label}</strong>
          <IconButton icon={X} label="Close" onClick={onClose} />
        </div>
        <Picture img={img} className="lw-insp__lbimg" />
        <p className="lw-insp__lbprompt">{img.prompt}</p>
        {img.notes && <p className="lw-insp__lbnotes">{img.notes}</p>}
        <p className="lw-faint lw-insp__lbmeta">{whenText(img.created)} · {img.model}{img.cost != null ? ` · ${costText(img.cost)}` : ""}{img.scene ? ` · ${img.scene}` : ""}</p>
        <div className="lw-insp__lbbuttons">
          <button className="lw-btn" disabled={pa.disabled} onClick={() => onPin(pa.pin)}><Icon icon={pa.pin ? Pin : PinOff} size={14} stroke={1.8} /> {pa.label}</button>
          <button className="lw-btn" onClick={onRegenerate}><Icon icon={RefreshCw} size={14} stroke={1.8} /> Regenerate</button>
          <button className="lw-btn" onClick={onCopy}><Icon icon={Copy} size={14} stroke={1.8} /> Copy prompt</button>
          <button className="lw-btn" onClick={onEdit}>Rename / notes…</button>
          <button className="lw-btn" onClick={onReveal}><Icon icon={FolderOpen} size={14} stroke={1.8} /> Reveal file</button>
          <button className="lw-btn lw-btn--danger" onClick={onTrash}><Icon icon={Trash2} size={14} stroke={1.8} /> Move to Trash</button>
        </div>
      </div>
    </div>
  );
}

function DetailsDialog({ img, onClose, onSave }: { img: InspirationImage; onClose: () => void; onSave: (title: string, notes: string) => void }) {
  const [title, setTitle] = useState(img.title);
  const [notes, setNotes] = useState(img.notes);
  return (
    <Modal title="Picture details" onClose={onClose}>
      <label className="lw-dialog__label">Name <span className="lw-faint">(shown instead of the prompt)</span>
        <input className="lw-launch__input" value={title} maxLength={120} placeholder={img.prompt.slice(0, 60)} autoFocus onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="lw-dialog__label">Notes
        <textarea className="lw-insp__prompt" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" onClick={() => onSave(title, notes)}>Save</button>
      </div>
    </Modal>
  );
}
